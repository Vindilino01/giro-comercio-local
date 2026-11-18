"""Testa o para_float contra os formatos que ja apareceram nas evidencias."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.preencher_relatorio import para_float

casos = [
    ("1.234,56", 1234.56),        # pt-BR
    ("1,234.56", 1234.56),        # en-US
    ("1234.56", 1234.56),         # sem milhar
    ("87,701.67", 87701.67),      # lc_monetary = C
    ("  266.318,86", 266318.86),  # pt-BR com espaco
    ("1.234", 1234.0),            # ponto ambiguo = milhar
    ("12,5", 12.5),               # virgula decimal
    ("R$ 266.318,86", 266318.86), # com simbolo
    (266318.86, 266318.86),       # numero
    (None, 0.0),                  # nulo
]

falhas = 0
for entrada, esperado in casos:
    obtido = para_float(entrada)
    ok = abs(obtido - esperado) < 0.01
    if not ok:
        falhas += 1
    marca = "OK " if ok else "ERRO"
    print(f"{marca} {entrada!r:>20} -> {obtido:>12,.2f}"
          + ("" if ok else f"   (esperado {esperado:,.2f})"))

print(f"\n{len(casos) - falhas}/{len(casos)} casos corretos")
sys.exit(1 if falhas else 0)
