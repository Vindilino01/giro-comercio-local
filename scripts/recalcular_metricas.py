"""Recalcula as metricas de qualidade no banco giro_qualidade ja carregado."""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg

from src.metricas_qualidade import analisar

DSN = "host=127.0.0.1 port=5433 dbname=giro_qualidade user=postgres"

gabarito = json.loads(
    (RAIZ / "data" / "bronze" / "sujo" / "_gabarito.json").read_text(encoding="utf-8"))

with psycopg.connect(DSN) as conn:
    metricas = analisar(conn, gabarito)

destino = RAIZ / "docs" / "evidencias" / "metricas_qualidade.json"
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(json.dumps(metricas, ensure_ascii=False, indent=2),
                   encoding="utf-8")

print(f"{'REGRA':<7} {'TABELA':<22} {'INJ':>8} {'REJ':>8} "
      f"{'RECALL':>8} {'PREC':>7} {'F1':>6}")
print("-" * 76)
for r in metricas["por_regra"]:
    print(f"{r['regra']:<7} {r['tabela']:<22} {r['injetados']:>8,} "
          f"{r['rejeitados']:>8,} {r['recall_pct']:>7.1f}% "
          f"{r['precisao_pct']:>6.1f}% {r['f1_pct']:>5.1f}")

res = metricas["resumo"]
print("-" * 76)
print(f"recall de linha    : {res['recall_defeitos_de_linha_pct']}% "
      f"({res['defeitos_de_linha_injetados']:,} defeitos)")
print(f"recall de conjunto : {res['recall_defeitos_de_conjunto_pct']}% "
      f"({res['defeitos_de_conjunto_injetados']:,} defeitos)")
print(f"recall global      : {res['recall_global_pct']}%")
print(f"em quarentena      : {res['registros_em_quarentena']:,}")
print(f"\nEvidencia: {destino.relative_to(RAIZ)}")
