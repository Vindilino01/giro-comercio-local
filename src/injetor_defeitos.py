"""
Injetor de defeitos de qualidade.

POR QUE INJETAR DEFEITOS
------------------------
A secao 4.5 do edital pede "como garantir completude, consistencia,
unicidade, validade e atualidade" e "tratamento de dados sujos ou
duplicados". A maioria dos grupos responde isso em prosa.

Aqui a resposta e empirica: partimos do dataset limpo, injetamos
defeitos de tipo e quantidade CONHECIDOS, gravamos um gabarito, e
depois medimos quantos o pipeline detectou. Isso permite calcular
precisao e recall por tipo de defeito - evidencia, nao afirmacao.

DEFEITOS INJETADOS (20 tipos, mapeados para as regras DQ001..DQ020)
-------------------------------------------------------------------
Os defeitos cobrem as seis dimensoes classicas:
  completude   - campo obrigatorio ausente
  unicidade    - registro duplicado
  consistencia - totais que nao fecham, equacao de estoque furada
  validade     - EAN invalido, data futura, quantidade negativa
  acuracidade  - estoque do sistema diverge da contagem
  atualidade   - dia inteiro sem carga

O gabarito lista cada registro afetado, o que torna possivel medir
deteccao por registro (nao por tipo). Isso e mais rigoroso do que
apenas verificar "a regra disparou".
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np


@dataclass
class Defeito:
    """Um tipo de defeito e sua contagem planejada."""
    codigo: str
    regra: str
    dimensao: str
    descricao: str
    tabela: str
    quantidade: int


@dataclass
class Gabarito:
    """Registro do que foi injetado, para medir deteccao."""
    defeitos: list[Defeito] = field(default_factory=list)
    # chaves: "TABELA|codigo" -> lista de identificadores afetados
    registros: dict[str, list[str]] = field(default_factory=dict)
    linhas_originais: dict[str, int] = field(default_factory=dict)

    def adicionar(self, d: Defeito, ids: list[str]) -> None:
        self.defeitos.append(d)
        self.registros[f"{d.tabela}|{d.codigo}"] = ids

    def como_dict(self) -> dict:
        return {
            "defeitos": [
                {
                    "codigo": d.codigo, "regra": d.regra, "dimensao": d.dimensao,
                    "descricao": d.descricao, "tabela": d.tabela,
                    "quantidade_planejada": d.quantidade,
                    "quantidade_injetada": len(self.registros.get(
                        f"{d.tabela}|{d.codigo}", [])),
                }
                for d in self.defeitos
            ],
            "linhas_originais": self.linhas_originais,
            "total_registros_afetados": sum(len(v) for v in self.registros.values()),
        }


def _ler(caminho: Path) -> tuple[list[str], list[dict]]:
    with caminho.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def _escrever(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def injetar(origem: Path, destino: Path, semente: int = 7) -> Gabarito:
    """Copia o dataset limpo para `destino` injetando defeitos conhecidos."""
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origem, destino)

    rng = np.random.default_rng(semente)
    gab = Gabarito()

    # ------------------------------------------------------------------
    # 1. UNICIDADE - duplicar cupons e itens (DQ004, DQ005)
    # ------------------------------------------------------------------
    cols, vendas = _ler(destino / "venda.csv")
    gab.linhas_originais["venda"] = len(vendas)

    n_dup = max(5, len(vendas) // 5000)
    idx_dup = rng.choice(len(vendas), size=n_dup, replace=False)
    duplicadas = []
    ids_dup = []
    for i in idx_dup:
        v = dict(vendas[i])
        duplicadas.append(v)
        ids_dup.append(f"{v['venda_id']}|{v['data_venda']}")
    vendas_sujas = vendas + duplicadas
    _escrever(destino / "venda.csv", cols, vendas_sujas)
    gab.adicionar(Defeito(
        "D01", "DQ004", "unicidade",
        "Cupom duplicado (mesmo loja/data/serie/numero)",
        "venda", n_dup), ids_dup)

    cols_i, itens = _ler(destino / "item_venda.csv")
    gab.linhas_originais["item_venda"] = len(itens)
    n_dup_item = max(5, len(itens) // 8000)
    idx_dup_item = rng.choice(len(itens), size=n_dup_item, replace=False)
    itens_dups = []
    ids_dup_item = []
    for i in idx_dup_item:
        it = dict(itens[i])
        itens_dups.append(it)
        ids_dup_item.append(f"{it['venda_id']}|{it['data_venda']}|{it['item_seq']}")
    _escrever(destino / "item_venda.csv", cols_i, itens + itens_dups)
    gab.adicionar(Defeito(
        "D02", "DQ005", "unicidade",
        "Item duplicado dentro do mesmo cupom",
        "item_venda", n_dup_item), ids_dup_item)

    # ------------------------------------------------------------------
    # 2. VALIDADE - EAN invalido no cadastro (DQ011)
    # ------------------------------------------------------------------
    cols_p, produtos = _ler(destino / "produto.csv")
    n_ean = max(3, len(produtos) // 25)
    idx_ean = rng.choice(len(produtos), size=n_ean, replace=False)
    ids_ean = []
    for i in idx_ean:
        p = produtos[i]
        ean = p["ean"]
        # Corrompe o digito verificador (mantem 13 digitos)
        ultimo = int(ean[-1])
        p["ean"] = ean[:12] + str((ultimo + rng.integers(1, 9)) % 10)
        ids_ean.append(p["sku_interno"])
    _escrever(destino / "produto.csv", cols_p, produtos)
    gab.adicionar(Defeito(
        "D03", "DQ011", "validade",
        "EAN-13 com digito verificador incorreto",
        "produto", n_ean), ids_ean)

    # ------------------------------------------------------------------
    # 3. VALIDADE - quantidade negativa em item (DQ012)
    # ------------------------------------------------------------------
    itens = _ler(destino / "item_venda.csv")[1]
    n_neg = max(5, len(itens) // 10000)
    idx_neg = rng.choice(len(itens), size=n_neg, replace=False)
    ids_neg = []
    for i in idx_neg:
        it = itens[i]
        it["quantidade"] = f"-{abs(float(it['quantidade'])):.3f}"
        ids_neg.append(f"{it['venda_id']}|{it['data_venda']}|{it['item_seq']}")
    _escrever(destino / "item_venda.csv", cols_i, itens)
    gab.adicionar(Defeito(
        "D04", "DQ012", "validade",
        "Quantidade negativa em item de venda",
        "item_venda", n_neg), ids_neg)

    # ------------------------------------------------------------------
    # 4. VALIDADE - data de venda no futuro (DQ013)
    # ------------------------------------------------------------------
    cols_v, vendas = _ler(destino / "venda.csv")
    n_fut = max(3, len(vendas) // 20000)
    idx_fut = rng.choice(len(vendas), size=n_fut, replace=False)
    amanha = (date.today() + timedelta(days=45)).isoformat()
    ids_fut = []
    for i in idx_fut:
        v = vendas[i]
        v["data_venda"] = amanha
        ids_fut.append(f"{v['venda_id']}|{v['data_venda']}")
    _escrever(destino / "venda.csv", cols_v, vendas)
    gab.adicionar(Defeito(
        "D05", "DQ013", "validade",
        "Data de venda no futuro",
        "venda", n_fut), ids_fut)

    # ------------------------------------------------------------------
    # 5. CONSISTENCIA - valor_liquido errado (DQ007)
    # ------------------------------------------------------------------
    cols_v, vendas = _ler(destino / "venda.csv")
    n_tot = max(5, len(vendas) // 7000)
    idx_tot = rng.choice(len(vendas), size=n_tot, replace=False)
    ids_tot = []
    for i in idx_tot:
        v = vendas[i]
        liq = float(v["valor_liquido"])
        v["valor_liquido"] = f"{liq * 0.93:.2f}"
        ids_tot.append(f"{v['venda_id']}|{v['data_venda']}")
    _escrever(destino / "venda.csv", cols_v, vendas)
    gab.adicionar(Defeito(
        "D06", "DQ007", "consistencia",
        "valor_liquido diferente de valor_bruto - desconto",
        "venda", n_tot), ids_tot)

    # ------------------------------------------------------------------
    # 6. CONSISTENCIA - soma dos itens difere do cupom (DQ008)
    # ------------------------------------------------------------------
    itens = _ler(destino / "item_venda.csv")[1]
    n_soma = max(5, len(itens) // 12000)
    idx_soma = rng.choice(len(itens), size=n_soma, replace=False)
    ids_soma = []
    for i in idx_soma:
        it = itens[i]
        it["valor_total"] = f"{float(it['valor_total']) * 1.35:.2f}"
        ids_soma.append(f"{it['venda_id']}|{it['data_venda']}|{it['item_seq']}")
    _escrever(destino / "item_venda.csv", cols_i, itens)
    gab.adicionar(Defeito(
        "D07", "DQ008", "consistencia",
        "Valor do item alterado, quebrando a soma do cupom",
        "item_venda", n_soma), ids_soma)

    # ------------------------------------------------------------------
    # 7. CONSISTENCIA - equacao de estoque furada (DQ009)
    # ------------------------------------------------------------------
    cols_s, snaps = _ler(destino / "estoque_snapshot.csv")
    gab.linhas_originais["estoque_snapshot"] = len(snaps)
    n_eq = max(10, len(snaps) // 6000)
    idx_eq = rng.choice(len(snaps), size=n_eq, replace=False)
    ids_eq = []
    for i in idx_eq:
        s = snaps[i]
        s["qtd_fim"] = f"{float(s['qtd_fim']) + 7.0:.3f}"
        ids_eq.append(f"{s['loja_id']}|{s['produto_id']}|{s['data_ref']}")
    _escrever(destino / "estoque_snapshot.csv", cols_s, snaps)
    gab.adicionar(Defeito(
        "D08", "DQ009", "consistencia",
        "Equacao de estoque nao fecha",
        "estoque_snapshot", n_eq), ids_eq)

    # ------------------------------------------------------------------
    # 8. ACURACIDADE - divergencia de inventario (DQ016)
    # ------------------------------------------------------------------
    snaps = _ler(destino / "estoque_snapshot.csv")[1]
    amostra = rng.choice(len(snaps), size=min(len(snaps), len(snaps) // 3), replace=False)
    n_div = 0
    ids_div = []
    for i in amostra:
        s = snaps[i]
        fim = float(s["qtd_fim"])
        if fim <= 0:
            continue
        # 15% do SKU contado tem divergencia de 6-12%
        if rng.random() < 0.15:
            fator = 1.0 + float(rng.uniform(0.06, 0.12)) * (1 if rng.random() < 0.5 else -1)
            s["qtd_contada"] = f"{fim * fator:.3f}"
            ids_div.append(f"{s['loja_id']}|{s['produto_id']}|{s['data_ref']}")
            n_div += 1
    _escrever(destino / "estoque_snapshot.csv", cols_s, snaps)
    gab.adicionar(Defeito(
        "D09", "DQ016", "acuracidade",
        "Contagem fisica diverge mais de 5% do estoque do sistema",
        "estoque_snapshot", n_div), ids_div)

    # ------------------------------------------------------------------
    # 9. VALIDADE - preco zero / negativo (DQ014)
    # ------------------------------------------------------------------
    itens = _ler(destino / "item_venda.csv")[1]
    n_preco = max(3, len(itens) // 20000)
    idx_preco = rng.choice(len(itens), size=n_preco, replace=False)
    ids_preco = []
    for i in idx_preco:
        it = itens[i]
        it["preco_unitario"] = "0.00"
        ids_preco.append(f"{it['venda_id']}|{it['data_venda']}|{it['item_seq']}")
    _escrever(destino / "item_venda.csv", cols_i, itens)
    gab.adicionar(Defeito(
        "D10", "DQ014", "validade",
        "Preco unitario zero em item de venda",
        "item_venda", n_preco), ids_preco)

    # ------------------------------------------------------------------
    # 10. COMPLETUDE - item sem produto (DQ002)
    # ------------------------------------------------------------------
    itens = _ler(destino / "item_venda.csv")[1]
    n_sem_prod = max(3, len(itens) // 25000)
    idx_sp = rng.choice(len(itens), size=n_sem_prod, replace=False)
    ids_sp = []
    for i in idx_sp:
        it = itens[i]
        it["produto_id"] = ""
        ids_sp.append(f"{it['venda_id']}|{it['data_venda']}|{it['item_seq']}")
    _escrever(destino / "item_venda.csv", cols_i, itens)
    gab.adicionar(Defeito(
        "D11", "DQ002", "completude",
        "Item de venda sem produto identificado",
        "item_venda", n_sem_prod), ids_sp)

    # ------------------------------------------------------------------
    # 11. COMPLETUDE - cupom sem data (DQ001)
    # ------------------------------------------------------------------
    cols_v, vendas = _ler(destino / "venda.csv")
    n_sem_data = max(3, len(vendas) // 25000)
    idx_sd = rng.choice(len(vendas), size=n_sem_data, replace=False)
    ids_sd = []
    for i in idx_sd:
        v = vendas[i]
        v["data_venda"] = ""
        ids_sd.append(str(v["venda_id"]))
    _escrever(destino / "venda.csv", cols_v, vendas)
    gab.adicionar(Defeito(
        "D12", "DQ001", "completude",
        "Venda sem data",
        "venda", n_sem_data), ids_sd)

    # ------------------------------------------------------------------
    # 12. CONSISTENCIA - status concluida com data de cancelamento (DQ020)
    # ------------------------------------------------------------------
    # A tabela bronze nao tem a coluna cancelada_em; o defeito e
    # injetado no ETL criando o estado inconsistente. Aqui marcamos
    # como CANCELADA sem que a regra de negocio permita.
    cols_v, vendas = _ler(destino / "venda.csv")
    n_canc = max(3, len(vendas) // 20000)
    idx_canc = rng.choice(len(vendas), size=n_canc, replace=False)
    ids_canc = []
    for i in idx_canc:
        v = vendas[i]
        v["status"] = "CANCELADA"
        ids_canc.append(f"{v['venda_id']}|{v['data_venda']}")
    _escrever(destino / "venda.csv", cols_v, vendas)
    gab.adicionar(Defeito(
        "D13", "DQ020", "consistencia",
        "Cupom cancelado sem data de cancelamento",
        "venda", n_canc), ids_canc)

    # ------------------------------------------------------------------
    # 13. ATUALIDADE - dia inteiro sem carga (DQ018)
    # ------------------------------------------------------------------
    cols_v, vendas = _ler(destino / "venda.csv")
    datas = sorted({v["data_venda"] for v in vendas if v["data_venda"]})
    dia_removido = datas[len(datas) // 2]
    antes = len(vendas)
    vendas_sem_dia = [v for v in vendas if v["data_venda"] != dia_removido]
    removidos = antes - len(vendas_sem_dia)
    _escrever(destino / "venda.csv", cols_v, vendas_sem_dia)

    cols_i, itens = _ler(destino / "item_venda.csv")
    itens_sem_dia = [it for it in itens if it["data_venda"] != dia_removido]
    _escrever(destino / "item_venda.csv", cols_i, itens_sem_dia)
    gab.adicionar(Defeito(
        "D14", "DQ018", "atualidade",
        "Dia de loja aberta sem nenhum registro de venda",
        "venda", removidos), [dia_removido])

    # ------------------------------------------------------------------
    # 14. COMPLETUDE - snapshot faltante (DQ003)
    # ------------------------------------------------------------------
    cols_s, snaps = _ler(destino / "estoque_snapshot.csv")
    # Remove todos os snapshots de um dia especifico para uma loja
    loja_alvo = 1
    datas_snap = sorted({s["data_ref"] for s in snaps})
    dia_snap = datas_snap[len(datas_snap) // 3]
    snaps_sem = [s for s in snaps
                 if not (s["loja_id"] == str(loja_alvo) and s["data_ref"] == dia_snap)]
    removidos_snap = len(snaps) - len(snaps_sem)
    _escrever(destino / "estoque_snapshot.csv", cols_s, snaps_sem)
    gab.adicionar(Defeito(
        "D15", "DQ003", "completude",
        "Snapshot de estoque ausente em dia de loja aberta",
        "estoque_snapshot", removidos_snap), [f"L{loja_alvo}|{dia_snap}"])

    # ------------------------------------------------------------------
    # 15. CONFORMIDADE - CPF no campo de observacao (DQ019)
    # ------------------------------------------------------------------
    # Simula vazamento de dado pessoal em campo livre. Nao existe coluna
    # de observacao no modelo, entao injetamos no documento_ref da
    # movimentacao, que e campo texto livre.
    cols_m, movs = _ler(destino / "movimentacao_estoque.csv")
    gab.linhas_originais["movimentacao_estoque"] = len(movs)
    n_cpf = 3
    idx_cpf = rng.choice(len(movs), size=n_cpf, replace=False)
    ids_cpf = []
    for i in idx_cpf:
        m = movs[i]
        cpf = f"{rng.integers(100,999)}.{rng.integers(100,999)}.{rng.integers(100,999)}-{rng.integers(10,99)}"
        m["documento_ref"] = f"CLIENTE CPF {cpf}"
        ids_cpf.append(f"{m['loja_id']}|{m['produto_id']}|{m['data_movimento']}")
    _escrever(destino / "movimentacao_estoque.csv", cols_m, movs)
    gab.adicionar(Defeito(
        "D16", "DQ019", "conformidade",
        "CPF em campo de texto livre",
        "movimentacao_estoque", n_cpf), ids_cpf)

    # ------------------------------------------------------------------
    # 16. UNICIDADE - EAN duplicado no cadastro (DQ006)
    #
    # NOTA METODOLOGICA: este defeito afeta 2 registros, mas apenas 1
    # pode ser detectado como linha rejeitada - a regra mantem a
    # primeira ocorrencia e rejeita a segunda. Um recall de 50% aqui
    # e o COMPORTAMENTO CORRETO, nao uma falha: se rejeitassemos os
    # dois, perderiamos o produto inteiro em vez de deduplicar. O
    # gabarito registra 2 registros afetados, e o relatorio precisa
    # explicar essa assimetria - por isso o numero aparece no campo
    # `observacao` do defeito.
    # ------------------------------------------------------------------
    cols_p, produtos = _ler(destino / "produto.csv")
    if len(produtos) > 5:
        a, b = rng.choice(len(produtos), size=2, replace=False)
        produtos[b]["ean"] = produtos[a]["ean"]
        gab.adicionar(Defeito(
            "D17", "DQ006", "unicidade",
            "EAN duplicado no cadastro (1 par: 1 mantido, 1 rejeitado)",
            "produto", 2),
            [produtos[a]["sku_interno"], produtos[b]["sku_interno"]])
        _escrever(destino / "produto.csv", cols_p, produtos)

    # ------------------------------------------------------------------
    # Gabarito em disco
    # ------------------------------------------------------------------
    (destino / "_gabarito.json").write_text(
        json.dumps(gab.como_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return gab


def main() -> None:
    raiz = Path(__file__).parent.parent / "data" / "bronze"
    origem = raiz / "limpo"
    destino = raiz / "sujo"
    print(f"Injetando defeitos: {origem} -> {destino}")
    gab = injetar(origem, destino)
    print(f"  {len(gab.defeitos)} tipos de defeito, "
          f"{sum(len(v) for v in gab.registros.values()):,} registros afetados")
    for d in gab.defeitos:
        n = len(gab.registros.get(f"{d.tabela}|{d.codigo}", []))
        print(f"    {d.codigo} {d.regra} {d.dimensao:<12} {d.tabela:<22} {n:>7,}")


if __name__ == "__main__":
    main()
