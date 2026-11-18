"""Teste rapido do gerador. Roda a escala 'rapida' e valida invariantes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
from collections import defaultdict
from src.gerador import ESCALAS, gerar, ean13_valido, cnpj_valido

SAIDA = Path(__file__).parent.parent / "data" / "bronze" / "_teste"


def ler(nome):
    with (SAIDA / f"{nome}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    import shutil
    if SAIDA.exists():
        shutil.rmtree(SAIDA)

    print("Gerando escala 'rapida'...")
    resumo = gerar(ESCALAS["rapida"], SAIDA, verbose=True)

    erros: list[str] = []

    # --- produtos ---------------------------------------------------
    produtos = ler("produto")
    eans = [p["ean"] for p in produtos]
    if len(set(eans)) != len(eans):
        erros.append("EAN duplicado no catalogo")
    invalidos = [e for e in eans if not ean13_valido(e)]
    if invalidos:
        erros.append(f"{len(invalidos)} EAN(s) com digito verificador invalido: {invalidos[:3]}")

    for p in produtos:
        if p["perecivel"] == "true" and not p["dias_validade"]:
            erros.append(f"perecivel sem validade: {p['sku_interno']}")
        if p["perecivel"] == "false" and p["dias_validade"]:
            erros.append(f"nao-perecivel com validade: {p['sku_interno']}")
        if float(p["preco_venda"]) <= float(p["preco_custo"]):
            erros.append(f"preco de venda <= custo: {p['sku_interno']}")

    fornecedores = ler("fornecedor")
    for f in fornecedores:
        if not cnpj_valido(f["cnpj"]):
            erros.append(f"CNPJ invalido: {f['cnpj']}")

    # --- vendas -----------------------------------------------------
    vendas = ler("venda")
    itens = ler("item_venda")
    if not vendas:
        erros.append("nenhuma venda gerada")

    # Total do cupom = soma dos itens
    soma_por_venda = defaultdict(float)
    qtd_por_venda = defaultdict(int)
    for it in itens:
        soma_por_venda[(it["venda_id"], it["data_venda"])] += float(it["valor_total"])
        qtd_por_venda[(it["venda_id"], it["data_venda"])] += 1

    divergencias = 0
    for v in vendas:
        chave = (v["venda_id"], v["data_venda"])
        soma = round(soma_por_venda[chave], 2)
        liquido = round(float(v["valor_liquido"]), 2)
        if abs(soma - liquido) > 0.02:
            divergencias += 1
        if qtd_por_venda[chave] != int(v["qtd_itens"]):
            erros.append(f"qtd_itens incoerente na venda {v['venda_id']}")
        bruto = float(v["valor_bruto"])
        desc = float(v["valor_desconto"])
        if abs(round(bruto - desc, 2) - liquido) > 0.001:
            erros.append(f"bruto-desconto != liquido na venda {v['venda_id']}")
    if divergencias:
        erros.append(f"{divergencias} vendas com soma de itens != valor_liquido")

    # --- estoque ----------------------------------------------------
    snaps = ler("estoque_snapshot")
    eq_ruins = 0
    negativos = 0
    for s in snaps:
        ini = float(s["qtd_inicio"])
        ent = float(s["qtd_entradas"])
        sai = float(s["qtd_saidas"])
        aju = float(s["qtd_ajustes"])
        fim = float(s["qtd_fim"])
        # Equacao: fim = inicio + entradas - saidas + ajustes
        #
        # ATENCAO ao sinal de `saidas`: `qtd_saidas` e MAGNITUDE positiva
        # (a direcao e dada pelo nome da coluna), exatamente como a
        # constraint snapshot_equacao_ck no banco. Uma versao anterior
        # deste teste usava `+ sai`, herdada de quando a coluna aceitava
        # valores negativos - e passou a acusar 15.601 snapshots
        # corretos como furados depois que o modelo mudou.
        if abs(round(ini + ent - sai + aju, 3) - fim) > 0.002:
            eq_ruins += 1
        if ini < 0 or fim < 0:
            negativos += 1
    if eq_ruins:
        erros.append(f"{eq_ruins} snapshots com equacao de estoque furada")
    if negativos:
        erros.append(f"{negativos} snapshots com quantidade negativa")

    # --- pedidos ----------------------------------------------------
    pedidos = ler("pedido_compra")
    itens_ped = ler("item_pedido")
    if len(pedidos) != len(itens_ped):
        erros.append(f"pedidos ({len(pedidos)}) != itens_pedido ({len(itens_ped)})")

    # --- resultado --------------------------------------------------
    print()
    if erros:
        print(f"FALHOU - {len(erros)} problema(s):")
        for e in erros[:20]:
            print(f"  - {e}")
        return 1

    total = sum(resumo.tabelas.values())
    print(f"OK - {total:,} linhas geradas, todas as invariantes validas")
    print(f"     vendas={len(vendas):,}  itens={len(itens):,}  "
          f"snapshots={len(snaps):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
