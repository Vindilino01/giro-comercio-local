"""
Testes de integridade sobre os dados CARREGADOS.

Diferenca para tests/test_constraints.py:
  - test_constraints.py prova que o BANCO REJEITA dado invalido (schema).
  - test_integridade.py prova que o DADO CARREGADO e coerente (conteudo).

Os dois sao necessarios. Um schema perfeito nao impede que o ETL grave
dado errado; e um ETL correto nao dispensa constraints no banco.

Uso:
    python tests/test_integridade.py
    python tests/test_integridade.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg


@dataclass
class Teste:
    # `__test__ = False` diz ao pytest para NAO coletar esta classe. Sem
    # isto ele tenta instanciar `Teste` como classe de teste, falha porque
    # a dataclass tem __init__ com campos obrigatorios, e emite
    # PytestCollectionWarning em toda execucao.
    __test__ = False

    codigo: str
    titulo: str
    sql: str
    esperado: str          # 'zero' (nenhuma violacao) ou 'nao_vazio'
    descricao_esperado: str = ""


TESTES: list[Teste] = [
    Teste("I01", "Toda venda tem ao menos um item",
          """SELECT count(*) FROM prata.venda v
              WHERE NOT EXISTS (SELECT 1 FROM prata.item_venda i
                                 WHERE i.venda_id = v.venda_id
                                   AND i.data_venda = v.data_venda)""",
          "zero",
          "Venda sem item indica carga parcial do cupom."),

    Teste("I02", "Soma dos itens confere com o total do cupom",
          """SELECT count(*) FROM (
                 SELECT v.venda_id, v.data_venda,
                        v.valor_liquido,
                        sum(i.valor_total) AS soma_itens
                   FROM prata.venda v
                   JOIN prata.item_venda i
                     ON i.venda_id = v.venda_id
                    AND i.data_venda = v.data_venda
                  WHERE v.status = 'CONCLUIDA'
                  GROUP BY v.venda_id, v.data_venda, v.valor_liquido
                 HAVING abs(v.valor_liquido - sum(i.valor_total)) > 0.02
             ) t""",
          "zero",
          "Cupom com total diferente da soma dos itens e corrupcao de receita."),

    Teste("I03", "Equacao de estoque fecha em todos os snapshots",
          """SELECT count(*) FROM prata.estoque_snapshot
              WHERE round(qtd_fim, 3) <> round(
                    qtd_inicio + qtd_entradas - qtd_saidas + qtd_ajustes, 3)""",
          "zero",
          "Se a equacao nao fecha, o estoque e reconstruivel de forma errada."),

    Teste("I04", "Nenhum estoque negativo",
          """SELECT count(*) FROM prata.estoque_snapshot
              WHERE qtd_fim < 0 OR qtd_inicio < 0 OR qtd_contada < 0""",
          "zero"),

    Teste("I05", "Nenhum item vendido sem produto existente",
          """SELECT count(*) FROM prata.item_venda i
              LEFT JOIN prata.produto p ON p.produto_id = i.produto_id
              WHERE p.produto_id IS NULL""",
          "zero",
          "FK deveria impedir, mas o teste confirma na pratica."),

    Teste("I06", "Todo produto tem ao menos um fornecedor",
          """SELECT count(*) FROM prata.produto p
              WHERE p.ativo
                AND NOT EXISTS (SELECT 1 FROM prata.produto_fornecedor pf
                                 WHERE pf.produto_id = p.produto_id)""",
          "zero",
          "Sem fornecedor, a sugestao de compra nao tem lead time."),

    Teste("I07", "Cada produto tem no maximo um fornecedor preferencial",
          """SELECT count(*) FROM (
                 SELECT produto_id FROM prata.produto_fornecedor
                  WHERE preferencial
                  GROUP BY produto_id HAVING count(*) > 1
             ) t""",
          "zero"),

    Teste("I08", "Cada produto tem no maximo uma faixa de preco aberta",
          """SELECT count(*) FROM (
                 SELECT produto_id FROM prata.produto_preco_historico
                  WHERE data_fim IS NULL
                  GROUP BY produto_id HAVING count(*) > 1
             ) t""",
          "zero"),

    Teste("I09", "Nenhuma faixa de preco se sobrepoe",
          """SELECT count(*) FROM prata.produto_preco_historico a
              JOIN prata.produto_preco_historico b
                ON b.produto_id = a.produto_id
               AND b.data_inicio > a.data_inicio
               AND (a.data_fim IS NULL OR b.data_inicio < a.data_fim)""",
          "zero",
          "Sobreposicao tornaria o preco ambíguo em uma data."),

    Teste("I10", "Nenhum cupom duplicado (incluindo serie NULL)",
          """SELECT count(*) FROM (
                 SELECT loja_id, data_venda, serie_cupom, numero_cupom
                   FROM prata.venda
                  GROUP BY 1, 2, 3, 4 HAVING count(*) > 1
             ) t""",
          "zero",
          "Este e o bug C11: UNIQUE padrao nao pega NULL duplicado."),

    Teste("I11", "Toda venda tem loja existente",
          """SELECT count(*) FROM prata.venda v
              LEFT JOIN prata.loja l ON l.loja_id = v.loja_id
              WHERE l.loja_id IS NULL""",
          "zero"),

    Teste("I12", "Datas de venda estao no intervalo do calendario",
          """SELECT count(*) FROM prata.venda v
              LEFT JOIN prata.calendario c ON c.data = v.data_venda
              WHERE c.data IS NULL""",
          "zero",
          "Venda em data sem calendario quebra a sazonalidade."),

    Teste("I13", "Nenhum EAN invalido no cadastro",
          """SELECT count(*) FROM prata.produto
              WHERE NOT gov.ean13_valido(ean)""",
          "zero"),

    Teste("I14", "Todos os itens de pedido tem pedido correspondente",
          """SELECT count(*) FROM prata.item_pedido ip
              LEFT JOIN prata.pedido_compra pc ON pc.pedido_id = ip.pedido_id
              WHERE pc.pedido_id IS NULL""",
          "zero"),

    Teste("I15", "Soma dos itens de pedido confere com o total",
          """SELECT count(*) FROM (
                 SELECT pc.pedido_id,
                        pc.valor_total,
                        sum(ip.valor_total) FILTER (
                            WHERE pc.status IN ('ENVIADO','CONFIRMADO','CANCELADO')
                        ) AS soma_pedida,
                        sum(ip.valor_total * (ip.quantidade_entregue
                                              / nullif(ip.quantidade_pedida, 0)))
                            FILTER (WHERE pc.status IN ('ENTREGUE','PARCIAL')
                                    AND ip.quantidade_entregue > 0) AS soma_entregue
                   FROM prata.pedido_compra pc
                   JOIN prata.item_pedido ip ON ip.pedido_id = pc.pedido_id
                  GROUP BY pc.pedido_id, pc.valor_total, pc.status
                 HAVING (pc.status IN ('ENVIADO','CONFIRMADO','CANCELADO')
                         AND abs(pc.valor_total - coalesce(sum(ip.valor_total), 0)) > 0.02)
                     OR (pc.status IN ('ENTREGUE','PARCIAL')
                         AND abs(pc.valor_total - coalesce(sum(ip.valor_total
                                  * (ip.quantidade_entregue
                                     / nullif(ip.quantidade_pedida, 0))), 0)) > 0.02)
             ) t""",
          "zero",
          "Entregue: total = soma(itens x fração entregue). Pendente: total = soma(itens)."),

    Teste("I16", "Fato de vendas nao inclui cupons cancelados",
          """SELECT count(*) FROM ouro.fato_vendas f
              JOIN prata.venda v ON v.venda_id = f.venda_id
                                AND v.data_venda = f.data_venda
              WHERE v.status <> 'CONCLUIDA'""",
          "zero",
          "Cancelada nao e receita."),

    Teste("I17", "Toda linha do fato tem dimensao correspondente",
          """SELECT
                 (SELECT count(*) FROM ouro.fato_vendas f
                   LEFT JOIN ouro.dim_produto p ON p.produto_id = f.produto_id
                   WHERE p.produto_id IS NULL)
               + (SELECT count(*) FROM ouro.fato_vendas f
                   LEFT JOIN ouro.dim_tempo t ON t.data = f.data_venda
                   WHERE t.data IS NULL)
               + (SELECT count(*) FROM ouro.fato_vendas f
                   LEFT JOIN ouro.dim_loja l ON l.loja_id = f.loja_id
                   WHERE l.loja_id IS NULL)""",
          "zero",
          "Star schema exige integridade referencial com as dimensoes."),

    Teste("I18", "A demanda reconstruida nunca e menor que a vendida",
          """SELECT count(*) FROM ouro.mv_demanda_diaria
              WHERE qtd_demanda < qtd_vendida - 0.001""",
          "zero",
          "Reconstruir demanda para baixo nao faz sentido."),

    Teste("I19", "A previsao existe para todos os SKUs ativos por loja",
          """SELECT count(*) FROM (
                 SELECT l.loja_id, p.produto_id
                   FROM prata.loja l CROSS JOIN prata.produto p
                  WHERE l.ativa AND p.ativo
             ) universo
             WHERE NOT EXISTS (
                 SELECT 1 FROM ouro.mv_previsao_demanda pv
                  WHERE pv.loja_id = universo.loja_id
                    AND pv.produto_id = universo.produto_id)""",
          "zero",
          "SKU sem previsao nao recebe sugestao de compra."),

    Teste("I20", "Sugestao de compra so existe para SKU com previsao",
          """SELECT count(*) FROM ouro.mv_sugestao_compra s
              WHERE NOT EXISTS (
                  SELECT 1 FROM ouro.mv_previsao_demanda pv
                   WHERE pv.loja_id = s.loja_id
                     AND pv.produto_id = s.produto_id)""",
          "zero"),

    Teste("I21", "Nenhum registro em quarentena sem motivo",
          """SELECT count(*) FROM gov.quarentena
              WHERE motivo IS NULL OR motivo = ''""",
          "zero",
          "Quarentena sem motivo nao e auditavel."),

    Teste("I22", "Soma aceitas + rejeitadas = lidas em todo lote",
          """SELECT count(*) FROM gov.lote_carga
              WHERE finalizado_em IS NOT NULL
                AND linhas_aceitas + linhas_rejeitadas <> linhas_lidas""",
          "zero",
          "Se a contabilidade do lote nao fecha, a auditoria e invalida."),

    Teste("I23", "Valores monetarios nunca sao negativos",
          """SELECT count(*) FROM prata.item_venda
              WHERE valor_total < 0 OR preco_unitario <= 0
                 OR valor_desconto < 0""",
          "zero"),

    Teste("I24", "Quantidades de venda sao sempre positivas",
          """SELECT count(*) FROM prata.item_venda WHERE quantidade <= 0""",
          "zero"),

    Teste("I25", "O volume carregado e compativel com o esperado",
          """SELECT CASE WHEN count(*) < 1000 THEN 1 ELSE 0 END
               FROM prata.item_venda""",
          "zero",
          "Base vazia ou quase vazia indica falha silenciosa na carga."),
]


def executar(conn: psycopg.Connection) -> list[dict]:
    resultados = []
    for t in TESTES:
        try:
            with conn.cursor() as cur:
                cur.execute(t.sql)
                n = cur.fetchone()[0]
            conn.rollback()
            ok = (n == 0) if t.esperado == "zero" else (n > 0)
            resultados.append({
                "codigo": t.codigo, "titulo": t.titulo,
                "valor": n, "ok": ok,
                "descricao": t.descricao_esperado,
            })
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            resultados.append({
                "codigo": t.codigo, "titulo": t.titulo,
                "valor": None, "ok": False,
                "erro": str(exc).splitlines()[0][:200],
            })
    return resultados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get(
        "GIRO_DSN", "host=127.0.0.1 port=5433 dbname=giro user=postgres"))
    args = ap.parse_args()

    try:
        with psycopg.connect(args.dsn) as conn:
            resultados = executar(conn)
    except psycopg.OperationalError as exc:
        print(f"ERRO: nao foi possivel conectar ({exc})", file=sys.stderr)
        return 2

    aprovados = sum(1 for r in resultados if r["ok"])
    total = len(resultados)

    if args.json:
        print(json.dumps({
            "total": total, "aprovados": aprovados,
            "taxa_pct": round(aprovados / total * 100, 1),
            "testes": resultados,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"{'COD':<5} {'SITUACAO':<10} {'VALOR':>10}  TITULO")
        print("-" * 84)
        for r in resultados:
            situacao = "OK" if r["ok"] else "FALHOU"
            cor = "\033[92m" if r["ok"] else "\033[91m"
            valor = "erro" if r["valor"] is None else f"{r['valor']:,}"
            print(f"{r['codigo']:<5} {cor}{situacao:<10}\033[0m {valor:>10}  {r['titulo']}")
            if not r["ok"] and r.get("descricao"):
                print(f"      -> {r['descricao']}")
            if r.get("erro"):
                print(f"      -> {r['erro']}")
        print("-" * 84)
        print(f"{aprovados}/{total} testes aprovados ({aprovados/total*100:.0f}%)")

    return 0 if aprovados == total else 1


if __name__ == "__main__":
    sys.exit(main())
