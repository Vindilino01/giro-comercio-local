"""Prova que a sazonalidade semanal agora muda o ponto de pedido (G8).

Antes: avg(fator)=1 por construcao, entao a previsao era nivel_ewma puro.
Agora: soma-se a demanda de cada dia do horizonte de lead time, com o
fator daquele dia da semana. O efeito depende de QUANDO o horizonte cai.
"""
import psycopg

DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

SQL = """
WITH base AS (
    SELECT loja_id, produto_id, lead_time_dias,
           referencia_estoque, demanda_dia_prevista,
           demanda_lead_time, quantidade_sugerida, situacao
      FROM ouro.mv_sugestao_compra
),
-- Formula plana: o que a versao anterior calculava
plano AS (
    SELECT b.loja_id, b.produto_id,
           b.demanda_dia_prevista * b.lead_time_dias AS demanda_plana
      FROM base b
)
SELECT count(*) AS pares,
       count(*) FILTER (WHERE abs(b.demanda_lead_time - p.demanda_plana) > 0.01)
                                                   AS com_diferenca,
       round(avg(abs(b.demanda_lead_time - p.demanda_plana)
                 / nullif(p.demanda_plana, 0) * 100), 2) AS diff_media_pct,
       round(max(abs(b.demanda_lead_time - p.demanda_plana)
                 / nullif(p.demanda_plana, 0) * 100), 2) AS diff_max_pct,
       count(*) FILTER (WHERE b.demanda_lead_time > p.demanda_plana) AS subiu,
       count(*) FILTER (WHERE b.demanda_lead_time < p.demanda_plana) AS desceu
  FROM base b
  JOIN plano p USING (loja_id, produto_id)
"""

with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute(SQL)
    pares, dif, media, maxima, subiu, desceu = cur.fetchone()

print(f"pares SKU-loja              : {pares}")
print(f"demanda do horizonte difere : {dif}  (antes: 0 - o fator se cancelava)")
print(f"diferenca media             : {media}%")
print(f"diferenca maxima            : {maxima}%")
print(f"ponto de pedido subiu       : {subiu}")
print(f"ponto de pedido desceu      : {desceu}")

print("\nexemplos (maior efeito):")
with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute("""
        SELECT s.loja_id, s.produto_id, s.lead_time_dias,
               s.referencia_estoque,
               round(s.demanda_dia_prevista, 3),
               round(s.demanda_dia_prevista * s.lead_time_dias, 2),
               round(s.demanda_lead_time, 2),
               s.situacao
          FROM ouro.mv_sugestao_compra s
         ORDER BY abs(s.demanda_lead_time
                      - s.demanda_dia_prevista * s.lead_time_dias)
                  / nullif(s.demanda_dia_prevista * s.lead_time_dias, 0) DESC
         LIMIT 5
    """)
    print(f"{'loja':>4} {'sku':>4} {'lead':>4} {'ref':>11} "
          f"{'dem/dia':>8} {'plano':>8} {'horiz':>8} {'sit':>8}")
    for r in cur.fetchall():
        print(f"{r[0]:>4} {r[1]:>4} {r[2]:>4} {str(r[3]):>11} "
              f"{r[4]:>8.3f} {r[5]:>8.2f} {r[6]:>8.2f} {r[7]:>8}")
