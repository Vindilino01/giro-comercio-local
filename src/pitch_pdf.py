"""
Gera os slides do pitch em PDF (16:9), a partir de HTML + Edge headless.

POR QUE HTML E NAO PPTX
-----------------------
  1. Controle tipografico total (PPTX depende de fonte instalada).
  2. Zero dependencia: Edge ja esta em qualquer Windows.
  3. O PDF e o formato de apresentacao; o HTML fica como fonte
     editavel se o grupo precisar ajustar texto.

Uso:
    python src/pitch_pdf.py
"""

from __future__ import annotations

import html
import subprocess
import tempfile
from pathlib import Path

RAIZ = Path(__file__).parent.parent

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


# =====================================================================
# Conteudo dos slides
# =====================================================================

SLIDES: list[dict] = [
    {
        "tipo": "capa",
        "titulo": "Giro",
        "subtitulo": "Previsão de estoque e vendas para pequenos mercados",
        "rodape": "A3 — Análise de Dados e Big Data",
    },
    {
        "tipo": "conteudo",
        "tempo": "0:00",
        "titulo": "O dono do mercadinho decide no feeling",
        "blocos": [
            ("problema", [
                "Compra de menos → **ruptura** → perde a venda e o cliente",
                "Compra de mais → **capital parado** ou **produto vencido**",
            ]),
            ("numeros", [
                ("10–12%", "das vendas perdidas por ruptura no varejo brasileiro<br><small>Neogrid, 2020–2024</small>"),
                ("2,79%", "de perda média de estoque no supermercado<br><small>ABRAPPE</small>"),
                ("8,3%", "de ruptura média global<br><small>Nielsen</small>"),
            ]),
        ],
        "fecho": "O dado para decidir já existe no PDV. Só não é usado.",
    },
    {
        "tipo": "conteudo",
        "tempo": "0:40",
        "titulo": "Diagnóstico: os 5 Vs",
        "blocos": [
            ("vs", [
                ("Volume", "6,36M linhas hoje<br>636M a 100×"),
                ("Velocidade", "0,3 cupons/s no pico<br>escrita trivial"),
                ("Variedade", "CSV, XML (NF-e), JSON"),
                ("Veracidade", "**o V crítico**<br>ruptura, EAN, estoque"),
                ("Valor", "R$ perdido quantificado"),
            ]),
        ],
        "destaque": "O padrão de acesso é assimétrico: escrita pequena e contínua, "
                    "leitura grande e esporádica.",
        "fecho": "É isso que define a escolha de banco.",
    },
    {
        "tipo": "conteudo",
        "tempo": "1:55",
        "titulo": "Escolha do banco: PostgreSQL",
        "blocos": [
            ("matriz", [
                ("Consistência ACID", "25%", "5"),
                ("Adequação à consulta", "20%", "4"),
                ("Manutenção", "15%", "5"),
                ("Custo", "15%", "5"),
                ("Maturidade", "10%", "5"),
                ("Escalabilidade", "10%", "4"),
                ("Latência", "5%", "4"),
            ]),
            ("alternativas", [
                ("MongoDB", "estoque exige invariante transacional"),
                ("Cassandra", "consistência eventual ≠ estoque"),
                ("TimescaleDB", "consulta não é janela de sensor"),
                ("BigQuery", "custo imprevisível, não roda offline"),
                ("Redis", "cache não é fonte de verdade"),
                ("SQLite", "sem concorrência multi-loja"),
            ]),
        ],
        "nota": "Nota ponderada: **4,65 / 5,00** — vence nos critérios de maior peso.",
    },
    {
        "tipo": "conteudo",
        "tempo": "3:00",
        "titulo": "CAP: o erro que quase todo trabalho comete",
        "blocos": [
            ("erro", [
                "**Errado:** \"escolhemos CP\"",
                "O MVP é **nó único** — não é sistema distribuído, então CAP "
                "**não se aplica**.",
            ]),
            ("certo", [
                "**Correto:** análise condicional, por caminho",
                "Baixa de estoque → **CP**: recusar a venda é aceitável",
                "Dashboard → **AP**: número de 2 min atrás é aceitável",
            ]),
        ],
        "fecho": "É uma decisão por caminho, não do sistema.",
    },
    {
        "tipo": "conteudo",
        "tempo": "3:20",
        "titulo": "Modelagem: três camadas, três propósitos",
        "blocos": [
            ("camadas", [
                ("Bronze", "CSV imutável + SHA-256", "linhagem e reprocessamento"),
                ("Prata", "**3ª Forma Normal**", "fonte de verdade transacional"),
                ("Ouro", "**Star schema** + views", "consulta analítica"),
            ]),
            ("decisoes", [
                "**Surrogate + natural única** — sem a natural, reimportar duplica receita",
                "**Particionamento mensal** — 30 dias lê 1 partição, não 24 meses",
                "**`EXCLUDE USING gist`** — faixas de preço não se sobrepõem",
            ]),
        ],
        "destaque": "Bug real encontrado por teste: `UNIQUE` padrão trata `NULL` "
                    "como distinto → corrigido com `NULLS NOT DISTINCT`.",
    },
    {
        "tipo": "conteudo",
        "tempo": "4:40",
        "titulo": "Qualidade: medida, não declarada",
        "blocos": [
            ("metodo", [
                "Dois datasets da **mesma semente**: limpo e com defeitos",
                "**17 tipos** de defeito em quantidade conhecida",
                "Gabarito permite calcular **recall e precisão por regra**",
            ]),
            ("resultado", [
                ("96.61%", "recall global"),
                ("0,5–100%", "precisão (ver notas por regra)"),
                ("21", "regras em 7 dimensões"),
                ("0", "rejeições na carga limpa"),
            ]),
        ],
        "nota": "LGPD resolvida na **modelagem**: o Giro não coleta dado pessoal. "
                "Minimização, não política escrita.",
    },
    {
        "tipo": "conteudo",
        "tempo": "5:30",
        "titulo": "Três números que não são 100% — e por que isso é bom",
        "blocos": [
            ("casos", [
                ("DQ006", "50%", "O defeito afeta 2 registros (par de EANs "
                                 "iguais) e a dedupe mantém 1. **Rejeitar os dois "
                                 "seria pior**: descartaria o produto."),
                ("DQ020", "0,8%", "Precisão baixa porque cancelamento é "
                                  "**evento legítimo**, não corrupção: 27 cupons "
                                  "cancelados sem data geram 3.312 correções."),
                ("DQ005", "52%", "O injetor duplica em pares e a dedupe remove "
                                 "N−1 cópias. Precisão de 52% com **recall de "
                                 "100%** é o comportamento correto."),
            ]),
        ],
        "fecho": "Saber interpretar o próprio número separa medir de fingir que mediu.",
    },
    {
        "tipo": "demo",
        "tempo": "5:55",
        "titulo": "Demo ao vivo",
        "itens": [
            ("1", "**Ruptura** — quanto deixei de vender",
             "reconstrói a demanda truncada pela falta"),
            ("2", "**Sugestão de compra** — o que comprar hoje",
             "previsão + lead time + estoque de segurança + selo"),
            ("3", "**Curva ABC** — window function em 4,1M linhas",
             "70 ms, sem self-join"),
        ],
        "rodape": "Views materializadas em ms; varreduras do fato em segundos · EXPLAIN ANALYZE em docs/evidencias/",
    },
    {
        "tipo": "conteudo",
        "tempo": "7:40",
        "titulo": "E se crescermos 100×?",
        "blocos": [
            ("benchmark", [
                ("Varredura ampla", "**DuckDB 10,5× mais rápido**",
                 "lê só as colunas usadas"),
                ("Filtro seletivo", "**PostgreSQL 11,5× mais rápido**",
                 "usa índice B-tree"),
            ]),
            ("quebra", [
                "1. Dashboard (~30 lojas)",
                "2. Backup (~100 lojas)",
                "3. `REFRESH` das views (~100 lojas)",
                "4. **Escrita: nunca** — 30 inserts/s é trivial",
            ]),
        ],
        "destaque": "O **modelo de dados sobrevive intacto**. Muda infraestrutura, "
                    "não modelagem.",
    },
    {
        "tipo": "conteudo",
        "tempo": "8:20",
        "titulo": "O que não fizemos — e por quê",
        "blocos": [
            ("honesto", [
                "**Machine learning** — vale 0 ponto na rubrica; o diferencial "
                "está no tratamento da ruptura",
                "**Dashboard bonito** — o edital diz que não é o foco",
                "**Dados reais** — sintéticos calibrados; próximo passo é o "
                "dataset público Favorita",
                "**Tempo real** — a decisão de compra é semanal",
            ]),
        ],
        "fecho": "Escolher o que não fazer também é decisão de arquitetura.",
    },
    {
        "tipo": "fechamento",
        "tempo": "8:50",
        "titulo": "O que o Giro entrega",
        "itens": [
            ("Um banco que **recusa** dado ruim", "23 testes provam — evidência executável"),
            ("Um pipeline que **mede** a própria eficácia", "96.61% de recall em 17 tipos de defeito"),
            ("Uma decisão de banco **defensável**", "8 alternativas, matriz ponderada, CAP preciso"),
            ("Uma resposta de **negócio**", "quanto perco, o que comprar, posso confiar"),
        ],
        "rodape": "`python run_all.py` recria tudo em cerca de 30 minutos. Toda afirmação tem teste por trás.",
    },
]


