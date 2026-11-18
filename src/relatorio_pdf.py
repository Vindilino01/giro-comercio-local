"""
Gera o relatorio final em PDF a partir dos markdowns.

PIPELINE: markdown -> HTML (com CSS de tipografia) -> PDF (Edge headless)

POR QUE EDGE E NAO weasyprint/reportlab
---------------------------------------
  1. Ja esta instalado em qualquer Windows 10/11 (zero dependencia).
  2. Renderiza UTF-8 e acentuacao corretamente - o problema que o
     projeto anterior teve nos titulos.
  3. Suporta CSS completo (quebras de pagina, cabecalho, tabelas),
     que reportlab nao tem e weasyprint exigiria instalar GTK.
  4. Gera PDF vetorial com fontes embutidas.

Uso:
    python src/relatorio_pdf.py
    python src/relatorio_pdf.py --saida docs/relatorio-final.pdf
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import tempfile
from pathlib import Path

RAIZ = Path(__file__).parent.parent

# Ordem das secoes no relatorio final, seguindo o roteiro do edital.
SECOES = [
    ("01-problema.md", "1"),
    ("02-diagnostico.md", "2"),
    ("03-escolha-banco.md", "3"),
    ("04-modelagem.md", "4"),
    ("05-qualidade.md", "5"),
    ("06-prova-conceito.md", "6"),
    ("07-limitacoes.md", "7"),
    ("08-declaracao-ia.md", "8"),
    # Referencias fecham o documento: toda afirmacao factual do texto
    # aponta para uma fonte aqui, e os numeros do proprio projeto apontam
    # para docs/evidencias/.
    ("referencias.md", "9"),
]

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page {
    size: A4;
    margin: 22mm 18mm 20mm 18mm;
    @bottom-center {
        content: counter(page);
        font-family: 'Segoe UI', sans-serif;
        font-size: 9pt;
        color: #888;
    }
}
@page :first { margin-top: 40mm; }

* { box-sizing: border-box; }

body {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.62;
    color: #1a1a1a;
    margin: 0;
    hyphens: auto;
    text-align: justify;
}

/* Justificar um paragrafo que contem `codigo` inline abre buracos: o
   navegador nao pode hifenizar dentro do <code>, entao empurra o espaco
   para os vazios entre palavras e a linha fica com "O    que    muda:".
   Paragrafos com trecho monoespacado ficam alinhados a esquerda, que e o
   que a tipografia tecnica recomenda. */
p:has(code) {
    text-align: left;
}

h1, h2, h3, h4 {
    font-family: 'Segoe UI Semibold', 'Segoe UI', sans-serif;
    color: #0f172a;
    line-height: 1.25;
    page-break-after: avoid;
    text-align: left;
}

h1 {
    font-size: 20pt;
    margin: 0 0 10mm 0;
    padding-bottom: 3mm;
    border-bottom: 2.5pt solid #0f766e;
    page-break-before: always;
}
h1:first-of-type { page-break-before: avoid; }

h2 {
    font-size: 14pt;
    margin: 9mm 0 3mm 0;
    color: #0f766e;
}

h3 {
    font-size: 11.5pt;
    margin: 7mm 0 2.5mm 0;
    color: #0f766e;
    /* Barra lateral: sem ela, um h3 de 11,5pt em #334155 fica
       indistinguivel do corpo e as seis limitacoes da secao 4.7 viram
       um bloco continuo de texto. */
    padding-left: 3mm;
    border-left: 2.5pt solid #0f766e;
}

h4 { font-size: 10.5pt; margin: 4mm 0 1.5mm 0; }

p { margin: 0 0 3mm 0; orphans: 3; widows: 3; }

strong { color: #0f172a; }

code {
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    font-size: 8.8pt;
    background: #f1f5f9;
    padding: 0.4mm 1.2mm;
    border-radius: 2px;
    color: #0f766e;
    word-break: break-word;
}

pre {
    background: #0f172a;
    color: #e2e8f0;
    padding: 3.5mm 4mm;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 8.3pt;
    line-height: 1.45;
    margin: 3mm 0 4mm 0;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
}
pre code {
    background: none;
    color: inherit;
    padding: 0;
    font-size: inherit;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 3mm 0 5mm 0;
    font-size: 8.8pt;
    page-break-inside: auto;
}
thead { display: table-header-group; }
tr { page-break-inside: avoid; }

th {
    background: #0f766e;
    color: white;
    text-align: left;
    padding: 2mm 2.5mm;
    font-weight: 600;
    border: 0.5pt solid #0d5f59;
}
td {
    padding: 1.8mm 2.5mm;
    border: 0.5pt solid #cbd5e1;
    vertical-align: top;
}
tbody tr:nth-child(even) { background: #f8fafc; }

blockquote {
    border-left: 3pt solid #0f766e;
    background: #f0fdfa;
    margin: 4mm 0;
    padding: 3mm 5mm;
    color: #134e4a;
    page-break-inside: avoid;
}
blockquote p:last-child { margin-bottom: 0; }

ul, ol { margin: 0 0 3mm 0; padding-left: 6mm; }
li { margin-bottom: 1.2mm; }

hr {
    border: none;
    border-top: 0.5pt solid #cbd5e1;
    margin: 6mm 0;
}

details {
    background: #f8fafc;
    border: 0.5pt solid #e2e8f0;
    border-radius: 3px;
    padding: 2mm 3mm;
    margin: 3mm 0;
}
summary { cursor: pointer; font-weight: 600; color: #0f766e; }

a { color: #0f766e; text-decoration: none; }

/* Sumario */
.sumario {
    page-break-after: always;
}
.sumario h1 {
    page-break-before: avoid;
    border-bottom: 2.5pt solid #0f766e;
}
.sumario ol { list-style: none; padding-left: 0; counter-reset: secao; }
.sumario li {
    counter-increment: secao;
    padding: 2.2mm 0;
    border-bottom: 0.5pt dotted #cbd5e1;
    font-size: 11pt;
}
.sumario li::before {
    content: counter(secao) ". ";
    font-weight: 700;
    color: #0f766e;
}
.sumario .sub { font-size: 9pt; color: #64748b; display: block; padding-left: 6mm; }

.capa {
    text-align: center;
    padding-top: 30mm;
    page-break-after: always;
}
.capa .titulo {
    font-size: 34pt;
    font-weight: 700;
    color: #0f766e;
    letter-spacing: -1pt;
    margin: 0 0 4mm 0;
    border: none;
}
.capa .subtitulo {
    font-size: 14pt;
    color: #334155;
    margin: 0 0 22mm 0;
    font-weight: 400;
}
.capa .disciplina {
    font-size: 11pt;
    color: #64748b;
    margin-bottom: 3mm;
}
.capa .info {
    font-size: 10pt;
    color: #475569;
    line-height: 1.9;
    margin-top: 25mm;
}
/* Bloco de integrantes na capa: nome e RA. Sem isto o PDF sai sem
   identificacao e o professor nao consegue atribuir a nota. */
.capa .integrantes {
    margin-top: 14mm;
    text-align: left;
    display: inline-block;
}
.capa .integrantes__titulo {
    font-size: 8.5pt;
    letter-spacing: .18em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 4mm;
}
.capa .integrantes ol {
    list-style: none;
    counter-reset: alum;
    margin: 0;
    padding: 0;
    font-size: 10.5pt;
    line-height: 1.85;
}
.capa .integrantes li { counter-increment: alum; }
.capa .integrantes li::before {
    content: counter(alum) ". ";
    color: #94a3b8;
}
.capa .integrantes .ra {
    font-size: 8.5pt;
    color: #64748b;
    font-variant-numeric: tabular-nums;
    margin-left: .5em;
}
.capa .integrantes--pendente p {
    font-size: 9pt;
    color: #b45309;
    margin: .5rem 0 0;
}
.capa .integrantes--pendente code {
    font-family: monospace;
    font-size: .95em;
}
.capa .linha {
    width: 50mm;
    height: 2.5pt;
    background: #0f766e;
    margin: 6mm auto;
}
"""


