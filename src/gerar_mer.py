"""Gera o MER (Modelo Entidade-Relacionamento) a partir do catalogo.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A banca pediu para ver o banco: as tabelas, a interface, o MER. O projeto
tinha um diagrama conceitual escrito a mao em ASCII no `04-modelagem.md`,
e um dicionario gerado do catalogo. Faltava o MER de verdade - o desenho
com todas as entidades, as chaves e as 249 chaves estrangeiras reais.

Escrever esse diagrama a mao garantiria que ele ficasse errado na
primeira migration seguinte. Entao ele e DERIVADO do PostgreSQL: le
`information_schema` e `pg_catalog`, e o desenho e consequencia do banco,
nao uma versao idealizada dele.

O QUE SAI
---------
  docs/mer.svg          visao prata + ouro + gov (28 tabelas logicas)
  docs/mer-prata.svg    so a camada transacional, com as colunas
  docs/mer-ouro.svg     so o star schema
  docs/mer.png          versao raster, para colar em slide

As particoes (`venda_2025_01`, ...) sao omitidas do desenho: sao a mesma
tabela fisicamente dividida, e desenhar 43 copias esconderia o modelo.

Uso:
    python src/gerar_mer.py
    python src/gerar_mer.py --dsn "host=... port=5433 dbname=giro user=postgres"
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent.parent
SAIDA = RAIZ / "docs"

# Onde o instalador do Graphviz coloca o binario no Windows.
DOT_CANDIDATOS = [
    r"C:\Program Files\Graphviz\bin\dot.exe",
    r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
]

# Cores por camada. Mesmo verde do painel para a prata (fonte de verdade),
# neutro para o ouro (derivado) e cinza para governanca.
ESTILO = {
    "prata": {"fill": "#e2e9e5", "border": "#0b4f3c", "label": "prata · 3FN (fonte de verdade)"},
    "ouro": {"fill": "#f6f4ec", "border": "#8a5a00", "label": "ouro · star schema (derivado)"},
    "gov": {"fill": "#eeeeee", "border": "#5e6961", "label": "gov · governança"},
}


def achar_dot() -> str:
    for caminho in DOT_CANDIDATOS:
        if Path(caminho).exists():
            return caminho
    # PATH como ultimo recurso
    import shutil
    achado = shutil.which("dot")
    if achado:
        return achado
    raise SystemExit(
        "Graphviz nao encontrado. Instale com:\n"
        "    winget install --id Graphviz.Graphviz --exact\n"
        "Ou passe o caminho em DOT_CANDIDATOS."
    )


def ler_catalogo(conn, schemas: tuple[str, ...]):
    """Devolve tabelas, colunas, chaves e relacionamentos do banco."""
    with conn.cursor() as cur:
        # ---- tabelas logicas (sem particoes) ----
        # relkind inclui 'p': tabela PARTICIONADA. As duas tabelas mais
        # importantes do modelo (venda e item_venda) sao `relkind='p'`, e
        # um filtro so com 'r' e 'm' as deixava FORA do MER - o desenho
        # saia sem o fato de vendas. Descoberto comparando o desenho com
        # o catalogo, nao confiando no desenho.
        cur.execute("""
            select c.relname as tabela, n.nspname as schema
              from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = any(%s)
               and c.relkind in ('r', 'p', 'm')  -- tabela, particionada, view mat
               and c.relispartition = false      -- a particao nao e entidade
             order by n.nspname, c.relname
        """, (list(schemas),))
        tabelas = [{"schema": s, "nome": t} for t, s in cur.fetchall()]

        # ---- colunas ----
        # pg_attribute, nao information_schema.columns: views
        # materializadas NAO aparecem em information_schema, e as cinco
        # mv_* saiam com "0 colunas" no MER. Toda relacao em pg_class
        # (tabela, particao, view materializada) tem atributos em
        # pg_attribute.
        cur.execute("""
            select n.nspname as schema, c.relname as tabela,
                   a.attname as coluna,
                   format_type(a.atttypid, a.atttypmod) as tipo,
                   not a.attnotnull as aceita_nulo,
                   a.attnum
              from pg_attribute a
              join pg_class c     on c.oid = a.attrelid
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = any(%s)
               and c.relkind in ('r', 'p', 'm')
               and a.attnum > 0
               and not a.attisdropped
             order by n.nspname, c.relname, a.attnum
        """, (list(schemas),))
        colunas: dict[tuple[str, str], list[dict]] = {}
        for sch, tab, col, tipo, nulo, _pos in cur.fetchall():
            colunas.setdefault((sch, tab), []).append({
                "nome": col, "tipo": tipo, "nulo": nulo, "tam": None,
            })

        # ---- chave primaria ----
        cur.execute("""
            select tc.table_schema, tc.table_name, kcu.column_name
              from information_schema.table_constraints tc
              join information_schema.key_column_usage kcu
                on kcu.constraint_name = tc.constraint_name
               and kcu.table_schema = tc.table_schema
             where tc.constraint_type = 'PRIMARY KEY'
               and tc.table_schema = any(%s)
             order by kcu.ordinal_position
        """, (list(schemas),))
        pks: dict[tuple[str, str], list[str]] = {}
        for sch, tab, col in cur.fetchall():
            pks.setdefault((sch, tab), []).append(col)

        # ---- chaves estrangeiras ----
        # Usa pg_constraint com unnest(conkey, confkey): cada posicao do
        # lado "de" casa com exatamente uma do lado "para". A versao
        # ingenua (information_schema.key_column_usage x
        # constraint_column_usage casando so pelo nome) produzia produto
        # cartesiano - medido 596 mil linhas para 249 FKs reais.
        cur.execute("""
            select
                cl.relnamespace::regnamespace::text as de_schema,
                cl.relname                          as de_tabela,
                att.attname                         as de_coluna,
                fc.relnamespace::regnamespace::text as para_schema,
                fc.relname                          as para_tabela,
                fatt.attname                        as para_coluna
              from pg_constraint con
              join pg_class cl       on cl.oid = con.conrelid
              join pg_class fc       on fc.oid = con.confrelid
              join lateral unnest(con.conkey, con.confkey)
                   with ordinality as k(de_attnum, para_attnum, ord) on true
              join pg_attribute att  on att.attrelid  = con.conrelid
                                     and att.attnum    = k.de_attnum
              join pg_attribute fatt on fatt.attrelid = con.confrelid
                                     and fatt.attnum   = k.para_attnum
             where con.contype = 'f'
               and cl.relnamespace::regnamespace::text = any(%s)
             order by 1, 2, k.ord
        """, (list(schemas),))
        fks = cur.fetchall()

        # ---- contagem de linhas (para dimensionar o desenho) ----
        contagens: dict[tuple[str, str], int] = {}
        for t in tabelas:
            try:
                cur.execute(f'select count(*) from "{t["schema"]}"."{t["nome"]}"')
                contagens[(t["schema"], t["nome"])] = cur.fetchone()[0]
            except Exception:
                contagens[(t["schema"], t["nome"])] = -1

    return tabelas, colunas, pks, fks, contagens


def fmt_num(n: int) -> str:
    if n < 0:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)


def gerar_dot(tabelas, colunas, pks, fks, contagens, schemas, com_colunas: bool) -> str:
    """Monta o arquivo DOT que o Graphviz transforma em desenho."""
    selecionadas = [t for t in tabelas if t["schema"] in schemas]
    chaves = {(t["schema"], t["nome"]) for t in selecionadas}

    # O star schema tem 8 tabelas e 5 views. Empilhado em LR, as views
    # formam uma coluna de 4.969 px de altura (razao 1:4,55) que nao cabe
    # em papel. Em TB com as views agrupadas lado a lado, o desenho fica
    # largo - que e a proporcao natural de um star schema (fatos no meio,
    # dimensoes em volta).
    # O MER geral com os tres schemas: em LR os clusters empilham na
    # vertical e o desenho sai 1:1,83 (7,6 cm de largura em A4 deitado).
    # Em TB com os schemas lado a lado, fica largo - que e a leitura
    # natural de tres camadas que se comunicam.
    eh_ouro = schemas == ("ouro",)
    eh_geral = len(schemas) == 3

    # O MER geral em `rank=same` nos clusters ficou 5532x1018 (1:0,18) -
    # uma tira fina demais para o papel. Aqui os schemas ficam em duas
    # linhas (prata em cima, ouro e gov embaixo), que da a proporcao de
    # uma pagina A4 deitada.
    linhas = [
        "digraph MER {",
        # `ratio=auto` deixa o Graphviz escolher a proporcao em vez de
        # comprimir mantendo a razao.
        f'  graph [rankdir={"TB" if (eh_ouro or eh_geral) else "LR"}, '
        'fontname="Segoe UI", fontsize=11,',
        '         bgcolor="white", pad=0.4, nodesep=0.30, ranksep=1.5,',
        '         overlap=false, ratio=auto];',
        '  node  [shape=plaintext, fontname="Segoe UI", fontsize=9];',
        '  edge  [color="#8a8a8a", arrowsize=0.6, penwidth=0.9];',
    ]

    # ---- clusters por schema ----
    # No modo geral: prata numa linha em cima; ouro e gov na linha de
    # baixo. O `rank=same` nos tres clusters dava uma tira de 1:0,18; sem
    # nada, os tres empilhavam em 1:1,83. Duas linhas dao a proporcao de
    # uma A4 deitada.

    for sch in schemas:
        est = ESTILO[sch]
        do_schema = [t for t in selecionadas if t["schema"] == sch]
        if not do_schema:
            continue
        linhas.append(f'  subgraph cluster_{sch} {{')
        linhas.append(f'    label="{est["label"]}";')
        linhas.append('    fontsize=12; fontname="Segoe UI Semibold";')
        linhas.append(f'    color="{est["border"]}"; fontcolor="{est["border"]}";')
        linhas.append('    style="rounded,dashed"; penwidth=1.2; margin=16;')

        # No ouro as views materializadas viram uma faixa horizontal
        # embaixo. Empilhadas em coluna, eram 4.969 px de altura.
        if eh_ouro:
            views = [t for t in do_schema if t["nome"].startswith("mv_")]
            demais = [t for t in do_schema if not t["nome"].startswith("mv_")]
            if views:
                linhas.append("    { rank=same;")
                for t in views:
                    linhas.append(f'      "{sch}.{t["nome"]}";')
                linhas.append("    }")
            do_schema = demais + views

        for t in do_schema:
            chave = (sch, t["nome"])
            pk = set(pks.get(chave, []))
            n = contagens.get(chave, -1)

            html = ['<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3">']
            # cabecalho: nome + linhas
            html.append(
                f'<TR><TD BGCOLOR="{est["border"]}" ALIGN="LEFT">'
                f'<FONT COLOR="white" POINT-SIZE="10"><B>{t["nome"]}</B></FONT>'
                f'</TD><TD BGCOLOR="{est["border"]}" ALIGN="RIGHT">'
                f'<FONT COLOR="white" POINT-SIZE="8">{fmt_num(n)}</FONT></TD></TR>'
            )

            if com_colunas:
                for c in colunas.get(chave, []):
                    marca = "&#128273; " if c["nome"] in pk else ""
                    negrito = "<B>" if c["nome"] in pk else ""
                    fecha = "</B>" if c["nome"] in pk else ""
                    tipo = (c["tipo"]
                            .replace("character varying", "varchar")
                            .replace("timestamp with time zone", "timestamptz")
                            .replace("numeric", "num")
                            .replace("character(", "char("))
                    if c["tam"] and c["tipo"] in ("character varying", "numeric"):
                        tipo += f"({c['tam']})"
                    html.append(
                        f'<TR><TD ALIGN="LEFT" PORT="{c["nome"]}" BGCOLOR="{est["fill"]}">'
                        f'{marca}{negrito}{c["nome"]}{fecha}</TD>'
                        f'<TD ALIGN="LEFT" BGCOLOR="{est["fill"]}">'
                        f'<FONT COLOR="#666666" POINT-SIZE="7">{tipo}</FONT></TD></TR>'
                    )
            else:
                n_col = len(colunas.get(chave, []))
                html.append(
                    f'<TR><TD ALIGN="LEFT" BGCOLOR="{est["fill"]}" COLSPAN="2">'
                    f'<FONT COLOR="#666666" POINT-SIZE="8">{n_col} colunas</FONT></TD></TR>'
                )

            html.append("</TABLE>")
            # DOT HTML-like labels ficam entre <...> e o conteudo e XML:
            # aspas NAO devem ser escapadas. Escapar produzia \" dentro do
            # XML e o Graphviz recusava com "not well-formed".
            rotulo = "".join(html)
            linhas.append(f'    "{sch}.{t["nome"]}" [label=<{rotulo}>];')

        linhas.append("  }")

    # ---- relacionamentos ----
    vistas = set()
    for de_sch, de_tab, de_col, pa_sch, pa_tab, pa_col in fks:
        if (de_sch, de_tab) not in chaves or (pa_sch, pa_tab) not in chaves:
            continue
        # Uma aresta por par de tabelas, nao uma por coluna: com 249 FKs,
        # desenhar cada coluna vira um emaranhado ilegivel.
        par = (f"{de_sch}.{de_tab}", f"{pa_sch}.{pa_tab}")
        if par in vistas:
            continue
        vistas.add(par)
        linhas.append(
            f'  "{de_sch}.{de_tab}" -> "{pa_sch}.{pa_tab}" '
            f'[label=" {de_col}", fontsize=7, fontcolor="#777777"];'
        )

    linhas.append("}")
    return "\n".join(linhas)


def renderizar(dot_bin: str, dot_src: str, destino_svg: Path) -> None:
    destino_svg.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [dot_bin, "-Tsvg", "-o", str(destino_svg)],
        input=dot_src.encode("utf-8"), capture_output=True,
    )
    if r.returncode != 0:
        raise SystemExit("Graphviz falhou:\n" + r.stderr.decode("utf-8", "replace"))


def main() -> None:
    import psycopg
    try:
        from src.ingestao import dsn_padrao
    except ModuleNotFoundError:
        # O arquivo roda tanto como `python src/gerar_mer.py` (sem pacote)
        # quanto via `-m src.gerar_mer`.
        import sys
        sys.path.insert(0, str(RAIZ))
        from src.ingestao import dsn_padrao

    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=dsn_padrao())
    args = ap.parse_args()

    dot_bin = achar_dot()
    SAIDA.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(args.dsn) as conn:
        tabelas, colunas, pks, fks, contagens = ler_catalogo(
            conn, ("prata", "ouro", "gov"))

    total_col = sum(len(v) for v in colunas.values())
    print(f"tabelas logicas : {len(tabelas)}")
    print(f"colunas         : {total_col}")
    print(f"chaves estrangeiras: {len(fks)}")

    # ---- 1. visao geral: os tres schemas, sem colunas ----
    dot = gerar_dot(tabelas, colunas, pks, fks, contagens,
                    ("prata", "ouro", "gov"), com_colunas=False)
    renderizar(dot_bin, dot, SAIDA / "mer.svg")
    print("  docs/mer.svg")

    # ---- 2. prata com colunas: e a camada que a banca quer ver ----
    dot = gerar_dot(tabelas, colunas, pks, fks, contagens,
                    ("prata",), com_colunas=True)
    renderizar(dot_bin, dot, SAIDA / "mer-prata.svg")
    print("  docs/mer-prata.svg")

    # ---- 3. ouro: star schema ----
    dot = gerar_dot(tabelas, colunas, pks, fks, contagens,
                    ("ouro",), com_colunas=True)
    renderizar(dot_bin, dot, SAIDA / "mer-ouro.svg")
    print("  docs/mer-ouro.svg")

    # ---- 4. PNG para slide ----
    # Renderiza a partir do DOT, nao do SVG: `dot` nao le SVG como entrada
    # (a versao anterior tentava e falhava com "syntax error in line 1",
    # deixando o PNG sem gerar sem avisar).
    for nome, schemas_png, com_col in (
        ("mer", ("prata", "ouro", "gov"), False),
        ("mer-prata", ("prata",), True),
        ("mer-ouro", ("ouro",), True),
    ):
        dot_png = gerar_dot(tabelas, colunas, pks, fks, contagens,
                            schemas_png, com_colunas=com_col)
        r = subprocess.run(
            [dot_bin, "-Tpng", "-Gdpi=140", "-o", str(SAIDA / f"{nome}.png")],
            input=dot_png.encode("utf-8"), capture_output=True,
        )
        if r.returncode == 0:
            print(f"  docs/{nome}.png")
        else:
            print(f"  FALHOU docs/{nome}.png: "
                  + r.stderr.decode("utf-8", "replace")[:120])


if __name__ == "__main__":
    main()