CSS = """
@page { size: 338.7mm 190.5mm; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
    background: #0b1220;
}

.slide {
    width: 338.7mm;
    height: 190.5mm;
    padding: 16mm 22mm;
    background: #ffffff;
    page-break-after: always;
    position: relative;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.slide:last-child { page-break-after: auto; }

/* Marca d'agua lateral */
.slide::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 5mm;
    background: linear-gradient(180deg, #0f766e, #14b8a6);
}

.tempo {
    position: absolute;
    top: 8mm; right: 22mm;
    font-size: 9pt;
    color: #94a3b8;
    font-variant-numeric: tabular-nums;
}

h1 {
    font-size: 26pt;
    color: #0f172a;
    font-weight: 700;
    line-height: 1.15;
    letter-spacing: -0.5pt;
    margin-bottom: 9mm;
    max-width: 95%;
}
h1::after {
    content: '';
    display: block;
    width: 18mm;
    height: 1.2mm;
    background: #0f766e;
    margin-top: 4mm;
}

.conteudo { flex: 1; display: flex; gap: 10mm; }
.col { flex: 1; }

/* ---- Capa ---- */
.capa {
    justify-content: center;
    align-items: center;
    text-align: center;
    background: linear-gradient(135deg, #0b1220 0%, #0f766e 100%);
}
.capa::before { background: #14b8a6; width: 8mm; }
.capa h1 {
    font-size: 84pt;
    color: #ffffff;
    margin: 0 0 2mm 0;
    letter-spacing: -3pt;
}
.capa h1::after {
    width: 30mm; height: 2mm;
    background: #5eead4;
    margin: 5mm auto 0;
}
.capa .sub {
    font-size: 19pt;
    color: #a7f3d0;
    font-weight: 300;
    margin-top: 10mm;
    max-width: 200mm;
}
/* Integrantes na capa: nomes em linha, discretos, para a banca
   associar quem apresenta ao trabalho. */
.capa .integrantes {
    margin-top: 18mm;
    font-size: 10.5pt;
    color: #99f6e4;
    letter-spacing: .04em;
    max-width: 230mm;
    line-height: 1.7;
}
.capa .rodape {
    position: absolute;
    bottom: 20mm;
    font-size: 11pt;
    color: #5eead4;
    letter-spacing: 2pt;
    text-transform: uppercase;
}

/* ---- Números grandes ---- */
.numeros { display: flex; gap: 7mm; margin-top: 4mm; }
.numero-item { flex: 1; }
.numero-item .valor {
    font-size: 32pt;
    font-weight: 700;
    color: #0f766e;
    line-height: 1;
    display: block;
}
.numero-item .desc {
    font-size: 9pt;
    color: #475569;
    line-height: 1.4;
    margin-top: 2mm;
    display: block;
}
.numero-item .desc small { color: #94a3b8; font-size: 7.5pt; }

/* ---- Blocos ---- */
.bloco {
    background: #f8fafc;
    border-left: 2mm solid #0f766e;
    padding: 5mm 6mm;
    margin-bottom: 5mm;
    border-radius: 1.5mm;
}
.bloco.alerta { border-left-color: #dc2626; background: #fef2f2; }
.bloco.ok { border-left-color: #16a34a; background: #f0fdf4; }

.bloco h3 {
    font-size: 10pt;
    text-transform: uppercase;
    letter-spacing: 1pt;
    color: #64748b;
    margin-bottom: 3mm;
    font-weight: 600;
}

.bloco p, .bloco li {
    font-size: 12pt;
    line-height: 1.5;
    color: #1e293b;
    margin-bottom: 2mm;
}
.bloco ul { padding-left: 5mm; }
.bloco li { list-style: none; position: relative; padding-left: 5mm; }
.bloco li::before {
    content: '→';
    position: absolute;
    left: 0;
    color: #0f766e;
    font-weight: 700;
}
.bloco strong { color: #0f172a; font-weight: 700; }

/* ---- 5 Vs ---- */
.vs-grid { display: flex; gap: 5mm; }
.vs-item {
    flex: 1;
    background: #f8fafc;
    border-top: 1.5mm solid #0f766e;
    padding: 4mm 3mm;
    border-radius: 1.5mm;
    text-align: center;
}
.vs-item .nome {
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: .8pt;
    color: #0f766e;
    font-weight: 700;
    display: block;
    margin-bottom: 2.5mm;
}
.vs-item .desc {
    font-size: 8.5pt;
    color: #475569;
    line-height: 1.4;
}

/* ---- Matriz ---- */
.matriz { width: 100%; border-collapse: collapse; font-size: 10pt; }
.matriz th {
    text-align: left;
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: .8pt;
    color: #64748b;
    padding: 2mm 3mm;
    border-bottom: 1pt solid #cbd5e1;
}
.matriz td {
    padding: 2.2mm 3mm;
    border-bottom: .5pt solid #e2e8f0;
    color: #1e293b;
}
.matriz td.nota {
    text-align: center;
    font-weight: 700;
    color: #0f766e;
    font-variant-numeric: tabular-nums;
}

/* ---- Alternativas ---- */
.alt { display: flex; flex-wrap: wrap; gap: 3mm; }
.alt-item {
    background: #f1f5f9;
    padding: 2.5mm 4mm;
    border-radius: 1.5mm;
    font-size: 9pt;
    color: #334155;
    flex: 1 1 45%;
}
.alt-item .nome { font-weight: 700; color: #0f172a; display: block; }
.alt-item .motivo { font-size: 8pt; color: #64748b; }

/* ---- Camadas ---- */
.camadas { display: flex; flex-direction: column; gap: 3mm; }
.camada {
    display: flex;
    align-items: center;
    gap: 5mm;
    background: #f8fafc;
    padding: 3.5mm 5mm;
    border-radius: 1.5mm;
    border-left: 2mm solid #0f766e;
}
.camada .nome {
    font-weight: 700;
    font-size: 11pt;
    color: #0f766e;
    width: 22mm;
}
.camada .modelo { font-size: 10pt; color: #1e293b; flex: 1; }
.camada .papel { font-size: 8.5pt; color: #64748b; text-align: right; }

/* ---- Casos ---- */
.caso {
    display: flex;
    align-items: baseline;
    gap: 4mm;
    padding: 3mm 0;
    border-bottom: .5pt solid #e2e8f0;
}
.caso .cod {
    font-size: 9pt;
    font-weight: 700;
    color: #0f766e;
    width: 18mm;
}
.caso .pct {
    font-size: 20pt;
    font-weight: 700;
    color: #0f172a;
    width: 22mm;
    font-variant-numeric: tabular-nums;
}
.caso .txt { font-size: 10pt; color: #475569; line-height: 1.45; flex: 1; }

/* ---- Benchmark ---- */
.bench { display: flex; gap: 6mm; }
.bench-item {
    flex: 1;
    text-align: center;
    padding: 6mm;
    border-radius: 2mm;
    background: #f8fafc;
}
.bench-item.ganha { background: #f0fdf4; border: 1pt solid #16a34a; }
.bench-item .quem {
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 1pt;
    color: #64748b;
    display: block;
    margin-bottom: 2mm;
}
.bench-item .venc {
    font-size: 16pt;
    font-weight: 700;
    color: #16a34a;
    display: block;
    margin-bottom: 2mm;
}
.bench-item .por {
    font-size: 9pt;
    color: #475569;
}

/* ---- Demo ---- */
.demo-item {
    display: flex;
    gap: 5mm;
    align-items: flex-start;
    padding: 5mm 0;
    border-bottom: .5pt solid #e2e8f0;
}
.demo-item .n {
    font-size: 28pt;
    font-weight: 700;
    color: #14b8a6;
    line-height: 1;
    width: 14mm;
}
.demo-item .corpo { flex: 1; }
.demo-item .tit { font-size: 13pt; font-weight: 700; color: #0f172a; }
.demo-item .sub { font-size: 10pt; color: #64748b; margin-top: 1.5mm; }

/* ---- Fecho ---- */
.destaque {
    background: #f0fdfa;
    border-left: 2.5mm solid #0f766e;
    padding: 5mm 6mm;
    border-radius: 1.5mm;
    font-size: 12pt;
    line-height: 1.5;
    color: #134e4a;
    margin-top: auto;
}
.destaque strong { color: #0f766e; }

.fecho {
    margin-top: auto;
    padding-top: 5mm;
    font-size: 13pt;
    color: #0f766e;
    font-weight: 600;
    line-height: 1.4;
}

.nota {
    margin-top: auto;
    font-size: 11pt;
    color: #475569;
    line-height: 1.5;
    padding-top: 5mm;
}
.nota strong { color: #0f172a; }

.rodape-slide {
    position: absolute;
    bottom: 7mm;
    left: 22mm;
    right: 22mm;
    font-size: 9pt;
    color: #94a3b8;
    border-top: .5pt solid #e2e8f0;
    padding-top: 2.5mm;
}

/* ---- Fechamento ---- */
.entregas { display: flex; flex-direction: column; gap: 4mm; }
.entrega {
    display: flex;
    gap: 5mm;
    align-items: baseline;
    background: #f8fafc;
    padding: 4mm 5mm;
    border-radius: 1.5mm;
    border-left: 1.5mm solid #0f766e;
}
.entrega .tit { font-size: 12pt; font-weight: 700; color: #0f172a; flex: 1; }
.entrega .sub { font-size: 9.5pt; color: #64748b; text-align: right; }

/* Utilitário */
.mono {
    font-family: 'Cascadia Mono', Consolas, monospace;
    background: #f1f5f9;
    padding: 0.3mm 1.5mm;
    border-radius: 1mm;
    font-size: 0.92em;
    color: #0f766e;
}
"""


