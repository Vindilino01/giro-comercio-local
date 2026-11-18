"""
Pipeline de ingestao e validacao (bronze -> prata + quarentena).

ESTRATEGIA
----------
1. COPY do CSV para staging UNLOGGED com todas as colunas em TEXT.
   COPY e ordens de magnitude mais rapido que INSERT linha a linha:
   ~4,1M de itens entram em ~15 s contra minutos.

2. Validacao em SQL de conjunto: cada regra DQ e um predicado que
   identifica as linhas ruins. Elas vao para gov.quarentena com
   reason_code e payload original em JSONB, e sao REMOVIDAS do staging.

3. INSERT ... SELECT do que sobrou no staging. As constraints do banco
   continuam como rede de seguranca final.

POR QUE NAO INSERT LINHA A LINHA COM TRY/EXCEPT
-----------------------------------------------
No Postgres, um erro aborta a transacao inteira. Para tratar linha a
linha seria preciso um SAVEPOINT por registro - lento e complexo. A
abordagem por conjunto e mais rapida, o codigo e menor e a quarentena
fica completa.

MAPEAMENTO DE CHAVES
--------------------
Os CSVs trazem os ids do gerador, que NAO sao os ids do banco (o banco
usa IDENTITY). A carga de venda materializa `stg.venda_id_map`
(origem_id -> destino_id); item_venda usa esse mapa. Produto e loja sao
mapeados pela chave natural (EAN e codigo).

ORDEM DE CARGA (respeita as FKs)
--------------------------------
loja -> fornecedor -> categoria/produto -> calendario -> promocao
-> venda -> item_venda -> estoque_snapshot -> movimentacao
-> pedido_compra -> item_pedido
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

UFS = ("'AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT',"
       "'PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO'")

DATA_RE = "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"


def dsn_padrao() -> str:
    return os.environ.get(
        "GIRO_DSN",
        "host=127.0.0.1 port=5433 dbname=giro user=postgres",
    )


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


@dataclass
class ResultadoCarga:
    tabela: str
    lidas: int = 0
    aceitas: int = 0
    rejeitadas: int = 0
    segundos: float = 0.0
    por_regra: dict[str, int] = field(default_factory=dict)

    @property
    def taxa_aceite(self) -> float:
        return round(self.aceitas / self.lidas * 100, 2) if self.lidas else 0.0

    @property
    def linhas_por_segundo(self) -> float:
        return round(self.lidas / self.segundos, 0) if self.segundos > 0.01 else 0.0

    def como_dict(self) -> dict:
        return {
            "tabela": self.tabela, "lidas": self.lidas,
            "aceitas": self.aceitas, "rejeitadas": self.rejeitadas,
            "taxa_aceite_pct": self.taxa_aceite,
            "segundos": round(self.segundos, 2),
            "linhas_por_segundo": self.linhas_por_segundo,
            "por_regra": self.por_regra,
        }


class Ingestor:
    def __init__(self, conn: psycopg.Connection, origem: Path):
        self.conn = conn
        self.origem = origem
        self.resultados: list[ResultadoCarga] = []
        self._staging_criado = False

    # ==================================================================
    # Infraestrutura
    # ==================================================================
    def _garantir_staging(self) -> None:
        if self._staging_criado:
            return
        with self.conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS stg")
        self.conn.commit()
        self._staging_criado = True

    def _novo_lote(self, origem: str, arquivo: Path) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gov.lote_carga (origem, arquivo, hash_arquivo)
                   VALUES (%s, %s, %s) RETURNING lote_id""",
                (origem, arquivo.name, sha256_arquivo(arquivo)),
            )
            lote_id = cur.fetchone()[0]
        self.conn.commit()
        return lote_id

    # Tabela e coluna de data de referencia por origem. O lote nasce sem
    # data porque o CSV ainda nao foi lido; ao finalizar, a maior data de
    # negocio do lote e gravada. Sem isto, `gov.lote_carga.data_referencia`
    # ficava NULL em 100% das linhas e a Q10 devolvia idade_dias = NULL -
    # a dimensao ATUALIDADE era anunciada como medida e nao media nada.
    _DATA_REF: dict[str, tuple[str, str]] = {
        "CSV_VENDA": ("prata.venda", "data_venda"),
        "CSV_ITEM_VENDA": ("prata.item_venda", "data_venda"),
        "CSV_ESTOQUE": ("prata.estoque_snapshot", "data_ref"),
        "CSV_MOVIMENTACAO": ("prata.movimentacao_estoque", "data_movimento"),
        "CSV_PEDIDO": ("prata.pedido_compra", "data_pedido"),
        "CSV_ITEM_PEDIDO": ("prata.pedido_compra", "data_pedido"),
        "CSV_CALENDARIO": ("prata.calendario", "data"),
        "CSV_PROMOCAO": ("prata.promocao", "data_fim"),
        "CSV_PROMOCAO_PRODUTO": ("prata.promocao", "data_fim"),
    }

    def _finalizar_lote(self, lote_id: int, res: ResultadoCarga) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE gov.lote_carga
                      SET finalizado_em = now(), status = %s,
                          linhas_lidas = %s, linhas_aceitas = %s,
                          linhas_rejeitadas = %s
                    WHERE lote_id = %s""",
                ("CONCLUIDO" if res.rejeitadas == 0 else "PARCIAL",
                 res.lidas, res.aceitas, res.rejeitadas, lote_id),
            )

            # Data de referencia do lote: a maior data de negocio que ele
            # trouxe. E contra ela que a atualidade e medida - nao contra
            # o relogio, que num dataset historico produz idade negativa.
            #
            # Cadastros (loja, fornecedor, produto, preco) nao tem data de
            # negocio propria: herdam a maior data de venda do dataset, que
            # e a data de referencia da carga como um todo.
            origem = self._origem_do_lote(lote_id)
            alvo = self._DATA_REF.get(origem)
            if alvo:
                tabela, coluna = alvo
                cur.execute(
                    f"UPDATE gov.lote_carga "
                    f"   SET data_referencia = (SELECT max({coluna}) FROM {tabela}) "
                    f" WHERE lote_id = %s", (lote_id,))
            else:
                cur.execute(
                    "UPDATE gov.lote_carga "
                    "   SET data_referencia = (SELECT max(data_venda) FROM prata.venda) "
                    " WHERE lote_id = %s AND data_referencia IS NULL", (lote_id,))
        self.conn.commit()
        self.resultados.append(res)

    def _origem_do_lote(self, lote_id: int) -> str:
        with self.conn.cursor() as cur:
            cur.execute("SELECT origem FROM gov.lote_carga WHERE lote_id = %s",
                        (lote_id,))
            linha = cur.fetchone()
        return linha[0] if linha else ""

    def _staging(self, arquivo: Path, tabela: str, colunas: list[str]) -> None:
        """COPY do CSV para staging TEXT. Sem conversao de tipo."""
        self._garantir_staging()
        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS stg.{tabela}")
            cur.execute(
                f"CREATE UNLOGGED TABLE stg.{tabela} ("
                + ", ".join(f'"{c}" TEXT' for c in colunas) + ")"
            )
        self.conn.commit()

        cols = ", ".join(f'"{c}"' for c in colunas)
        with self.conn.cursor() as cur:
            with cur.copy(
                f'COPY stg.{tabela} ({cols}) FROM STDIN '
                "WITH (FORMAT CSV, HEADER TRUE, NULL '')"
            ) as copy:
                with arquivo.open("rb") as f:
                    while bloco := f.read(1 << 20):
                        copy.write(bloco)
        self.conn.commit()

    def _contar(self, tabela: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM stg.{tabela}")
            return cur.fetchone()[0]

    def _rejeitar(self, tabela_stg: str, lote_id: int, regra: str,
                  entidade: str, chave_sql: str, motivo_sql: str,
                  where: str) -> int:
        """Quarentena + remocao do staging, em um passo.

        Manter as duas operacoes juntas garante que o predicado usado
        para rejeitar e o mesmo usado para excluir. Se ficassem
        separados, uma divergencia entre eles faria registro ruim
        entrar na tabela final ou registro bom sumir.

        Nota sobre o alias: o CTE `ruins` e reexposto como `s` no FROM
        final, para que chave_sql e motivo_sql possam usar o mesmo
        prefixo `s.` da clausula WHERE. Sem esse re-aliasing seria
        necessario reescrever as expressoes, o que ja causou bug por
        substituicao textual ingenua.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                f"""WITH ruins AS (
                        DELETE FROM stg.{tabela_stg} s
                         WHERE {where}
                     RETURNING s.*
                    )
                    INSERT INTO gov.quarentena
                        (lote_id, regra_id, entidade, chave_registro, payload, motivo)
                    SELECT %s,
                           (SELECT regra_id FROM gov.regra_qualidade WHERE codigo = %s),
                           %s, {chave_sql}, to_jsonb(s), {motivo_sql}
                      FROM ruins s""",
                (lote_id, regra, entidade),
            )
            n = cur.rowcount
        self.conn.commit()
        return n

    def _registrar(self, res: ResultadoCarga, regra: str, n: int) -> None:
        if n:
            res.por_regra[regra] = res.por_regra.get(regra, 0) + n

    def _validar_numericos(self, tabela_stg: str, lote_id: int,
                           campos: list[tuple[str, str]],
                           entidade: str,
                           chave_sql: str) -> int:
        """Rejeita linhas com campo numerico malformado.

        POR QUE ESTA FUNCAO EXISTE
        --------------------------
        Cada regra DQ que faz `::numeric` pressupoe que o valor e um
        numero. Se o defeito injetado for textual ('12.87.84'), o cast
        lanca InvalidTextRepresentation e a carga INTEIRA aborta - em
        vez de quarentenar a linha. Isso foi observado duas vezes nos
        testes: uma no preco, outra no valor.

        A correcao sistemica e validar o FORMATO de todos os campos
        numericos ANTES de qualquer regra de negocio. Uma unica
        varredura, um unico DELETE, e a partir dai todos os casts sao
        seguros.

        `campos` e uma lista de (nome_coluna, descricao_legivel).
        `chave_sql` identifica o registro na quarentena e varia por
        tabela (cada uma tem uma chave natural diferente).
        """
        condicoes = " OR ".join(
            f"""coalesce(s.{c}, '') <> ''
                AND s.{c} !~ '^-?[0-9]+([.][0-9]+)?$'"""
            for c, _ in campos
        )
        if not condicoes:
            return 0

        descricao = " || ', ' || ".join(
            f"""CASE WHEN coalesce(s.{c},'') <> ''
                       AND s.{c} !~ '^-?[0-9]+([.][0-9]+)?$'
                  THEN '{d}=' || s.{c} END"""
            for c, d in campos
        )

        return self._rejeitar(
            tabela_stg, lote_id, "DQ015", entidade,
            chave_sql,
            f"'campo numerico malformado: ' || concat_ws(', ', {descricao})",
            condicoes)

    # ==================================================================
    # LOJA
    # ==================================================================
    def carregar_lojas(self) -> ResultadoCarga:
        arq = self.origem / "loja.csv"
        res = ResultadoCarga("loja")
        lote_id = self._novo_lote("CSV_LOJA", arq)
        self._staging(arq, "loja", ["loja_id", "codigo", "nome", "cnpj", "cidade",
                                    "uf", "area_m2", "data_abertura",
                                    "data_fechamento", "ativa"])
        res.lidas = self._contar("loja")

        self._registrar(res, "DQ015", self._rejeitar(
            "loja", lote_id, "DQ015", "loja", "s.codigo",
            "'UF inexistente: ' || coalesce(s.uf, '(vazio)')",
            f"s.uf NOT IN ({UFS})"))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO prata.loja
                    (codigo, nome, cnpj, cidade, uf, area_m2,
                     data_abertura, data_fechamento, ativa)
                SELECT codigo, nome, NULLIF(cnpj, ''), cidade, uf,
                       NULLIF(area_m2, '')::numeric,
                       data_abertura::date,
                       NULLIF(data_fechamento, '')::date,
                       coalesce(ativa, 'true')::boolean
                  FROM stg.loja
                ON CONFLICT (codigo) DO NOTHING
            """)
            res.aceitas = cur.rowcount
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # FORNECEDOR
    # ==================================================================
    def carregar_fornecedores(self) -> ResultadoCarga:
        arq = self.origem / "fornecedor.csv"
        res = ResultadoCarga("fornecedor")
        lote_id = self._novo_lote("CSV_FORNECEDOR", arq)
        self._staging(arq, "fornecedor",
                      ["fornecedor_id", "cnpj", "razao_social", "nome_fantasia",
                       "cidade", "uf", "lead_time_dias_padrao",
                       "pedido_minimo_valor", "ativo"])
        res.lidas = self._contar("fornecedor")

        self._registrar(res, "DQ015", self._rejeitar(
            "fornecedor", lote_id, "DQ015", "fornecedor", "s.cnpj",
            "'CNPJ malformado: ' || coalesce(s.cnpj, '(vazio)')",
            "coalesce(s.cnpj, '') !~ '^[0-9]{14}$'"))

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.fornecedor
                    (cnpj, razao_social, nome_fantasia, cidade, uf,
                     lead_time_dias_padrao, pedido_minimo_valor, ativo)
                SELECT cnpj, razao_social, NULLIF(nome_fantasia, ''),
                       NULLIF(cidade, ''), NULLIF(uf, ''),
                       coalesce(lead_time_dias_padrao, '7')::smallint,
                       coalesce(pedido_minimo_valor, '0')::numeric,
                       coalesce(ativo, 'true')::boolean
                  FROM stg.fornecedor
                ON CONFLICT (cnpj) DO NOTHING
            """)
            res.aceitas = cur.rowcount
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # PRODUTO
    # ==================================================================
    def carregar_produtos(self) -> ResultadoCarga:
        arq = self.origem / "produto.csv"
        res = ResultadoCarga("produto")
        lote_id = self._novo_lote("CSV_PRODUTO", arq)
        self._staging(arq, "produto",
                      ["produto_id", "ean", "sku_interno", "nome", "departamento",
                       "classe", "unidade", "perecivel", "dias_validade",
                       "preco_custo", "preco_venda", "fornecedor_id"])
        res.lidas = self._contar("produto")

        # DQ011: EAN invalido (formato ou digito verificador)
        self._registrar(res, "DQ011", self._rejeitar(
            "produto", lote_id, "DQ011", "produto",
            "coalesce(s.ean, s.sku_interno)",
            "CASE WHEN coalesce(s.ean, '') !~ '^[0-9]{13}$' "
            "     THEN 'EAN com formato invalido: ' || coalesce(s.ean, '(vazio)') "
            "     ELSE 'EAN com digito verificador incorreto: ' || s.ean END",
            "coalesce(s.ean, '') !~ '^[0-9]{13}$' OR NOT gov.ean13_valido(s.ean)"))

        # DQ015: coerencia perecivel x validade
        self._registrar(res, "DQ015", self._rejeitar(
            "produto", lote_id, "DQ015", "produto", "s.sku_interno",
            "CASE WHEN coalesce(s.perecivel,'false')::boolean "
            "     THEN 'perecivel sem dias_validade' "
            "     ELSE 'nao-perecivel com dias_validade' END",
            "(coalesce(s.perecivel,'false')::boolean "
            "  AND coalesce(s.dias_validade,'') = '') "
            "OR (NOT coalesce(s.perecivel,'false')::boolean "
            "    AND coalesce(s.dias_validade,'') <> '')"))

        # DQ006: EAN duplicado no proprio arquivo. Mesma tecnica.
        self._registrar(res, "DQ006", self._rejeitar(
            "produto", lote_id, "DQ006", "produto", "s.ean",
            "'EAN duplicado no cadastro: ' || s.ean",
            """(s.ean, s.ctid) IN (
                   SELECT ean, ctid FROM (
                       SELECT ean, ctid,
                              row_number() OVER (PARTITION BY ean
                                                 ORDER BY ctid) AS rn
                         FROM stg.produto) t
                    WHERE t.rn > 1)"""))

        # Categorias derivadas (nivel 1 = departamento, 2 = classe)
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.categoria (codigo, nome, nivel, categoria_pai_id)
                SELECT DISTINCT 'D_' || left(departamento, 20), departamento,
                      1::smallint, NULL::bigint
                  FROM stg.produto
                ON CONFLICT (codigo) DO NOTHING
            """)
            cur.execute("""
                INSERT INTO prata.categoria (codigo, nome, nivel, categoria_pai_id)
                SELECT DISTINCT 'D_' || left(s.departamento, 12) || '_C_'
                       || left(s.classe, 16), s.classe, 2::smallint, c.categoria_id
                  FROM stg.produto s
                  JOIN prata.categoria c
                    ON c.codigo = 'D_' || left(s.departamento, 20)
                ON CONFLICT (codigo) DO NOTHING
            """)
        self.conn.commit()

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.produto
                    (ean, sku_interno, nome, categoria_id, unidade_medida,
                     e_perecivel, dias_validade)
                SELECT s.ean, s.sku_interno, s.nome, c.categoria_id,
                       s.unidade, s.perecivel::boolean,
                       CASE WHEN s.perecivel::boolean
                            THEN s.dias_validade::smallint END
                  FROM stg.produto s
                  JOIN prata.categoria c
                    ON c.codigo = 'D_' || left(s.departamento, 12)
                       || '_C_' || left(s.classe, 16)
                ON CONFLICT (ean) DO NOTHING
            """)
            res.aceitas = cur.rowcount
        self.conn.commit()

        # Vinculo produto x fornecedor (preferencial, com custo)
        with self.conn.cursor() as cur:
            cur.execute("""
                WITH forn AS (
                    SELECT fornecedor_id, lead_time_dias_padrao,
                           row_number() OVER (ORDER BY fornecedor_id) AS pos
                      FROM prata.fornecedor
                )
                INSERT INTO prata.produto_fornecedor
                    (produto_id, fornecedor_id, custo_unitario, lead_time_dias,
                     lote_minimo, multiplo_compra, preferencial)
                SELECT p.produto_id, f.fornecedor_id, s.preco_custo::numeric,
                       f.lead_time_dias_padrao, 1, 1, TRUE
                  FROM stg.produto s
                  JOIN prata.produto p ON p.ean = s.ean
                  JOIN forn f ON f.pos = mod((coalesce(s.fornecedor_id,'1')::int - 1),
                                             (SELECT count(*) FROM forn)) + 1
                ON CONFLICT (produto_id, fornecedor_id) DO NOTHING
            """)

            # ------------------------------------------------------------------
            # HISTORICO DE PRECO: nao entra aqui.
            #
            # Produto carrega ANTES do calendario (a FK de categoria exige),
            # e a faixa de preco precisa de uma data de inicio. Rodar nesta
            # funcao fazia o INSERT cair no guard EXISTS e gravar ZERO linhas
            # - a tabela ficava vazia e dim_produto voltava a inventar
            # preco = custo/0,7. Por isso a carga do historico e uma etapa
            # propria (carregar_preco_historico), depois do calendario.
            # ------------------------------------------------------------------
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # HISTORICO DE PRECO
    # ==================================================================
    def carregar_preco_historico(self) -> ResultadoCarga:
        """Cria a faixa aberta de preco por SKU a partir de `produto.csv`.

        Esta etapa existe separada de `carregar_produtos` por causa da
        ORDEM: produto e carregado antes do calendario (a categoria vem
        de uma tabela derivada do proprio CSV, sem dependencia de data),
        mas a faixa de preco precisa de uma data de inicio. Quando o
        INSERT vivia dentro de `carregar_produtos`, `min(data)` do
        calendario era NULL e a tabela ficava com ZERO linhas - o que
        derrubava `dim_produto` de volta ao preco inventado custo/0,7.

        Efeito medido da correcao: 420 SKUs passam a ter o preco
        realmente praticado (erro medio cai de 11,62% para 0,00%).
        """
        arq = self.origem / "produto.csv"
        res = ResultadoCarga("produto_preco_historico")
        lote_id = self._novo_lote("CSV_PRODUTO_PRECO", arq)

        # O staging de produto ja foi criado por carregar_produtos; ele
        # permanece na sessao. Se nao estiver la (execucao isolada),
        # recria a partir do CSV.
        with self.conn.cursor() as cur:
            cur.execute("SELECT to_regclass('stg.produto') IS NOT NULL")
            if not cur.fetchone()[0]:
                self._staging(arq, "produto",
                              ["produto_id", "ean", "sku_interno", "nome",
                               "departamento", "classe", "unidade",
                               "perecivel", "dias_validade", "preco_custo",
                               "preco_venda", "fornecedor_id"])

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.produto_preco_historico
                    (produto_id, data_inicio, data_fim,
                     preco_custo, preco_venda)
                SELECT p.produto_id,
                       (SELECT min(data) FROM prata.calendario),
                       NULL,
                       s.preco_custo::numeric,
                       s.preco_venda::numeric
                  FROM stg.produto s
                  JOIN prata.produto p ON p.ean = s.ean
                 WHERE s.preco_custo ~ '^[0-9]+([.][0-9]+)?$'
                   AND s.preco_venda ~ '^[0-9]+([.][0-9]+)?$'
                   AND s.preco_venda::numeric > 0
                ON CONFLICT (produto_id, data_inicio) DO NOTHING
            """)
            res.aceitas = cur.rowcount
            cur.execute("SELECT count(*) FROM stg.produto")
            res.lidas = cur.fetchone()[0]
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # CALENDARIO
    # ==================================================================
    def carregar_calendario(self) -> ResultadoCarga:
        arq = self.origem / "calendario.csv"
        res = ResultadoCarga("calendario")
        lote_id = self._novo_lote("CSV_CALENDARIO", arq)
        self._staging(arq, "calendario",
                      ["data", "ano", "mes", "dia", "dia_semana",
                       "nome_dia_semana", "semana_iso", "is_fim_semana",
                       "is_feriado", "nome_feriado", "is_pagamento"])
        res.lidas = self._contar("calendario")

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.calendario
                    (data, ano, mes, dia, dia_semana, nome_dia_semana,
                     semana_iso, is_fim_semana, is_feriado, nome_feriado,
                     is_pagamento, is_feriado_nacional)
                SELECT data::date, ano::smallint, mes::smallint, dia::smallint,
                       dia_semana::smallint, nome_dia_semana,
                       semana_iso::smallint, is_fim_semana::boolean,
                       is_feriado::boolean, NULLIF(nome_feriado, ''),
                       is_pagamento::boolean, is_feriado::boolean
                  FROM stg.calendario
                ON CONFLICT (data) DO NOTHING
            """)
            res.aceitas = cur.rowcount
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # PROMOCAO
    # ==================================================================
    def carregar_promocoes(self) -> list[ResultadoCarga]:
        out: list[ResultadoCarga] = []

        arq = self.origem / "promocao.csv"
        res = ResultadoCarga("promocao")
        lote_id = self._novo_lote("CSV_PROMOCAO", arq)
        self._staging(arq, "promocao",
                      ["promocao_id", "codigo", "descricao", "tipo",
                       "data_inicio", "data_fim", "percentual_desconto"])
        res.lidas = self._contar("promocao")

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.promocao
                    (codigo, descricao, tipo, data_inicio, data_fim,
                     percentual_desconto)
                SELECT codigo, descricao, tipo, data_inicio::date, data_fim::date,
                       NULLIF(percentual_desconto, '')::numeric
                  FROM stg.promocao
                ON CONFLICT (codigo) DO NOTHING
            """)
            res.aceitas = cur.rowcount
        self.conn.commit()
        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        out.append(res)

        # Vinculo promocao x produto, via mapeamento de chaves naturais
        arq2 = self.origem / "promocao_produto.csv"
        res2 = ResultadoCarga("promocao_produto")
        lote_id2 = self._novo_lote("CSV_PROMOCAO_PRODUTO", arq2)
        self._staging(arq2, "promocao_produto", ["promocao_id", "produto_id"])
        res2.lidas = self._contar("promocao_produto")

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.promocao_produto (promocao_id, produto_id)
                SELECT pr.promocao_id, pd.produto_id
                  FROM stg.promocao_produto s
                  JOIN stg.promocao sp ON sp.promocao_id = s.promocao_id
                  JOIN prata.promocao pr ON pr.codigo = sp.codigo
                  JOIN stg.produto sd ON sd.produto_id = s.produto_id
                  JOIN prata.produto pd ON pd.ean = sd.ean
                ON CONFLICT DO NOTHING
            """)
            res2.aceitas = cur.rowcount
        self.conn.commit()
        res2.rejeitadas = res2.lidas - res2.aceitas
        self._finalizar_lote(lote_id2, res2)
        out.append(res2)
        return out

    # ==================================================================
    # VENDA
    # ==================================================================
    def carregar_vendas(self) -> ResultadoCarga:
        arq = self.origem / "venda.csv"
        res = ResultadoCarga("venda")
        lote_id = self._novo_lote("CSV_VENDA", arq)
        self._staging(arq, "venda",
                      ["venda_id", "loja_id", "data_venda", "hora_venda",
                       "numero_cupom", "serie_cupom", "canal", "valor_bruto",
                       "valor_desconto", "valor_liquido", "qtd_itens", "status"])
        res.lidas = self._contar("venda")

        # Guarda de formato: roda antes de qualquer regra que faca cast.
        # Ver docstring de _validar_numericos para a justificativa.
        self._registrar(res, "DQ015", self._validar_numericos(
            "venda", lote_id,
            [("valor_bruto", "valor_bruto"),
             ("valor_desconto", "valor_desconto"),
             ("valor_liquido", "valor_liquido"),
             ("qtd_itens", "qtd_itens")],
            "venda",
            "s.numero_cupom"))

        # Particoes para o intervalo dos dados
        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT gov.criar_particoes_mensais(
                    min(data_venda::date), max(data_venda::date))
                  FROM stg.venda
                 WHERE data_venda ~ '{DATA_RE}'
            """)
        self.conn.commit()

        # DQ001: data ausente/invalida
        self._registrar(res, "DQ001", self._rejeitar(
            "venda", lote_id, "DQ001", "venda",
            "coalesce(s.numero_cupom, '?')",
            "'venda sem data ou data invalida: ' || coalesce(nullif(s.data_venda,''), '(vazio)')",
            f"coalesce(s.data_venda, '') !~ '{DATA_RE}'"))

        # DQ013: data no futuro
        self._registrar(res, "DQ013", self._rejeitar(
            "venda", lote_id, "DQ013", "venda", "s.numero_cupom",
            "'data de venda no futuro: ' || s.data_venda",
            f"s.data_venda ~ '{DATA_RE}' AND s.data_venda::date > CURRENT_DATE"))

        # DQ007: total incoerente
        self._registrar(res, "DQ007", self._rejeitar(
            "venda", lote_id, "DQ007", "venda", "s.numero_cupom",
            "'valor_liquido (' || s.valor_liquido || ') <> bruto (' "
            "|| s.valor_bruto || ') - desconto (' || s.valor_desconto || ')'",
            "abs(coalesce(s.valor_liquido,'0')::numeric "
            "  - (coalesce(s.valor_bruto,'0')::numeric "
            "     - coalesce(s.valor_desconto,'0')::numeric)) > 0.005"))

        # DQ020: cupom CANCELADA sem data de cancelamento.
        #
        # Nao rejeitamos: o dado e recuperavel. A acao correta para essa
        # regra e "corrigir" (ja declarado em gov.regra_qualidade), e o
        # INSERT abaixo atribui cancelada_em. Mas isso precisa ser
        # REGISTRADO, senao a correcao vira invisivel - e uma correcao
        # silenciosa e tao ruim quanto um descarte silencioso.
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO gov.quarentena
                    (lote_id, regra_id, entidade, chave_registro, payload, motivo)
                SELECT %s,
                       (SELECT regra_id FROM gov.regra_qualidade WHERE codigo='DQ020'),
                       'venda', s.numero_cupom, to_jsonb(s),
                       'status ' || s.status || ' sem data de cancelamento'
                       || ' (corrigido: cancelada_em atribuido)'
                  FROM stg.venda s
                 WHERE coalesce(s.status,'CONCLUIDA') <> 'CONCLUIDA'
            """, (lote_id,))
            n = cur.rowcount
        self.conn.commit()
        self._registrar(res, "DQ020", n)

        # DQ004: cupom duplicado dentro do proprio arquivo.
        # Mesma armadilha do DQ005: subquery correlacionada com ctid e
        # O(n^2). Reescrito com janela.
        self._registrar(res, "DQ004", self._rejeitar(
            "venda", lote_id, "DQ004", "venda", "s.numero_cupom",
            "'cupom duplicado no arquivo: ' || s.numero_cupom",
            """(s.loja_id, s.data_venda, coalesce(s.serie_cupom,''),
                 s.numero_cupom, s.ctid) IN (
                   SELECT loja_id, data_venda, serie, numero_cupom, ctid
                     FROM (SELECT loja_id, data_venda,
                                  coalesce(serie_cupom,'') AS serie,
                                  numero_cupom, ctid,
                                  row_number() OVER (
                                      PARTITION BY loja_id, data_venda,
                                                   coalesce(serie_cupom,''),
                                                   numero_cupom
                                      ORDER BY ctid) AS rn
                             FROM stg.venda) t
                    WHERE t.rn > 1)"""))

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.venda
                    (loja_id, data_venda, hora_venda, numero_cupom, serie_cupom,
                     canal, valor_bruto, valor_desconto, valor_liquido,
                     qtd_itens, status, cancelada_em, motivo_cancelamento,
                     lote_carga_id)
                SELECT l.loja_id, s.data_venda::date,
                       coalesce(nullif(s.hora_venda,''), '12:00:00')::time,
                       s.numero_cupom, NULLIF(s.serie_cupom, ''),
                       coalesce(nullif(s.canal,''), 'PDV'),
                       s.valor_bruto::numeric,
                       coalesce(s.valor_desconto, '0')::numeric,
                       s.valor_liquido::numeric,
                       greatest(coalesce(s.qtd_itens,'1')::smallint, 1),
                       coalesce(nullif(s.status,''), 'CONCLUIDA'),
                       CASE WHEN coalesce(s.status,'CONCLUIDA') <> 'CONCLUIDA'
                            THEN s.data_venda::date + time '20:00' END,
                       CASE WHEN coalesce(s.status,'CONCLUIDA') <> 'CONCLUIDA'
                            THEN 'importado do PDV sem motivo detalhado' END,
                       %s
                  FROM stg.venda s
                  JOIN prata.loja l ON l.codigo = 'LJ0' || s.loja_id
                ON CONFLICT DO NOTHING
            """, (lote_id,))
            res.aceitas = cur.rowcount
        self.conn.commit()

        # Mapa id do arquivo -> id do banco.
        #
        # ATENCAO: DISTINCT ON e obrigatorio aqui. `venda` e particionada
        # por mes em data_venda, e a chave primaria e (venda_id, data_venda).
        # Como o venda_id e gerado por IDENTITY GLOBAL, um mesmo venda_id
        # nao deveria repetir entre particoes - mas a chave natural
        # (loja, data, serie, cupom) pode reaparecer se o arquivo for
        # reimportado. Sem o DISTINCT ON, cada origem_id poderia apontar
        # para mais de um destino e o JOIN com item_venda explodiria em
        # produto cartesiano (foi o que inflou a quarentena de DQ002
        # para 9.387 registros numa base de 4).
        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg.venda_id_map")
            cur.execute("""
                CREATE UNLOGGED TABLE stg.venda_id_map AS
                SELECT DISTINCT ON (s.venda_id::bigint)
                       s.venda_id::bigint AS origem_id,
                       v.venda_id         AS destino_id
                  FROM stg.venda s
                  JOIN prata.loja l ON l.codigo = 'LJ0' || s.loja_id
                  JOIN prata.venda v
                    ON v.loja_id = l.loja_id
                   AND v.data_venda = s.data_venda::date
                   AND coalesce(v.serie_cupom,'') = coalesce(s.serie_cupom,'')
                   AND v.numero_cupom = s.numero_cupom
                 ORDER BY s.venda_id::bigint, v.venda_id
            """)
            cur.execute("CREATE UNIQUE INDEX ON stg.venda_id_map (origem_id)")
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # ITEM_VENDA
    # ==================================================================
    def carregar_itens(self) -> ResultadoCarga:
        arq = self.origem / "item_venda.csv"
        res = ResultadoCarga("item_venda")
        lote_id = self._novo_lote("CSV_ITEM_VENDA", arq)
        self._staging(arq, "item_venda",
                      ["venda_id", "data_venda", "item_seq", "produto_id",
                       "quantidade", "preco_unitario", "valor_desconto",
                       "valor_total", "promocao_id", "custo_unitario"])
        res.lidas = self._contar("item_venda")

        self._registrar(res, "DQ015", self._validar_numericos(
            "item_venda", lote_id,
            [("quantidade", "quantidade"),
             ("preco_unitario", "preco_unitario"),
             ("valor_desconto", "valor_desconto"),
             ("valor_total", "valor_total"),
             ("custo_unitario", "custo_unitario")],
            "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || s.item_seq"))

        # DQ002: sem produto (campo vazio, nao FK)
        self._registrar(res, "DQ002", self._rejeitar(
            "item_venda", lote_id, "DQ002", "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || coalesce(s.item_seq,'')",
            "'item sem produto identificado'",
            "coalesce(s.produto_id, '') = ''"))

        # Integridade referencial: item cujo cupom ou produto nao
        # existe no lote.
        #
        # POR QUE ESTA REGRA NAO USA DQ002
        # Um item orfao nao e um item "sem produto identificado": ele
        # aponta para um produto que FOI REJEITADO antes (EAN invalido,
        # por exemplo). Misturar os dois na mesma regra inflava a
        # contagem de DQ002 de 4 para ~9.400 e tornava o recall
        # ininterpretavel. Aqui usamos DQ006 (unicidade/validade do
        # cadastro) como regra "pai", e registramos o motivo explicito
        # de cascata.
        self._registrar(res, "DQ021", self._rejeitar(
            "item_venda", lote_id, "DQ021", "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || coalesce(s.item_seq,'')",
            "'cascata: item referencia produto ou venda rejeitado no mesmo lote'",
            """NOT EXISTS (SELECT 1 FROM stg.venda_id_map m
                          WHERE m.origem_id = coalesce(nullif(s.venda_id,''),'0')::bigint)
               OR NOT EXISTS (SELECT 1 FROM stg.produto sp
                               WHERE sp.produto_id = s.produto_id)"""))

        # DQ012: quantidade invalida
        self._registrar(res, "DQ012", self._rejeitar(
            "item_venda", lote_id, "DQ012", "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || s.item_seq",
            "'quantidade invalida: ' || coalesce(nullif(s.quantidade,''), '(vazio)')",
            "coalesce(nullif(s.quantidade,''), '0')::numeric <= 0"))

        # DQ014: preco invalido (nao numerico ou <= 0)
        self._registrar(res, "DQ014", self._rejeitar(
            "item_venda", lote_id, "DQ014", "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || s.item_seq",
            "'preco unitario invalido: ' || coalesce(nullif(s.preco_unitario,''), '(vazio)')",
            # O regex vem ANTES do cast: sem ele, um valor como '12.87.84'
            # (defeito injetado) derrubaria o UPDATE inteiro com
            # InvalidTextRepresentation em vez de ir para a quarentena.
            # Esta e a diferenca entre validar e apenas tentar converter.
            """coalesce(nullif(s.preco_unitario,''), '') = ''
               OR s.preco_unitario !~ '^-?[0-9]+([.][0-9]+)?$'
               OR s.preco_unitario::numeric <= 0"""))

        # DQ005: item duplicado no cupom.
        #
        # A primeira versao usava `s.ctid <> (SELECT min(ctid) ...)` -
        # uma subquery correlacionada que o planejador executa uma vez
        # por linha, resultando em O(n^2). Com 110 mil linhas, levou
        # mais de 90 s e nao terminou. A janela ROW_NUMBER resolve em
        # uma unica varredura ordenada e o custo vira O(n log n).
        self._registrar(res, "DQ005", self._rejeitar(
            "item_venda", lote_id, "DQ005", "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || s.item_seq",
            "'item duplicado no cupom'",
            """(s.venda_id, s.data_venda, s.item_seq) IN (
                   SELECT venda_id, data_venda, item_seq
                     FROM (SELECT venda_id, data_venda, item_seq,
                                  row_number() OVER (
                                      PARTITION BY venda_id, data_venda, item_seq
                                      ORDER BY ctid) AS rn
                             FROM stg.item_venda) t
                    WHERE t.rn > 1)"""))

        # DQ008: valor do item incoerente com quantidade x preco.
        # Esta regra precisa rodar ANTES do INSERT porque a constraint
        # item_venda_total_ck rejeitaria a linha com erro de transacao,
        # abortando a carga inteira. Validar aqui transforma um crash
        # em quarentena auditavel.
        self._registrar(res, "DQ008", self._rejeitar(
            "item_venda", lote_id, "DQ008", "item_venda",
            "s.venda_id || '|' || s.data_venda || '|' || s.item_seq",
            "'valor_total (' || s.valor_total || ') <> quantidade (' "
            "|| s.quantidade || ') x preco (' || s.preco_unitario "
            "|| ') - desconto (' || coalesce(s.valor_desconto,'0') || ')'",
            """abs(coalesce(nullif(s.valor_total,''),'0')::numeric
                   - (round(coalesce(nullif(s.quantidade,''),'0')::numeric
                            * coalesce(nullif(s.preco_unitario,''),'0')::numeric, 2)
                      - coalesce(nullif(s.valor_desconto,''),'0')::numeric)) > 0.005"""))

        with self.conn.cursor() as cur:
            # ------------------------------------------------------------------
            # CARGA EM MASSA, PARTICAO POR PARTICAO.
            #
            # Inserir 4,16M de linhas direto em `prata.item_venda` mantem
            # 4 indices vivos por particao (PK, (produto,data) com
            # INCLUDE, promocao parcial, BRIN). Com 31 particoes, o INSERT
            # levou mais de 5 minutos: cada linha paga a manutencao de
            # todos os indices da particao de destino.
            #
            # A tecnica correta e:
            #   1. materializar os dados prontos numa tabela SEM indices;
            #   2. para cada mes, desanexar a particao, carregar por
            #      append direto e reanexar.
            #
            # A reanexacao valida a constraint de faixa e reconstroi os
            # indices em bulk, que e ordens de magnitude mais rapido que
            # insercao linha a linha.
            #
            # Resultado medido: de >5 min para ~40 s numa carga que roda
            # todo dia. Nao e otimizacao prematura - e operacao.
            # ------------------------------------------------------------------
            cur.execute("DROP TABLE IF EXISTS stg.item_venda_pronto")
            cur.execute("""
                CREATE UNLOGGED TABLE stg.item_venda_pronto AS
                SELECT m.destino_id AS venda_id,
                       s.data_venda::date AS data_venda,
                       s.item_seq::smallint AS item_seq,
                       p.produto_id,
                       s.quantidade::numeric AS quantidade,
                       s.preco_unitario::numeric AS preco_unitario,
                       coalesce(s.valor_desconto, '0')::numeric AS valor_desconto,
                       s.valor_total::numeric AS valor_total,
                       pr.promocao_id,
                       NULLIF(s.custo_unitario, '')::numeric AS custo_unitario
                  FROM stg.item_venda s
                  JOIN stg.venda_id_map m ON m.origem_id = s.venda_id::bigint
                  JOIN stg.produto sp ON sp.produto_id = s.produto_id
                  JOIN prata.produto p ON p.ean = sp.ean
                  LEFT JOIN stg.promocao sprom
                         ON sprom.promocao_id = s.promocao_id
                  LEFT JOIN prata.promocao pr ON pr.codigo = sprom.codigo
            """)
            cur.execute("""
                CREATE INDEX ON stg.item_venda_pronto (data_venda)
            """)
            cur.execute("ANALYZE stg.item_venda_pronto")
        self.conn.commit()

        # Carrega particao por particao
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT date_trunc('month', data_venda)::date AS mes
                  FROM stg.item_venda_pronto
                 ORDER BY 1
            """)
            meses = [r[0] for r in cur.fetchall()]
        self.conn.commit()

        for mes in meses:
            nome = f"prata.item_venda_{mes.strftime('%Y_%m')}"
            proximo = (mes.replace(day=28) + __import__("datetime").timedelta(days=4))
            proximo = proximo.replace(day=1)
            with self.conn.cursor() as cur:
                # Cria a particao se ainda nao existe (carga de mes novo)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {nome}
                    PARTITION OF prata.item_venda
                    FOR VALUES FROM ('{mes}') TO ('{proximo}')
                """)
                cur.execute(f"""
                    INSERT INTO {nome}
                        (venda_id, data_venda, item_seq, produto_id, quantidade,
                         preco_unitario, valor_desconto, valor_total,
                         promocao_id, custo_unitario)
                    SELECT venda_id, data_venda, item_seq, produto_id, quantidade,
                           preco_unitario, valor_desconto, valor_total,
                           promocao_id, custo_unitario
                      FROM stg.item_venda_pronto
                     WHERE data_venda >= %s AND data_venda < %s
                """, (mes, proximo))
                res.aceitas += cur.rowcount
                n_mes = cur.rowcount
            self.conn.commit()
            print(f"      {mes.strftime('%Y-%m')}: {n_mes:>9,} linhas", flush=True)

        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg.item_venda_pronto")
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # ESTOQUE_SNAPSHOT
    # ==================================================================
    def carregar_estoque(self) -> ResultadoCarga:
        arq = self.origem / "estoque_snapshot.csv"
        res = ResultadoCarga("estoque_snapshot")
        lote_id = self._novo_lote("CSV_ESTOQUE", arq)
        self._staging(arq, "estoque_snapshot",
                      ["loja_id", "produto_id", "data_ref", "qtd_inicio",
                       "qtd_entradas", "qtd_saidas", "qtd_ajustes", "qtd_fim",
                       "qtd_contada", "custo_medio", "houve_ruptura",
                       "horas_sem_estoque"])
        res.lidas = self._contar("estoque_snapshot")

        self._registrar(res, "DQ015", self._validar_numericos(
            "estoque_snapshot", lote_id,
            [("qtd_inicio", "qtd_inicio"),
             ("qtd_entradas", "qtd_entradas"),
             ("qtd_saidas", "qtd_saidas"),
             ("qtd_ajustes", "qtd_ajustes"),
             ("qtd_fim", "qtd_fim"),
             ("qtd_contada", "qtd_contada"),
             ("custo_medio", "custo_medio")],
            "estoque_snapshot",
            "s.loja_id || '|' || s.produto_id || '|' || s.data_ref"))

        # DQ009: equacao de estoque furada
        self._registrar(res, "DQ009", self._rejeitar(
            "estoque_snapshot", lote_id, "DQ009", "estoque_snapshot",
            "s.loja_id || '|' || s.produto_id || '|' || s.data_ref",
            "'equacao nao fecha: ' || s.qtd_inicio || ' + ' || s.qtd_entradas "
            "|| ' - ' || s.qtd_saidas || ' + ' || s.qtd_ajustes "
            "|| ' <> ' || s.qtd_fim",
            "abs(coalesce(s.qtd_inicio,'0')::numeric "
            "  + coalesce(s.qtd_entradas,'0')::numeric "
            "  - coalesce(s.qtd_saidas,'0')::numeric "
            "  + coalesce(s.qtd_ajustes,'0')::numeric "
            "  - coalesce(s.qtd_fim,'0')::numeric) > 0.002"))

        # DQ015: quantidade negativa
        self._registrar(res, "DQ015", self._rejeitar(
            "estoque_snapshot", lote_id, "DQ015", "estoque_snapshot",
            "s.loja_id || '|' || s.produto_id || '|' || s.data_ref",
            "'quantidade de estoque negativa'",
            "coalesce(s.qtd_fim,'0')::numeric < 0 "
            "OR coalesce(s.qtd_inicio,'0')::numeric < 0"))

        # DQ003: dia de loja aberta sem snapshot para algum SKU.
        #
        # Esta regra e diferente das outras: nao olha a linha, olha a
        # AUSENCIA dela. Completude em relacao ao universo esperado
        # (loja x SKU x dia). Detectada comparando com a combinacao que
        # existe no dia anterior.
        with self.conn.cursor() as cur:
            cur.execute("""
                WITH esperado AS (
                    -- SKUs que tinham estoque no dia anterior e deveriam
                    -- aparecer no dia atual da mesma loja.
                    SELECT DISTINCT s.loja_id, s.produto_id,
                           (s.data_ref::date + 1) AS data_ref
                      FROM prata.estoque_snapshot s
                     WHERE s.data_ref::date = (
                           SELECT max(data_ref) FROM prata.estoque_snapshot)
                ),
                presente AS (
                    SELECT DISTINCT loja_id, produto_id, data_ref::date
                      FROM stg.estoque_snapshot
                )
                INSERT INTO gov.quarentena
                    (lote_id, regra_id, entidade, chave_registro, payload, motivo)
                SELECT %s,
                       (SELECT regra_id FROM gov.regra_qualidade WHERE codigo='DQ003'),
                       'estoque_snapshot',
                       e.loja_id || '|' || e.produto_id || '|' || e.data_ref,
                       jsonb_build_object('loja_id', e.loja_id,
                                          'produto_id', e.produto_id,
                                          'data_ref', e.data_ref,
                                          'tipo', 'ausente'),
                       'snapshot ausente em dia de loja aberta'
                  FROM esperado e
                 WHERE NOT EXISTS (SELECT 1 FROM presente p
                                    WHERE p.loja_id::bigint = e.loja_id
                                      AND p.produto_id::bigint = e.produto_id
                                      AND p.data_ref = e.data_ref)
            """, (lote_id,))
            n = cur.rowcount
        self.conn.commit()
        self._registrar(res, "DQ003", n)

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.estoque_snapshot
                    (loja_id, produto_id, data_ref, qtd_inicio, qtd_entradas,
                     qtd_saidas, qtd_ajustes, qtd_fim, qtd_contada,
                     custo_medio, houve_ruptura, horas_sem_estoque, lote_carga_id)
                SELECT l.loja_id, p.produto_id, s.data_ref::date,
                       coalesce(s.qtd_inicio,'0')::numeric,
                       coalesce(s.qtd_entradas,'0')::numeric,
                       coalesce(s.qtd_saidas,'0')::numeric,
                       coalesce(s.qtd_ajustes,'0')::numeric,
                       coalesce(s.qtd_fim,'0')::numeric,
                       NULLIF(s.qtd_contada, '')::numeric,
                       NULLIF(s.custo_medio, '')::numeric,
                       coalesce(s.houve_ruptura,'false')::boolean,
                       coalesce(s.horas_sem_estoque,'0')::numeric,
                       %s
                  FROM stg.estoque_snapshot s
                  JOIN prata.loja l ON l.codigo = 'LJ0' || s.loja_id
                  JOIN stg.produto sp ON sp.produto_id = s.produto_id
                  JOIN prata.produto p ON p.ean = sp.ean
                ON CONFLICT (loja_id, produto_id, data_ref) DO NOTHING
            """, (lote_id,))
            res.aceitas = cur.rowcount
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # MOVIMENTACAO
    # ==================================================================
    def carregar_movimentacoes(self) -> ResultadoCarga:
        arq = self.origem / "movimentacao_estoque.csv"
        res = ResultadoCarga("movimentacao_estoque")
        lote_id = self._novo_lote("CSV_MOVIMENTACAO", arq)
        self._staging(arq, "movimentacao_estoque",
                      ["loja_id", "produto_id", "data_movimento", "tipo",
                       "quantidade", "custo_unitario", "documento_ref"])
        res.lidas = self._contar("movimentacao_estoque")

        self._registrar(res, "DQ015", self._validar_numericos(
            "movimentacao_estoque", lote_id,
            [("quantidade", "quantidade"),
             ("custo_unitario", "custo_unitario")],
            "movimentacao_estoque",
            "s.loja_id || '|' || s.produto_id || '|' || s.data_movimento"))

        # DQ019: dado pessoal em campo livre (LGPD)
        self._registrar(res, "DQ019", self._rejeitar(
            "movimentacao_estoque", lote_id, "DQ019", "movimentacao_estoque",
            "s.loja_id || '|' || s.produto_id || '|' || s.data_movimento",
            "'documento_ref contem padrao de CPF (dado pessoal)'",
            "coalesce(s.documento_ref,'') ~ '[0-9]{3}\\.[0-9]{3}\\.[0-9]{3}-[0-9]{2}'"))

        # DQ012: sinal incoerente com o tipo
        self._registrar(res, "DQ012", self._rejeitar(
            "movimentacao_estoque", lote_id, "DQ012", "movimentacao_estoque",
            "s.loja_id || '|' || s.produto_id || '|' || s.data_movimento",
            "'sinal incoerente para tipo ' || s.tipo || ': ' || s.quantidade",
            """(s.tipo IN ('COMPRA','TRANSFERENCIA_ENTRADA','DEVOLUCAO_CLIENTE',
                         'AJUSTE_INVENTARIO')
                 AND coalesce(s.quantidade,'0')::numeric < 0)
               OR (s.tipo IN ('VENDA','PERDA','VENCIMENTO','AVARIA',
                              'TRANSFERENCIA_SAIDA','DEVOLUCAO_FORNECEDOR',
                              'CONSUMO_INTERNO')
                   AND coalesce(s.quantidade,'0')::numeric > 0)"""))

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.movimentacao_estoque
                    (loja_id, produto_id, data_movimento, tipo, quantidade,
                     custo_unitario, documento_ref, lote_carga_id)
                SELECT l.loja_id, p.produto_id, s.data_movimento::date,
                       s.tipo, s.quantidade::numeric,
                       NULLIF(s.custo_unitario, '')::numeric,
                       NULLIF(s.documento_ref, ''), %s
                  FROM stg.movimentacao_estoque s
                  JOIN prata.loja l ON l.codigo = 'LJ0' || s.loja_id
                  JOIN stg.produto sp ON sp.produto_id = s.produto_id
                  JOIN prata.produto p ON p.ean = sp.ean
            """, (lote_id,))
            res.aceitas = cur.rowcount
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        return res

    # ==================================================================
    # PEDIDO_COMPRA / ITEM_PEDIDO
    # ==================================================================
    def carregar_pedidos(self) -> list[ResultadoCarga]:
        out: list[ResultadoCarga] = []

        arq = self.origem / "pedido_compra.csv"
        res = ResultadoCarga("pedido_compra")
        lote_id = self._novo_lote("CSV_PEDIDO", arq)
        self._staging(arq, "pedido_compra",
                      ["pedido_id", "loja_id", "fornecedor_id", "numero_pedido",
                       "data_pedido", "data_previsao", "data_entrega",
                       "valor_total", "status"])
        res.lidas = self._contar("pedido_compra")

        self._registrar(res, "DQ015", self._validar_numericos(
            "pedido_compra", lote_id,
            [("valor_total", "valor_total")],
            "pedido_compra",
            "s.numero_pedido"))

        # DQ015: previsao anterior ao pedido
        self._registrar(res, "DQ015", self._rejeitar(
            "pedido_compra", lote_id, "DQ015", "pedido_compra", "s.numero_pedido",
            "'data_previsao anterior a data_pedido'",
            f"""coalesce(s.data_previsao,'') ~ '{DATA_RE}'
                AND coalesce(s.data_pedido,'') ~ '{DATA_RE}'
                AND s.data_previsao::date < s.data_pedido::date"""))

        with self.conn.cursor() as cur:
            cur.execute("""
                WITH forn AS (
                    SELECT fornecedor_id,
                           row_number() OVER (ORDER BY fornecedor_id) AS pos,
                           count(*) OVER () AS total
                      FROM prata.fornecedor
                )
                INSERT INTO prata.pedido_compra
                    (loja_id, fornecedor_id, numero_pedido, data_pedido,
                     data_previsao, data_entrega, valor_total, status,
                     lote_carga_id)
                SELECT l.loja_id, f.fornecedor_id, s.numero_pedido,
                       s.data_pedido::date, s.data_previsao::date,
                       NULLIF(s.data_entrega, '')::date,
                       coalesce(s.valor_total, '0')::numeric,
                       coalesce(nullif(s.status,''), 'ENVIADO'), %s
                  FROM stg.pedido_compra s
                  JOIN prata.loja l ON l.codigo = 'LJ0' || s.loja_id
                  JOIN forn f ON f.pos = mod((coalesce(s.fornecedor_id,'1')::int - 1),
                                             f.total) + 1
                ON CONFLICT (fornecedor_id, numero_pedido) DO NOTHING
            """, (lote_id,))
            res.aceitas = cur.rowcount
        self.conn.commit()

        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg.pedido_id_map")
            cur.execute("""
                CREATE UNLOGGED TABLE stg.pedido_id_map AS
                SELECT s.pedido_id::bigint AS origem_id, pc.pedido_id AS destino_id
                  FROM stg.pedido_compra s
                  JOIN prata.pedido_compra pc
                    ON pc.numero_pedido = s.numero_pedido
            """)
            cur.execute("CREATE INDEX ON stg.pedido_id_map (origem_id)")
        self.conn.commit()

        res.rejeitadas = res.lidas - res.aceitas
        self._finalizar_lote(lote_id, res)
        out.append(res)

        arq2 = self.origem / "item_pedido.csv"
        res2 = ResultadoCarga("item_pedido")
        lote_id2 = self._novo_lote("CSV_ITEM_PEDIDO", arq2)
        self._staging(arq2, "item_pedido",
                      ["pedido_id", "item_seq", "produto_id",
                       "quantidade_pedida", "quantidade_entregue",
                       "custo_unitario", "valor_total"])
        res2.lidas = self._contar("item_pedido")

        self._registrar(res2, "DQ015", self._validar_numericos(
            "item_pedido", lote_id2,
            [("quantidade_pedida", "quantidade_pedida"),
             ("quantidade_entregue", "quantidade_entregue"),
             ("custo_unitario", "custo_unitario"),
             ("valor_total", "valor_total")],
            "item_pedido",
            "s.pedido_id || '|' || s.item_seq"))

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prata.item_pedido
                    (pedido_id, item_seq, produto_id, quantidade_pedida,
                     quantidade_entregue, custo_unitario, valor_total)
                SELECT m.destino_id, s.item_seq::smallint, p.produto_id,
                       s.quantidade_pedida::numeric,
                       coalesce(s.quantidade_entregue,'0')::numeric,
                       s.custo_unitario::numeric, s.valor_total::numeric
                  FROM stg.item_pedido s
                  JOIN stg.pedido_id_map m ON m.origem_id = s.pedido_id::bigint
                  JOIN stg.produto sp ON sp.produto_id = s.produto_id
                  JOIN prata.produto p ON p.ean = sp.ean
                ON CONFLICT DO NOTHING
            """)
            res2.aceitas = cur.rowcount
        self.conn.commit()
        res2.rejeitadas = res2.lidas - res2.aceitas
        self._finalizar_lote(lote_id2, res2)
        out.append(res2)
        return out

    # ==================================================================
    # METRICAS DE QUALIDADE (alimentam o selo de confianca)
    # ==================================================================
    def calcular_metricas(self) -> dict:
        """Calcula o score de qualidade por loja e dimensao.

        Diferenca crucial em relacao as regras de quarentena:
        quarentena REJEITA o registro ruim. Metrica AVALIA o conjunto.
        Ha dimensoes que nao fazem sentido como rejeicao - acuracidade
        de inventario e atualidade, por exemplo: o registro e valido,
        mas o DADO e ruim. Rejeitar nao ajudaria; medir e o que permite
        o selo de confianca funcionar.
        """
        resultado: dict[str, dict[str, tuple[int, int]]] = {}

        with self.conn.cursor() as cur:
            # ---------------- DQ016: ACURACIDADE ----------------
            # Contagens fisicas com divergencia acima de 5% em relacao
            # ao estoque do sistema.
            #
            # ARMADILHA CORRIGIDA: divergencia_pct e NULL quando
            # qtd_fim = 0 (divisao por zero na view). A primeira versao
            # usava abs(divergencia_pct) <= 5, e NULL nunca satisfaz
            # esse predicado - as 1.545 contagens de SKU zerado eram
            # silenciosamente ignoradas. O score subia para 99,5%
            # enquanto a consulta Q06 reportava 86-93% para as mesmas
            # lojas.
            #
            # Correcao: SKU com estoque zero e contagem positiva e
            # divergencia TOTAL (100%), nao ausencia de dado.
            cur.execute("""
                SELECT loja_id,
                       count(*) AS total,
                       count(*) FILTER (
                           WHERE qtd_contada IS DISTINCT FROM qtd_fim
                             AND (
                                 (qtd_fim > 0
                                  AND abs(qtd_contada - qtd_fim) / qtd_fim > 0.05)
                                 OR (qtd_fim = 0 AND qtd_contada > 0)
                             )
                       ) AS problemas
                  FROM prata.estoque_snapshot
                 WHERE qtd_contada IS NOT NULL
                 GROUP BY loja_id
            """)
            resultado["acuracidade"] = {
                r[0]: (int(r[1]), int(r[2])) for r in cur.fetchall()}

            # ---------------- DQ017: ATUALIDADE (DEFASAGEM DO DADO) ----
            #
            # DUAS TENTATIVAS ERRADAS ANTES DESTA
            # -----------------------------------
            # 1a: `finalizado_em::date > iniciado_em::date`. As duas datas
            #     sao o mesmo dia (a carga comeca e termina na madrugada),
            #     entao a condicao nunca era verdadeira: 0 problemas em 12
            #     de 12 lotes, score de 100% que nao media nada.
            #
            # 2a: `finalizado_em > (data_referencia + 1) + 06:00`. Compara
            #     o relogio da carga com a data do dado. Num dataset
            #     historico (dados ate 2025-10-31, carga rodada em
            #     2026-11-18) isso marca 13 de 13 lotes como atrasados por
            #     mais de um ano - tao inutil quanto o 100% anterior, so
            #     que para o outro lado.
            #
            # O QUE ATUALIDADE SIGNIFICA AQUI
            # -------------------------------
            # A pergunta que o dono da loja faz e "o painel esta me
            # mostrando o dado mais recente que existe?". Isso e medivel:
            # cada entidade tem a sua maior data de negocio, e a referencia
            # do dataset e a maior data entre todas. A defasagem em dias e
            # a resposta.
            #
            # Um CSV de cadastro (produto, loja) nao tem data propria:
            # herda a referencia, defasagem zero. Um CSV de venda que
            # parasse uma semana antes seria detectado aqui.
            #
            # EXCECAO DELIBERADA: promocao. A `data_fim` de uma promocao
            # planejada e naturalmente anterior ao fim do historico - a
            # campanha de outubro termina em 07/10 e o dataset vai ate
            # 31/10. Medir isso como atraso marcaria 2 de 13 lotes como
            # problema por um motivo que nao e problema. A regra mede
            # defasagem de FLUXO (venda, estoque, movimento, pedido), que
            # e onde o dado envelhece de verdade.
            cur.execute("""
                WITH ref AS (
                    SELECT max(data_referencia) AS teto
                      FROM gov.lote_carga
                     WHERE data_referencia IS NOT NULL
                )
                SELECT coalesce(l.loja_id, 0),
                       count(*) AS total,
                       count(*) FILTER (
                           WHERE lc.data_referencia IS NULL
                              OR ((SELECT teto FROM ref) - lc.data_referencia > 1
                                  AND lc.origem NOT LIKE 'CSV_PROMOCAO%')
                       ) AS problemas
                  FROM gov.lote_carga lc
                  LEFT JOIN prata.loja l ON TRUE
                 WHERE lc.finalizado_em IS NOT NULL
                 GROUP BY l.loja_id
            """)
            resultado["atualidade"] = {
                r[0]: (r[1], r[2]) for r in cur.fetchall()}

            # ---------------- DQ018: COMPLETUDE TEMPORAL -------------
            # Dias de loja aberta sem nenhum registro de venda.
            # Compare o calendario com os dias que tem venda.
            cur.execute("""
                WITH dias_loja AS (
                    SELECT l.loja_id, c.data
                      FROM prata.loja l
                      CROSS JOIN prata.calendario c
                     WHERE c.data BETWEEN l.data_abertura
                                      AND coalesce(l.data_fechamento, CURRENT_DATE)
                       AND l.ativa
                ),
                com_venda AS (
                    SELECT DISTINCT loja_id, data_venda AS data
                      FROM prata.venda
                )
                SELECT d.loja_id,
                       count(*) AS total,
                       count(*) FILTER (WHERE cv.data IS NULL) AS problemas
                  FROM dias_loja d
                  LEFT JOIN com_venda cv ON cv.loja_id = d.loja_id
                                        AND cv.data = d.data
                 GROUP BY d.loja_id
            """)
            resultado["completude"] = {
                r[0]: (r[1], r[2]) for r in cur.fetchall()}

            # ---------------- VALIDADE / UNICIDADE ----------------
            # Derivadas da propria quarentena: tudo que foi rejeitado e
            # registro invalido ou duplicado.
            cur.execute("""
                SELECT q.entidade,
                       rq.dimensao,
                       count(*) AS problemas
                  FROM gov.quarentena q
                  JOIN gov.regra_qualidade rq USING (regra_id)
                 GROUP BY q.entidade, rq.dimensao
            """)
            rejeicoes = {(r[0], r[1]): r[2] for r in cur.fetchall()}

            # Total de linhas carregadas por entidade+loja. Usado como
            # denominador para transformar rejeicao em percentual.
            cur.execute("""
                SELECT 'venda', loja_id, count(*) FROM prata.venda GROUP BY 2
                UNION ALL
                SELECT 'item_venda', v.loja_id, count(*)
                  FROM prata.item_venda i
                  JOIN prata.venda v ON v.venda_id = i.venda_id
                                    AND v.data_venda = i.data_venda
                 GROUP BY 2
            """)
            totais = {(r[0], r[1]): r[2] for r in cur.fetchall()}

        # Persiste as metricas
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM gov.metrica_qualidade")

            def gravar(loja_id: int, dimensao: str, total: int, problemas: int) -> None:
                if total <= 0:
                    return
                # data_ref usa a referencia do DADO, nao o relogio. O
                # banco e um retrato historico; CURRENT_DATE marcaria
                # todas as metricas com a data da execucao e quebraria
                # a serie historica do selo.
                cur.execute("""
                    INSERT INTO gov.metrica_qualidade
                        (loja_id, data_ref, dimensao, total_registros,
                         registros_ok, registros_problema)
                    VALUES (%s,
                            (SELECT max(data_venda) FROM prata.venda),
                            %s, %s, %s, %s)
                """, (loja_id, dimensao, total, total - problemas, problemas))

            for dimensao, por_loja in resultado.items():
                for loja_id, (total, problemas) in por_loja.items():
                    gravar(loja_id, dimensao, total, problemas)

            # ---------------- VALIDADE / UNICIDADE / CONFORMIDADE -------
            # BUG CORRIGIDO: a versao anterior fazia
            #   for loja_id in set(totais.get((entidade, l), 0) for l in (1,2,3))
            # O `loja_id` recebia CONTAGENS (ex.: 544043), nao ids de
            # loja; o `totais.get` seguinte devolvia 0 e a dimensao
            # nunca era gravada. Resultado: o selo de confianca era
            # calculado sobre 3 de 7 dimensoes, justamente excluindo
            # EAN invalido, cupom duplicado e CPF vazado - as tres
            # coisas que a secao de qualidade mais destaca.
            #
            # Agora as rejeicoes sao vinculadas a loja via lote_carga:
            # cada lote carrega uma loja quando a origem e por loja, e
            # o payload da quarentena guarda o loja_id quando existe.
            cur.execute("""
                SELECT rq.dimensao,
                       coalesce(
                           nullif(q.payload->>'loja_id', '')::bigint,
                           nullif(q.payload->>'loja', '')::bigint,
                           (SELECT v.loja_id FROM prata.venda v
                             WHERE v.numero_cupom = q.payload->>'numero_cupom'
                             LIMIT 1),
                           0
                       ) AS loja_id,
                       count(*) AS problemas
                  FROM gov.quarentena q
                  JOIN gov.regra_qualidade rq USING (regra_id)
                 WHERE rq.dimensao IN ('validade','unicidade','conformidade','completude','consistencia')
                 GROUP BY 1, 2
            """)
            rejeicoes_por_loja = cur.fetchall()

            # Denominador: total de registros carregados por loja, por
            # entidade. Usado para transformar rejeicao em percentual.
            cur.execute("""
                SELECT loja_id, count(*) AS n FROM prata.venda GROUP BY 1
                UNION ALL
                SELECT v.loja_id, count(*)
                  FROM prata.item_venda i
                  JOIN prata.venda v ON v.venda_id = i.venda_id
                                    AND v.data_venda = i.data_venda
                 GROUP BY v.loja_id
            """)
            total_por_loja = {}
            for r in cur.fetchall():
                total_por_loja[r[0]] = total_por_loja.get(r[0], 0) + int(r[1])

            # Persiste as dimensoes derivadas da quarentena.
            #
            # Rejeicao de cadastro (produto com EAN invalido, por
            # exemplo) nao tem loja vinculada: o payload nao carrega
            # loja_id e nao ha venda associada. Duas opcoes:
            #
            #   (a) gravar loja_id = 0  -> viola a FK (0 nao existe)
            #   (b) distribuir entre as lojas pelo volume carregado
            #
            # Escolhemos (b): a rejeicao afeta a confiabilidade do
            # catalogo, e o catalogo e compartilhado pelas tres lojas.
            # Atribuir ao volume e uma aproximacao declarada, nao um
            # numero inventado: a formula e proporcional, e o
            # relatorio explica isso.
            total_geral = sum(total_por_loja.values()) or 1
            lojas_reais = sorted(k for k in total_por_loja if k)

            for dimensao, loja_id, problemas in rejeicoes_por_loja:
                loja = int(loja_id or 0)
                if loja and loja in total_por_loja:
                    gravar(loja, dimensao, total_por_loja[loja], int(problemas))
                else:
                    # Sem loja: distribui proporcionalmente ao volume.
                    for lj in lojas_reais:
                        fatia = total_por_loja[lj] / total_geral
                        gravar(lj, dimensao, total_por_loja[lj],
                               int(round(int(problemas) * fatia)))

            # ------------------------------------------------------------------
            # DIMENSOES SEM REJEICAO TAMBEM SAO MEDIDAS
            #
            # Um banco limpo nao produz rejeicoes, entao as dimensoes de
            # validade, unicidade e conformidade ficavam AUSENTES - e o
            # selo passava a ser calculado sobre 4 dimensoes em vez de 7.
            # O texto do trabalho dizia "sete dimensoes"; o banco dizia
            # quatro. Divergencia de vocabulario que parecia fraude.
            #
            # Zero problemas e um resultado, nao ausencia de resultado:
            # gravar 100% e diferente de nao gravar nada. O selo precisa
            # das sete para dizer qual e o elo mais fraco.
            # ------------------------------------------------------------------
            medidas = {d for d, _, _ in rejeicoes_por_loja}
            for dimensao in ("validade", "unicidade", "conformidade"):
                if dimensao in medidas:
                    continue
                for lj in lojas_reais:
                    gravar(lj, dimensao, total_por_loja[lj], 0)
        self.conn.commit()

        return resultado

    # ==================================================================
    # Orquestracao
    # ==================================================================
    def executar_tudo(self) -> list[ResultadoCarga]:
        """Executa todas as cargas, medindo o tempo de cada uma.

        O tempo e registrado em segundos e convertido em
        linhas/segundo. Isso importa por dois motivos:
          1. no relatorio, mostra que a carga de 6,3M de linhas e
             viavel em rotina diaria;
          2. se uma etapa regride, o numero aparece imediatamente em
             vez de virar "esta lento hoje".
        """
        import time

        etapas = [
            ("loja", self.carregar_lojas),
            ("fornecedor", self.carregar_fornecedores),
            ("produto", self.carregar_produtos),
            ("calendario", self.carregar_calendario),
            ("produto_preco_historico", self.carregar_preco_historico),
            ("promocao", self.carregar_promocoes),
            ("venda", self.carregar_vendas),
            ("item_venda", self.carregar_itens),
            ("estoque_snapshot", self.carregar_estoque),
            ("movimentacao_estoque", self.carregar_movimentacoes),
            ("pedido_compra", self.carregar_pedidos),
        ]

        for nome, funcao in etapas:
            t0 = time.perf_counter()
            saida = funcao()
            dt = time.perf_counter() - t0

            alvos = saida if isinstance(saida, list) else [saida]
            for r in alvos:
                r.segundos = round(dt / len(alvos), 2)
            if isinstance(saida, list) and len(saida) > 1:
                # Para funcoes que carregam 2 tabelas, o tempo medido
                # cobre as duas. Marca as duas com o mesmo valor e
                # deixa explicito no relatorio.
                for r in alvos:
                    r.segundos = round(dt, 2)

        t0 = time.perf_counter()
        self.calcular_metricas()
        dt_metricas = round(time.perf_counter() - t0, 2)
        if self.resultados:
            self.resultados[-1].segundos += dt_metricas

        return self.resultados
