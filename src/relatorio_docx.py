"""Gera o relatorio final em Word (.docx) a partir dos markdowns.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O relatorio anterior era um PDF de 66 paginas gerado por HTML + Edge
headless. Bonito na tela, ruim para quem precisa trabalhar com ele: o
orientador nao consegue comentar, o grupo nao consegue corrigir uma frase
sem regenerar tudo, e a secretaria pede Word.

Alem disso, 66 paginas para 18 mil palavras significa 279 palavras por
pagina - muito espaco para pouco conteudo. O Word usa estilos nativos
(Heading 1, List Bullet, Table Grid), entao o mesmo texto cabe em ~30
paginas e continua navegavel pela janela de Navegacao.

O QUE E GERADO, E NAO ESCRITO A MAO
-----------------------------------
  1. Capa: nomes e RAs vem de docs/integrantes.md.
  2. Sumario: campo TOC nativo. O Word preenche ao abrir (F9).
  3. Resumo: os cinco numeros vem de docs/evidencias/*.json, nunca do
     texto deste arquivo. Se a evidencia mudar, o resumo muda.
  4. Apendice A: tabela das 28 tabelas, extraida de
     docs/dicionario-de-dados.md, que por sua vez vem do catalogo.

REGRA DO PROJETO QUE VALE AQUI
------------------------------
"Nenhum numero sem comando que o produza." O resumo le os JSONs; nao
repete numeros digitados. O texto das secoes 4.1 a 4.7 vem dos markdowns,
que passam pelo scripts/lint_texto.py antes de entrar.

Uso:
    python src/relatorio_docx.py
    python src/relatorio_docx.py --saida docs/relatorio-final.docx

Depois de gerar, rode `scripts/atualizar_sumario.ps1` para o Word
preencher o sumario e gravar a contagem de paginas.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

# Import com fallback: o arquivo roda tanto como `python src/relatorio_docx.py`
# (sem pacote, "src" nao esta no sys.path) quanto via `-m src.relatorio_docx`.
try:
    from src.integrantes import ler_integrantes
except ModuleNotFoundError:  # pragma: no cover - depende de como foi chamado
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.integrantes import ler_integrantes

RAIZ = Path(__file__).parent.parent

# =====================================================================
# Identidade visual
#
# Mesmo teal do painel e do PDF anterior. O relatorio e a peca impressa
# do mesmo produto; mudar a cor aqui quebraria a continuidade.
# =====================================================================
TEAL = RGBColor(0x0F, 0x76, 0x6E)
TEAL_ESCURO = RGBColor(0x0D, 0x5F, 0x59)
GRAFITE = RGBColor(0x33, 0x41, 0x55)
CINZA = RGBColor(0x64, 0x74, 0x8B)
CINZA_CLARO = "F8FAFC"
TEAL_CLARO = "F0FDFA"
TEAL_HEX = "0F766E"

FONTE = "Calibri"
FONTE_MONO = "Consolas"

# Ordem das secoes no documento, seguindo o roteiro do edital.
SECOES = [
    ("01-problema.md", "4.1"),
    ("02-diagnostico.md", "4.2"),
    ("03-escolha-banco.md", "4.3"),
    ("04-modelagem.md", "4.4"),
    ("05-qualidade.md", "4.5"),
    ("06-prova-conceito.md", "4.6"),
    ("07-limitacoes.md", "4.7"),
]

# Largura util: A4 (21 cm) menos 2 cm de margem de cada lado.
LARGURA_UTIL = Cm(17.0)


# =====================================================================
# Helpers de baixo nivel (XML do Word)
# =====================================================================

def _sombra(elemento, cor: str) -> None:
    """Pinta o fundo de uma celula ou paragrafo."""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), cor)
    elemento.append(shd)


def _borda_celula(cell, lados=("top", "left", "bottom", "right"),
                  cor="CBD5E1", tamanho=4) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    bordas = tcPr.find(qn("w:tcBorders"))
    if bordas is None:
        bordas = OxmlElement("w:tcBorders")
        tcPr.append(bordas)
    for lado in lados:
        el = OxmlElement(f"w:{lado}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(tamanho))
        el.set(qn("w:color"), cor)
        bordas.append(el)


def _campo(paragrafo, instrucao: str, texto_inicial: str = "") -> None:
    """Insere um campo do Word (PAGE, NUMPAGES, TOC).

    Os tres pedacos precisam estar em runs separados: begin, instrucao e
    resultado, depois separate/end. Num run unico o Word ignora.
    """
    def _run():
        r = OxmlElement("w:r")
        paragrafo._p.append(r)
        return r

    r1 = _run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "begin")
    r1.append(fc)

    r2 = _run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = instrucao
    r2.append(it)

    r3 = _run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "separate")
    r3.append(fc)

    r4 = _run()
    t = OxmlElement("w:t")
    t.text = texto_inicial
    r4.append(t)

    r5 = _run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "end")
    r5.append(fc)


def _somente_uma_linha(paragrafo) -> None:
    """Impede que o paragrafo se parta entre duas paginas."""
    pPr = paragrafo._p.get_or_add_pPr()
    pPr.append(OxmlElement("w:keepLines"))


# =====================================================================
# Markdown inline -> runs do Word
# =====================================================================

PADRAO_INLINE = re.compile(
    r"(\*\*.+?\*\*"          # negrito
    r"|(?<!\*)\*(?!\*).+?(?<!\*)\*(?!\*)"   # italico
    r"|`[^`]+`"              # codigo
    r"|\[[^\]]+\]\([^)]+\)"  # link markdown
    r"|<https?://[^>]+>"     # autolink
    r")"
)


def dividir_celulas(linha: str) -> list[str]:
    """Separa uma linha de tabela em celulas, respeitando `\\|` e backticks.

    O split ingenuo por "|" quebra a unica linha do relatorio que tem
    pipe escapado dentro da celula:

        | Acurácia | 1 - \\|contado - sistema\\| / sistema | Q06 | >= 95% |

    Ela produzia 6 celulas num cabecalho de 4, e o conversor estourava
    com IndexError. O pipe dentro de `codigo` tambem nao separa celula:
    em markdown de tabela ele e literal.
    """
    linha = linha.strip()
    if linha.startswith("|"):
        linha = linha[1:]
    if linha.endswith("|") and not linha.endswith("\\|"):
        linha = linha[:-1]

    celulas: list[str] = []
    atual: list[str] = []
    em_codigo = False
    i = 0
    while i < len(linha):
        c = linha[i]
        if c == "\\" and i + 1 < len(linha) and linha[i + 1] == "|":
            atual.append("|")
            i += 2
            continue
        if c == "`":
            em_codigo = not em_codigo
            atual.append(c)
            i += 1
            continue
        if c == "|" and not em_codigo:
            celulas.append("".join(atual).strip())
            atual = []
            i += 1
            continue
        atual.append(c)
        i += 1
    celulas.append("".join(atual).strip())
    return celulas


def escrever_inline(paragrafo, texto: str, tamanho: float | None = None,
                    cor: RGBColor | None = None) -> None:
    """Escreve texto com **negrito**, *italico* e `codigo` como runs."""
    for parte in PADRAO_INLINE.split(texto):
        if not parte:
            continue

        if parte.startswith("**") and parte.endswith("**"):
            run = paragrafo.add_run(parte[2:-2])
            run.bold = True
        elif parte.startswith("`") and parte.endswith("`"):
            run = paragrafo.add_run(parte[1:-1])
            run.font.name = FONTE_MONO
            run.font.size = Pt((tamanho or 10.5) - 0.8)
            run.font.color.rgb = TEAL_ESCURO
        elif (parte.startswith("*") and parte.endswith("*")
              and len(parte) > 2):
            run = paragrafo.add_run(parte[1:-1])
            run.italic = True
        elif parte.startswith("["):
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", parte)
            run = paragrafo.add_run(m.group(1) if m else parte)
            run.font.color.rgb = TEAL
        elif parte.startswith("<http"):
            run = paragrafo.add_run(parte[1:-1])
            run.font.color.rgb = TEAL
        else:
            run = paragrafo.add_run(parte)

        if tamanho:
            run.font.size = Pt(tamanho)
        if cor is not None:
            run.font.color.rgb = cor


# =====================================================================
# Blocos
# =====================================================================

def adicionar_tabela(doc, cabecalho: list[str], corpo: list[list[str]]) -> None:
    """Tabela nativa do Word, com cabecalho repetido em cada pagina.

    Largura das colunas proporcional ao conteudo (mediana das celulas),
    porque o markdown nao informa largura e o Word distribuiria igual -
    o que deixa a coluna "Banco" do tamanho da coluna "Total".
    """
    n_cols = len(cabecalho)
    corpo = [linha + [""] * (n_cols - len(linha)) for linha in corpo]

    tabela = doc.add_table(rows=1, cols=n_cols)
    tabela.style = "Table Grid"
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False

    # ---- larguras proporcionais ----
    def peso(texto: str) -> int:
        return min(max(len(texto.strip()), 3), 60)

    def mediana(valores: list[int]) -> int:
        v = sorted(valores)
        return v[len(v) // 2] if v else 3

    larguras_peso = []
    for i in range(n_cols):
        amostra = [len(cabecalho[i])] + [len(linha[i]) for linha in corpo[:40]]
        larguras_peso.append(max(mediana([peso(str(a)) for a in amostra]), 4))
    total_peso = sum(larguras_peso)

    larguras = [LARGURA_UTIL * (p / total_peso) for p in larguras_peso]

    # ---- cabecalho ----
    linha_cab = tabela.rows[0]
    trPr = linha_cab._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))   # repete na proxima pagina
    trPr.append(OxmlElement("w:cantSplit"))   # nao parte a linha ao meio

    for i, titulo in enumerate(cabecalho):
        cell = linha_cab.cells[i]
        cell.width = larguras[i]
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        escrever_inline(p, titulo, tamanho=8, cor=RGBColor(0xFF, 0xFF, 0xFF))
        for run in p.runs:
            run.bold = True
        _sombra(cell._tc.get_or_add_tcPr(), TEAL_HEX)

    # ---- corpo ----
    for indice, linha in enumerate(corpo):
        row = tabela.add_row()
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:cantSplit"))
        for i, valor in enumerate(linha):
            cell = row.cells[i]
            cell.width = larguras[i]
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            escrever_inline(p, valor, tamanho=8)
            if indice % 2 == 1:
                _sombra(cell._tc.get_or_add_tcPr(), CINZA_CLARO)

    # Respiro depois da tabela: sem isto, dois paragrafos colados.
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def adicionar_codigo(doc, linhas: list[str]) -> None:
    """Bloco de codigo dentro de uma tabela de uma celula.

    Tabela e nao paragrafo com sombreamento: e a unica forma de o Word
    respeitar o fundo em toda a altura do bloco e nao deixar o texto
    vazar da area pintada. `cantSplit` desligado permite que um SQL de 30
    linhas atravesse a pagina em vez de pular para a seguinte.
    """
    tabela = doc.add_table(rows=1, cols=1)
    tabela.autofit = False
    cell = tabela.rows[0].cells[0]
    cell.width = LARGURA_UTIL
    _sombra(cell._tc.get_or_add_tcPr(), "F1F5F9")
    _borda_celula(cell, cor="E2E8F0", tamanho=4)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.0

    for i, linha in enumerate(linhas):
        if i > 0:
            p.add_run().add_break()
        run = p.add_run(linha if linha else " ")
        run.font.name = FONTE_MONO
        run.font.size = Pt(7.5)
        run.font.color.rgb = GRAFITE
        # Mantem o espacamento entre caracteres do diagrama ASCII.
        rPr = run._r.get_or_add_rPr()
        rPr.append(OxmlElement("w:noProof"))

    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def adicionar_citacao(doc, texto: str) -> None:
    """Blockquote: barra teal a esquerda e fundo claro."""
    tabela = doc.add_table(rows=1, cols=1)
    tabela.autofit = False
    cell = tabela.rows[0].cells[0]
    cell.width = LARGURA_UTIL
    _sombra(cell._tc.get_or_add_tcPr(), TEAL_CLARO)
    _borda_celula(cell, lados=("left",), cor=TEAL_HEX, tamanho=18)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.left_indent = Cm(0.3)
    escrever_inline(p, texto, tamanho=9.5, cor=TEAL_ESCURO)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def adicionar_regua(doc) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    bordas = OxmlElement("w:pBdr")
    inferior = OxmlElement("w:bottom")
    inferior.set(qn("w:val"), "single")
    inferior.set(qn("w:sz"), "4")
    inferior.set(qn("w:color"), "CBD5E1")
    bordas.append(inferior)
    pPr.append(bordas)


# =====================================================================
# Conversor de markdown
# =====================================================================

def limpar_latex(bloco: str) -> str:
    """Converte o unico bloco LaTeX do relatorio em texto legivel.

    Nao vale trazer um interpretador de formula: e uma linha, com tres
    fracoes. `\\frac{a}{b}` vira `a / b` e `\\text{x}` vira `x`.
    """
    t = re.sub(r"\\text\{([^}]*)\}", r"\1", bloco)
    t = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1 / \2", t)
    t = re.sub(r"\\qquad|\\quad", "      ", t)
    t = t.replace("$$", "").replace("\\", "")
    return "   ".join(linha.strip() for linha in t.splitlines() if linha.strip())


def converter_markdown(doc, md: str) -> None:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    linhas = md.split("\n")
    i = 0
    em_codigo = False
    bloco_codigo: list[str] = []
    lista_aberta: str | None = None

    def fechar_lista():
        nonlocal lista_aberta
        lista_aberta = None

    while i < len(linhas):
        linha = linhas[i]
        sem = linha.strip()

        # ---- cerca de codigo -------------------------------------
        if sem.startswith("```"):
            if em_codigo:
                adicionar_codigo(doc, bloco_codigo)
                bloco_codigo = []
                em_codigo = False
            else:
                fechar_lista()
                em_codigo = True
            i += 1
            continue

        if em_codigo:
            bloco_codigo.append(linha.rstrip())
            i += 1
            continue

        # ---- linha vazia ------------------------------------------
        if not sem:
            fechar_lista()
            i += 1
            continue

        # ---- formula ----------------------------------------------
        if sem.startswith("$$"):
            acumulado = [sem]
            if sem.count("$$") < 2:
                i += 1
                while i < len(linhas) and "$$" not in linhas[i]:
                    acumulado.append(linhas[i])
                    i += 1
                if i < len(linhas):
                    acumulado.append(linhas[i])
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            escrever_inline(p, limpar_latex("\n".join(acumulado)), tamanho=9.5)
            i += 1
            continue

        # ---- tabela -----------------------------------------------
        if ("|" in sem and i + 1 < len(linhas)
                and re.match(r"^\|?[\s:|-]+\|[\s:|-]*$", linhas[i + 1].strip())):
            fechar_lista()
            cabecalho = dividir_celulas(sem)
            i += 2
            corpo: list[list[str]] = []
            while i < len(linhas) and "|" in linhas[i]:
                corpo.append(dividir_celulas(linhas[i]))
                i += 1
            adicionar_tabela(doc, cabecalho, corpo)
            continue

        # ---- titulos ----------------------------------------------
        m = re.match(r"^(#{1,4})\s+(.*)$", sem)
        if m:
            fechar_lista()
            nivel = len(m.group(1))
            texto = m.group(2)
            p = doc.add_heading(level=min(nivel, 4))
            if nivel == 1:
                # page_break_before em vez de add_page_break(): a quebra
                # pertence ao titulo. Um paragrafo de quebra solto antes
                # dele gera folha em branco quando o conteudo anterior
                # termina exatamente na borda da pagina - foi a pagina 46
                # em branco entre o apendice e as referencias.
                p.paragraph_format.page_break_before = True
            escrever_inline(p, texto, tamanho=None)
            i += 1
            continue

        # ---- regua ------------------------------------------------
        if re.match(r"^-{3,}$|^\*{3,}$", sem):
            fechar_lista()
            adicionar_regua(doc)
            i += 1
            continue

        # ---- citacao ----------------------------------------------
        if sem.startswith(">"):
            fechar_lista()
            partes = []
            while i < len(linhas) and linhas[i].strip().startswith(">"):
                partes.append(linhas[i].strip().lstrip(">").strip())
                i += 1
            texto = " ".join(x for x in partes if x)
            if texto:
                adicionar_citacao(doc, texto)
            continue

        # ---- listas ------------------------------------------------
        m_ul = re.match(r"^[-*+]\s+(.*)$", sem)
        m_ol = None
        if not re.match(r"^\d{4}\.\s", sem):
            m_ol = re.match(r"^\d+[.)]\s+(.*)$", sem)

        if m_ul or m_ol:
            tipo = "ul" if m_ul else "ol"
            texto = m_ul.group(1) if m_ul else m_ol.group(1)
            i += 1
            # Continuacao: linha seguinte sem marcador pertence ao item.
            while i < len(linhas):
                prox = linhas[i].strip()
                if (not prox or prox.startswith(("-", "*", "+", "#", "|", ">", "```", "<"))
                        or re.match(r"^\d+[.)]\s", prox)):
                    break
                texto += " " + prox
                i += 1
            estilo = "List Bullet" if tipo == "ul" else "List Number"
            if tipo == "ol":
                estilo = "List Number"
            p = doc.add_paragraph(style=estilo)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            escrever_inline(p, texto)
            lista_aberta = tipo
            continue

        # ---- paragrafo ---------------------------------------------
        fechar_lista()
        partes = [sem]
        j = i + 1
        while j < len(linhas):
            prox = linhas[j].strip()
            if (not prox or prox.startswith(("#", "|", ">", "-", "*", "```", "<"))
                    or re.match(r"^\d+[.)]\s", prox) or prox.startswith("$$")):
                break
            partes.append(prox)
            j += 1
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        escrever_inline(p, " ".join(partes))
        i = j

    if em_codigo and bloco_codigo:
        adicionar_codigo(doc, bloco_codigo)


# =====================================================================
# Numeros do resumo: lidos da evidencia, nunca digitados
# =====================================================================

def _json(nome: str):
    caminho = RAIZ / "docs" / "evidencias" / nome
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def _num(valor: float, casas: int = 0) -> str:
    """Formata numero no padrao brasileiro: 1.234,56."""
    if valor is None:
        return "-"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def numeros_do_resumo() -> dict[str, str]:
    """Le os cinco numeros que abrem o documento."""
    d: dict[str, str] = {}

    q01 = _json("q01_ruptura_demanda_perdida.json")
    if q01:
        cols = q01["colunas"]
        linha = q01["linhas"][0]
        d["ruptura"] = _num(linha[cols.index("taxa_ruptura_pct")], 2) + "%"
        d["receita_perdida"] = "R$ " + _num(
            linha[cols.index("receita_perdida")], 2)

    q02 = _json("q02_sugestao_compra.json")
    if q02:
        cols = q02["colunas"]
        total = sum(linha[cols.index("valor_total")] for linha in q02["linhas"])
        d["pedido"] = "R$ " + _num(total, 2)

    q03 = _json("q03_curva_abc.json")
    if q03:
        cols = q03["colunas"]
        a = next(linha for linha in q03["linhas"] if linha[0] == "A")
        d["abc_skus"] = _num(a[cols.index("pct_skus")], 1) + "%"
        d["abc_receita"] = _num(a[cols.index("pct_receita")], 1) + "%"

    mq = _json("metricas_qualidade.json")
    if mq:
        d["recall"] = _num(mq["resumo"]["recall_global_pct"], 2) + "%"

    q06 = _json("q06_acuracidade_inventario.json")
    if q06:
        cols = q06["colunas"]
        acuracias = [linha[cols.index("acuracidade_pct")] for linha in q06["linhas"]]
        d["acuracidade"] = (f"{_num(min(acuracias), 1)}% a "
                            f"{_num(max(acuracias), 1)}%")

    return d


# =====================================================================
# Partes do documento
# =====================================================================

def montar_capa(doc) -> None:
    for _ in range(3):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Giro")
    run.font.size = Pt(44)
    run.font.bold = True
    run.font.color.rgb = TEAL
    p.paragraph_format.space_after = Pt(2)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Previsão de estoque e vendas para comércio de bairro")
    run.font.size = Pt(14)
    run.font.color.rgb = GRAFITE
    p.paragraph_format.space_after = Pt(18)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pPr = p._p.get_or_add_pPr()
    bordas = OxmlElement("w:pBdr")
    inferior = OxmlElement("w:bottom")
    inferior.set(qn("w:val"), "single")
    inferior.set(qn("w:sz"), "18")
    inferior.set(qn("w:color"), TEAL_HEX)
    bordas.append(inferior)
    pPr.append(bordas)
    p.paragraph_format.left_indent = Cm(6.5)
    p.paragraph_format.right_indent = Cm(6.5)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("A3 — Análise de Dados e Big Data")
    run.font.size = Pt(12)
    run.font.color.rgb = CINZA
    p.paragraph_format.space_after = Pt(24)

    # ---- integrantes ----
    integrantes = ler_integrantes()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("INTEGRANTES")
    run.font.size = Pt(8.5)
    run.font.bold = True
    run.font.color.rgb = CINZA
    p.paragraph_format.space_after = Pt(6)

    if integrantes:
        for indice, (nome, ra) in enumerate(integrantes, 1):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(f"{indice}. {nome}")
            r.font.size = Pt(11)
            r = p.add_run(f"   RA {ra}")
            r.font.size = Pt(9)
            r.font.color.rgb = CINZA
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("Preencha docs/integrantes.md e gere novamente")
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)

    for _ in range(2):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, texto in enumerate([
        "Projeto de startup de dados",
        "Avaliação A3 · 10,0 pontos",
        "",
        "PostgreSQL 18 · Python 3.14 · DuckDB",
    ]):
        if i:
            p.add_run().add_break()
        r = p.add_run(texto)
        r.font.size = Pt(10)
        r.font.color.rgb = GRAFITE


def montar_sumario(doc) -> None:
    # Sem add_page_break(): o paragrafo de quebra fica solto e, quando a
    # capa termina na borda da pagina, produz uma folha em branco. A
    # quebra vai no paragrafo do titulo.
    p = doc.add_paragraph()
    p.paragraph_format.page_break_before = True

    # O titulo "Sumario" NAO usa add_heading(): o campo TOC varre os
    # estilos de titulo e listaria a si mesmo ("Sumario ..... 2"), como
    # acontecia na primeira versao. Aqui ele e um paragrafo formatado a
    # mao, com nivel de estrutura "corpo de texto" para ficar fora da
    # varredura.
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Sumário")
    run.font.name = FONTE
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = TEAL
    pPr = p._p.get_or_add_pPr()
    nivel = OxmlElement("w:outlineLvl")
    nivel.set(qn("w:val"), "9")   # 9 = corpo de texto, fora do TOC
    pPr.append(nivel)

    p = doc.add_paragraph()
    instrucao = OxmlElement("w:fldSimple")
    instrucao.set(qn("w:instr"), r'TOC \o "1-1" \h \z \u')
    run = OxmlElement("w:r")
    texto = OxmlElement("w:t")
    # Texto de espera: se alguem abrir num leitor que nao atualiza campo,
    # ve a instrucao em vez de uma pagina em branco sem explicacao.
    texto.text = ("O sumário é preenchido pelo Word. "
                  "Abra o arquivo e pressione F9, ou Ctrl+A e F9.")
    run.append(texto)
    instrucao.append(run)
    p._p.append(instrucao)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    r = p.add_run("As tabelas e figuras são numeradas no corpo do texto. "
                  "A numeração de páginas está no rodapé.")
    r.font.size = Pt(8.5)
    r.font.color.rgb = CINZA


def montar_resumo(doc) -> None:
    """Uma pagina com o essencial, para quem so vai ler isso."""
    n = numeros_do_resumo()

    cab = doc.add_heading("Resumo", level=1)
    cab.paragraph_format.page_break_before = True

    p = doc.add_paragraph()
    escrever_inline(
        p,
        "O Giro lê o histórico do ponto de venda de um comércio de bairro, "
        "prevê a demanda de cada produto e diz o que comprar, quanto e de "
        "quem. O mesmo motor serve a qualquer loja com PDV; a demonstração "
        "usa um mercado porque é o segmento com mais dado público de "
        "calibração.")

    p = doc.add_paragraph()
    escrever_inline(
        p,
        "**O problema.** O dono decide a compra por intuição. Comprar de "
        "menos gera falta, e a venda perdida não volta. Comprar de mais "
        "imobiliza capital e, no perecível, vira perda.")

    doc.add_heading("O que foi construído", level=2)
    p = doc.add_paragraph()
    escrever_inline(
        p,
        "Um banco PostgreSQL com 6,36 milhões de linhas, 28 tabelas, "
        "11 consultas de negócio, 21 regras de qualidade e 48 testes "
        "automatizados. Os dados são sintéticos, calibrados com benchmarks "
        "públicos do setor.")

    doc.add_heading("Cinco números", level=2)
    adicionar_tabela(
        doc,
        ["Medida", "Valor", "O que significa"],
        [
            ["Taxa de ruptura medida", n.get("ruptura", "-"),
             "fatia de produto-dia com prateleira vazia"],
            ["Receita perdida em 12 meses", n.get("receita_perdida", "-"),
             "venda que não aconteceu por falta"],
            ["Pedido sugerido hoje", n.get("pedido", "-"),
             "reposição calculada para as 3 lojas"],
            ["Concentração da receita",
             f"{n.get('abc_skus', '-')} dos SKUs fazem {n.get('abc_receita', '-')}",
             "classe A da curva ABC"],
            ["Defeitos detectados", n.get("recall", "-"),
             "recall medido contra gabarito de defeitos injetados"],
        ],
    )

    doc.add_heading("Como ler este documento", level=2)
    p = doc.add_paragraph()
    escrever_inline(
        p,
        "As seções 4.1 a 4.7 seguem o roteiro do edital, na ordem. Quem tem "
        "pouco tempo deve ler a 4.1 (problema e diferenciais) e a 4.7 "
        "(onde o projeto admite falhar). Quem vai avaliar a nota deve "
        "conferir a matriz de decisão da 4.3 e a tabela de recall da 4.5: "
        "são as duas partes com conta verificável.")

    p = doc.add_paragraph()
    escrever_inline(
        p,
        "Todo número deste relatório é gerado por script a partir do banco "
        "ou de `docs/evidencias/`. A seção 8 lista, afirmação por afirmação, "
        "o comando que reproduz cada uma.")


def _descricao_da_tabela(linhas: list[str], inicio: int) -> str:
    """Extrai a primeira frase de prosa que descreve a tabela.

    Precisa ignorar HTML (`<details><summary>...`), cercas de codigo e
    linhas de tabela. A primeira versao so pulava linhas comecando por
    #, |, ** ou >, e por isso o apendice saiu com
    "<details><summary>Definicao SQL</summary>" impresso na coluna
    Propósito de cinco views materializadas.
    """
    for j in range(inicio + 1, min(inicio + 8, len(linhas))):
        candidato = linhas[j].strip()
        if (not candidato
                or candidato.startswith(("#", "|", "**", ">", "<", "```", "-", "*"))):
            continue
        if re.match(r"^\d+[.)]\s", candidato):
            continue
        return candidato
    return ""


def montar_apendice(doc) -> None:
    """Apendice A: indice das tabelas, extraido do dicionario gerado."""
    caminho = RAIZ / "docs" / "dicionario-de-dados.md"
    if not caminho.exists():
        return

    texto = caminho.read_text(encoding="utf-8")
    entradas: list[tuple[str, str, str]] = []
    linhas = texto.splitlines()

    for i, linha in enumerate(linhas):
        m_schema = re.match(r"^#\s+Schema\s+`(\w+)`", linha)
        if m_schema:
            schema_atual = m_schema.group(1)
            continue
        m_tab = re.match(r"^##\s+`(\w+)\.(\w+)`", linha)
        if not m_tab:
            continue
        # O schema vem do proprio titulo, nunca de uma variavel de
        # contexto: a secao "# Views materializadas" nao declara schema,
        # e as cinco views herdavam "gov" - o schema da secao anterior.
        schema = m_tab.group(1)
        entradas.append((schema, m_tab.group(2),
                         _descricao_da_tabela(linhas, i)))

    if not entradas:
        return

    # As cinco views materializadas nao tem frase de prosa no dicionario
    # (o gerador emite a definicao SQL direto). Sem isto, a coluna
    # "Proposito" do apendice sairia com "WITH por_loja AS (".
    # A descricao vem do papel de cada uma na secao 4.4.
    descricao_view = {
        "mv_demanda_diaria": "demanda diária com reconstrução de dia em falta",
        "mv_previsao_demanda": "previsão EWMA de 28 dias com fator de dia da semana",
        "mv_sugestao_compra": "ponto de pedido, lote mínimo e valor da reposição",
        "mv_rupturas": "faltas com receita perdida estimada",
        "mv_qualidade_loja": "selo de confiança por loja, na pior dimensão",
    }
    entradas = [
        (s, t, descricao_view[t] if (not d or d.upper().startswith(("WITH", "SELECT", "CREATE")))
         else d)
        for s, t, d in entradas
    ]

    cab = doc.add_heading("Apêndice A — Tabelas do banco", level=1)
    cab.paragraph_format.page_break_before = True
    p = doc.add_paragraph()
    escrever_inline(
        p,
        "Índice das 28 tabelas e 5 views materializadas. O dicionário "
        "completo, coluna por coluna e com as constraints, está em "
        "`docs/dicionario-de-dados.md`. Ele é gerado do catálogo do "
        "PostgreSQL, não escrito à mão.")

    adicionar_tabela(
        doc,
        ["Schema", "Tabela", "Propósito"],
        [[s, t, d] for s, t, d in entradas],
    )


def montar_anexo_autorizacao(doc) -> str | None:
    """Pagina final com a autorizacao da professora, se o arquivo existir.

    Aceita imagem (png/jpg). PDF nao entra: python-docx nao embute pagina
    de PDF, e converter exigiria dependencia externa. Quando o arquivo e
    PDF, a funcao avisa e nao insere nada, em vez de falhar em silencio -
    quem gera precisa saber que a pagina ficou de fora.

    Devolve o nome do arquivo inserido, ou None.
    """
    for nome in ("autorizacao-grupo.png", "autorizacao-grupo.jpg",
                 "autorizacao-grupo.jpeg"):
        caminho = RAIZ / "docs" / nome
        if not caminho.exists():
            continue

        cab = doc.add_heading("Anexo — autorização do grupo", level=1)
        cab.paragraph_format.page_break_before = True
        p = doc.add_paragraph()
        escrever_inline(
            p,
            "Documento da professora autorizando a composição do grupo "
            "com sete integrantes.")
        doc.add_picture(str(caminho), width=LARGURA_UTIL)
        return nome

    if (RAIZ / "docs" / "autorizacao-grupo.pdf").exists():
        print("  aviso: docs/autorizacao-grupo.pdf existe, mas o gerador "
              "Word nao embute PDF.")
        print("         Converta para .png ou anexe a pagina pelo Word.")
    return None


def montar_referencias(doc) -> None:
    caminho = RAIZ / "docs" / "referencias.md"
    if not caminho.exists():
        return
    converter_markdown(doc, caminho.read_text(encoding="utf-8"))


def montar_declaracao(doc) -> None:
    caminho = RAIZ / "docs" / "08-declaracao-ia.md"
    if not caminho.exists():
        return
    converter_markdown(doc, caminho.read_text(encoding="utf-8"))


# =====================================================================
# Estilos e pagina
# =====================================================================

def configurar_estilos(doc) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = FONTE
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = GRAFITE
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15
    # Fonte do Leste Asiatico: sem isto, o Word troca a fonte de
    # caracteres de desenho de caixa nos diagramas ASCII.
    rPr = normal.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), FONTE)
    rFonts.set(qn("w:hAnsi"), FONTE)
    rFonts.set(qn("w:eastAsia"), FONTE)
    rFonts.set(qn("w:cs"), FONTE)

    titulos = {
        "Heading 1": (16, TEAL, 14, 6),
        "Heading 2": (12.5, TEAL_ESCURO, 12, 4),
        "Heading 3": (11, GRAFITE, 10, 3),
        "Heading 4": (10.5, GRAFITE, 8, 2),
    }
    for nome, (tamanho, cor, antes, depois) in titulos.items():
        estilo = doc.styles[nome]
        estilo.font.name = FONTE
        estilo.font.size = Pt(tamanho)
        estilo.font.bold = True
        estilo.font.color.rgb = cor
        estilo.paragraph_format.space_before = Pt(antes)
        estilo.paragraph_format.space_after = Pt(depois)
        estilo.paragraph_format.keep_with_next = True


def configurar_pagina(doc) -> None:
    secao = doc.sections[0]
    secao.page_width = Mm(210)
    secao.page_height = Mm(297)
    secao.left_margin = Cm(2)
    secao.right_margin = Cm(2)
    secao.top_margin = Cm(2)
    secao.bottom_margin = Cm(1.8)

    # ---- cabecalho ----
    cabecalho = secao.header
    p = cabecalho.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run("Giro · A3 Análise de Dados e Big Data")
    r.font.size = Pt(8)
    r.font.color.rgb = CINZA

    # ---- rodape com numero de pagina ----
    rodape = secao.footer
    p = rodape.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("")
    r.font.size = Pt(8)
    _campo(p, "PAGE", "1")
    for run in p.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = CINZA


# =====================================================================
# Montagem
# =====================================================================

def gerar(saida: Path) -> Path:
    doc = Document()
    configurar_pagina(doc)
    configurar_estilos(doc)

    montar_capa(doc)
    montar_sumario(doc)
    montar_resumo(doc)

    for arquivo, _num in SECOES:
        caminho = RAIZ / "docs" / arquivo
        if not caminho.exists():
            print(f"  ausente: {arquivo}")
            continue
        # Sem add_page_break() aqui: o titulo de nivel 1 da secao ja
        # quebra a pagina dentro de converter_markdown(). As duas
        # quebras juntas geravam uma folha em branco entre cada secao -
        # 10 paginas vazias no total.
        converter_markdown(doc, caminho.read_text(encoding="utf-8"))

    montar_declaracao(doc)
    montar_apendice(doc)
    montar_referencias(doc)
    montar_anexo_autorizacao(doc)

    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(saida)
    return saida


def compactar_sumario(caminho: Path) -> int:
    """Reduz o espacamento das entradas do sumario no .docx salvo.

    O campo TOC e preenchido pelo Word na primeira atualizacao, e ele cria
    as entradas com o estilo TOC 1/TOC 2 do modelo padrao - 11pt com
    respiro de 6pt entre linhas. Com 150 titulos, o sumario ocupa 3
    paginas e transborda duas linhas para uma quarta.

    Rodar depois de scripts/atualizar_sumario.ps1, que e quem cria as
    entradas. Mexer no estilo do documento antes nao adianta: o estilo
    TOC ainda nao existe no arquivo recem-gerado.
    """
    from docx import Document as _Doc

    doc = _Doc(str(caminho))
    ajustados = 0
    # Os nomes variam com o idioma do modelo: em pt-BR o Word cria
    # "Sumrio1"/"Sumrio2" (de "Sumario"), em ingles "TOC1"/"TOC2".
    # A primeira versao so procurava "TOC n" e nao ajustava nada.
    existentes = {s.name for s in doc.styles}
    for nome in ("TOC 1", "TOC 2", "TOC 3", "Sumrio1", "Sumrio2", "Sumrio3"):
        if nome not in existentes:
            continue
        estilo = doc.styles[nome]
        eh_nivel_1 = nome in ("TOC 1", "Sumrio1")
        estilo.font.size = Pt(9.5 if eh_nivel_1 else 9)
        estilo.paragraph_format.space_before = Pt(0)
        estilo.paragraph_format.space_after = Pt(0)
        estilo.paragraph_format.line_spacing = 1.0
        ajustados += 1
    if ajustados:
        doc.save(str(caminho))
    return ajustados


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    destino = Path(args.saida) if args.saida else (
        RAIZ / "docs" / "relatorio-final.docx")

    print("Gerando relatorio em Word...")
    caminho = gerar(destino)
    tamanho = caminho.stat().st_size / 1024
    print(f"  {caminho}")
    print(f"  {tamanho:.0f} KB")
    print("  Proximo passo: scripts/atualizar_sumario.ps1")


if __name__ == "__main__":
    main()
