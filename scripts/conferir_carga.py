"""Confere os numeros de carga e a consistencia com gov.lote_carga."""
import json
from pathlib import Path

import psycopg

EVID = Path(__file__).parent.parent / "docs" / "evidencias"
carga = json.loads((EVID / "carga_limpa.json").read_text(encoding="utf-8"))

print(f"{'tabela':<26} {'lidas':>12} {'aceitas':>12} {'rejeitadas':>12}")
print("-" * 66)
tl = ta = tr = 0
for r in carga:
    tl += r["lidas"]
    ta += r["aceitas"]
    tr += r["rejeitadas"]
    print(f"{r['tabela']:<26} {r['lidas']:>12,} {r['aceitas']:>12,} "
          f"{r['rejeitadas']:>12,}")
print("-" * 66)
print(f"{'TOTAL':<26} {tl:>12,} {ta:>12,} {tr:>12,}")

with psycopg.connect("host=127.0.0.1 port=5433 dbname=giro user=postgres") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT sum(linhas_lidas), sum(linhas_aceitas), "
                    "sum(linhas_rejeitadas) FROM gov.lote_carga")
        print(f"\nbanco (gov.lote_carga): lidas={cur.fetchone()}")
