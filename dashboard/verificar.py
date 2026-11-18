"""
Verificacao do painel gerado contra o banco.

Confere que cada numero-chave exibido no HTML bate com a consulta que o
produziu. Roda depois de `python dashboard/gerar.py`.

    python dashboard/verificar.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
PAINEL = RAIZ / "docs" / "painel.html"
DSN = os.environ.get("GIRO_DSN", "host=127.0.0.1 port=5433 dbname=giro user=postgres")

falhas: list[str] = []
ok = 0


def brl(v: float) -> str:
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def check(nome: str, esperado, obtido) -> None:
    global ok
    if esperado == obtido:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(f"{nome}: esperado {esperado!r}, obtido {obtido!r}")
        print(f"  FAIL {nome}: esperado {esperado!r}, obtido {obtido!r}")


Z_POR_NIVEL = {95: 1.65}  # z do nivel de servico padrao da tela


def recalcular(p: dict, z: float = 1.65) -> tuple[float, int]:
    """Repete a conta do front: ponto de pedido, quantidade e valor em centavos.

    Usa `demanda_lt` (a demanda acumulada no horizonte de lead time) que o
    painel recebe pronto do banco, em vez de reconstruir a formula a partir
    da demanda diaria. A versao anterior multiplicava `demanda * lead` no
    verificador e no JS - duas copias da mesma formula, que divergiram em
    726 dos 1.260 itens quando a definicao de demanda mudou no banco.
    """
    import math

    lt = p["lead"] or 0
    dem_lt = p.get("demanda_lt")
    if dem_lt is None:
        dem_lt = (p["demanda"] or 0.0) * lt
    sig = p["sigma"] or 0.0
    est = p["estoque"] or 0.0
    mult = p["multiplo"] or 1

    ponto = dem_lt + z * sig * math.sqrt(lt)
    falta = max(0.0, ponto - est)
    qtd = math.ceil(falta / mult) * mult
    return qtd, round(qtd * (p["custo"] or 0.0) * 100)


def main() -> int:
    if not PAINEL.exists():
        print("painel.html nao existe; rode python dashboard/gerar.py")
        return 1

    html = PAINEL.read_text(encoding="utf-8")
    m = re.search(r"const DADOS = (\{.*?\});\n", html, re.S)
    if not m:
        print("nao achei o bloco de dados no HTML")
        return 1
    dados = json.loads(m.group(1).replace("<\\/", "</"))

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # 1. O total do pedido, por loja e consolidado.
        print("\nPedido:")
        cur.execute("""
            SELECT coalesce(loja_id, 0), round(sum(valor_compra_sugerido), 2)
              FROM ouro.mv_sugestao_compra
             WHERE situacao <> 'OK'
             GROUP BY GROUPING SETS ((loja_id), ())
             ORDER BY 1
        """)
        for loja_id, total in cur.fetchall():
            esperado = brl(float(total))
            linhas = [p for p in dados["pedido"] if loja_id == 0 or p["loja_id"] == loja_id]
            cent = 0
            for p in linhas:
                _, valor = recalcular(p)
                # A tela exclui o que nao precisa de compra.
                if valor > 0:
                    cent += valor
            check(f"total loja {loja_id}", esperado, brl(cent / 100))

        # 2. A perda em 12 meses.
        print("\nPerda em 12 meses:")
        cur.execute("""
            SELECT coalesce(loja_id, 0), round(sum(receita_perdida_estimada), 2)
              FROM ouro.mv_rupturas r
             WHERE data_venda > (SELECT max(data_venda) - interval '12 months'
                                   FROM ouro.fato_vendas)
             GROUP BY GROUPING SETS ((loja_id), ())
             ORDER BY 1
        """)
        for loja_id, total in cur.fetchall():
            no_payload = [p for p in dados["perda"] if p["loja_id"] == loja_id]
            check(f"perda loja {loja_id}", brl(float(total)),
                  brl(no_payload[0]["receita"]) if no_payload else "ausente")

        # 3. Taxa de ruptura.
        print("\nTaxa de ruptura:")
        cur.execute("""
            SELECT coalesce(loja_id, 0),
                   round(100.0 * count(*) FILTER (WHERE houve_ruptura) / count(*), 2)
              FROM ouro.fato_estoque_diario
             GROUP BY GROUPING SETS ((loja_id), ())
             ORDER BY 1
        """)
        for loja_id, taxa in cur.fetchall():
            no_payload = [r for r in dados["ruptura"] if r["loja_id"] == loja_id]
            check(f"taxa loja {loja_id}", float(taxa),
                  no_payload[0]["taxa_pct"] if no_payload else "ausente")

        # 4. Cada linha do pedido tem insumo para a conta ao vivo.
        print("\nIntegridade do payload:")
        faltando = [p for p in dados["pedido"]
                    if p["lead"] in (None, 0) or not p["fornecedor"] or p["demanda"] is None]
        check("linhas com insumo completo", 0, len(faltando))

        # 5. A soma por fornecedor bate com o total.
        por_forn: dict[str, int] = {}
        for p in dados["pedido"]:
            _, valor = recalcular(p)
            if valor > 0:
                por_forn[p["fornecedor"]] = por_forn.get(p["fornecedor"], 0) + valor
        cur.execute("""
            SELECT fornecedor, round(sum(valor_compra_sugerido), 2)
              FROM ouro.mv_sugestao_compra WHERE situacao <> 'OK' GROUP BY 1
        """)
        divergentes = 0
        for forn, total in cur.fetchall():
            if abs(por_forn.get(forn, 0) - round(float(total) * 100)) > 2:
                divergentes += 1
        check("soma por fornecedor bate com o banco", 0, divergentes)

        # 6. Nenhum texto de placeholder vazou para a tela. A busca ignora o
        #    base64 das fontes e os literais do proprio script.
        sem_fontes = re.sub(r"url\(data:font/woff2;base64,[^)]+\)", "", html)
        sem_script = re.sub(r"<script>.*?</script>", "", sem_fontes, flags=re.S)
        check("sem 'SEM DEPARTAMENTO'", False, "SEM DEPARTAMENTO" in sem_script)
        check("sem 'NaN'", False, "NaN" in sem_script)
        check("sem 'undefined'", False, "undefined" in sem_script)
        check("sem 'Infinity' visivel", False, "Infinity" in sem_script)

    print(f"\n{ok} verificacoes ok, {len(falhas)} falha(s)")
    for f in falhas:
        print("  -", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
