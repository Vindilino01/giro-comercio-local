"""Testa o roteiro do guia da banca, comando por comando.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Um guia que nao roda nao serve. Este script executa exatamente os comandos
que o docs/guia-banca.md manda a pessoa rodar, e falha se algum nao
devolver o que o guia promete.

Nao testa o psql interativo (impossivel sem TTY); testa as CONSULTAS e a
existencia dos binarios, que e onde o guia pode mentir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent
PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"

DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

falhas = 0


def ok(nome: str, cond: bool, detalhe: str = "") -> None:
    global falhas
    print(f"{'OK  ' if cond else 'FALHA'} {nome}" + (f" — {detalhe}" if detalhe else ""))
    if not cond:
        falhas += 1


def psql(sql: str) -> tuple[bool, str]:
    """Roda um comando pelo psql, como o guia manda."""
    if not Path(PSQL).exists():
        return False, "psql nao encontrado"
    r = subprocess.run(
        [PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "postgres",
         "-d", "giro", "-t", "-A", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()


# ---------------------------------------------------------------------
# 1. binarios que o guia manda usar
# ---------------------------------------------------------------------
ok("psql no caminho do guia", Path(PSQL).exists(), PSQL)
dot = Path(r"C:\Program Files\Graphviz\bin\dot.exe")
ok("Graphviz instalado (gera o MER)", dot.exists(), str(dot))

# ---------------------------------------------------------------------
# 2. as consultas da secao 3
# ---------------------------------------------------------------------
ok_sql, saida = psql("select count(*) from information_schema.schemata "
                     "where schema_name in ('prata','ouro','gov')")
ok("3.1 tres schemas existem", ok_sql and saida == "3", saida)

ok_sql, saida = psql("""
    select count(*) from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'prata' and c.relkind in ('r','p')
       and c.relispartition = false
""")
ok("3.2 prata tem 15 tabelas logicas", ok_sql and saida == "15", saida)

ok_sql, saida = psql("""
    select count(*) from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'ouro' and c.relkind = 'r'
       and c.relispartition = false
""")
ok("3.2 ouro tem 8 tabelas", ok_sql and saida == "8", saida)

ok_sql, saida = psql("""
    select count(*) from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'gov' and c.relkind = 'r'
""")
ok("3.2 gov tem 5 tabelas", ok_sql and saida == "5", saida)

ok_sql, saida = psql("select count(*) from pg_matviews where schemaname='ouro'")
ok("3.4 cinco views materializadas", ok_sql and saida == "5", saida)

# ---------------------------------------------------------------------
# 3. a prova que fecha a arguicao (secao 3.5)
# ---------------------------------------------------------------------
ok_sql, saida = psql("select round(sum(valor_compra_sugerido)::numeric, 2) "
                     "from ouro.mv_sugestao_compra")
ok("3.5 total do pedido responde", ok_sql and saida, f"R$ {saida}")

ok_sql, saida = psql("select count(*) from prata.item_venda")
ok("4 linhas em item_venda respondem", ok_sql and saida, saida)

# ---------------------------------------------------------------------
# 4. os arquivos que o guia manda abrir
# ---------------------------------------------------------------------
for nome in ("mer.svg", "mer-prata.svg", "mer-ouro.svg", "mer.png",
             "casos-de-uso.svg", "casos-de-uso.png",
             "dicionario-de-dados.md", "guia-banca.md"):
    caminho = RAIZ / "docs" / nome
    ok(f"docs/{nome}", caminho.exists(),
       f"{caminho.stat().st_size / 1024:.0f} KB" if caminho.exists() else "AUSENTE")

# ---------------------------------------------------------------------
# 5. o MER inclui as tabelas que importam
# ---------------------------------------------------------------------
svg = (RAIZ / "docs" / "mer-prata.svg").read_text(encoding="utf-8")
for tabela in ("venda", "item_venda", "produto", "loja", "categoria",
               "estoque_snapshot", "movimentacao_estoque"):
    ok(f"MER prata inclui {tabela}", f">{tabela}<" in svg)

# ---------------------------------------------------------------------
# 6. o diagrama de casos de uso tem os 14 casos
# ---------------------------------------------------------------------
svg_uc = (RAIZ / "docs" / "casos-de-uso.svg").read_text(encoding="utf-8")
import re
ucs = sorted(set(re.findall(r"UC\d\d", svg_uc)))
ok("casos de uso: 14 casos", len(ucs) == 14, f"{len(ucs)}: {ucs[0]}..{ucs[-1]}")

# ---------------------------------------------------------------------
# 7. numeros do guia conferem com o banco
# ---------------------------------------------------------------------
ok_sql, saida = psql("""
    select count(*) from pg_constraint con
     join pg_namespace n on n.oid = con.connamespace
     where con.contype = 'f' and n.nspname in ('prata','ouro','gov')
""")
ok("guia: 249 chaves estrangeiras", ok_sql and saida == "249", saida)

ok_sql, saida = psql("""
    select count(*) from pg_indexes
     where schemaname in ('prata','ouro','gov')
""")
ok("guia: 464 indices", ok_sql and saida == "464", saida)

print()
print(f"{'GUIA OK' if falhas == 0 else str(falhas) + ' FALHA(S)'}")
sys.exit(0 if falhas == 0 else 1)
