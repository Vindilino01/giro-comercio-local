"""Recria as views materializadas da camada ouro a partir de 011.

Por que nao basta `REFRESH MATERIALIZED VIEW`: REFRESH reexecuta a query
antiga, que continua gravada no catalogo. Quando a DEFINICAO muda (o caso
da demanda no horizonte de lead time), e preciso DROP + CREATE - nesta
ordem, porque mv_demanda_diaria e mv_previsao_demanda sao dependencias de
mv_sugestao_compra.

Uso: python scripts/rebuild_views.py
"""

import io
import re
import sys
import time
from pathlib import Path

import psycopg

RAIZ = Path(__file__).parent.parent
SQL_FILE = RAIZ / "db" / "migrations" / "011_ouro_views.sql"
DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

# Ordem de dependencia: cada view so pode ser criada depois das que ela le.
ORDEM = [
    "mv_demanda_diaria",
    "mv_previsao_demanda",
    "mv_sugestao_compra",
    "mv_rupturas",
    "mv_qualidade_loja",
]


def _sem_comentario(linha: str) -> str:
    """Remove o comentario de linha, preservando o codigo.

    Necessario porque comentarios contem `;` no meio do texto ("616.913
    na view;"), e o extrator ingenuo cortava a instrucao no meio da
    frase - o CREATE chegava truncado ao banco.
    """
    i = linha.find("--")
    return linha[:i] if i >= 0 else linha


def extrair(sql: str, nome: str) -> str:
    """Recorta `CREATE MATERIALIZED VIEW ... nome ... ;` do arquivo."""
    linhas = sql.splitlines()
    inicio = next(
        i for i, l in enumerate(linhas)
        if l.startswith(f"CREATE MATERIALIZED VIEW ouro.{nome}")
    )
    fim = inicio
    for i in range(inicio, len(linhas)):
        if _sem_comentario(linhas[i]).rstrip().endswith(";"):
            fim = i
            break
    return "\n".join(linhas[inicio:fim + 1])


def indices(sql: str, nome: str) -> list[str]:
    """Recorta os CREATE INDEX que apontam para a view, por linhas."""
    linhas = sql.splitlines()
    out: list[str] = []
    i = 0
    while i < len(linhas):
        codigo = _sem_comentario(linhas[i])
        if codigo.startswith("CREATE UNIQUE INDEX") or codigo.startswith("CREATE INDEX"):
            bloco = [linhas[i]]
            j = i
            while not _sem_comentario(linhas[j]).rstrip().endswith(";"):
                j += 1
                bloco.append(linhas[j])
            if nome in " ".join(bloco):
                out.append("\n".join(bloco))
            i = j + 1
            continue
        i += 1
    return out


def comentarios(sql: str, nome: str) -> list[str]:
    """Recorta os COMMENT ON que citam a view, por linhas."""
    linhas = sql.splitlines()
    out: list[str] = []
    i = 0
    while i < len(linhas):
        codigo = _sem_comentario(linhas[i])
        if codigo.startswith("COMMENT ON"):
            bloco = [linhas[i]]
            j = i
            while not _sem_comentario(linhas[j]).rstrip().endswith(";"):
                j += 1
                bloco.append(linhas[j])
            if nome in " ".join(bloco):
                out.append("\n".join(bloco))
            i = j + 1
            continue
        i += 1
    return out


def main() -> int:
    sql = io.open(SQL_FILE, encoding="utf-8").read()

    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        # DROP na ordem inversa das dependencias.
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS ouro.mv_sugestao_compra CASCADE")
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS ouro.mv_previsao_demanda CASCADE")
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS ouro.mv_demanda_diaria CASCADE")
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS ouro.mv_rupturas CASCADE")
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS ouro.mv_qualidade_loja CASCADE")
        print("  views antigas removidas")

        for nome in ORDEM:
            t0 = time.perf_counter()
            try:
                cur.execute(extrair(sql, nome))
            except Exception as exc:  # noqa: BLE001
                print(f"  X {nome}: {str(exc).splitlines()[0]}")
                return 1
            for ddl in indices(sql, nome):
                cur.execute(ddl)
            for com in comentarios(sql, nome):
                try:
                    cur.execute(com)
                except Exception:  # noqa: BLE001
                    pass
            cur.execute(f"SELECT count(*) FROM ouro.{nome}")
            n = cur.fetchone()[0]
            dt = time.perf_counter() - t0
            print(f"  ok {nome:<22} {n:>9,} linhas  {dt:6.2f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
