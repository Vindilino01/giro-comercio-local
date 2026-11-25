"""Leitura de docs/integrantes.md, compartilhada por relatorio e pitch.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A capa do relatorio e a capa do pitch mostram os mesmos nomes e RAs. As
duas liam `docs/integrantes.md` por uma funcao que morava em
`relatorio_pdf.py` - o gerador de PDF antigo. Quando o relatorio passou a
ser gerado em Word (`relatorio_docx.py`), o pitch continuaria dependendo
do arquivo velho, e apagar o velho quebraria o pitch em silencio (o
`try/except` de la engole a excecao e a capa sai sem nome nenhum).

Agora os dois importam daqui.

FORMATO DO ARQUIVO
------------------
Uma tabela markdown com colunas #, Nome completo e RA. Linhas com o
marcador `_(preencher)_` sao ignoradas: trabalho sem identificacao e
melhor que trabalho com placeholder impresso.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).parent.parent


def ler_integrantes() -> list[tuple[str, str]]:
    """Devolve [(nome, ra)] lidos de docs/integrantes.md.

    Lista vazia significa "ainda nao preenchido" - e quem chama deve
    avisar em vez de imprimir uma linha em branco.
    """
    caminho = RAIZ / "docs" / "integrantes.md"
    if not caminho.exists():
        return []

    out: list[tuple[str, str]] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", linha)
        if not m:
            continue
        nome, ra = m.group(1), m.group(2)
        if "preencher" in nome.lower() or "preencher" in ra.lower():
            continue
        out.append((nome, ra))
    return out
