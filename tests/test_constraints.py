"""
Validator de constraints do Giro.

Por que nao usar so psql com \\echo?
  Porque o objetivo e EVIDENCIA, nao leitura visual. Este script:
    - executa cada caso em sua propria transacao (isolamento real);
    - afirma o SQLSTATE esperado, nao apenas "deu erro";
    - falha com exit code != 0 se um caso que devia falhar passar;
    - gera um relatorio JSON que o relatorio final cita como evidencia.

Uso:
    python tests/test_constraints.py            # roda e imprime
    python tests/test_constraints.py --json     # saida JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import errors as pgerr

# SQLSTATEs que contam como "rejeicao correta" para constraint
# 23514 check_violation | 23505 unique_violation | 23503 fk_violation
# 23502 not_null_violation | 23P01 exclusion_violation
# 22001 string_data_right_truncation | 22P02 invalid_text_representation
SQLSTATE_ESPERADOS = {"23514", "23505", "23503", "23502", "23P01", "22001", "22P02"}


@dataclass
class Caso:
    codigo: str
    titulo: str
    setup: list[str] = field(default_factory=list)
    alvo: str = ""
    deve_falhar: bool = True
    nota: str = ""
    # Quando definido, o alvo NAO deve falhar: deve devolver exatamente
    # este valor. Permite testar policies (RLS) e checagens que retornam
    # um numero em vez de levantar excecao - sem isso, um caso como o C23
    # passaria mesmo se o RLS estivesse desligado.
    valor_esperado: Any = None


# ---------------------------------------------------------------------
# Casos de teste. Cada `setup` roda dentro da MESMA transacao do `alvo`,
# e a transacao e revertida ao final. Isso permite montar o cenario
# (loja, produto) sem sujar a base.
# ---------------------------------------------------------------------
CASOS: list[Caso] = [
    Caso("C01", "EAN-13 com digito verificador errado", alvo="""
        INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida)
        VALUES ('7891000053500','SKU-BAD1','EAN invalido',
                (SELECT categoria_id FROM prata.categoria WHERE codigo='DEP1'),'UN')""",
        nota="Digito verificador e a primeira barreira contra SKU fantasma."),

    Caso("C02", "Perecivel sem dias_validade", alvo="""
        INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida, e_perecivel)
        VALUES ('7891000100103','SKU-BAD2','Perecivel sem validade',
                (SELECT categoria_id FROM prata.categoria WHERE codigo='DEP1'),'UN',TRUE)""",
        nota="Perecivel sem validade impede o alerta de vencimento."),

    Caso("C03", "Nao-perecivel COM dias_validade", alvo="""
        INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida, e_perecivel, dias_validade)
        VALUES ('7891000100103','SKU-BAD3','Nao perecivel com validade',
                (SELECT categoria_id FROM prata.categoria WHERE codigo='DEP1'),'UN',FALSE,10)"""),

    Caso("C04", "EAN duplicado", alvo="""
        INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida)
        VALUES ('7891000053508','SKU-BAD4','EAN duplicado',
                (SELECT categoria_id FROM prata.categoria WHERE codigo='DEP1'),'UN')"""),

    Caso("C05", "Unidade de medida invalida", alvo="""
        INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida)
        VALUES ('7891000100103','SKU-BAD5','Unidade invalida',
                (SELECT categoria_id FROM prata.categoria WHERE codigo='DEP1'),'XYZ')"""),

    Caso("C06", "UF inexistente (XX)", alvo="""
        INSERT INTO prata.loja (codigo,nome,cidade,uf,data_abertura)
        VALUES ('BADUF','Loja UF ruim','Santos','XX','2020-01-01')""",
        nota="Regex '^[A-Z]{2}$' aceitava XX. So lista fechada garante o dominio."),

    Caso("C07", "CNPJ com mascara", alvo="""
        INSERT INTO prata.fornecedor (cnpj, razao_social)
        VALUES ('12.345.678/0001-90','Fornecedor com mascara')"""),

    Caso("C08", "Quantidade negativa no estoque", alvo="""
        INSERT INTO prata.estoque_snapshot (loja_id,produto_id,data_ref,qtd_inicio,qtd_fim)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                (SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                '2025-01-01',-5,0)"""),

    Caso("C09", "Equacao de estoque que nao fecha", alvo="""
        INSERT INTO prata.estoque_snapshot
            (loja_id,produto_id,data_ref,qtd_inicio,qtd_entradas,qtd_saidas,qtd_ajustes,qtd_fim)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                (SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                '2025-01-02',10,0,0,0,7)""",
        nota="inicio+entradas+saidas+ajustes deve ser igual a fim."),

    Caso("C10", "Cupom com total incoerente", alvo="""
        INSERT INTO prata.venda
            (loja_id,data_venda,hora_venda,numero_cupom,valor_bruto,valor_desconto,valor_liquido,qtd_itens)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                '2025-01-01','10:00','000001',100.00,5.00,90.00,2)""",
        nota="100-5=95, nao 90."),

    Caso("C11", "Cupom duplicado com serie NULL", setup=[
        """INSERT INTO prata.venda
            (loja_id,data_venda,hora_venda,numero_cupom,valor_bruto,valor_desconto,valor_liquido,qtd_itens)
           VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                   '2025-01-06','10:00','DUPNULL',100.00,0,100.00,2)""" ], alvo="""
        INSERT INTO prata.venda
            (loja_id,data_venda,hora_venda,numero_cupom,valor_bruto,valor_desconto,valor_liquido,qtd_itens)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                '2025-01-06','11:00','DUPNULL',50.00,0,50.00,1)""",
        nota="BUG ENCONTRADO: UNIQUE padrao trata NULL como distinto. "
             "Corrigido com NULLS NOT DISTINCT."),

    Caso("C12", "Status CANCELADA sem data de cancelamento", alvo="""
        INSERT INTO prata.venda
            (loja_id,data_venda,hora_venda,numero_cupom,valor_bruto,valor_desconto,valor_liquido,qtd_itens,status)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                '2025-01-02','10:00','CP-CANC',100.00,0,100.00,2,'CANCELADA')"""),

    Caso("C13", "Item de venda com quantidade zero", setup=[
        """INSERT INTO prata.venda
            (loja_id,data_venda,hora_venda,numero_cupom,valor_bruto,valor_desconto,valor_liquido,qtd_itens)
           VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                   '2025-01-03','10:00','CP-QTD0',10.00,0,10.00,1)""" ], alvo="""
        INSERT INTO prata.item_venda (venda_id,data_venda,item_seq,produto_id,quantidade,preco_unitario,valor_total)
        VALUES ((SELECT venda_id FROM prata.venda WHERE numero_cupom='CP-QTD0' AND data_venda='2025-01-03'),
                '2025-01-03',1,
                (SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                0,10.00,0)"""),

    Caso("C14", "Duas faixas de preco abertas", setup=[
        """INSERT INTO prata.produto_preco_historico (produto_id,data_inicio,preco_custo,preco_venda)
           VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                   '2024-01-01',5.00,10.00)""" ], alvo="""
        INSERT INTO prata.produto_preco_historico (produto_id,data_inicio,preco_custo,preco_venda)
        VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                '2024-06-01',6.00,12.00)"""),

    Caso("C15", "Faixas de preco sobrepostas", setup=[
        """INSERT INTO prata.produto_preco_historico (produto_id,data_inicio,data_fim,preco_custo,preco_venda)
           VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                   '2024-01-01','2024-06-01',5.00,10.00)""" ], alvo="""
        INSERT INTO prata.produto_preco_historico (produto_id,data_inicio,data_fim,preco_custo,preco_venda)
        VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                '2024-03-01','2024-09-01',6.00,12.00)""",
        nota="EXCLUDE USING gist com daterange impede sobreposicao."),

    Caso("C16", "VENDA com quantidade positiva", alvo="""
        INSERT INTO prata.movimentacao_estoque (loja_id,produto_id,data_movimento,tipo,quantidade)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                (SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                '2025-01-01','VENDA',5)""",
        nota="Saida de estoque deve ter sinal negativo."),

    Caso("C17", "Dois fornecedores preferenciais", setup=[
        """INSERT INTO prata.fornecedor (cnpj,razao_social) VALUES ('11111111111111','Forn A')""",
        """INSERT INTO prata.fornecedor (cnpj,razao_social) VALUES ('22222222222222','Forn B')""",
        """INSERT INTO prata.produto_fornecedor
             (produto_id,fornecedor_id,custo_unitario,lead_time_dias,preferencial)
           VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                   (SELECT fornecedor_id FROM prata.fornecedor WHERE cnpj='11111111111111'),
                   5.00,7,TRUE)""" ], alvo="""
        INSERT INTO prata.produto_fornecedor
            (produto_id,fornecedor_id,custo_unitario,lead_time_dias,preferencial)
        VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                (SELECT fornecedor_id FROM prata.fornecedor WHERE cnpj='22222222222222'),
                5.50,5,TRUE)"""),

    Caso("C18", "horas_sem_estoque acima de 24", alvo="""
        INSERT INTO prata.estoque_snapshot
            (loja_id,produto_id,data_ref,qtd_inicio,qtd_fim,houve_ruptura,horas_sem_estoque)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                (SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                '2025-01-04',0,0,TRUE,30)"""),

    Caso("C19", "Pedido com previsao anterior ao pedido", setup=[
        """INSERT INTO prata.fornecedor (cnpj,razao_social) VALUES ('33333333333333','Forn C')"""
    ], alvo="""
        INSERT INTO prata.pedido_compra
            (loja_id,fornecedor_id,numero_pedido,data_pedido,data_previsao,status)
        VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                (SELECT fornecedor_id FROM prata.fornecedor WHERE cnpj='33333333333333'),
                'PED-ERR','2025-01-10','2025-01-05','ENVIADO')"""),

    Caso("C20", "Item de pedido entregue muito acima do pedido", setup=[
        """INSERT INTO prata.fornecedor (cnpj,razao_social) VALUES ('44444444444444','Forn D')""",
        """INSERT INTO prata.pedido_compra
             (loja_id,fornecedor_id,numero_pedido,data_pedido,data_previsao,status)
           VALUES ((SELECT loja_id FROM prata.loja WHERE codigo='TST'),
                   (SELECT fornecedor_id FROM prata.fornecedor WHERE cnpj='44444444444444'),
                   'PED-X','2025-01-10','2025-01-15','ENVIADO')""" ], alvo="""
        INSERT INTO prata.item_pedido
            (pedido_id,item_seq,produto_id,quantidade_pedida,quantidade_entregue,custo_unitario,valor_total)
        VALUES ((SELECT pedido_id FROM prata.pedido_compra WHERE numero_pedido='PED-X'),
                1,(SELECT produto_id FROM prata.produto WHERE sku_interno='ARROZ-5KG'),
                10,20,5.00,50.00)"""),

    Caso("C21", "Valor monetario negativo (dominio)", alvo="""
        SELECT (-1)::gov.dinheiro""",
        nota="Dominio gov.dinheiro nao aceita negativo. Cast dispara a checagem."),

    Caso("C22", "Percentual acima de 100", setup=[
        """INSERT INTO prata.promocao (codigo,descricao,tipo,data_inicio,data_fim,percentual_desconto)
           VALUES ('PRM-OK','ok','DESCONTO','2025-01-01','2025-01-31',10)""" ], alvo="""
        INSERT INTO prata.promocao (codigo,descricao,tipo,data_inicio,data_fim,percentual_desconto)
        VALUES ('PRM-BAD','bad','DESCONTO','2025-01-01','2025-01-31',150)"""),

    Caso("C23", "RLS: gerente de loja nao ve item de outra loja", deve_falhar=False,
         valor_esperado=0, alvo="""
        SET ROLE giro_bi;
        SET app.loja_id = '1';
        SELECT count(*) FROM prata.item_venda i
         JOIN prata.venda v ON v.venda_id = i.venda_id
                           AND v.data_venda = i.data_venda
         WHERE v.loja_id <> 1""",
        nota="Deve devolver 0. Era 4.159.608 antes da policy item_por_loja."),
]


def garantir_base(conn: psycopg.Connection) -> None:
    """Cria o cenario minimo usado por varios casos, uma unica vez.

    ATENCAO — por que isto NAO pode rodar em transacao commitada:
    a primeira versao chamava conn.commit() aqui, e o cenario de teste
    (loja 'TST', categoria 'DEP1', produto 'ARROZ-5KG') ficava
    permanentemente no banco de negocio. O teste de integridade I06
    passou a falhar porque encontrou o produto ARROZ-5KG sem
    fornecedor — um dado que so existia por causa do proprio teste.

    Aqui o cenario e criado com ON CONFLICT DO NOTHING e removido ao
    final de main(), na ordem inversa das FKs. Se o processo morrer no
    meio, a limpeza e idempotente e roda na proxima execucao.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO prata.loja (codigo,nome,cidade,uf,data_abertura)
            VALUES ('TST','Loja Teste','Santos','SP','2020-01-01')
            ON CONFLICT (codigo) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO prata.categoria (codigo,nome,nivel)
            VALUES ('DEP1','Departamento Teste',1)
            ON CONFLICT (codigo) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO prata.produto (ean,sku_interno,nome,categoria_id,unidade_medida,e_perecivel,dias_validade)
            VALUES ('7891000053508','ARROZ-5KG','Arroz 5kg',
                    (SELECT categoria_id FROM prata.categoria WHERE codigo='DEP1'),'UN',TRUE,180)
            ON CONFLICT (ean) DO NOTHING
        """)
    conn.commit()


def limpar_base(conn: psycopg.Connection) -> None:
    """Remove o cenario de teste. Idempotente.

    Ordem inversa das FKs: filhas primeiro. Sem isto, o banco de
    negocio acumula loja/produto de teste a cada execucao da suite.
    """
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM prata.item_venda i
             USING prata.venda v
             WHERE i.venda_id = v.venda_id
               AND i.data_venda = v.data_venda
               AND v.loja_id IN (SELECT loja_id FROM prata.loja WHERE codigo = 'TST')
        """)
        cur.execute("""
            DELETE FROM prata.venda
             WHERE loja_id IN (SELECT loja_id FROM prata.loja WHERE codigo = 'TST')
        """)
        for tabela in ("estoque_snapshot", "movimentacao_estoque"):
            cur.execute(f"""
                DELETE FROM prata.{tabela}
                 WHERE loja_id IN (SELECT loja_id FROM prata.loja WHERE codigo = 'TST')
                    OR produto_id IN (SELECT produto_id FROM prata.produto
                                       WHERE sku_interno = 'ARROZ-5KG')
            """)
        cur.execute("""
            DELETE FROM prata.produto_fornecedor
             WHERE produto_id IN (SELECT produto_id FROM prata.produto
                                   WHERE sku_interno = 'ARROZ-5KG')
        """)
        cur.execute("""
            DELETE FROM prata.produto_preco_historico
             WHERE produto_id IN (SELECT produto_id FROM prata.produto
                                   WHERE sku_interno = 'ARROZ-5KG')
        """)
        cur.execute("DELETE FROM prata.produto WHERE sku_interno = 'ARROZ-5KG'")
        cur.execute("DELETE FROM prata.loja WHERE codigo = 'TST'")
        cur.execute("""
            DELETE FROM prata.categoria
             WHERE codigo = 'DEP1'
               AND NOT EXISTS (SELECT 1 FROM prata.produto p
                                WHERE p.categoria_id = prata.categoria.categoria_id)
        """)
        cur.execute("""
            DELETE FROM prata.fornecedor
             WHERE cnpj IN ('11111111111111', '22222222222222',
                            '33333333333333', '44444444444444')
        """)
    conn.commit()