# =====================================================================
# Markdown -> HTML (subconjunto suficiente para o relatorio)
# =====================================================================

def _inline(texto: str) -> str:
    """Converte markdown inline para HTML."""
    t = html.escape(texto, quote=False)

    # Codigo inline primeiro (protege contra outras substituicoes)
    marcadores: dict[str, str] = {}

    def guardar(m: re.Match) -> str:
        chave = f"\x00CODE{len(marcadores)}\x00"
        marcadores[chave] = f"<code>{m.group(1)}</code>"
        return chave

    t = re.sub(r"`([^`]+)`", guardar, t)

    # Negrito e italico
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)

    # Links
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)

    # Restaura codigo
    for chave, valor in marcadores.items():
        t = t.replace(chave, valor)

    return t


def normalizar_markdown(md: str) -> str:
    """Prepara o markdown antes da conversao para HTML.

    O parser de `markdown_para_html` ja reune linhas de continuacao de
    paragrafo, item de lista e blockquote. A versao anterior desta funcao
    tentava fazer o mesmo trabalho antes, com regras proprias, e as duas
    logicas discordavam: um `**negrito**` que atravessava a quebra de
    linha saia como texto literal porque a funcao "resolvia" o paragrafo
    cedo demais.

    Restou o que o parser nao faz e que faz falta:

    1. remove espacos no fim das linhas (o markdown os ignora, mas eles
       contam como conteudo ao juntar continuacoes);
    2. garante UMA linha em branco entre blocos, nunca duas - linha em
       branco extra nao muda o HTML, apenas infla o arquivo.
    """
    saida: list[str] = []
    em_codigo = False
    vazias = 0

    for linha in md.splitlines():
        if linha.strip().startswith("```"):
            em_codigo = not em_codigo
            saida.append(linha.rstrip())
            vazias = 0
            continue

        if em_codigo:
            saida.append(linha)
            continue

        limpa = linha.rstrip()
        if not limpa:
            vazias += 1
            if vazias <= 1:
                saida.append("")
            continue

        vazias = 0
        saida.append(limpa)

    return "\n".join(saida)


