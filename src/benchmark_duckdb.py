"""
Benchmark PostgreSQL x DuckDB para o cenario 100x (secao 4.7).

POR QUE ESTE BENCHMARK EXISTE
-----------------------------
O edital pergunta explicitamente: "o que mudaria se a startup crescesse
100 vezes?" (secao 4.7). A resposta em prosa seria fraca. Com numeros
medidos, a resposta vira evidencia.

HIPOTESE A TESTAR
-----------------
A 100x, o gargalo migra de TRANSACAO para VARREDURA ANALITICA. Isso
sugere que um formato colunar (Parquet/DuckDB) passaria a valer a pena
para o caminho analitico - sem substituir o PostgreSQL no transacional.

METODOLOGIA
-----------
Mede a MESMA consulta nos dois motores, sobre os MESMOS dados:

  1. PostgreSQL: consulta direta em ouro.fato_vendas (row store)
  2. DuckDB: consulta sobre Parquet exportado (column store)

Consultas medidas:
  A) varredura ampla: receita por mes em 24 meses
  B) agregacao por SKU: curva ABC completa
  C) filtro seletivo: vendas de um SKU em um mes (onde o row store
     deveria ganhar, por causa do indice)

A comparacao C e a mais importante: ela mostra que DuckDB NAO vence
sempre. Um benchmark que so mostra o caso favoravel e propaganda, nao
evidencia.

COMO LER O RESULTADO
--------------------
- Varredura ampla: DuckDB tende a vencer por ler so as colunas usadas.
- Filtro seletivo: PostgreSQL tende a vencer por usar indice B-tree.
- Conclusao honesta: a escolha depende do padrao de acesso, e por isso
  o PostgreSQL continua sendo o núcleo e o colunar entra como camada
  analitica - exatamente o que a secao 4.7 propoe.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psycopg

RAIZ = Path(__file__).parent.parent
SAIDA = RAIZ / "docs" / "evidencias"

CONSULTAS = {
    "A_varredura_ampla": {
        "titulo": "Receita por mes em 24 meses",
        "descricao": "Varredura de toda a tabela de fatos, agregando por mes. "
                     "Cenario classico de dashboard anual.",
        "pg": """
            SELECT t.ano_mes,
                   count(*)              AS itens,
                   sum(f.valor_liquido)  AS receita
              FROM ouro.fato_vendas f
              JOIN ouro.dim_tempo t ON t.data = f.data_venda
             GROUP BY t.ano_mes
             ORDER BY t.ano_mes
        """,
        "duck": """
            SELECT strftime(t.data, '%Y-%m') AS ano_mes,
                   count(*)                   AS itens,
                   sum(f.valor_liquido)       AS receita
              FROM fato_vendas f
              JOIN dim_tempo t ON t.data = f.data_venda
             GROUP BY 1
             ORDER BY 1
        """,
    },
    "B_agregacao_por_sku": {
        "titulo": "Curva ABC completa (420 SKUs)",
        "descricao": "Agregacao por SKU com window function para acumulado. "
                     "Cenario de analise de sortimento.",
        "pg": """
            WITH r AS (
                SELECT produto_id, sum(valor_liquido) AS receita
                  FROM ouro.fato_vendas
                 GROUP BY produto_id
            )
            SELECT produto_id, receita,
                   sum(receita) OVER (ORDER BY receita DESC
                                      ROWS UNBOUNDED PRECEDING) AS acumulado
              FROM r
             ORDER BY receita DESC
        """,
        "duck": """
            WITH r AS (
                SELECT produto_id, sum(valor_liquido) AS receita
                  FROM fato_vendas
                 GROUP BY produto_id
            )
            SELECT produto_id, receita,
                   sum(receita) OVER (ORDER BY receita DESC
                                      ROWS UNBOUNDED PRECEDING) AS acumulado
              FROM r
             ORDER BY receita DESC
        """,
    },
    "C_filtro_seletivo": {
        "titulo": "Vendas de um SKU em um mes",
        "descricao": "Filtro altamente seletivo (~1/4200 da tabela). "
                     "Cenario onde o indice do row store deveria vencer.",
        "pg": """
            SELECT data_venda, sum(quantidade), sum(valor_liquido)
              FROM ouro.fato_vendas
             WHERE produto_id = (SELECT min(produto_id) FROM ouro.dim_produto)
               AND data_venda >= '2025-06-01'
               AND data_venda <  '2025-07-01'
             GROUP BY data_venda
             ORDER BY data_venda
        """,
        "duck": """
            SELECT data_venda, sum(quantidade), sum(valor_liquido)
              FROM fato_vendas
             WHERE produto_id = (SELECT min(produto_id) FROM dim_produto)
               AND data_venda >= DATE '2025-06-01'
               AND data_venda <  DATE '2025-07-01'
             GROUP BY data_venda
             ORDER BY data_venda
        """,
    },
}


def _medir_pg(conn: psycopg.Connection, sql: str, repeticoes: int = 3) -> dict:
    tempos: list[float] = []
    linhas = 0
    for _ in range(repeticoes):
        with conn.cursor() as cur:
            t0 = time.perf_counter()
            cur.execute(sql)
            resultado = cur.fetchall()
            tempos.append((time.perf_counter() - t0) * 1000)
            linhas = len(resultado)
        conn.rollback()
    return {
        "tempos_ms": [round(t, 2) for t in tempos],
        "mediana_ms": round(sorted(tempos)[len(tempos) // 2], 2),
        "minimo_ms": round(min(tempos), 2),
        "linhas": linhas,
    }


def _medir_duck(con, sql: str, repeticoes: int = 3) -> dict:
    tempos: list[float] = []
    linhas = 0
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        resultado = con.execute(sql).fetchall()
        tempos.append((time.perf_counter() - t0) * 1000)
        linhas = len(resultado)
    return {
        "tempos_ms": [round(t, 2) for t in tempos],
        "mediana_ms": round(sorted(tempos)[len(tempos) // 2], 2),
        "minimo_ms": round(min(tempos), 2),
        "linhas": linhas,
    }


def exportar_parquet(conn: psycopg.Connection, destino: Path) -> dict:
    """Exporta fato e dimensoes para Parquet via DuckDB.

    CORRECAO: a primeira versao montava a tabela DuckDB com todas as
    colunas VARCHAR ('CREATE TABLE x (col VARCHAR)') e enviava os
    valores como texto. O Parquet saia com tudo string, e funcoes como
    strftime e sum falhavam com BinderException. Agora o schema e
    inferido dos tipos do cursor do PostgreSQL.
    """
    import duckdb

    destino.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    tamanhos: dict[str, float] = {}

    # Mapa de OID do PostgreSQL -> tipo DuckDB
    def tipo_duck(pg_tipo: int) -> str:
        # 20,21,23 = int8,int2,int4 | 700,701 = float4,float8
        # 1700 = numeric | 1082 = date | 1114,1184 = timestamp
        # 1043 = varchar | 16 = bool | 1083 = time
        return {
            16: "BOOLEAN", 20: "BIGINT", 21: "SMALLINT", 23: "INTEGER",
            25: "VARCHAR", 1043: "VARCHAR", 700: "FLOAT", 701: "DOUBLE",
            1700: "DECIMAL(18,4)", 1082: "DATE", 1083: "TIME",
            1114: "TIMESTAMP", 1184: "TIMESTAMP WITH TIME ZONE",
        }.get(pg_tipo, "VARCHAR")

    for tabela in ("fato_vendas", "dim_tempo", "dim_produto"):
        parquet = destino / f"{tabela}.parquet"
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM ouro.{tabela}")
            colunas = [(d.name, tipo_duck(d.type_code)) for d in cur.description]
            linhas = cur.fetchall()
        conn.rollback()

        ddl = ", ".join(f'"{c}" {t}' for c, t in colunas)
        con.execute(f"CREATE OR REPLACE TABLE {tabela} ({ddl})")

        if linhas:
            placeholders = ", ".join("?" for _ in colunas)
            for i in range(0, len(linhas), 50_000):
                con.executemany(
                    f"INSERT INTO {tabela} VALUES ({placeholders})",
                    linhas[i:i + 50_000])

        con.execute(f"""
            COPY (SELECT * FROM {tabela}) TO '{parquet.as_posix()}'
            (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        tamanhos[tabela] = round(parquet.stat().st_size / 1024 / 1024, 2)

        con.execute(f"DROP TABLE {tabela}")
        con.execute(f"""
            CREATE TABLE {tabela} AS
            SELECT * FROM read_parquet('{parquet.as_posix()}')
        """)

    con.close()
    return tamanhos


def executar(dsn: str, exportar: bool = True) -> dict:
    import duckdb

    parquet_dir = RAIZ / "data" / "parquet"
    resultado: dict = {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "consultas": {},
        "tamanhos_parquet_mb": {},
        "config": {},
    }

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            resultado["config"]["postgres"] = cur.fetchone()[0]
            cur.execute("""
                SELECT pg_size_pretty(pg_total_relation_size('ouro.fato_vendas')),
                       pg_total_relation_size('ouro.fato_vendas'),
                       (SELECT count(*) FROM ouro.fato_vendas)
            """)
            tam, bytes_, n = cur.fetchone()
            resultado["config"]["fato_vendas_pg"] = tam
            resultado["config"]["fato_vendas_bytes"] = bytes_
            resultado["config"]["fato_vendas_linhas"] = n
        conn.rollback()

        resultado["config"]["duckdb"] = duckdb.__version__

        if exportar:
            resultado["tamanhos_parquet_mb"] = exportar_parquet(conn, parquet_dir)
        else:
            resultado["tamanhos_parquet_mb"] = {
                p.stem: round(p.stat().st_size / 1024 / 1024, 2)
                for p in parquet_dir.glob("*.parquet")
            }

        con_duck = duckdb.connect()
        for tabela in ("fato_vendas", "dim_tempo", "dim_produto"):
            con_duck.execute(f"""
                CREATE OR REPLACE VIEW {tabela} AS
                SELECT * FROM read_parquet('{(parquet_dir / f'{tabela}.parquet').as_posix()}')
            """)

        for nome, spec in CONSULTAS.items():
            print(f"  medindo {nome}...", flush=True)
            pg = _medir_pg(conn, spec["pg"])
            duck = _medir_duck(con_duck, spec["duck"])
            razao = (pg["mediana_ms"] / duck["mediana_ms"]
                     if duck["mediana_ms"] > 0 else None)

            vencedor = "duckdb" if duck["mediana_ms"] < pg["mediana_ms"] else "postgres"
            resultado["consultas"][nome] = {
                "titulo": spec["titulo"],
                "descricao": spec["descricao"],
                "postgres": pg,
                "duckdb": duck,
                "razao_pg_sobre_duck": round(razao, 2) if razao else None,
                "vencedor": vencedor,
            }

        con_duck.close()

    return resultado


def gerar_markdown(r: dict) -> str:
    linhas = [
        "# Benchmark PostgreSQL × DuckDB",
        "",
        "> Medição real executada em `src/benchmark_duckdb.py`. Evidência para a "
        "seção 4.7 do relatório (cenário 100×).",
        "",
        f"**Gerado em:** {r['gerado_em']}  ",
        f"**PostgreSQL:** {r['config'].get('postgres', '—')}  ",
        f"**DuckDB:** {r['config'].get('duckdb', '—')}  ",
        f"**Linhas em `fato_vendas`:** {r['config'].get('fato_vendas_linhas', 0):,}  ",
        f"**Tamanho no PostgreSQL:** {r['config'].get('fato_vendas_pg', '—')}",
        "",
        "## Tamanho em disco",
        "",
        "| Tabela | Parquet (ZSTD) |",
        "|---|---|",
    ]
    for t, mb in r["tamanhos_parquet_mb"].items():
        linhas.append(f"| `{t}` | {mb} MB |")

    linhas += [
        "",
        "## Resultados",
        "",
        "| Consulta | PostgreSQL (mediana) | DuckDB (mediana) | Razão | Vencedor |",
        "|---|---|---|---|---|",
    ]
    for nome, c in r["consultas"].items():
        razao = c["razao_pg_sobre_duck"]
        razao_txt = f"{razao:.2f}×" if razao else "—"
        venc = c["vencedor"].upper()
        linhas.append(
            f"| **{nome}** — {c['titulo']} | "
            f"{c['postgres']['mediana_ms']:.1f} ms | "
            f"{c['duckdb']['mediana_ms']:.1f} ms | "
            f"{razao_txt} | {venc} |")

    linhas += ["", "### Detalhe por consulta", ""]
    for nome, c in r["consultas"].items():
        linhas += [
            f"#### {nome} — {c['titulo']}",
            "",
            c["descricao"],
            "",
            f"- **PostgreSQL:** {c['postgres']['tempos_ms']} ms "
            f"({c['postgres']['linhas']} linhas)",
            f"- **DuckDB:** {c['duckdb']['tempos_ms']} ms "
            f"({c['duckdb']['linhas']} linhas)",
            "",
        ]

    return "\n".join(linhas)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get(
        "GIRO_DSN", "host=127.0.0.1 port=5433 dbname=giro user=postgres"))
    ap.add_argument("--sem-exportar", action="store_true",
                    help="reaproveita os Parquet ja exportados")
    args = ap.parse_args()

    print("Executando benchmark PostgreSQL x DuckDB...")
    resultado = executar(args.dsn, exportar=not args.sem_exportar)

    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "benchmark_duckdb.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    (SAIDA / "benchmark_duckdb.md").write_text(
        gerar_markdown(resultado), encoding="utf-8")

    print()
    print(f"{'CONSULTA':<24} {'POSTGRES':>12} {'DUCKDB':>12} {'VENCEDOR':>10}")
    print("-" * 62)
    for nome, c in resultado["consultas"].items():
        print(f"{nome:<24} {c['postgres']['mediana_ms']:>10.1f}ms "
              f"{c['duckdb']['mediana_ms']:>10.1f}ms {c['vencedor']:>10}")

    print(f"\nEvidencia: docs/evidencias/benchmark_duckdb.md")


if __name__ == "__main__":
    main()
