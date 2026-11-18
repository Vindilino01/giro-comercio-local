"""Verifica artefatos visiveis de markdown/HTML nos PDFs entregues."""
import re
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).parent.parent

for nome in ("relatorio-final.pdf", "pitch.pdf"):
    p = RAIZ / "docs" / nome
    d = pymupdf.open(p)
    texto = "\n".join(pag.get_text() for pag in d)

    negrito = len(re.findall(r"\*\*[A-Za-z]", texto))
    comentario = texto.count("<!--")
    placeholder = texto.count("_(preencher)_")
    # formato americano de dinheiro (lc_monetary = C)
    americano = len(re.findall(r"\d{1,3},\d{3}\.\d{2}", texto))

    print(f"{nome}: {d.page_count} paginas")
    print(f"  negrito cru        : {negrito}")
    print(f"  comentario HTML    : {comentario}")
    print(f"  placeholder        : {placeholder}")
    print(f"  dinheiro en-US     : {americano}")
    ok = negrito == comentario == placeholder == americano == 0
    print(f"  {'LIMPO' if ok else 'COM PROBLEMAS'}")
