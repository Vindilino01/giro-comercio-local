"""Redirecionamento: o relatorio agora e gerado em Word.

POR QUE ESTE ARQUIVO MUDOU DE FUNCAO
------------------------------------
Ate a revisao, este era o gerador do relatorio: markdown -> HTML -> PDF
pelo Edge headless. Produzia 66 paginas para 18 mil palavras, e o
resultado nao servia para o uso real - o orientador nao conseguia
comentar, o grupo nao conseguia corrigir uma frase sem regenerar tudo, e
a secretaria pede Word.

O gerador atual e `src/relatorio_docx.py`, que usa estilos nativos do
Word. O PDF continua existindo, mas como derivado do .docx: quem exporta
e o proprio Word, e o texto e o mesmo nos dois.

Este arquivo ficou como porta de entrada para nao quebrar quem ja sabe o
comando antigo. Ele explica o novo caminho e sai com codigo 1, para que
um script de automacao perceba que nao gerou nada.

Uso:
    python src/relatorio_docx.py
    pwsh scripts/atualizar_sumario.ps1
"""

from __future__ import annotations

import sys


def main() -> int:
    print(__doc__)
    print("Nada foi gerado. Use os dois comandos acima.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
