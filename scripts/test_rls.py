"""Prova que o RLS isola item_venda por loja (achado G2 da auditoria).

Antes: SET ROLE giro_bi com app.loja_id='1' lia 4.159.608 linhas em
prata.item_venda - todas as lojas - enquanto prata.venda devolvia apenas
154.339. O isolamento vazava justamente o dado transacional.
"""

import psycopg

DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

CASOS = [("1", None), ("2", None), ("3", None)]

print(f"{'loja':<6} {'venda':>10} {'item_venda':>12}")
print("-" * 32)

with psycopg.connect(DSN) as conn:
    for loja, _ in CASOS:
        with conn.cursor() as cur:
            cur.execute("SET ROLE giro_bi")
            cur.execute("SELECT set_config('app.loja_id', %s, false)", (loja,))
            cur.execute("SELECT count(*) FROM prata.venda")
            vendas = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM prata.item_venda")
            itens = cur.fetchone()[0]
            cur.execute("RESET ROLE")
        conn.rollback()
        print(f"{loja:<6} {vendas:>10,} {itens:>12,}")

# Total sem filtro de loja: deve ser 0 (fail-closed).
with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute("SET ROLE giro_bi")
    cur.execute("SELECT count(*) FROM prata.item_venda")
    sem_sessao = cur.fetchone()[0]
    cur.execute("RESET ROLE")
print(f"\nsem app.loja_id (deve ser 0): {sem_sessao}")
