"""
Ciclo de teste rapido do pipeline (dataset pequeno, banco descartavel).

POR QUE ESTE SCRIPT EXISTE
  Carregar 4,1M de linhas leva ~2 min. Se houver um erro de SQL na
  etapa 8, perdemos 2 min para descobrir. Este script usa a escala
  'rapida' (1 loja, 6 meses, ~110k itens) num banco separado e roda o
  pipeline inteiro em ~20 s. Assim os erros aparecem em segundos.

Uso:
    python tests/test_pipeline_rapido.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))

PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
DB = "giro_teste"
DSN = f"host=127.0.0.1 port=5433 dbname={DB} user=postgres"
ADMIN = "host=127.0.0.1 port=5433 dbname=postgres user=postgres"


def psql(*args: str, dsn: str = DSN) -> str:
    partes = dict(kv.split("=", 1) for kv in dsn.split())
    cmd = [str(PG_BIN / "psql.exe"),
           "-h", partes["host"], "-p", partes["port"],
           "-U", partes["user"], "-d", partes["dbname"],
           "-v", "ON_ERROR_STOP=1", "-X", "-q", *args]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:1200])
    return r.stdout


def etapa(nome: str) -> None:
    print(f"\n{'=' * 62}\n  {nome}\n{'=' * 62}")


def main() -> int:
    t_total = time.time()

    etapa("1. Banco descartavel")
    psql("-c", f"""
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
         WHERE datname = '{DB}' AND pid <> pg_backend_pid()
    """, dsn=ADMIN)
    psql("-c", f"DROP DATABASE IF EXISTS {DB}", dsn=ADMIN)
    psql("-c", f"CREATE DATABASE {DB} WITH ENCODING 'UTF8' TEMPLATE template0",
         dsn=ADMIN)
    psql("-f", str(RAIZ / "db" / "build.sql"))
    print("  OK banco e schema criados")

    etapa("2. Geracao (escala rapida)")
    from src.gerador import ESCALAS, gerar
    from src.injetor_defeitos import injetar

    bronze = RAIZ / "data" / "bronze_teste"
    limpo = bronze / "limpo"
    sujo = bronze / "sujo"
    t0 = time.time()
    resumo = gerar(ESCALAS["rapida"], limpo, verbose=False)
    print(f"  OK {sum(resumo.tabelas.values()):,} linhas em {time.time()-t0:.1f}s")

    gab = injetar(limpo, sujo)
    n = sum(len(v) for v in gab.registros.values())
    print(f"  OK {len(gab.defeitos)} tipos de defeito, {n:,} registros")

    etapa("3. Ingestao do dataset limpo")
    import psycopg
    from src.ingestao import Ingestor

    t0 = time.time()
    with psycopg.connect(DSN) as conn:
        ing = Ingestor(conn, limpo)
        resultados = ing.executar_tudo()
    print(f"  OK em {time.time()-t0:.1f}s")
    for r in resultados:
        marca = "OK " if r.rejeitadas == 0 else "!! "
        print(f"  {marca}{r.tabela:<24} lidas={r.lidas:>8,} "
              f"aceitas={r.aceitas:>8,} rejeitadas={r.rejeitadas:>6,}")

    etapa("4. Camada ouro")
    from src.marts import construir

    t0 = time.time()
    with psycopg.connect(DSN) as conn:
        construir(conn, verbose=True)
    print(f"  OK em {time.time()-t0:.1f}s")

    etapa("5. Consultas de negocio")
    from src.consultas import executar_todas

    with psycopg.connect(DSN) as conn:
        indice = executar_todas(conn, RAIZ,
                                pasta_saida=RAIZ / "docs" / "evidencias_teste")
    erros = [c for c in indice["consultas"] if "erro" in c]
    if erros:
        print(f"\n  {len(erros)} consulta(s) com erro:")
        for e in erros:
            print(f"    {e['numero']}: {e['erro'][:100]}")
        return 1

    etapa("6. Carga do dataset sujo (banco separado)")
    dsn_q = DSN.replace(f"dbname={DB} ", f"dbname={DB}_q ")
    psql("-c", f"""
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
         WHERE datname = '{DB}_q' AND pid <> pg_backend_pid()
    """, dsn=ADMIN)
    psql("-c", f"DROP DATABASE IF EXISTS {DB}_q", dsn=ADMIN)
    psql("-c", f"CREATE DATABASE {DB}_q WITH ENCODING 'UTF8' TEMPLATE template0",
         dsn=ADMIN)
    psql("-f", str(RAIZ / "db" / "build.sql"), dsn=dsn_q)

    import json
    from src.metricas_qualidade import analisar

    with psycopg.connect(dsn_q) as conn:
        ing = Ingestor(conn, sujo)
        res_sujo = ing.executar_tudo()
        gabarito = json.loads((sujo / "_gabarito.json").read_text(encoding="utf-8"))
        metricas = analisar(conn, gabarito)
    print(f"  {'REGRA':<7} {'TABELA':<20} {'INJ':>6} {'REJ':>6} "
          f"{'RECALL':>8} {'PREC':>7}")
    print("  " + "-" * 62)
    for m in metricas["por_regra"]:
        print(f"  {m['regra']:<7} {m['tabela']:<20} {m['injetados']:>6,} "
              f"{m['rejeitados']:>6,} {m['recall_pct']:>7.1f}% "
              f"{m['precisao_pct']:>6.1f}%")
    r = metricas["resumo"]
    print(f"  recall global: {r['recall_global_pct']}%")

    print(f"\n{'=' * 62}")
    print(f"  PIPELINE COMPLETO EM {time.time() - t_total:.1f}s")
    print(f"{'=' * 62}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"\nFALHOU: {exc}")
        sys.exit(1)
