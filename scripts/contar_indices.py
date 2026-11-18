"""Conta definicoes de indice escritas no DDL (nao objetos fisicos).

A confusao que a auditoria apontou: `pg_indexes` devolve 464 linhas, mas
cada particao replica os indices da tabela mae, entao o numero mede
objetos no disco, nao decisoes de modelagem. Quem le "464 indices" pensa
em 464 escolhas justificadas; sao 29 definicoes, materializadas em 43
particoes cada.
"""
import io
import re
from pathlib import Path

RAIZ = Path(__file__).parent.parent
MIG = RAIZ / "db" / "migrations"

total = 0
print(f"{'arquivo':<34} {'definicoes':>10}")
print("-" * 46)
for sql in sorted(MIG.glob("*.sql")):
    texto = io.open(sql, encoding="utf-8").read()
    # remove comentarios de linha antes de contar
    codigo = "\n".join(
        l for l in texto.splitlines() if not l.strip().startswith("--"))
    n = len(re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX", codigo))
    if n:
        print(f"{sql.name:<34} {n:>10}")
        total += n
print("-" * 46)
print(f"{'TOTAL':<34} {total:>10}")
