"""Mede a estrutura real do banco e imprime os numeros para a documentacao.

Motivo: README e docs/06 traziam contagens digitadas a mao (tabelas,
indices, particoes) que nao batiam com o catalogo. Numero de estrutura
nao deve ser escrito a mao - ele e uma consulta.
"""
import psycopg

DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

CONSULTAS = {
    "tabelas logicas": """
        SELECT count(*) FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind IN ('r','p')
           AND n.nspname IN ('prata','ouro','gov','bronze')
           AND c.relname NOT LIKE 'venda\\_20%'
           AND c.relname NOT LIKE 'item\\_venda\\_20%'
           AND c.relname NOT LIKE 'estoque\\_snapshot\\_20%'
           AND c.relname NOT LIKE 'movimentacao\\_estoque\\_20%'
           AND c.relname NOT LIKE 'item\\_pedido\\_20%'
    """,
    "por schema": """
        SELECT n.nspname, count(*)
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind IN ('r','p')
           AND n.nspname IN ('prata','ouro','gov','bronze')
           AND c.relname NOT LIKE 'venda\\_20%'
           AND c.relname NOT LIKE 'item\\_venda\\_20%'
           AND c.relname NOT LIKE 'estoque\\_snapshot\\_20%'
           AND c.relname NOT LIKE 'movimentacao\\_estoque\\_20%'
           AND c.relname NOT LIKE 'item\\_pedido\\_20%'
         GROUP BY 1 ORDER BY 1
    """,
    "particoes": """
        SELECT count(*) FROM pg_class WHERE relkind = 'r' AND relispartition
    """,
    "particoes por tabela": """
        SELECT parent.relname AS tabela, count(*) AS particoes
          FROM pg_inherits i
          JOIN pg_class parent ON parent.oid = i.inhparent
          JOIN pg_class child  ON child.oid  = i.inhrelid
         GROUP BY 1 ORDER BY 1
    """,
    "indices (definicoes CREATE INDEX)": """
        SELECT count(DISTINCT indexname) FROM pg_indexes
         WHERE schemaname IN ('prata','ouro','gov')
    """,
    "views materializadas": """
        SELECT count(*) FROM pg_matviews WHERE schemaname = 'ouro'
    """,
    "constraints nomeadas": """
        SELECT contype, count(*) FROM pg_constraint c
          JOIN pg_namespace n ON n.oid = c.connamespace
         WHERE n.nspname IN ('prata','ouro','gov')
         GROUP BY 1 ORDER BY 1
    """,
    "tamanho do banco": "SELECT pg_size_pretty(pg_database_size('giro'))",
    "dominios": """
        SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
         WHERE t.typtype='d' AND n.nspname='gov'
    """,
}

with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    for rotulo, sql in CONSULTAS.items():
        cur.execute(sql)
        linhas = cur.fetchall()
        print(f"\n{rotulo}:")
        for l in linhas:
            print("   ", " | ".join(str(x) for x in l))
