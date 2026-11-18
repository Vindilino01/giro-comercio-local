"""
Gera o dicionario de dados a partir do catalogo do PostgreSQL.

POR QUE GERAR E NAO ESCREVER A MAO
----------------------------------
Dicionario escrito a mao desatualiza na primeira migration. Gerado do
catalogo, ele reflete o banco REAL - se o DDL mudar, o documento muda
no proximo build. Para um trabalho avaliado, isso significa que nao ha
como o relatorio descrever um modelo diferente do que foi implementado.

Uso:
    python src/dicionario.py
    python src/dicionario.py --saida docs/dicionario-de-dados.md
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

SCHEMAS = ("prata", "ouro", "gov")
ORDEM_SCHEMA = {"prata": 1, "ouro": 2, "gov": 3}

DESCRICAO_SCHEMA = {
    "prata": "Camada prata — modelo OLTP normalizado em 3FN. Fonte de verdade "
             "transacional.",
    "ouro": "Camada ouro — star schema e views materializadas para consulta "
            "analítica.",
    "gov": "Governança — quarentena, linhagem, métricas de qualidade e "
           "auditoria.",
}

# Descricao de cada tabela. Mantida aqui (e nao lida do catalogo) porque
# o COMMENT do banco nao cobre 100% das tabelas e queremos o documento
# completo.
DESCRICAO_TABELA: dict[str, str] = {
    "prata.loja": "Unidade física do mercado. Multi-loja desde o início.",
    "prata.categoria": "Hierarquia de categorias (departamento > classe > subclasse). "
                       "Auto-referenciada para permitir profundidade variável.",
    "prata.fornecedor": "Fornecedor/distribuidor. `lead_time` alimenta a sugestão de compra.",
    "prata.produto": "Cadastro de SKU. Soft delete via `ativo` para preservar histórico.",
    "prata.produto_fornecedor": "Preço e prazo por par produto-fornecedor. "
                                "Índice parcial garante um preferencial por SKU.",
    "prata.produto_preco_historico": "Vigência de preço de custo e venda (SCD tipo 2). "
                                     "Faixas não se sobrepõem (EXCLUDE).",
    "prata.calendario": "Calendário com feriados e dias de pagamento. "
                        "Dimensão de tempo materializada.",
    "prata.promocao": "Campanha promocional com janela de vigência.",
    "prata.promocao_produto": "Produtos participantes de cada promoção.",
    "prata.venda": "Cabeçalho de cupom fiscal. Particionada por mês em `data_venda`.",
    "prata.item_venda": "Linha do cupom. PK inclui `data_venda` por exigência "
                        "do particionamento.",
    "prata.movimentacao_estoque": "Livro-razão de eventos de estoque "
                                  "(event sourcing). Saldo = SUM(quantidade).",
    "prata.estoque_snapshot": "Fotografia diária de estoque por loja/SKU. "
                              "A constraint `snapshot_equacao_ck` garante integridade.",
    "prata.pedido_compra": "Pedido ao fornecedor. `data_entrega` vs `data_previsao` "
                           "mede o OTIF.",
    "prata.item_pedido": "Linha do pedido. `quantidade_entregue` < pedida "
                         "caracteriza entrega parcial.",
    "ouro.dim_tempo": "Dimensão de tempo desnormalizada para leitura.",
    "ouro.dim_loja": "Dimensão loja com porte derivado da área.",
    "ouro.dim_produto": "Dimensão produto com hierarquia achatada e preço vigente.",
    "ouro.dim_fornecedor": "Dimensão fornecedor.",
    "ouro.dim_promocao": "Dimensão promoção com duração calculada.",
    "ouro.fato_vendas": "Fato de vendas. Grão: uma linha de cupom.",
    "ouro.fato_estoque_diario": "Fato de estoque. Grão: um SKU-loja-dia.",
    "ouro.fato_compras": "Fato de compras. Grão: um item de pedido.",
    "gov.lote_carga": "Auditoria de cada execução de carga. "
                      "`lote_carga_id` é a chave de linhagem de todo dado.",
    "gov.regra_qualidade": "Catálogo das 21 regras de qualidade (DQ001..DQ021).",
    "gov.quarentena": "Registros rejeitados com `reason_code` e payload original "
                      "em JSONB. Nunca descarte silencioso.",
    "gov.metrica_qualidade": "Score de qualidade por loja e dimensão. "
                             "Alimenta o selo de confiança.",
    "gov.auditoria": "Trilha de auditoria. Base para LGPD art. 37.",
}


def _tipo_legivel(tipo: str) -> str:
    """Simplifica o tipo do catalogo para leitura humana."""
    substituicoes = {
        "character varying": "text",
        "timestamp with time zone": "timestamptz",
        "double precision": "float8",
        "numeric": "numeric",
    }
    t = tipo
    for de, para in substituicoes.items():
        t = t.replace(de, para)
    return t


def coletar(conn: psycopg.Connection) -> dict:
    dados: dict = {"tabelas": [], "views": []}

    with conn.cursor() as cur:
        # ---- Tabelas e colunas -------------------------------------
        cur.execute("""
            SELECT c.table_schema, c.table_name, c.column_name,
                   c.data_type, c.character_maximum_length,
                   c.numeric_precision, c.numeric_scale,
                   c.is_nullable, c.column_default, c.ordinal_position,
                   col_description(
                       (quote_ident(c.table_schema) || '.' ||
                        quote_ident(c.table_name))::regclass::oid,
                       c.ordinal_position) AS comentario
              FROM information_schema.columns c
              JOIN information_schema.tables t
                ON t.table_schema = c.table_schema
               AND t.table_name = c.table_name
              -- Apenas tabelas LOGICAS: particoes de venda/item_venda
              -- nao entram no dicionario. Sao fisicas, geradas pela
              -- funcao gov.criar_particoes_mensais, e listar as 31 de
              -- cada uma inflaria o documento sem informacao nova.
             WHERE c.table_schema = ANY(%s)
               AND t.table_type = 'BASE TABLE'
               AND c.table_name NOT LIKE 'venda\\_20%%'
               AND c.table_name NOT LIKE 'item\\_venda\\_20%%'
             ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """, (list(SCHEMAS),))
        colunas = cur.fetchall()

        # ---- Constraints -------------------------------------------
        cur.execute("""
            SELECT n.nspname, c.relname, con.conname,
                   pg_get_constraintdef(con.oid),
                   con.contype
              FROM pg_constraint con
              JOIN pg_class c ON c.oid = con.conrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = ANY(%s)
             ORDER BY n.nspname, c.relname, con.contype, con.conname
        """, (list(SCHEMAS),))
        constraints = cur.fetchall()

        # ---- Indices ------------------------------------------------
        cur.execute("""
            SELECT schemaname, tablename, indexname, indexdef
              FROM pg_indexes
             WHERE schemaname = ANY(%s)
             ORDER BY schemaname, tablename, indexname
        """, (list(SCHEMAS),))
        indices = cur.fetchall()

        # ---- Views materializadas -----------------------------------
        cur.execute("""
            SELECT schemaname, matviewname,
                   pg_get_viewdef((quote_ident(schemaname) || '.' ||
                                   quote_ident(matviewname))::regclass)
              FROM pg_matviews
             WHERE schemaname = ANY(%s)
             ORDER BY schemaname, matviewname
        """, (list(SCHEMAS),))
        views = cur.fetchall()

    # Agrupa colunas por tabela
    por_tabela: dict[tuple[str, str], list] = {}
    for row in colunas:
        chave = (row[0], row[1])
        por_tabela.setdefault(chave, []).append(row)

    for (schema, tabela), cols in por_tabela.items():
        cons = [c for c in constraints
                if c[0] == schema and c[1] == tabela]
        idx = [i for i in indices
               if i[0] == schema and i[1] == tabela]
        dados["tabelas"].append({
            "schema": schema,
            "nome": tabela,
            "descricao": DESCRICAO_TABELA.get(
                f"{schema}.{tabela}", "_(sem descrição)_"),
            "colunas": [
                {
                    "nome": r[2],
                    "tipo": _tipo_legivel(
                        r[3] + (f"({r[4]})" if r[4] else
                                (f"({r[5]},{r[6]})" if r[5] else ""))),
                    "nulo": r[7] == "YES",
                    "default": r[8],
                    "comentario": r[10],
                }
                for r in cols
            ],
            "constraints": [
                {"nome": c[2], "definicao": c[3],
                 "tipo": {"p": "PK", "f": "FK", "u": "UNIQUE",
                          "c": "CHECK", "x": "EXCLUDE"}.get(c[4], c[4])}
                for c in cons
            ],
            "indices": [
                {"nome": i[2], "definicao": i[3]}
                for i in idx
                if not i[2].endswith("_pkey")
            ],
        })

    dados["tabelas"].sort(key=lambda x: (ORDEM_SCHEMA.get(x["schema"], 9), x["nome"]))
    dados["views"] = [
        {"schema": v[0], "nome": v[1], "definicao": v[2]} for v in views
    ]
    return dados


def gerar_markdown(dados: dict) -> str:
    linhas: list[str] = [
        "# Dicionário de dados",
        "",
        "> **Documento gerado automaticamente** a partir do catálogo do PostgreSQL",
        "> (`src/dicionario.py`). Reflete o banco real, não uma versão idealizada.",
        "",
        f"**Schemas:** {', '.join(f'`{s}`' for s in SCHEMAS)}  ",
        f"**Tabelas:** {len(dados['tabelas'])}  ",
        f"**Views materializadas:** {len(dados['views'])}",
        "",
        "## Convenções",
        "",
        "| Convenção | Regra | Motivo |",
        "|---|---|---|",
        "| PK | `BIGINT GENERATED ALWAYS AS IDENTITY` | Chave surrogate estável, "
        "sem semântica embutida |",
        "| Chave natural | Sempre `UNIQUE`, além da surrogate | Permite deduplicação "
        "idempotente |",
        "| Dinheiro | `NUMERIC(14,2)` | Nunca `FLOAT` — erro de arredondamento |",
        "| Quantidade | `NUMERIC(14,3)` | kg e litro fracionam |",
        "| Data/hora | `TIMESTAMPTZ` | Brasil tem 4 fusos horários |",
        "| Nomes | português, sem acento | Evita problema de encoding em exportação |",
        "| Enum | `CHECK`, não tipo `ENUM` | Permite alteração sem lock de catálogo |",
        "",
        "## Resumo por schema",
        "",
        "| Schema | Tabelas | Propósito |",
        "|---|---|---|",
    ]

    for schema in SCHEMAS:
        n = sum(1 for t in dados["tabelas"] if t["schema"] == schema)
        linhas.append(f"| `{schema}` | {n} | {DESCRICAO_SCHEMA[schema]} |")

    linhas += ["", "---", ""]

    for schema in SCHEMAS:
        tabelas = [t for t in dados["tabelas"] if t["schema"] == schema]
        if not tabelas:
            continue
        linhas += [f"# Schema `{schema}`", "", DESCRICAO_SCHEMA[schema], ""]

        for t in tabelas:
            linhas += [
                f"## `{t['schema']}.{t['nome']}`",
                "",
                t["descricao"],
                "",
                "| Coluna | Tipo | Nulo | Descrição |",
                "|---|---|---|---|",
            ]
            for c in t["colunas"]:
                desc = c["comentario"] or ""
                linhas.append(
                    f"| `{c['nome']}` | `{c['tipo']}` | "
                    f"{'sim' if c['nulo'] else 'não'} | {desc} |")

            if t["constraints"]:
                linhas += ["", "**Constraints:**", ""]
                for con in t["constraints"]:
                    linhas.append(
                        f"- `{con['nome']}` ({con['tipo']}): "
                        f"`{con['definicao']}`")

            if t["indices"]:
                linhas += ["", "**Índices adicionais:**", ""]
                for i in t["indices"]:
                    linhas.append(f"- `{i['nome']}`: `{i['definicao']}`")

            linhas += ["", "---", ""]

    if dados["views"]:
        linhas += ["# Views materializadas", "",
                   "Views pré-computadas que sustentam o dashboard e a previsão. "
                   "O `REFRESH` roda ao final de cada carga.", ""]
        for v in dados["views"]:
            linhas += [
                f"## `{v['schema']}.{v['nome']}`",
                "",
                "<details><summary>Definição SQL</summary>",
                "",
                "```sql",
                v["definicao"].strip(),
                "```",
                "",
                "</details>",
                "",
            ]

    return "\n".join(linhas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=None)
    ap.add_argument("--dsn", default=os.environ.get(
        "GIRO_DSN", "host=127.0.0.1 port=5433 dbname=giro user=postgres"))
    args = ap.parse_args()

    raiz = Path(__file__).parent.parent
    destino = Path(args.saida) if args.saida else raiz / "docs" / "dicionario-de-dados.md"

    with psycopg.connect(args.dsn) as conn:
        dados = coletar(conn)

    md = gerar_markdown(dados)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(md, encoding="utf-8")

    n_colunas = sum(len(t["colunas"]) for t in dados["tabelas"])
    print(f"dicionario gerado: {destino}")
    print(f"  {len(dados['tabelas'])} tabelas, {n_colunas} colunas, "
          f"{len(dados['views'])} views materializadas")


if __name__ == "__main__":
    main()
