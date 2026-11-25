"""
Giro - gerador do painel estatico.

POR QUE UM GERADOR E NAO UM APP SERVIDOR
----------------------------------------
O pitch roda num notebook emprestado, sem rede, com projetor. Um servidor a
mais e um ponto de falha a mais. Este script le o PostgreSQL e escreve UM
arquivo HTML que abre com duplo clique: sem servidor, sem CDN, sem internet.
As fontes vao embutidas em base64; os dados vao embutidos como JSON.

O QUE ELE GARANTE
-----------------
1. Todo numero na tela sai de uma consulta neste arquivo. Nada e digitado a mao.
2. Se o banco nao responder, ele falha alto e nao escreve um painel vazio.
3. O painel declara a propria data de referencia e que o dado e sintetico.
4. Nenhuma consulta usa CURRENT_DATE: o dataset termina em 2025-10-31 e o
   relogio da maquina nao e a verdade do dado.

USO
    python dashboard/gerar.py
    python dashboard/gerar.py --saida docs/painel.html
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

RAIZ = Path(__file__).resolve().parent.parent
AQUI = Path(__file__).resolve().parent
FONTES = AQUI / "fonts"

DSN = os.environ.get(
    "GIRO_DSN", "host=127.0.0.1 port=5433 dbname=giro user=postgres")

# z = 1,65 => 95% de nivel de servico. O mesmo valor da migration 011.
# O front recalcula a sugestao ao vivo quando o dono mexe no nivel de
# servico, entao a formula do SQL e a do JS tem que ser a mesma.
Z = 1.65


# =====================================================================
# Acesso a dados
# =====================================================================

def consultar(conn: psycopg.Connection, sql: str, params=None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def numero(v):
    """Converte Decimal e datas em algo serializavel."""
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


# ---------------------------------------------------------------------
# Rotulo humano para o departamento.
#
# A prata guarda a CHAVE ('FRIOS_E_LATICINIOS'), que e estavel e nao
# depende de encoding. A tela precisa do NOME. A conversao acontece
# aqui, na geracao, e nao no banco: o dado permanece normalizado e a
# apresentacao fica num unico lugar.
# ---------------------------------------------------------------------
NOMES_DEPARTAMENTO = {
    "MERCEARIA": "Mercearia",
    "BEBIDAS": "Bebidas",
    "HIGIENE": "Higiene",
    "LIMPEZA": "Limpeza",
    "FRIOS_E_LATICINIOS": "Frios e laticínios",
    "PADARIA": "Padaria",
    "HORTIFRUTI": "Hortifrúti",
    "ACOUGUE": "Açougue",
}


def rotulo_departamento(chave) -> str:
    """Converte a chave do banco em rotulo legivel.

    O fallback troca underscore por espaco e capitaliza, para que um
    departamento novo nao apareca cru na tela.
    """
    if not chave:
        return "—"
    k = str(chave)
    if k in NOMES_DEPARTAMENTO:
        return NOMES_DEPARTAMENTO[k]
    return k.replace("_", " ").title()


def limpar(linhas: list[dict]) -> list[dict]:
    return [{k: numero(v) for k, v in linha.items()} for linha in linhas]


# =====================================================================
# Coleta
# =====================================================================

def coletar(conn: psycopg.Connection) -> dict:
    """Cada bloco abaixo alimenta uma secao da tela.

    Convencao: os agregados vem em duas formas, `loja_id = 0` (todas as
    lojas) e uma linha por loja. O front filtra por `estado.loja` e cai
    na linha 0 quando o dono escolhe "todas". Assim o filtro e uma
    operacao de leitura, nao um recalculo de agregado.
    """

    # -----------------------------------------------------------------
    # Contexto
    # -----------------------------------------------------------------
    ref = consultar(conn, """
        SELECT max(data_venda) AS fim,
               min(data_venda) AS inicio,
               count(*)        AS linhas_venda,
               count(DISTINCT loja_id)    AS lojas,
               count(DISTINCT produto_id) AS skus,
               count(DISTINCT data_venda) AS dias
          FROM ouro.fato_vendas
    """)[0]

    lojas = consultar(conn, """
        SELECT loja_id, codigo, nome, cidade, uf, area_m2, porte
          FROM ouro.dim_loja WHERE ativa ORDER BY nome
    """)

    # -----------------------------------------------------------------
    # Bloco 1 - O PEDIDO
    #
    # Traz TODOS os SKUs (nao so os que precisam de compra): a
    # distribuicao de cobertura da secao de capital usa o sortimento
    # inteiro, e filtrar aqui faria o histograma mentir.
    #
    # sigma e custo vem como insumo cru para o front refazer a conta
    # quando o nivel de servico muda. `multiplo` e lido do cadastro em
    # vez de assumido como 1.
    # -----------------------------------------------------------------
    pedido = consultar(conn, """
        WITH sigma AS (
            SELECT loja_id, produto_id,
                   coalesce(stddev_samp(qtd_demanda), 0) AS sigma_dia
              FROM ouro.mv_demanda_diaria
             GROUP BY 1, 2
        ), info AS (
            SELECT pf.produto_id,
                   pf.lead_time_dias,
                   pf.multiplo_compra,
                   pf.custo_unitario,
                   f.razao_social
              FROM prata.produto_fornecedor pf
              JOIN ouro.dim_fornecedor f ON f.fornecedor_id = pf.fornecedor_id
             WHERE pf.preferencial
        ), ultimo AS (
            SELECT DISTINCT ON (loja_id, produto_id)
                   loja_id, produto_id, qtd_fim
              FROM ouro.fato_estoque_diario
             ORDER BY loja_id, produto_id, data_ref DESC
        ), previsao AS (
            -- Demanda do horizonte de lead time.
            --
            -- O painel NAO recalcula a formula: le `demanda_lead_time` da
            -- propria view. Recalcular foi a origem de uma divergencia de
            -- 726 dos 1.260 itens entre painel e banco, porque a formula
            -- vivia em dois lugares e cada um evoluiu por conta propria.
            --
            -- A demanda diaria exibida e a media do horizonte, e o
            -- `demanda_lead_time` e o que a conta do ponto de pedido usa.
            SELECT loja_id, produto_id,
                   demanda_lead_time / nullif(lead_time_dias, 0) AS demanda_dia,
                   demanda_lead_time,
                   demanda_pico_dia, dia_pico_semana,
                   demanda_vale_dia, dia_vale_semana
              FROM ouro.mv_sugestao_compra
        )
        SELECT s.loja_id,
               s.produto_id,
               s.produto                                   AS nome,
               s.departamento                              AS dep,
               s.e_perecivel,
               -- Unidade de medida: sem isto, "Comprar 405" e
               -- ambiguo (405 unidades? 405 kg? 405 caixas?). Para um
               -- pedido real, a unidade muda o volume em 12x.
               coalesce(dp.unidade_medida, 'UN')           AS unidade,
               u.qtd_fim                                   AS estoque,
               p.demanda_dia                               AS demanda,
               p.demanda_lead_time                         AS demanda_lt,
               p.demanda_pico_dia, p.dia_pico_semana,
               p.demanda_vale_dia, p.dia_vale_semana,
               i.lead_time_dias                            AS lead,
               coalesce(sg.sigma_dia, 0)                   AS sigma,
               coalesce(i.multiplo_compra, 1)              AS multiplo,
               coalesce(i.custo_unitario, 0)               AS custo,
               i.razao_social                              AS fornecedor,
               s.situacao,
               s.pior_dimensao_pct,
               s.score_qualidade_loja
          FROM ouro.mv_sugestao_compra s
          JOIN ouro.dim_produto dp ON dp.produto_id = s.produto_id
          JOIN ultimo  u  ON u.loja_id = s.loja_id AND u.produto_id = s.produto_id
          JOIN previsao p ON p.loja_id = s.loja_id AND p.produto_id = s.produto_id
          JOIN info    i  ON i.produto_id = s.produto_id
          LEFT JOIN sigma sg ON sg.loja_id = s.loja_id AND sg.produto_id = s.produto_id
         ORDER BY s.loja_id, i.razao_social, s.produto
    """)

    # A receita que o pedido vai consumir, para a lede poder comparar
    # o valor da compra com a receita do mes.
    receita_mes = consultar(conn, """
        WITH janela AS (
            SELECT max(data_venda) - interval '12 months' AS inicio,
                   max(data_venda)                        AS fim
              FROM ouro.fato_vendas
        )
        SELECT coalesce(l.loja_id, 0) AS loja_id,
               round(sum(f.valor_liquido)
                     / nullif(count(DISTINCT f.data_venda), 0) * 30, 2)
                      AS receita_mes
          FROM ouro.fato_vendas f
          LEFT JOIN ouro.dim_loja l ON l.loja_id = f.loja_id
          CROSS JOIN janela j
         WHERE f.data_venda > j.inicio AND f.data_venda <= j.fim
         GROUP BY GROUPING SETS ((l.loja_id), ())
    """)

    # -----------------------------------------------------------------
    # Bloco 2 - A PERDA POR RUPTURA
    # -----------------------------------------------------------------
    perda = consultar(conn, """
        WITH janela AS (
            SELECT max(data_venda) - interval '12 months' AS inicio,
                   max(data_venda)                        AS fim
              FROM ouro.fato_vendas
        ), base AS (
            SELECT coalesce(r.loja_id, 0) AS loja_id,
                   count(*)                            AS eventos,
                   coalesce(sum(r.demanda_perdida_un), 0)      AS unidades,
                   coalesce(sum(r.receita_perdida_estimada), 0) AS receita,
                   count(DISTINCT r.produto_id)        AS skus
              FROM ouro.mv_rupturas r
              CROSS JOIN janela j
             WHERE r.data_venda > j.inicio AND r.data_venda <= j.fim
             GROUP BY GROUPING SETS ((r.loja_id), ())
        )
        SELECT loja_id, eventos,
               round(unidades)     AS unidades,
               round(receita, 2)   AS receita,
               skus
          FROM base ORDER BY loja_id
    """)

    perda_mes = consultar(conn, """
        SELECT coalesce(loja_id, 0) AS loja_id, ano_mes,
               count(*)                        AS eventos,
               round(sum(receita_perdida_estimada), 2) AS receita
          FROM ouro.mv_rupturas
         GROUP BY GROUPING SETS ((loja_id, ano_mes), (ano_mes))
         ORDER BY loja_id, ano_mes
    """)

    perda_sku = consultar(conn, """
        WITH janela AS (
            SELECT max(data_venda) - interval '12 months' AS inicio,
                   max(data_venda)                        AS fim
              FROM ouro.fato_vendas
        )
        SELECT coalesce(r.loja_id, 0) AS loja_id,
               r.produto,
               r.departamento,
               count(*)                                  AS eventos,
               round(sum(r.demanda_perdida_un))          AS unidades,
               round(sum(r.receita_perdida_estimada), 2) AS receita
          FROM ouro.mv_rupturas r, janela j
         WHERE r.data_venda > j.inicio AND r.data_venda <= j.fim
         GROUP BY GROUPING SETS ((r.loja_id, r.produto, r.departamento),
                                 (r.produto, r.departamento))
         ORDER BY loja_id, receita DESC
    """)

    reconstrucao = consultar(conn, """
        SELECT coalesce(loja_id, 0) AS loja_id, fonte_demanda,
               count(*) AS linhas,
               round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY coalesce(loja_id, 0)), 2) AS pct
          FROM ouro.mv_demanda_diaria
         GROUP BY GROUPING SETS ((loja_id, fonte_demanda), (fonte_demanda))
         ORDER BY loja_id, linhas DESC
    """)

    ruptura = consultar(conn, """
        SELECT coalesce(loja_id, 0) AS loja_id,
               count(*)                              AS sku_dia,
               count(*) FILTER (WHERE houve_ruptura) AS com_ruptura,
               round(100.0 * count(*) FILTER (WHERE houve_ruptura)
                     / count(*), 2)                  AS taxa_pct
          FROM ouro.fato_estoque_diario
         GROUP BY GROUPING SETS ((loja_id), ())
         ORDER BY loja_id
    """)

    # -----------------------------------------------------------------
    # Bloco 3 - O CAPITAL
    # -----------------------------------------------------------------
    estoque_valor = consultar(conn, """
        SELECT coalesce(loja_id, 0) AS loja_id,
               round(sum(valor_estoque) / count(DISTINCT data_ref), 2)
                   AS valor_medio_dia,
               count(DISTINCT data_ref) AS dias
          FROM ouro.fato_estoque_diario
         GROUP BY GROUPING SETS ((loja_id), ())
         ORDER BY loja_id
    """)

    vencimento = consultar(conn, """
        WITH atual AS (
            SELECT DISTINCT ON (loja_id, produto_id)
                   loja_id, produto_id, qtd_fim, valor_estoque
              FROM ouro.fato_estoque_diario
             ORDER BY loja_id, produto_id, data_ref DESC
        ), demanda AS (
            SELECT loja_id, produto_id, avg(qtd_demanda) AS dia
              FROM ouro.mv_demanda_diaria GROUP BY 1, 2
        )
        SELECT coalesce(a.loja_id, 0) AS loja_id,
               p.departamento,
               count(*)                        AS skus,
               round(sum(a.valor_estoque), 2)  AS valor
          FROM atual a
          JOIN ouro.dim_produto p USING (produto_id)
          JOIN demanda d USING (loja_id, produto_id)
         WHERE p.e_perecivel AND p.ativo AND a.qtd_fim > 0
           AND a.qtd_fim / nullif(d.dia, 0) > coalesce(p.dias_validade, 999) * 0.7
         GROUP BY GROUPING SETS ((a.loja_id, p.departamento), (p.departamento))
         ORDER BY loja_id, valor DESC
    """)

    # Receita e margem por departamento nos 12 meses de dado.
    departamentos = consultar(conn, """
        WITH janela AS (
            SELECT max(data_venda) - interval '12 months' AS inicio,
                   max(data_venda)                        AS fim
              FROM ouro.fato_vendas
        )
        SELECT coalesce(f.loja_id, 0) AS loja_id,
               p.departamento,
               count(DISTINCT f.produto_id)                AS skus,
               round(sum(f.valor_liquido), 2)              AS receita,
               round(sum(f.margem_liquida), 2)             AS margem
          FROM ouro.fato_vendas f
          JOIN ouro.dim_produto p USING (produto_id)
          CROSS JOIN janela j
         WHERE f.data_venda > j.inicio AND f.data_venda <= j.fim
         GROUP BY GROUPING SETS ((f.loja_id, p.departamento), (p.departamento))
         ORDER BY loja_id, receita DESC
    """)

    # Curva ABC sobre o sortimento inteiro (nao so o que falta).
    abc = consultar(conn, """
        WITH janela AS (
            SELECT max(data_venda) - interval '12 months' AS inicio,
                   max(data_venda)                        AS fim
              FROM ouro.fato_vendas
        ), receita AS (
            SELECT f.loja_id, f.produto_id, sum(f.valor_liquido) AS rec
              FROM ouro.fato_vendas f CROSS JOIN janela j
             WHERE f.data_venda > j.inicio AND f.data_venda <= j.fim
             GROUP BY 1, 2
        ), acumulado AS (
            SELECT loja_id, produto_id, rec,
                   sum(rec) OVER (PARTITION BY loja_id ORDER BY rec DESC
                                  ROWS UNBOUNDED PRECEDING)
                     / sum(rec) OVER (PARTITION BY loja_id) AS pct
              FROM receita
        ), classe AS (
            SELECT loja_id, CASE WHEN pct <= 0.80 THEN 'A'
                                 WHEN pct <= 0.95 THEN 'B' ELSE 'C' END AS classe,
                   rec
              FROM acumulado
        )
        SELECT coalesce(loja_id, 0) AS loja_id, classe,
               count(*)               AS skus,
               round(sum(rec), 2)     AS receita
          FROM classe
         GROUP BY GROUPING SETS ((loja_id, classe), (classe))
         ORDER BY loja_id, classe
    """)

    # -----------------------------------------------------------------
    # Bloco 4 - A CONFIANCA
    # -----------------------------------------------------------------
    selo = consultar(conn, """
        SELECT loja_id, loja, dimensoes_medidas, score_medio_pct,
               pior_dimensao_pct, selo
          FROM ouro.mv_qualidade_loja ORDER BY score_medio_pct DESC
    """)

    dimensoes = consultar(conn, """
        SELECT l.nome AS loja, mq.dimensao,
               round(avg(mq.score_pct), 2) AS score
          FROM gov.metrica_qualidade mq
          JOIN ouro.dim_loja l USING (loja_id)
         GROUP BY 1, 2 ORDER BY 1, 2
    """)

    lotes = consultar(conn, """
        SELECT origem, count(*) AS lotes,
               sum(linhas_lidas)      AS lidas,
               sum(linhas_aceitas)    AS aceitas,
               sum(linhas_rejeitadas) AS rejeitadas,
               max(finalizado_em)     AS ultima
          FROM gov.lote_carga
         WHERE status = 'CONCLUIDO'
         GROUP BY origem ORDER BY origem
    """)

    regras = consultar(conn, """
        SELECT count(*) AS total, count(*) FILTER (WHERE ativa) AS ativas
          FROM gov.regra_qualidade
    """)[0]

    # Uma linha por regra: a dimensao vem do catalogo do banco, nao do
    # arquivo de metricas (que traz tabela e classe, nao dimensao).
    catalogo_regras = consultar(conn, """
        SELECT codigo, dimensao, descricao, severidade, acao
          FROM gov.regra_qualidade
         ORDER BY codigo
    """)

    # Metricas de deteccao contra o gabarito injetado. O arquivo e gerado
    # pelo pipeline; o painel apenas le, nunca recalcula indicador.
    metricas = None
    caminho_metricas = RAIZ / "docs" / "evidencias" / "metricas_qualidade.json"
    if caminho_metricas.exists():
        metricas = json.loads(caminho_metricas.read_text(encoding="utf-8"))
        if metricas:
            dimensao = {r["codigo"]: r for r in catalogo_regras}
            for r in metricas.get("por_regra", []):
                meta = dimensao.get(r["regra"], {})
                r["dimensao"] = meta.get("dimensao") or "-"
                r["severidade"] = meta.get("severidade") or "-"
                r["alvo"] = r.get("tabela") or "-"

    # ------------------------------------------------------------------
    # Rotulo humano de departamento, aplicado uma vez sobre cada lista
    # que carrega a chave crua. A chave fica normalizada no banco; a
    # traducao acontece na fronteira de apresentacao.
    # ------------------------------------------------------------------
    def traduzir(linhas: list[dict]) -> list[dict]:
        for linha in linhas:
            if "departamento" in linha:
                linha["departamento"] = rotulo_departamento(linha["departamento"])
            if "dep" in linha:
                linha["dep"] = rotulo_departamento(linha["dep"])
        return linhas

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "referencia": limpar([ref])[0],
        "lojas": limpar(lojas),
        "pedido": traduzir(limpar(pedido)),
        "receita_mes": limpar(receita_mes),
        "perda": limpar(perda),
        "perda_mes": limpar(perda_mes),
        "perda_sku": traduzir(limpar(perda_sku)),
        "reconstrucao": limpar(reconstrucao),
        "ruptura": limpar(ruptura),
        "estoque_valor": limpar(estoque_valor),
        "vencimento": traduzir(limpar(vencimento)),
        "departamentos": traduzir(limpar(departamentos)),
        "abc": limpar(abc),
        "selo": limpar(selo),
        "dimensoes": limpar(dimensoes),
        "lotes": limpar(lotes),
        "regras": limpar([regras])[0],
        "catalogo_regras": limpar(catalogo_regras),
        "metricas": metricas,
        "z": Z,
    }


# =====================================================================
# Fontes embutidas
# =====================================================================

def fonte_base64(nome: str) -> str:
    caminho = FONTES / nome
    if not caminho.exists():
        raise SystemExit(
            f"Fonte ausente: {caminho}\n"
            "O painel precisa das fontes para rodar offline.")
    return base64.b64encode(caminho.read_bytes()).decode("ascii")


def bloco_fontes() -> str:
    """Fontes embutidas em base64.

    Duas faces, nao tres. A Piazzolla italica estava embutida (43 KB em
    base64) e nunca renderizava: medido no navegador, os unicos tres
    elementos com font-style:italic sao <i> vazios de legenda, e herdam
    Archivo. O documento nao tem uma palavra em italico na serifa.

    Embutir fonte nao usada custa download, memoria e uma afirmacao
    falsa ("tres fontes embutidas") num projeto que se vende por
    rastreabilidade.
    """
    return f"""
