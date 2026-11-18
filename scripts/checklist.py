"""Lista o que ainda falta para a entrega, de forma objetiva.

Roda as verificacoes e imprime um checklist final. Serve tanto para o
grupo saber o que fazer quanto para responder "esta pronto?" com fatos.
"""

import re
import subprocess
import sys
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).parent.parent
DOCS = RAIZ / "docs"


def titulo(t: str) -> None:
    print(f"\n{'=' * 62}\n  {t}\n{'=' * 62}")


def item(ok: bool, texto: str, detalhe: str = "") -> None:
    marca = "OK   " if ok else "FALTA"
    print(f"  [{marca}] {texto}" + (f"  ({detalhe})" if detalhe else ""))


titulo("ENTREGAVEIS")

pdf = DOCS / "relatorio-final.pdf"
pitch = DOCS / "pitch.pdf"
painel = DOCS / "painel.html"

item(pdf.exists(), "relatorio-final.pdf",
     f"{pdf.stat().st_size / 1024 / 1024:.1f} MB" if pdf.exists() else "")
item(pitch.exists(), "pitch.pdf",
     f"{pitch.stat().st_size / 1024 / 1024:.2f} MB" if pitch.exists() else "")
item(painel.exists(), "painel.html",
     f"{painel.stat().st_size / 1024:.0f} KB" if painel.exists() else "")

# --- secoes obrigatorias no PDF
if pdf.exists():
    t = "\n".join(p.get_text() for p in pymupdf.open(pdf))
    titulo("SECOES DO EDITAL NO PDF")
    for rotulo, padrao in [
        ("4.1 Problema e visao", "4.1"),
        ("4.2 Diagnostico dos dados", "4.2"),
        ("4.3 Escolha do banco", "4.3"),
        ("4.4 Modelagem", "4.4"),
        ("4.5 Qualidade e governanca", "4.5"),
        ("4.6 Prova de conceito", "4.6"),
        ("4.7 Limitacoes e proximos passos", "4.7"),
    ]:
        item(padrao in t, rotulo)

    titulo("EXIGENCIAS ADICIONAIS")
    item("Referências" in t, "secao de referencias")
    item(bool(re.search(r"declara..o de uso de .?i.?a", t, re.I)),
         "declaracao de uso de IA (secao 2 do edital)")

    # A capa usa letter-spacing no rotulo, entao o extrator de PDF
    # devolve "I N T E G R A N T E S" com espaco entre as letras. Comparar
    # a string crua dava falso OK: o PDF estava sem nomes e o checklist
    # dizia que estava tudo certo.
    compacto = re.sub(r"\s+", "", t).upper()
    sem_nomes = "INTEGRANTESNÃOINFORMADOS" in compacto
    item(not sem_nomes,
         "capa com nome e RA dos integrantes",
         "preencha docs/integrantes.md e regenere o PDF" if sem_nomes else "ok")

titulo("PENDENCIAS QUE DEPENDEM DE VOCES")
autorizacao = list(DOCS.glob("autorizacao-grupo.*"))
item(bool(autorizacao), "autorizacao da professora anexada",
     "salve como docs/autorizacao-grupo.pdf" if not autorizacao else
     autorizacao[0].name)

placeholders = sum(
    1 for linha in (DOCS / "integrantes.md").read_text(encoding="utf-8").splitlines()
    if "preencher" in linha.lower())
item(placeholders == 0, "docs/integrantes.md preenchido",
     f"{placeholders} linhas com placeholder" if placeholders else "ok")

titulo("VERIFICACAO AUTOMATICA")

checagens = [
    ("pytest (5 suites)", [sys.executable, "-m", "pytest", "-q"]),
    ("painel x banco (18)", [sys.executable, "dashboard/verificar.py"]),
    ("runtime do painel (15)", ["node", "scripts/verificar_painel.js"]),
    ("gate de confianca", ["node", "scripts/testar_gate_confianca.js"]),
    ("PDF sem afirmacao obsoleta", [sys.executable, "scripts/conferir_pdf_obsoleto.py"]),
]

for rotulo, cmd in checagens:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=RAIZ,
                       encoding="utf-8", errors="replace", timeout=1200)
    item(r.returncode == 0, rotulo)

print()
