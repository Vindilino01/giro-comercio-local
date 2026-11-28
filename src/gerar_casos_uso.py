"""Gera o diagrama de casos de uso do Giro.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A banca pediu o diagrama de casos de uso, e ele nao existia. O projeto
tinha o roteiro do pitch, o PRODUCT.md com a persona e um MER - nenhum
desenho dos atores e do que cada um faz com o sistema.

Os casos de uso sao os que a interface REALMENTE oferece. Cada um aponta,
no codigo, o controle que o executa - caso de uso que nao existe no
painel nao entra no desenho.

Uso:
    python src/gerar_casos_uso.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent.parent
SAIDA = RAIZ / "docs"

DOT_CANDIDATOS = [
    r"C:\Program Files\Graphviz\bin\dot.exe",
    r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
]

# ---------------------------------------------------------------------
# Tres colunas, como um diagrama de casos de uso de livro:
#
#   ator  |  caso de uso  |  o que o executa no painel
#
# A terceira coluna e o que impede o diagrama de virar ficcao: se o
# controle nao existe, o caso nao existe.
# ---------------------------------------------------------------------
CASOS = [
    # (id, nome, ator, controle no painel)
    ("UC01", "Ver o pedido da semana", "nelson",
     "pôster do total + faixa de fornecedores"),
    ("UC02", "Escolher o fornecedor", "nelson",
     "segmento da faixa · largura = valor"),
    ("UC03", "Mudar a disponibilidade desejada", "nelson",
     "Ajustes do cenário · 90 / 95 / 99"),
    ("UC04", "Filtrar por loja", "nelson",
     "seletor de loja no masthead"),
    ("UC05", "Separar a mercadoria", "nelson",
     "caixas da lista · progresso salvo"),
    ("UC06", "Imprimir a folha de separação", "nelson",
     "botão Imprimir · 4 páginas, 1 por loja"),
    ("UC07", "Conferir a conta", "nelson",
     "aba «Conferir a conta» · 10 colunas"),
    ("UC08", "Saber se o dado é confiável", "nelson",
     "selo por loja · pior dimensão"),
    ("UC09", "Copiar o pedido", "nelson",
     "Copiar deste fornecedor / completo"),
    ("UC10", "Receber o pedido", "fornecedor",
     "texto copiado (WhatsApp) ou folha"),
    ("UC11", "Ver quanto a falta custou", "nelson",
     "seção «Quanto a prateleira vazia custou»"),
    ("UC12", "Ver onde o dinheiro está parado", "nelson",
     "seção do capital · cobertura por produto"),
    ("UC13", "Conferir a rastreabilidade", "banca",
     "notas de método + rodapé com o gerador"),
    ("UC14", "Ver o modelo de dados", "banca",
     "dicionário do catálogo + MER"),
]

# (de, para, tipo)
RELACOES = [
    ("UC02", "UC01", "extend"),
    ("UC03", "UC01", "extend"),
    ("UC04", "UC01", "extend"),
    ("UC08", "UC01", "extend"),
    ("UC11", "UC01", "extend"),
    ("UC12", "UC01", "extend"),
    ("UC13", "UC01", "extend"),
    ("UC14", "UC01", "extend"),
    ("UC06", "UC05", "extend"),
    ("UC07", "UC05", "extend"),
    ("UC09", "UC02", "extend"),
    ("UC10", "UC09", "include"),
]

ATORES = {
    "nelson": ("Nelson", "dono do mercado"),
    "fornecedor": ("Fornecedor", "recebe o pedido"),
    "banca": ("Banca", "avalia o projeto"),
}


def achar_dot() -> str:
    for caminho in DOT_CANDIDATOS:
        if Path(caminho).exists():
            return caminho
    import shutil
    achado = shutil.which("dot")
    if achado:
        return achado
    raise SystemExit("Graphviz nao encontrado. "
                     "winget install --id Graphviz.Graphviz --exact")


def gerar_dot() -> str:
    """Por que grade fixa em vez de layout automatico.

    Tentei primeiro o layout livre: 14 elipses e 26 arestas produziram um
    emaranhado, com os atores jogados para o rodape e as associacoes
    cruzando o desenho inteiro. Depois tentei `rank=same` dentro de
    clusters com `rankdir=LR` - o Graphviz ignorou a restricao e empilhou
    tudo numa coluna de 2.500px de altura.

    A grade funciona porque cada caso tem posicao declarada: `rank` fixa a
    linha, `group` fixa a coluna. E o que o diagrama pede - nao ha nada a
    descobrir sobre o arranjo.
    """
    L = [
        "digraph CasosDeUso {",
        '  graph [rankdir=LR, fontname="Segoe UI", fontsize=10,',
        '         bgcolor="white", pad=0.5, nodesep=0.42, ranksep=1.5];',
        '  node  [fontname="Segoe UI", fontsize=9];',
        '  edge  [color="#a9a79c", penwidth=0.9, arrowsize=0.6];',
        "",
        "  // ================= ATORES =================",
        '  subgraph cluster_atores {',
        '    label=""; style="invis";',
    ]
    boneco = (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="1">'
        '<TR><TD><FONT POINT-SIZE="28">&#128100;</FONT></TD></TR>'
        '<TR><TD><FONT POINT-SIZE="9"><B>{nome}</B></FONT></TD></TR>'
        '<TR><TD><FONT POINT-SIZE="7" COLOR="#6a756e">{papel}</FONT></TD></TR>'
        '</TABLE>>'
    )
    for chave, (nome, papel) in ATORES.items():
        L.append(
            f'    "{chave}" [shape=plaintext, group=ator, '
            f'label={boneco.format(nome=nome, papel=papel)}];'
        )
    L.append("  }")
    L.append("")

    L.append("  // ================= SISTEMA =================")
    L.append("  subgraph cluster_sistema {")
    L.append('    label="Giro — painel de decisão de compra";')
    L.append('    fontsize=12; fontname="Segoe UI Semibold";')
    L.append('    color="#0b4f3c"; fontcolor="#0b4f3c";')
    L.append('    style="rounded,dashed"; penwidth=1.4; margin=20;')

    for codigo, nome, _ator, _onde in CASOS:
        L.append(
            f'    "{codigo}" [shape=ellipse, style="filled", group=caso, '
            f'fillcolor="#e2e9e5", color="#0b4f3c", penwidth=1.1, '
            f'label="{codigo}\\n{nome}", margin="0.12,0.06", width=2.2];'
        )

    L.append("  }")
    L.append("")

    # ---- coluna 3: o controle que executa ----
    L.append("  // ================= ONDE NO PAINEL =================")
    for codigo, _nome, _ator, onde in CASOS:
        L.append(
            f'  "c{codigo}" [shape=note, style="filled", group=onde, '
            f'fillcolor="#fbfaf5", color="#dcd9ce", fontsize=7, '
            f'fontcolor="#5e6961", label="{onde}", margin="0.08,0.04"];'
        )
        L.append(f'  "{codigo}" -> "c{codigo}" [style="dotted", '
                 f'arrowhead="none", color="#dcd9ce"];')

    L.append("")

    # ---- alinhamento por linha ----
    # Cada caso com o seu controle na mesma altura.
    L.append("  // ================= ALINHAMENTO =================")
    for i, (codigo, *_resto) in enumerate(CASOS):
        L.append(f'  {{ rank=same; "c{codigo}"; }}')

    L.append("")

    # ---- associacoes ator -> caso ----
    L.append("  // ================= ASSOCIACOES =================")
    for codigo, _nome, ator, _onde in CASOS:
        L.append(
            f'  "{ator}" -> "{codigo}" [dir="none", color="#c9c7be", '
            f'penwidth=0.8];'
        )

    L.append("")
    L.append("  // ================= «include» / «extend» =================")
    for de, para, tipo in RELACOES:
        rotulo = "«include»" if tipo == "include" else "«extend»"
        L.append(
            f'  "{de}" -> "{para}" [style="dashed", arrowhead="open", '
            f'color="#b9b7ae", label=" {rotulo}", fontsize=6, '
            f'fontcolor="#909a93", constraint=false];'
        )

    L.append("}")
    return "\n".join(L)


def main() -> None:
    dot_bin = achar_dot()
    SAIDA.mkdir(parents=True, exist_ok=True)
    fonte = gerar_dot()

    (SAIDA / "casos-de-uso.dot").write_text(fonte, encoding="utf-8")

    for fmt in ("svg", "png"):
        extra = ["-Gdpi=150"] if fmt == "png" else []
        r = subprocess.run(
            [dot_bin, f"-T{fmt}", *extra, "-o",
             str(SAIDA / f"casos-de-uso.{fmt}")],
            input=fonte.encode("utf-8"), capture_output=True,
        )
        if r.returncode != 0:
            raise SystemExit(r.stderr.decode("utf-8", "replace"))

    print(f"casos de uso : {len(CASOS)}")
    print(f"relacoes     : {len(RELACOES)}")
    print("  docs/casos-de-uso.svg")
    print("  docs/casos-de-uso.png")
    print("  docs/casos-de-uso.dot  (fonte editavel)")


if __name__ == "__main__":
    main()