def executar_caso(conn: psycopg.Connection, caso: Caso) -> dict[str, Any]:
    """Roda um caso em transacao isolada e sempre reverte."""
    resultado: dict[str, Any] = {
        "codigo": caso.codigo,
        "titulo": caso.titulo,
        "deve_falhar": caso.deve_falhar,
        "nota": caso.nota,
    }
    try:
        with conn.transaction(force_rollback=True):
            with conn.cursor() as cur:
                for sql in caso.setup:
                    cur.execute(sql)
                cur.execute(caso.alvo)
                # Casos de policy (RLS) nao levantam excecao: devolvem uma
                # contagem. Sem ler o valor, o teste passaria com o RLS
                # desligado - seria um teste que nao testa.
                if caso.valor_esperado is not None and cur.description:
                    obtido = cur.fetchone()
                    obtido = obtido[0] if obtido else None
                    if obtido != caso.valor_esperado:
                        resultado |= {
                            "falhou": False,
                            "sqlstate": None,
                            "mensagem": None,
                            "observacao": (f"devolveu {obtido!r}, "
                                           f"esperado {caso.valor_esperado!r}"),
                            "ok": False,
                        }
                        return resultado
        # Se chegou aqui, o alvo foi aceito (transacao revertida).
        resultado |= {"falhou": False, "sqlstate": None, "mensagem": None}
    except pgerr.Error as exc:
        resultado |= {
            "falhou": True,
            "sqlstate": exc.sqlstate,
            "mensagem": str(exc).splitlines()[0][:200],
        }
    except Exception as exc:  # noqa: BLE001
        resultado |= {"falhou": True, "sqlstate": "XXXXX", "mensagem": str(exc)[:200]}

    ok = resultado["falhou"] if caso.deve_falhar else not resultado["falhou"]
    if resultado["falhou"] and resultado["sqlstate"] not in SQLSTATE_ESPERADOS:
        ok = False
        resultado["observacao"] = (
            f"falhou por motivo inesperado (sqlstate {resultado['sqlstate']}), "
            "nao por constraint"
        )
    resultado["ok"] = ok
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="saida JSON")
    ap.add_argument("--dsn", default=os.environ.get(
        "GIRO_DSN",
        "host=127.0.0.1 port=5433 dbname=giro user=postgres",
    ))
    args = ap.parse_args()

    resultados: list[dict[str, Any]] = []
    try:
        with psycopg.connect(args.dsn, autocommit=True) as conn:
            garantir_base(conn)
            try:
                for caso in CASOS:
                    resultados.append(executar_caso(conn, caso))
            finally:
                # Limpeza SEMPRE roda, inclusive se um caso levantar
                # excecao inesperada. Sem isto, o cenario de teste
                # vaza para o banco de negocio e quebra o I06.
                limpar_base(conn)
    except psycopg.OperationalError as exc:
        print(f"ERRO: nao foi possivel conectar ({exc})", file=sys.stderr)
        return 2

    total = len(resultados)
    aprovados = sum(1 for r in resultados if r["ok"])

    if args.json:
        print(json.dumps(
            {"total": total, "aprovados": aprovados,
             "taxa_pct": round(aprovados / total * 100, 1),
             "casos": resultados},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(f"{'CASO':<5} {'SITUACAO':<10} {'SQLSTATE':<9} TITULO")
        print("-" * 88)
        for r in resultados:
            situacao = "OK" if r["ok"] else "FALHOU"
            cor = "\033[92m" if r["ok"] else "\033[91m"
            print(f"{r['codigo']:<5} {cor}{situacao:<10}\033[0m "
                  f"{str(r['sqlstate'] or '-'):<9} {r['titulo']}")
            if not r["ok"]:
                print(f"      -> {r.get('observacao') or r['mensagem']}")
        print("-" * 88)
        print(f"{aprovados}/{total} casos aprovados ({aprovados/total*100:.0f}%)")
        pular = [r["codigo"] for r in resultados if not r["ok"]]
        if pular:
            print(f"Casos com problema: {', '.join(pular)}")

    return 0 if aprovados == total else 1


if __name__ == "__main__":
    sys.exit(main())