def markdown_para_html(md: str) -> str:
    # Marcadores de preenchimento (<!-- X_INICIO --> ... <!-- X_FIM -->)
    # sao instrucoes para src/preencher_relatorio.py, nao conteudo. Sem
    # esta limpeza eles vazavam como texto literal para o PDF - o leitor
    # via "<!-- BENCHMARK_INICIO -->" impresso na pagina.
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    md = normalizar_markdown(md)
    linhas = md.split("\n")
    saida: list[str] = []
    i = 0
    em_lista: str | None = None   # 'ul' | 'ol'
    em_tabela = False
    em_codigo = False
    bloco_codigo: list[str] = []
    em_blockquote = False
    em_details = False

    def fechar_lista() -> None:
        nonlocal em_lista
        if em_lista:
            saida.append(f"</{em_lista}>")
            em_lista = None

    def fechar_tabela() -> None:
        nonlocal em_tabela
        if em_tabela:
            saida.append("</tbody></table>")
            em_tabela = None

    while i < len(linhas):
        linha = linhas[i]
        sem = linha.strip()

        # ---- Bloco de codigo --------------------------------------
        if sem.startswith("```"):
            if em_codigo:
                saida.append(
                    "<pre><code>" + html.escape("\n".join(bloco_codigo))
                    + "</code></pre>")
                bloco_codigo = []
                em_codigo = False
            else:
                fechar_lista()
                fechar_tabela()
                em_codigo = True
            i += 1
            continue

        if em_codigo:
            bloco_codigo.append(linha)
            i += 1
            continue

        # ---- Linha vazia ------------------------------------------
        if not sem:
            fechar_lista()
            fechar_tabela()
            i += 1
            continue

        # ---- Details / summary ------------------------------------
        if sem.startswith("<details>"):
            em_details = True
            saida.append("<details>")
            i += 1
            continue
        if sem.startswith("</details>"):
            em_details = False
            saida.append("</details>")
            i += 1
            continue
        if sem.startswith("<summary>"):
            saida.append(sem)
            i += 1
            continue

        # ---- Tabela -----------------------------------------------
        if "|" in sem and i + 1 < len(linhas) and re.match(
                r"^\|?[\s:|-]+\|[\s:|-]*$", linhas[i + 1].strip()):
            fechar_lista()
            celulas = [c.strip() for c in sem.strip("|").split("|")]
            saida.append("<table><thead><tr>"
                         + "".join(f"<th>{_inline(c)}</th>" for c in celulas)
                         + "</tr></thead><tbody>")
            em_tabela = True
            i += 2
            continue

        if em_tabela:
            if "|" in sem:
                celulas = [c.strip() for c in sem.strip("|").split("|")]
                saida.append("<tr>"
                             + "".join(f"<td>{_inline(c)}</td>" for c in celulas)
                             + "</tr>")
                i += 1
                continue
            fechar_tabela()

        # ---- Titulos ----------------------------------------------
        m = re.match(r"^(#{1,4})\s+(.*)$", sem)
        if m:
            fechar_lista()
            fechar_tabela()
            nivel = len(m.group(1))
            saida.append(f"<h{nivel}>{_inline(m.group(2))}</h{nivel}>")
            i += 1
            continue

        # ---- HR ---------------------------------------------------
        if re.match(r"^-{3,}$|^\*{3,}$", sem):
            fechar_lista()
            fechar_tabela()
            saida.append("<hr>")
            i += 1
            continue

        # ---- Blockquote -------------------------------------------
        if sem.startswith(">"):
            if not em_blockquote:
                saida.append("<blockquote>")
                em_blockquote = True
            # Junta as linhas consecutivas do mesmo blockquote. Antes cada
            # linha virava um <p>, e um negrito que atravessava a quebra
            # ("**Dado ruim nao e descartado em silencio. Ele vai para
            # quarentena...**") saia partido: o ** abria num <p> e fechava
            # no seguinte, sem par, e aparecia literal no PDF.
            partes_bq: list[str] = []
            while i < len(linhas) and linhas[i].strip().startswith(">"):
                partes_bq.append(linhas[i].strip().lstrip(">").strip())
                i += 1
            texto_bq = " ".join(p for p in partes_bq if p)
            if texto_bq:
                saida.append(f"<p>{_inline(texto_bq)}</p>")
            continue
        elif em_blockquote:
            saida.append("</blockquote>")
            em_blockquote = False

        # ---- Lista ------------------------------------------------
        m_ul = re.match(r"^[-*+]\s+(.*)$", sem)
        # `\d+[.)]` e marcador de lista, MAS "2019. Metricas de OTIF" no
        # meio de uma referencia bibliografica tambem casa. O discriminador
        # e o espaco depois do ponto: em lista o texto comeca minusculo ou
        # e uma frase; num ano de referencia o numero tem 4 digitos e vem
        # logo apos uma virgula no paragrafo anterior. Aqui basta excluir
        # anos de 4 digitos, que nunca iniciam item de lista legitimo.
        m_ol = None
        if not re.match(r"^\d{4}\.\s", sem):
            m_ol = re.match(r"^\d+[.)]\s+(.*)$", sem)

        if m_ul or m_ol:
            tipo = "ul" if m_ul else "ol"
            if em_lista != tipo:
                fechar_lista()
                saida.append(f"<{tipo}>")
                em_lista = tipo
            texto = m_ul.group(1) if m_ul else m_ol.group(1)
            i += 1

            # Continuacao do item: linhas seguintes sem marcador e sem
            # estrutura pertencem a este item. Sem isto, um item escrito
            # em duas linhas ("- **X** ... favorece\n  o colunar") virava
            # <li>X</li> mais um <p> solto, e a lista se partia em tres
            # paragrafos no PDF.
            while i < len(linhas):
                prox = linhas[i]
                pst = prox.strip()
                if not pst:
                    break
                if (pst.startswith(("-", "*", "+", "#", "|", ">", "```", "<"))
                        or re.match(r"^\d+[.)]\s", pst)):
                    break
                # Linha nao indentada apos lista ainda e continuacao neste
                # subset de markdown (o autor quebra a linha por largura).
                texto += " " + pst
                i += 1

            saida.append(f"<li>{_inline(texto)}</li>")
            continue

        # ---- Paragrafo --------------------------------------------
        fechar_lista()
        partes = [sem]
        j = i + 1
        while j < len(linhas):
            prox = linhas[j].strip()
            if (not prox or prox.startswith(("#", "|", ">", "-", "*", "```"))
                    or re.match(r"^\d+[.)]\s", prox)
                    or prox.startswith("<")):
                break
            partes.append(prox)
            j += 1
        saida.append(f"<p>{_inline(' '.join(partes))}</p>")
        i = j

    if em_codigo:
        saida.append("<pre><code>"
                     + html.escape("\n".join(bloco_codigo)) + "</code></pre>")
    fechar_lista()
    fechar_tabela()
    if em_blockquote:
        saida.append("</blockquote>")

    return "\n".join(saida)


