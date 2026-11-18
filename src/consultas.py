"""
Executa as consultas de negocio e exporta as evidencias.

Por que exportar:
  1. O relatorio precisa citar numeros. Se o numero nao tiver origem
     verificavel, e afirmacao, nao evidencia.
  2. O professor pode reproduzir. Cada arquivo em docs/evidencias traz
     a consulta SQL, o plano de execucao e o resultado.
  3. O pitch pode mostrar o numero sem depender do banco estar no ar.

Formato de saida, por consulta:
  docs/evidencias/qNN_<nome>.md    -> consulta + resultado em tabela
  docs/evidencias/qNN_<nome>.json  -> resultado estruturado
  docs/evidencias/qNN_<nome>.plan.txt -> EXPLAIN (ANALYZE, BUFFERS)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg


@dataclass
class Consulta:
    numero: str
    nome: str
    arquivo: Path
    pergunta: str


CONSULTAS: list[Consulta] = [
    Consulta("Q01", "ruptura_demanda_perdida", Path("q01_ruptura_demanda_perdida.sql"),
             "Quanto deixei de vender por falta de produto?"),
    Consulta("Q02", "sugestao_compra", Path("q02_sugestao_compra.sql"),
             "O que comprar hoje e quanto custa?"),
    Consulta("Q02b", "lista_compra", Path("q02b_lista_compra.sql"),
             "Quais SKUs priorizar na compra?"),
    Consulta("Q03", "curva_abc", Path("q03_curva_abc.sql"),
             "Quais 20% dos produtos fazem 80% da receita?"),
    Consulta("Q04", "giro_cobertura", Path("q04_giro_cobertura.sql"),
             "Onde meu dinheiro esta parado?"),
    Consulta("Q05", "risco_vencimento", Path("q05_risco_vencimento.sql"),
             "O que vai vencer e virar prejuizo?"),
    Consulta("Q06", "acuracidade_inventario", Path("q06_acuracidade_inventario.sql"),
             "Posso confiar no estoque do sistema?"),
    Consulta("Q07", "sazonalidade", Path("q07_sazonalidade.sql"),
             "Quando eu vendo mais?"),
    Consulta("Q08", "otif_fornecedores", Path("q08_otif_fornecedores.sql"),
             "Qual fornecedor me deixa na mao?"),
    Consulta("Q09", "lift_promocao", Path("q09_lift_promocao.sql"),
             "A promocao valeu a pena?"),
    Consulta("Q10", "painel_qualidade", Path("q10_painel_qualidade.sql"),
             "Posso confiar nos numeros que estou vendo?"),
]


def _json_velho(v):
    """Serializa Decimal como numero, nao como string.

    `default=str` transformava Decimal("266318.86") em "266318.86" - que
    um leitor pt-BR interpreta como duzentos e sessenta e seis mil. Agora
    sai como float, e quem exibe decide o formato.
    """
    from decimal import Decimal
    if isinstance(v, Decimal):
        return float(v)
    return str(v)


def _formatar_tabela(colunas: list[str], linhas: list[tuple]) -> str:
    """Renderiza resultado em tabela Markdown."""
    from decimal import Decimal

    if not linhas:
        return "_(sem resultado)_\n"

    def celula(v) -> str:
        if v is None:
            return "—"
        if isinstance(v, Decimal):
            v = float(v)
        if isinstance(v, float):
            return f"{v:,.2f}".replace(",", "\u00a0")
        if isinstance(v, int):
            return f"{v:,}".replace(",", "\u00a0")
        return str(v).replace("|", "\\|")

    larguras = [len(c) for c in colunas]
    texto = [[celula(v) for v in linha] for linha in linhas]
    for linha in texto:
        for i, c in enumerate(linha):
            larguras[i] = max(larguras[i], len(c))

    cab = "| " + " | ".join(c.ljust(larguras[i]) for i, c in enumerate(colunas)) + " |"
    sep = "|" + "|".join("-" * (l + 2) for l in larguras) + "|"
    corpo = [
        "| " + " | ".join(c.ljust(larguras[i]) for i, c in enumerate(linha)) + " |"
        for linha in texto
    ]
    return "\n".join([cab, sep, *corpo]) + "\n"


def executar_todas(conn: psycopg.Connection, raiz: Path | None = None,
                   pasta_saida: Path | None = None,
                   verbose: bool = True) -> dict:
    """Executa todas as consultas e exporta as evidencias.

    `raiz` e a raiz do projeto (onde ficam db/queries e docs/evidencias).
    `pasta_saida` permite redirecionar a saida em testes, sem confundir
    com a raiz de onde os .sql sao lidos.
    """
    if raiz is None:
        raiz = Path(__file__).parent.parent
    evidencias = pasta_saida or (raiz / "docs" / "evidencias")
    evidencias.mkdir(parents=True, exist_ok=True)
    consulta_dir = raiz / "db" / "queries"

    indice: dict = {"consultas": [], "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S")}

    for c in CONSULTAS:
        caminho_sql = consulta_dir / c.arquivo
        if not caminho_sql.exists():
            if verbose:
                print(f"    {c.numero:<5} ARQUIVO AUSENTE: {c.arquivo}")
            continue

        sql = caminho_sql.read_text(encoding="utf-8")
        # EXPLAIN antes de executar (nao consome o cursor)
        plano = ""
        try:
            with conn.cursor() as cur:
                cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql)
                plano = "\n".join(r[0] for r in cur.fetchall())
            conn.rollback()
        except Exception as exc:  # noqa: BLE001
            plano = f"-- EXPLAIN falhou: {exc}"
            conn.rollback()

        t0 = time.time()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                colunas = [d[0] for d in cur.description] if cur.description else []
                linhas = cur.fetchall() if cur.description else []
            conn.rollback()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            if verbose:
                print(f"    {c.numero:<5} {c.nome:<26} ERRO: {str(exc).splitlines()[0][:90]}")
            (evidencias / f"{c.numero.lower()}_{c.nome}.error.txt").write_text(
                str(exc), encoding="utf-8")
            indice["consultas"].append({
                "numero": c.numero, "nome": c.nome,
                "pergunta": c.pergunta, "erro": str(exc).splitlines()[0],
            })
            continue

        duracao_ms = round((time.time() - t0) * 1000, 1)

        # Arquivos de evidencia
        base = evidencias / f"{c.numero.lower()}_{c.nome}"
        (base.with_suffix(".json")).write_text(
            json.dumps({"colunas": colunas, "linhas": linhas},
                       ensure_ascii=False, indent=2, default=_json_velho),
            encoding="utf-8")
        (base.with_suffix(".plan.txt")).write_text(plano, encoding="utf-8")

        md = [
            f"# {c.numero} — {c.nome.replace('_', ' ').title()}",
            "",
            f"**Pergunta de negocio:** {c.pergunta}",
            "",
            f"**Linhas retornadas:** {len(linhas)}  ",
            f"**Tempo de execucao:** {duracao_ms} ms",
            "",
            "## Consulta",
            "",
            "```sql",
            sql.strip(),
            "```",
            "",
            "## Resultado",
            "",
            _formatar_tabela(colunas, linhas),
        ]
        (base.with_suffix(".md")).write_text("\n".join(md), encoding="utf-8")

        if verbose:
            print(f"    {c.numero:<5} {c.nome:<26} {len(linhas):>5} linhas  "
                  f"{duracao_ms:>8.1f} ms")

        indice["consultas"].append({
            "numero": c.numero, "nome": c.nome, "pergunta": c.pergunta,
            "linhas": len(linhas), "duracao_ms": duracao_ms,
            "colunas": colunas,
        })

    (evidencias / "indice_consultas.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")

    return indice


def main() -> None:
    import os

    raiz = Path(__file__).parent.parent
    dsn = os.environ.get("GIRO_DSN",
                         "host=127.0.0.1 port=5433 dbname=giro user=postgres")
    print("Executando consultas de negocio...")
    with psycopg.connect(dsn) as conn:
        indice = executar_todas(conn, raiz)
    print(f"\n{len(indice['consultas'])} consultas exportadas em docs/evidencias/")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    main()
