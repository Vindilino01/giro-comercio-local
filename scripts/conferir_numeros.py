"""Confere as afirmacoes numericas dos documentos contra o banco.

Roda as mesmas consultas que a documentacao cita e compara com o texto.
E o teste que faltava: os numeros do relatorio eram escritos a mao e
divergiam do banco em silencio.
"""

import io
import json
import re
from pathlib import Path

import psycopg

RAIZ = Path(__file__).parent.parent
DOCS = RAIZ / "docs"
DSN = "host=127.0.0.1 port=5433 dbname=giro user=postgres"

# O que cada afirmacao deve valer, medido agora.
with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    def um(sql: str):
        cur.execute(sql)
        return cur.fetchone()[0]

    real = {
        "vendas": um("SELECT count(*) FROM prata.venda"),
        "itens": um("SELECT count(*) FROM prata.item_venda"),
        "snapshots": um("SELECT count(*) FROM prata.estoque_snapshot"),
        "fato_vendas": um("SELECT count(*) FROM ouro.fato_vendas"),
        "produtos": um("SELECT count(*) FROM ouro.dim_produto"),
        "preco_faixas": um("SELECT count(*) FROM prata.produto_preco_historico"),
        "db_mb": um("SELECT round(pg_database_size('giro')/1024.0/1024)"),
        "tabelas": um("""
            SELECT count(*) FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind IN ('r','p')
               AND n.nspname IN ('prata','ouro','gov','bronze')
               AND c.relname NOT LIKE 'venda\\_20%'
               AND c.relname NOT LIKE 'item\\_venda\\_20%'
               AND c.relname NOT LIKE 'estoque\\_snapshot\\_20%'
               AND c.relname NOT LIKE 'movimentacao\\_estoque\\_20%'
               AND c.relname NOT LIKE 'item\\_pedido\\_20%'
        """),
        "regras": um("SELECT count(*) FROM gov.regra_qualidade"),
        "dimensoes": um("SELECT count(DISTINCT dimensao) FROM gov.metrica_qualidade"),
        "quarentena": um("SELECT count(*) FROM gov.quarentena"),
        "auditoria": um("SELECT count(*) FROM gov.auditoria"),
        "triggers": um("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"),
    }

print("=== medido no banco ===")
for k, v in real.items():
    print(f"  {k:<14} {v:>12,}" if isinstance(v, int) else f"  {k:<14} {v}")

# Metricas de qualidade vindas do JSON
m = json.loads((DOCS / "evidencias" / "metricas_qualidade.json")
               .read_text(encoding="utf-8"))
res = m["resumo"]
print("\n=== metricas de qualidade (JSON) ===")
for k in ("recall_global_pct", "recall_defeitos_de_linha_pct",
          "recall_defeitos_de_conjunto_pct", "registros_em_quarentena",
          "tipos_de_defeito"):
    print(f"  {k:<36} {res.get(k)}")

# Procura numeros que os docs afirmam e que nao batem
CHECAGENS = [
    ("6.361.900", "linhas geradas", 6_361_900),
    ("6.362.320", "linhas aceitas em lote_carga", None),
    ("4.159.608", "itens de venda", real["itens"]),
    ("4.134.291", "fato_vendas", real["fato_vendas"]),
    ("921.060", "snapshots", real["snapshots"]),
    ("545.093", "vendas", real["vendas"]),
    ("420", "produtos na dimensao", real["produtos"]),
]

print("\n=== numeros citados nos docs ===")
texto = "\n".join(p.read_text(encoding="utf-8") for p in DOCS.glob("*.md"))
for numero, rotulo, esperado in CHECAGENS:
    aparece = numero in texto
    bate = "n/a" if esperado is None else ("OK" if esperado == int(numero.replace(".", "")) else "DIVERGE")
    print(f"  {numero:<12} {rotulo:<32} citado={aparece}  {bate}")

# Dimensoes: o texto diz 7?
q7 = sum(1 for p in DOCS.glob("*.md")
         if re.search(r"sete dimens", p.read_text(encoding="utf-8"), re.I))
print(f"\n  docs que dizem 'sete dimensoes': {q7} "
      f"(banco mede {real['dimensoes']})")
