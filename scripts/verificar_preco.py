"""Valida o preco de venda da dim_produto contra o preco praticado nas vendas.

O achado B2 da auditoria: dim_produto usava custo/0,7 para 420 de 420 SKUs,
com erro medio de 11,62% contra o preco que o PDV realmente cobrou. Este
script mede o mesmo indicador depois da correcao (historico de preco
populado + margem ancorada na data do dado).
"""
import psycopg

DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

SQL = """
WITH praticado AS (
    SELECT produto_id,
           sum(valor_total) / nullif(sum(quantidade), 0) AS preco_medio
      FROM prata.item_venda
     GROUP BY produto_id
)
SELECT count(*)                                          AS skus,
       count(*) FILTER (WHERE d.preco_venda_atual = round(d.preco_custo_atual / 0.7, 2))
                                                          AS com_formula_30,
       round(avg(abs(d.preco_venda_atual - p.preco_medio)
                 / nullif(p.preco_medio, 0) * 100), 2)    AS erro_medio_pct,
       round(max(abs(d.preco_venda_atual - p.preco_medio)
                 / nullif(p.preco_medio, 0) * 100), 2)    AS erro_maximo_pct,
       count(*) FILTER (WHERE abs(d.preco_venda_atual - p.preco_medio)
                          / nullif(p.preco_medio, 0) < 0.005) AS dentro_de_0_5_pct
  FROM ouro.dim_produto d
  JOIN praticado p ON p.produto_id = d.produto_id
"""

with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute(SQL)
    skus, formula, medio, maximo, dentro = cur.fetchone()

print(f"SKUs avaliados            : {skus}")
print(f"preco = custo/0,7         : {formula}  (antes: 420 de 420)")
print(f"erro medio vs praticado   : {medio}%  (antes: 11,62%)")
print(f"erro maximo               : {maximo}%  (antes: 25,77%)")
print(f"dentro de 0,5% do praticado: {dentro} de {skus}  (antes: 11)")