# =====================================================================
# Montagem do documento
# =====================================================================

def ler_integrantes() -> list[tuple[str, str]]:
    """Le docs/integrantes.md e devolve [(nome, ra)].

    A capa nao pode ficar sem identificacao: trabalho entregue sem nome e
    RA e trabalho que o professor nao consegue atribuir. Se a tabela ainda
    estiver com os marcadores `_(preencher)_`, a capa avisa em vez de
    imprimir placeholders.
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


def capa() -> str:
    integrantes = ler_integrantes()

    if integrantes:
        lista = "".join(
            f"<li>{html.escape(nome)}"
            f" <span class='ra'>RA {html.escape(ra)}</span></li>"
            for nome, ra in integrantes)
        bloco_grupo = f"""
      <div class="integrantes">
        <div class="integrantes__titulo">Integrantes</div>
        <ol>{lista}</ol>
      </div>"""
    else:
        bloco_grupo = """
      <div class="integrantes integrantes--pendente">
        <div class="integrantes__titulo">Integrantes não informados</div>
        <p>Preencha <code>docs/integrantes.md</code> e gere o PDF novamente.</p>
      </div>"""

    return f"""
    <div class="capa">
      <div class="titulo">Giro</div>
      <div class="subtitulo">Previsão de estoque e vendas para pequenos mercados</div>
      <div class="linha"></div>
      <div class="disciplina">A3 — Análise de Dados e Big Data</div>{bloco_grupo}
      <div class="info">
        Projeto de startup de dados<br>
        Avaliação A3 · 10,0 pontos<br><br>
        PostgreSQL 18 · Python 3.14 · DuckDB<br><br>
        <em>Repositório com código, evidências e instruções de reprodução</em>
      </div>
    </div>
    """


def sumario() -> str:
    itens = [
        ("Problema e visão da startup",
         "Dor, público-alvo, proposta de valor, KPIs"),
        ("Diagnóstico dos dados",
         "Fontes, tipos, os 5 Vs, volumetria e padrão de acesso"),
        ("Escolha do banco de dados",
         "Justificativa, 8 alternativas descartadas, Teorema CAP"),
        ("Organização e modelagem",
         "Modelo conceitual, lógico e físico; chaves, índices, normalização"),
        ("Qualidade e governança",
         "21 regras, fluxo ETL, medição de recall, LGPD, backup e riscos"),
        ("Prova de conceito",
         "Banco real, 11 consultas com resultado, testes e evidências"),
        ("Limitações e próximos passos",
         "Onde a escolha falha, cenário 100×, aprendizados do grupo"),
        ("Declaração de uso de IA",
         "Onde foi usada, o que foi revisado, como verificar"),
        ("Referências",
         "Fontes de mercado, legislação, banco de dados e modelagem"),
    ]
    lis = "".join(
        f'<li>{html.escape(t)}<span class="sub">{html.escape(s)}</span></li>'
        for t, s in itens
    )
    return f"""
    <div class="sumario">
      <h1>Sumário</h1>
      <ol>{lis}</ol>
    </div>
    """


def construir_html() -> str:
    partes = [
        "<!DOCTYPE html>",
        '<html lang="pt-BR"><head><meta charset="utf-8">',
        "<title>Giro — A3 Análise de Dados e Big Data</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        capa(),
        sumario(),
    ]

    for arquivo, _num in SECOES:
        caminho = RAIZ / "docs" / arquivo
        if not caminho.exists():
            partes.append(f"<p><em>[seção ausente: {arquivo}]</em></p>")
            continue
        partes.append(markdown_para_html(caminho.read_text(encoding="utf-8")))

    # Autorizacao da professora para o grupo de 7: se o arquivo existir,
    # entra como pagina final. O PDF e embutido em base64 para que o HTML
    # continue sendo um arquivo unico (o Edge headless nao carrega arquivo
    # local referenciado por <iframe> quando a origem e data: ou file:).
    anexo = anexo_autorizacao()
    if anexo:
        partes.append(anexo)

    partes += ["</body></html>"]
    return "\n".join(partes)


def anexo_autorizacao() -> str:
    """Pagina com a autorizacao da professora, se o arquivo existir."""
    import base64

    for nome in ("autorizacao-grupo.pdf", "autorizacao-grupo.png",
                 "autorizacao-grupo.jpg"):
        caminho = RAIZ / "docs" / nome
        if not caminho.exists():
            continue

        dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
        tipo = "pdf" if caminho.suffix == ".pdf" else "png" if caminho.suffix == ".png" else "jpeg"

        if tipo == "pdf":
            corpo = (f'<iframe src="data:application/pdf;base64,{dados}" '
                     f'style="width:100%;height:250mm;border:0"></iframe>')
        else:
            corpo = (f'<img src="data:image/{tipo};base64,{dados}" '
                     f'style="max-width:100%;max-height:250mm;display:block;'
                     f'margin:0 auto">')

        return f"""
        <div class="anexo">
          <h1 class="titulo-secao">Anexo — autorização do grupo</h1>
          <p class="anexo__nota">Documento da professora autorizando a
          composição do grupo com sete integrantes.</p>
          {corpo}
        </div>"""
    return ""


def achar_edge() -> Path | None:
    """Localiza um browser Chromium para gerar o PDF.

    Ordem: caminhos conhecidos do Windows (Edge, Chrome), depois PATH e
    shutil.which. A versao anterior so olhava dois caminhos fixos do Edge
    - numa maquina sem Edge nesses diretorios, a regeneracao falhava sem
    alternativa e sem instrucao de como resolver.
    """
    import shutil

    candidatos = list(EDGE_PATHS) + [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidatos:
        if Path(p).exists():
            return Path(p)

    for nome in ("msedge", "chrome", "chromium", "chromium-browser"):
        achado = shutil.which(nome)
        if achado:
            return Path(achado)
    return None


def gerar_pdf(saida: Path, manter_html: bool = False) -> bool:
    edge = achar_edge()
    if edge is None:
        print("ERRO: browser Chromium nao encontrado.")
        print("  Instale o Microsoft Edge (padrao no Windows) ou o Google Chrome.")
        print("  O PDF ja gerado esta em docs/; isto so afeta a regeneracao.")
        return False

    doc_html = construir_html()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        html_file = tmp_path / "relatorio.html"
        html_file.write_text(doc_html, encoding="utf-8")

        if manter_html:
            (RAIZ / "docs" / "relatorio-final.html").write_text(
                doc_html, encoding="utf-8")

        saida.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(edge),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=10000",
            f"--print-to-pdf={saida}",
            html_file.as_uri(),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)

    if not saida.exists():
        print(f"ERRO ao gerar PDF: {r.stderr[:500]}")
        return False

    tamanho = saida.stat().st_size / 1024
    print(f"PDF gerado: {saida}")
    print(f"  {tamanho:.0f} KB")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=None)
    ap.add_argument("--html", action="store_true",
                    help="tambem salva o HTML intermediario")
    args = ap.parse_args()

    destino = Path(args.saida) if args.saida else (
        RAIZ / "docs" / "relatorio-final.pdf")

    print("Gerando relatorio final...")
    ok = gerar_pdf(destino, manter_html=args.html)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
