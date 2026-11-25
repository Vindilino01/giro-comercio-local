"""Gera um cartao de divulgacao com o QR code do painel.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Numa apresentacao, ninguem digita uma URL de 56 caracteres. O QR code
resolve: o grupo aponta a camera e abre o painel no proprio celular.

O cartao e um SVG, nao um PNG, por dois motivos:
  - fica nitido em projetor e em impressao A4;
  - o texto continua selecionavel no PDF.

E o QR aponta para a pagina de ENTRADA, nao para painel.html: quem abre
no celular precisa ver a apresentacao do projeto antes de encarar uma
tabela de 140 linhas.

Uso:
    python scripts/gerar_cartao.py
    python scripts/gerar_cartao.py --url https://exemplo.com/

Saida:
    docs/qr-painel.svg   (o cartao inteiro, pronto para projetar)
    docs/qr-painel.png   (o QR sozinho, quadrado, para colar em slide)
"""

from __future__ import annotations

import argparse
from pathlib import Path

RAIZ = Path(__file__).parent.parent

URL_PADRAO = "https://vindilino01.github.io/giro-comercio-local/"

# Mesmo verde e mesma serifa do painel. O cartao e uma peca do produto:
# se a cor divergisse, pareceria material de outra pessoa.
VERDE = "#0b4f3c"
VERDE_ESCURO = "#073a2c"
PAPEL = "#f1f0ea"
TINTA = "#16211c"
TINTA_2 = "#4a554e"
REGUA = "#c9c7be"


def gerar_matriz(url: str) -> list[list[bool]]:
    """Devolve a matriz de modulos do QR como lista de listas de bool."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,               # deixa o lib escolher o menor
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=0,                   # a margem e do cartao, nao do QR
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


def svg_qr(matriz: list[list[bool]], lado: float, x0: float, y0: float) -> str:
    """Desenha o QR como um unico path, no tamanho pedido.

    Um path por modulo geraria ~1.500 elementos e um SVG de 200 KB. Um
    path unico com retangulos concatenados gera ~15 KB e abre instantaneo
    no projetor.
    """
    n = len(matriz)
    mod = lado / n
    partes = []
    for linha, valores in enumerate(matriz):
        i = 0
        while i < n:
            if not valores[i]:
                i += 1
                continue
            # Junta modulos vizinhos na mesma linha num retangulo so.
            j = i
            while j < n and valores[j]:
                j += 1
            largura = (j - i) * mod
            partes.append(
                f"M{x0 + i * mod:.3f} {y0 + linha * mod:.3f}"
                f"h{largura:.3f}v{mod:.3f}h-{largura:.3f}z")
            i = j

    return (f'<path d="{"".join(partes)}" fill="{VERDE_ESCURO}" '
            f'shape-rendering="crispEdges"/>')


def construir_svg(url: str, matriz: list[list[bool]]) -> str:
    """Cartao A4 em paisagem: QR a esquerda, texto a direita."""
    largura, altura = 1123, 794          # A4 paisagem em px a 96 dpi
    margem = 64

    # ---- QR ----
    lado_qr = 400
    qr_x = margem + 24
    qr_y = (altura - lado_qr) / 2 + 20

    # ---- bloco de texto ----
    tx = qr_x + lado_qr + 72

    linhas = [
        ("Giro", 68, VERDE, "Georgia,serif", "700", tx, 250),
        ("Previsão de estoque e sugestão de compra", 26, TINTA_2,
         "Segoe UI,system-ui,sans-serif", "400", tx, 296),
        ("para comércio de bairro", 26, TINTA_2,
         "Segoe UI,system-ui,sans-serif", "400", tx, 330),
    ]

    texto = ""
    for conteudo, tamanho, cor, fonte, peso, x, y in linhas:
        texto += (f'<text x="{x}" y="{y}" font-family="{fonte}" '
                  f'font-size="{tamanho}" font-weight="{peso}" '
                  f'fill="{cor}">{conteudo}</text>')

    # regua
    texto += (f'<rect x="{tx}" y="356" width="120" height="4" '
              f'fill="{VERDE}"/>')

    # link, em duas linhas para nao estourar a largura
    url_curta = url.replace("https://", "").rstrip("/")
    partes = [url_curta]
    if len(url_curta) > 38:
        corte = url_curta.rfind("/", 0, 38)
        if corte > 20:
            partes = [url_curta[:corte + 1], url_curta[corte + 1:]]

    y = 420
    for parte in partes:
        texto += (f'<text x="{tx}" y="{y}" font-family="Consolas,monospace" '
                  f'font-size="22" fill="{VERDE_ESCURO}">{parte}</text>')
        y += 32

    texto += (f'<text x="{tx}" y="{y + 26}" '
              f'font-family="Segoe UI,system-ui,sans-serif" font-size="18" '
              f'fill="{TINTA_2}">Aponte a câmera do celular</text>')

    texto += (f'<text x="{tx}" y="{altura - 132}" '
              f'font-family="Segoe UI,system-ui,sans-serif" font-size="17" '
              f'fill="{TINTA_2}">Projeto A3 — Análise de Dados e Big Data</text>')
    texto += (f'<text x="{tx}" y="{altura - 108}" '
              f'font-family="Segoe UI,system-ui,sans-serif" font-size="15" '
              f'fill="{TINTA_2}">Funciona no celular. Não precisa instalar nada.</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}">
  <rect width="{largura}" height="{altura}" fill="{PAPEL}"/>
  <rect x="{margem}" y="{margem}" width="{largura - 2 * margem}" height="{altura - 2 * margem}"
        fill="#ffffff" stroke="{REGUA}" stroke-width="2"/>
  {svg_qr(matriz, lado_qr, qr_x, qr_y)}
  {texto}
</svg>
"""


def svg_qr_sozinho(url: str, matriz: list[list[bool]]) -> str:
    """Só o QR, com margem branca: para colar num slide."""
    n = len(matriz)
    margem_mod = 4                       # 4 modulos, o padrao da especificacao
    lado = 512
    total_mod = n + 2 * margem_mod
    mod = lado / total_mod
    deslocamento = margem_mod * mod

    corpo = svg_qr(matriz, n * mod, deslocamento, deslocamento)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{lado}" '
            f'height="{lado}" viewBox="0 0 {lado} {lado}">'
            f'<rect width="{lado}" height="{lado}" fill="#ffffff"/>'
            f'{corpo}</svg>\n')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL_PADRAO)
    args = ap.parse_args()

    matriz = gerar_matriz(args.url)
    n = len(matriz)
    print(f"URL        : {args.url}")
    print(f"QR         : {n}x{n} modulos (versao {(n - 17) // 4})")

    cartao = RAIZ / "docs" / "qr-painel.svg"
    cartao.write_text(construir_svg(args.url, matriz), encoding="utf-8")

    sozinho = RAIZ / "docs" / "qr-so.svg"
    sozinho.write_text(svg_qr_sozinho(args.url, matriz), encoding="utf-8")

    print(f"cartao     : docs/qr-painel.svg ({cartao.stat().st_size / 1024:.0f} KB)")
    print(f"QR sozinho : docs/qr-so.svg "
          f"({sozinho.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
