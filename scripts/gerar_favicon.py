"""Gera o favicon do Giro como SVG e imprime o data URI.

POR QUE NAO UM .ico
-------------------
Um favicon.ico e um binario de 16 KB que o navegador pede sozinho em toda
visita. Se o arquivo nao existe, o servidor devolve 404 e o console do
Pages registra uma requisicao falha - foi o que o teste do site
publicado apontou.

O SVG em data URI resolve os dois lados: zero requisicao de rede (fica
embutido no HTML) e nitidez em qualquer tamanho de aba.

O desenho: o "G" de Giro em serifa, no verde do painel (#0b4f3c), sobre
fundo claro. Sem texto pequeno - em 16px, so a silhueta sobrevive.

Uso:
    python scripts/gerar_favicon.py
"""

from __future__ import annotations

import base64

# SVG com o G centralizado. `text` com serifa generica: o navegador usa a
# Georgia do sistema, que existe em Windows, macOS e Linux. Nao embutir
# fonte aqui - o favicon precisa ser menor que 1 KB.
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#0b4f3c"/>'
    '<text x="32" y="47" font-family="Georgia,serif" font-size="46" '
    'font-weight="700" fill="#f1f0ea" text-anchor="middle">G</text>'
    "</svg>"
)


def data_uri() -> str:
    """SVG em base64, no formato que o atributo href aceita."""
    b64 = base64.b64encode(SVG.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def main() -> None:
    uri = data_uri()
    print(f"tamanho do SVG : {len(SVG)} bytes")
    print(f"tamanho do URI : {len(uri)} bytes")
    print()
    print(f'<link rel="icon" href="{uri}">')


if __name__ == "__main__":
    main()
