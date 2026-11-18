"""Mostra os tempos reais de cada consulta a partir do indice exportado."""
import json
from pathlib import Path

EVID = Path(__file__).parent.parent / "docs" / "evidencias"
d = json.loads((EVID / "indice_consultas.json").read_text(encoding="utf-8"))

print(f"{'consulta':<6} {'tempo':>10}  nome")
print("-" * 44)
for c in d["consultas"]:
    ms = c.get("duracao_ms", 0)
    print(f"{c['numero']:<6} {ms:>8.1f}ms  {c['nome']}")