def _inline(texto: str) -> str:
    """Converte markdown inline (negrito, codigo) para HTML."""
    import re
    t = texto
    t = re.sub(r"`([^`]+)`", r'<span class="mono">\1</span>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    return t


def renderizar_slide(s: dict) -> str:
    tipo = s["tipo"]

    if tipo == "capa":
        # Nomes na capa: o pitch e apresentado por sete pessoas, e a banca
        # precisa associar quem esta falando ao trabalho. Se
        # docs/integrantes.md ainda estiver com os marcadores, a capa nao
        # imprime lista vazia nem placeholder - apenas omite o bloco.
        try:
            from src.relatorio_pdf import ler_integrantes
            nomes = " · ".join(n for n, _ in ler_integrantes())
        except Exception:  # noqa: BLE001
            nomes = ""
        bloco_nomes = (f'<div class="integrantes">{nomes}</div>'
                       if nomes else "")
        return f"""
        <section class="slide capa">
          <h1>{s['titulo']}</h1>
          <div class="sub">{s['subtitulo']}</div>
          {bloco_nomes}
          <div class="rodape">{s['rodape']}</div>
        </section>"""

    tempo = f'<div class="tempo">{s["tempo"]}</div>' if "tempo" in s else ""
    rodape = (f'<div class="rodape-slide">{s["rodape"]}</div>'
              if "rodape" in s else "")

    corpo: list[str] = []

    if tipo == "demo":
        for n, tit, sub in s["itens"]:
            corpo.append(f"""
            <div class="demo-item">
              <div class="n">{_inline(str(n))}</div>
              <div class="corpo">
                <div class="tit">{_inline(tit)}</div>
                <div class="sub">{_inline(sub)}</div>
              </div>
            </div>""")
        return f"""
        <section class="slide">
          {tempo}<h1>{_inline(s['titulo'])}</h1>
          <div class="conteudo"><div class="col">{''.join(corpo)}</div></div>
          {rodape}
        </section>"""

    if tipo == "fechamento":
        for tit, sub in s["itens"]:
            corpo.append(f"""
            <div class="entrega">
              <span class="tit">{_inline(tit)}</span>
              <span class="sub">{_inline(sub)}</span>
            </div>""")
        return f"""
        <section class="slide">
          {tempo}<h1>{_inline(s['titulo'])}</h1>
          <div class="conteudo"><div class="col">
            <div class="entregas">{''.join(corpo)}</div>
          </div></div>
          {rodape}
        </section>"""

    # ---- Slide de conteudo: blocos tipados ----
    colunas: list[list[str]] = []
    atual: list[str] = []

    for bloco in s.get("blocos", []):
        tipo_bloco, dados = bloco
        html_bloco = ""

        if tipo_bloco == "problema":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = f'<div class="bloco"><ul>{itens}</ul></div>'

        elif tipo_bloco == "numeros":
            itens = "".join(
                f'<div class="numero-item"><span class="valor">{_inline(v)}</span>'
                f'<span class="desc">{_inline(d)}</span></div>' for v, d in dados)
            html_bloco = f'<div class="numeros">{itens}</div>'

        elif tipo_bloco == "vs":
            itens = "".join(
                f'<div class="vs-item"><span class="nome">{_inline(n)}</span>'
                f'<span class="desc">{_inline(d)}</span></div>' for n, d in dados)
            html_bloco = f'<div class="vs-grid">{itens}</div>'

        elif tipo_bloco == "matriz":
            linhas = "".join(
                f'<tr><td>{_inline(c)}</td><td>{_inline(p)}</td><td class="nota">{_inline(n)}</td></tr>'
                for c, p, n in dados)
            html_bloco = (
                '<div class="bloco"><h3>Matriz de decisão</h3>'
                '<table class="matriz"><thead><tr>'
                '<th>Critério</th><th>Peso</th><th>Nota</th>'
                f'</tr></thead><tbody>{linhas}</tbody></table></div>')

        elif tipo_bloco == "alternativas":
            itens = "".join(
                f'<div class="alt-item"><span class="nome">{_inline(n)}</span>'
                f'<span class="motivo">{_inline(m)}</span></div>' for n, m in dados)
            html_bloco = (f'<div class="bloco alerta"><h3>Descartadas</h3>'
                          f'<div class="alt">{itens}</div></div>')

        elif tipo_bloco == "erro":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = (f'<div class="bloco alerta"><h3>O erro comum</h3>'
                          f'<ul>{itens}</ul></div>')

        elif tipo_bloco == "certo":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = (f'<div class="bloco ok"><h3>Análise correta</h3>'
                          f'<ul>{itens}</ul></div>')

        elif tipo_bloco == "camadas":
            linhas = "".join(
                f'<div class="camada"><span class="nome">{_inline(n)}</span>'
                f'<span class="modelo">{_inline(m)}</span>'
                f'<span class="papel">{p}</span></div>' for n, m, p in dados)
            html_bloco = f'<div class="camadas">{linhas}</div>'

        elif tipo_bloco == "decisoes":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = (f'<div class="bloco"><h3>Decisões que valem nota</h3>'
                          f'<ul>{itens}</ul></div>')

        elif tipo_bloco == "metodo":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = (f'<div class="bloco"><h3>Método</h3>'
                          f'<ul>{itens}</ul></div>')

        elif tipo_bloco == "resultado":
            itens = "".join(
                f'<div class="numero-item"><span class="valor">{_inline(v)}</span>'
                f'<span class="desc">{_inline(d)}</span></div>' for v, d in dados)
            html_bloco = f'<div class="numeros">{itens}</div>'

        elif tipo_bloco == "casos":
            linhas = "".join(
                f'<div class="caso"><span class="cod">{c}</span>'
                f'<span class="pct">{p}</span>'
                f'<span class="txt">{_inline(t)}</span></div>'
                for c, p, t in dados)
            html_bloco = f'<div class="bloco"><h3>Casos reais</h3>{linhas}</div>'

        elif tipo_bloco == "benchmark":
            # _inline e obrigatorio: sem ele, os "**" dos rotulos saem
            # literais no PDF ("**DuckDB vence**"). Era o unico bloco que
            # nao passava pela conversao de markdown inline.
            itens = "".join(
                f'<div class="bench-item ganha"><span class="quem">{_inline(d)}</span>'
                f'<span class="venc">{_inline(v)}</span>'
                f'<span class="por">{_inline(p)}</span></div>' for d, v, p in dados)
            html_bloco = f'<div class="bench">{itens}</div>'

        elif tipo_bloco == "quebra":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = (f'<div class="bloco alerta"><h3>O que quebra, em ordem</h3>'
                          f'<ul>{itens}</ul></div>')

        elif tipo_bloco == "honesto":
            itens = "".join(f"<li>{_inline(x)}</li>" for x in dados)
            html_bloco = (f'<div class="bloco alerta"><h3>Escopo assumido</h3>'
                          f'<ul>{itens}</ul></div>')

        if html_bloco:
            atual.append(html_bloco)
            if len(atual) >= 2 and len(s.get("blocos", [])) > 2:
                colunas.append(atual)
                atual = []

    if atual:
        colunas.append(atual)

    colunas_html = "".join(
        f'<div class="col">{"".join(c)}</div>' for c in colunas)

    extras = ""
    if "destaque" in s:
        extras += f'<div class="destaque">{_inline(s["destaque"])}</div>'
    if "fecho" in s:
        extras += f'<div class="fecho">{_inline(s["fecho"])}</div>'
    if "nota" in s:
        extras += f'<div class="nota">{_inline(s["nota"])}</div>'

    return f"""
    <section class="slide">
      {tempo}
      <h1>{_inline(s['titulo'])}</h1>
      <div class="conteudo">{colunas_html}</div>
      {extras}
      {rodape}
    </section>"""


def construir_html() -> str:
    slides = "\n".join(renderizar_slide(s) for s in SLIDES)
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Giro — Pitch</title>
<style>{CSS}</style>
</head><body>{slides}</body></html>"""


def achar_edge() -> Path | None:
    """Localiza um browser Chromium para gerar o PDF.

    Ordem: caminhos conhecidos do Windows (Edge, Chrome), depois PATH e
    shutil.which. So dois caminhos fixos do Edge deixavam o projeto sem
    saida numa maquina com Chrome ou com Edge em outro diretorio.
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


def main() -> None:
    edge = achar_edge()
    if edge is None:
        raise SystemExit(
            "Browser Chromium nao encontrado.\n"
            "  Instale o Microsoft Edge (padrao no Windows) ou o Google Chrome.\n"
            "  Os PDFs ja gerados estao em docs/; isto so afeta a regeneracao.")

    destino = RAIZ / "docs" / "pitch.pdf"
    html_doc = construir_html()

    with tempfile.TemporaryDirectory() as tmp:
        html_file = Path(tmp) / "pitch.html"
        html_file.write_text(html_doc, encoding="utf-8")

        (RAIZ / "docs" / "pitch.html").write_text(html_doc, encoding="utf-8")

        subprocess.run([
            str(edge), "--headless", "--disable-gpu",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={destino}",
            html_file.as_uri(),
        ], capture_output=True, timeout=180)

    if destino.exists():
        kb = destino.stat().st_size / 1024
        print(f"Pitch gerado: {destino}")
        print(f"  {kb:.0f} KB · {len(SLIDES)} slides · 16:9")
    else:
        raise SystemExit("falha ao gerar o PDF")


if __name__ == "__main__":
    main()