@font-face {{
  font-family: 'Piazzolla';
  font-style: normal;
  font-weight: 400 700;
  font-display: block;
  src: url(data:font/woff2;base64,{fonte_base64("piazzolla-latin.woff2")}) format('woff2');
}}
@font-face {{
  font-family: 'Archivo';
  font-style: normal;
  font-weight: 400 700;
  font-display: block;
  src: url(data:font/woff2;base64,{fonte_base64("archivo-latin.woff2")}) format('woff2');
}}
"""


# =====================================================================
# Escrita
# =====================================================================

def escrever(dados: dict, saida: Path) -> None:
    molde = (AQUI / "molde.html").read_text(encoding="utf-8")
    html = molde.replace("/*__FONTES__*/", bloco_fontes())

    payload = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    # "</" dentro de <script> fecharia a tag, mesmo em string JSON.
    payload = payload.replace("</", "<\\/")
    html = html.replace("/*__DADOS__*/null", payload)

    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(html, encoding="utf-8")

    tamanho = saida.stat().st_size / 1024
    print(f"OK  {saida}  ({tamanho:,.0f} KB)")
    print(f"    referencia do dado: {dados['referencia']['fim']}")
    print(f"    linhas de venda:    {dados['referencia']['linhas_venda']:,}")


def main() -> int:
    p = argparse.ArgumentParser(description="Gera o painel estatico do Giro.")
    p.add_argument("--saida", default=str(RAIZ / "docs" / "painel.html"),
                   help="arquivo HTML de saida")
    args = p.parse_args()

    try:
        with psycopg.connect(DSN) as conn:
            dados = coletar(conn)
    except psycopg.OperationalError as exc:
        print("ERRO: nao consegui conectar ao banco.", file=sys.stderr)
        print(f"  DSN: {DSN}", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        print("\nRode:  .\\scripts\\pg.ps1 start", file=sys.stderr)
        return 1

    escrever(dados, Path(args.saida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
