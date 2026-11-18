"""Procura no PDF entregue as afirmacoes que o revisor derrubou.

Cada item aqui foi um erro real encontrado na revisao. O script existe
para que nao voltem: se um texto antigo for reintroduzido, o numero
aparece.
"""

import re
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).parent.parent
PDF = RAIZ / "docs" / "relatorio-final.pdf"

# (padrao, o que significa, valor correto)
PROIBIDOS = [
    (r"900 \(399 CHECK", "constraints contadas com particoes", "311"),
    (r"\b22 testes\b", "suites antes do C23", "23 testes"),
    (r"\b22/22\b", "idem", "23/23"),
    (r"10 migrations", "antes do 009/012", "12 migrations"),
    (r"001\.\.011", "idem", "001..012"),
    (r"591 pares", "medicao antiga do horizonte", "545"),
    (r"19B linhas", "1000x de 6,36M = 6,36B", "6,36B"),
    (r"14 tabelas normalizadas", "sao 15", "15 tabelas"),
    (r"~9\.400 rejei", "cascata real: 171.603", "171.603"),
    (r"7\.? ?alternativas", "sao 8", "8 alternativas"),
    (r"1.90 ms", "Q09 leva 3,6 s", "1 ms a 3,6 s"),
    (r"70 ms e v.rios", "Q03 leva 1,27 s", "1,27 s"),
    (r"INTEGRANTES N.O INFORMADOS", "capa sem nomes", "preencher integrantes.md"),
]

texto = "\n".join(p.get_text() for p in pymupdf.open(PDF))
achados = 0
for padrao, motivo, correto in PROIBIDOS:
    n = len(re.findall(padrao, texto))
    if n:
        achados += 1
        print(f"  AINDA: {padrao!r} x{n} - {motivo} (correto: {correto})")

print(f"\n{achados} afirmacao(oes) obsoleta(s) no PDF")
