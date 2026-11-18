"""
Gerador de dados sinteticos do Giro.

POR QUE SINTETICO
-----------------
O edital permite dado ficticio, publico ou anonimizado (secao 2). Optamos
por sintetico CALIBRADO por tres razoes:

  1. Nenhum dataset publico de mercadinho brasileiro traz, ao mesmo tempo,
     venda por item-dia, estoque diario, ruptura, validade e pedido de
     compra. O fenomeno central do Giro (ruptura truncando a venda) exige
     esse dado que nao existe publico.
  2. Precisamos INJETAR defeitos de qualidade em quantidade conhecida para
     medir a eficacia das regras. Dataset publico nao tem gabarito.
  3. Reprodutibilidade: a mesma semente produz o mesmo dataset, entao o
     relatorio e os numeros sao auditaveis por qualquer integrante.

A calibragem (ticket medio, sazonalidade, mix de SKUs, lead time) esta
declarada em Parametros e justificada em docs/02-diagnostico.md.

ARQUITETURA
-----------
Escreve CSV em streaming na camada bronze. Nao acumula em memoria: o
dataset padrao tem ~5M de linhas, o que inviabilizaria uma lista de dicts.

Gera duas versoes:
  bronze/limpo/  dados coerentes
  bronze/sujo/   mesma base + defeitos injetados + gabarito.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np


# =====================================================================
# Aritmetica monetaria
# =====================================================================
#
# POR QUE Decimal E NAO float
# ---------------------------
# A constraint do banco verifica
#     valor_total = round(quantidade * preco_unitario, 2) - valor_desconto
# usando NUMERIC, que arredonda "half up" em decimal (6.765 -> 6.77).
# float em Python, por ser binario, arredonda 6.765 para 6.76 - a
# representacao binaria de 6.765 e ligeiramente menor que o valor
# decimal. O resultado era violacao de constraint em ~1 a cada 200
# linhas (encontrado no caso real: 0.820 kg x 8.25).
#
# A licao vale para o relatorio: dinheiro nunca deve ser float. O tipo
# NUMERIC(14,2) na prata e a garantia final; Decimal aqui garante que
# o gerador produza exatamente o que o banco espera.
CENTAVO = Decimal("0.01")


def money(valor) -> Decimal:
    """Converte para Decimal com 2 casas, arredondando como o Postgres."""
    if isinstance(valor, Decimal):
        d = valor
    else:
        d = Decimal(str(valor))
    return d.quantize(CENTAVO, rounding=ROUND_HALF_UP)


# =====================================================================
# Parametros
# =====================================================================

@dataclass(frozen=True)
class Parametros:
    """Parametros do gerador. Cada bloco esta justificado no relatorio."""

    semente: int = 20261115

    # Janela: 24 meses fecha dois ciclos anuais, necessario para
    # estimar sazonalidade mensal sem confundir com tendencia.
    data_inicio: date = date(2023, 11, 1)
    data_fim: date = date(2025, 10, 31)

    n_lojas: int = 3
    n_skus: int = 420
    cupons_por_dia_loja: int = 210
    itens_por_cupom: float = 8.4

    # Sazonalidade semanal. Indice 0 = segunda ... 6 = domingo.
    # Mercadinho de bairro: sabado e o pico (compra da semana);
    # segunda e terca sao os vales.
    fator_dia_semana: tuple[float, ...] = (0.86, 0.88, 0.94, 1.02, 1.24, 1.18, 0.78)

    fator_pagamento: float = 1.14
    fator_feriado: float = 0.71
    fator_perecivel: float = 1.22

    # Ruptura: o gerador modela a POLITICA RUIM do dono, nao a ideal.
    # Se o modelo usasse a politica otima nao haveria ruptura, e a
    # ruptura e justamente o fenomeno que o Giro trata.
    #
    # CALIBRACAO CONTRA BENCHMARK REAL (secao 4.2 do relatorio):
    #   - media global de ruptura no varejo: 8,3% (Nielsen)
    #   - varejo alimentar brasileiro: 10% a 12% (Neogrid, 2020-2024;
    #     ABRAPPE)
    # O dataset produz ~8,3% de SKU-dia em ruptura, portanto igual a
    # media global e CONSERVADOR em relacao ao Brasil. Isso e
    # proposital: com um numero mais agressivo, a simulacao pareceria
    # exagerada; com um numero menor, o problema pareceria trivial.
    ponto_reposicao_dias: float = 14.0   # repoe com ~14 dias de demanda
    cobertura_dias: float = 30.0         # pedido cobre ~30 dias
    prob_pedido_dia: float = 0.95        # chance de pedir ao cruzar o ponto

    # Nem todo SKU e gerido igual. Na pratica a ruptura se concentra num
    # subconjunto de itens que o dono "esquece" de repor. Modelar isso
    # torna a taxa realista e ESTAVEL em relacao ao horizonte.
    #
    # A negligencia e EPISODICA, nao permanente: o dono esquece por um
    # periodo, um dia percebe (cliente reclama, ele bate o olho na
    # prateleira) e volta a repor. Se fosse permanente, o estoque
    # drenaria para sempre e a taxa de ruptura cresceria com o tempo de
    # simulacao - foi exatamente o que aconteceu na primeira versao
    # (4% em 6 meses, 8,5% em 24 meses), um artefato e nao um fenomeno.
    fracao_sku_mal_gerido: float = 0.10
    prob_pedido_mal_gerido: float = 0.34
    ponto_reposicao_mal_gerido_dias: float = 4.0
    dias_medio_negligencia: float = 26.0   # duracao media do esquecimento

    lead_time_min: int = 3
    lead_time_max: int = 14
    prob_atraso_fornecedor: float = 0.18

    taxa_cancelamento: float = 0.004
    taxa_devolucao: float = 0.002

    prob_sku_promocao: float = 0.18
    desconto_promocao_min: float = 8.0
    desconto_promocao_max: float = 32.0
    lift_promocao: float = 1.55

    # Fracao dos SKUs sujeitos a contagem de inventario ciclico por dia.
    prob_inventario: float = 0.02

    @property
    def dias(self) -> int:
        return (self.data_fim - self.data_inicio).days + 1

    @property
    def n_dias_semana(self) -> int:
        return 7


ESCALAS: dict[str, Parametros] = {
    # Desenvolvimento e testes automatizados: roda em segundos.
    "rapida": Parametros(
        data_inicio=date(2025, 5, 1),
        data_fim=date(2025, 10, 31),
        n_lojas=1,
        n_skus=120,
        cupons_por_dia_loja=80,
    ),
    # Padrao: o dataset do relatorio.
    "padrao": Parametros(),
    # Projecao de volumetria citada na secao 4.2 (nao roda por padrao).
    "completa": Parametros(
        n_lojas=3,
        n_skus=1200,
        cupons_por_dia_loja=520,
    ),
}


# =====================================================================
# Catalogos
# =====================================================================

DEPARTAMENTOS: dict[str, list[str]] = {
    "MERCEARIA": ["Arroz", "Feijao", "Macarrao", "Acucar", "Cafe", "Oleo", "Farinha"],
    "BEBIDAS": ["Refrigerante", "Cerveja", "Suco", "Agua", "Energetico"],
    "HIGIENE": ["Sabonete", "Shampoo", "Pasta de Dente", "Papel Higienico"],
    "LIMPEZA": ["Detergente", "Sabao em Po", "Agua Sanitaria", "Amaciante"],
    "FRIOS_E_LATICINIOS": ["Leite", "Queijo", "Presunto", "Iogurte", "Manteiga"],
    "PADARIA": ["Pao Frances", "Pao de Forma", "Bolo", "Rosca"],
    "HORTIFRUTI": ["Banana", "Tomate", "Batata", "Cebola", "Maca", "Laranja"],
    "ACOUGUE": ["Frango", "Carne Bovina", "Linguica", "Peixe"],
}

# Itens que praticamente todo mercadinho vende. Garantem series densas
# para a previsao e uma curva ABC com concentracao realista.
ANCORAS: list[tuple[str, str, str, bool, float]] = [
    ("Arroz Branco 5kg",        "MERCEARIA", "UN", False, 42.0),
    ("Feijao Carioca 1kg",      "MERCEARIA", "UN", False, 34.0),
    ("Acucar Refinado 1kg",     "MERCEARIA", "UN", False, 28.0),
    ("Cafe Torrado 500g",       "MERCEARIA", "UN", False, 26.0),
    ("Oleo de Soja 900ml",      "MERCEARIA", "UN", False, 31.0),
    ("Leite Integral 1L",       "FRIOS_E_LATICINIOS", "UN", True, 58.0),
    ("Pao Frances",             "PADARIA", "KG", True, 74.0),
    ("Banana Prata",            "HORTIFRUTI", "KG", True, 46.0),
    ("Tomate",                  "HORTIFRUTI", "KG", True, 38.0),
    ("Frango Inteiro",          "ACOUGUE", "KG", True, 22.0),
    ("Refrigerante Cola 2L",    "BEBIDAS", "UN", False, 40.0),
    ("Cerveja Lata 350ml",      "BEBIDAS", "UN", False, 66.0),
    ("Papel Higienico 4un",     "HIGIENE", "PCT", False, 21.0),
    ("Detergente 500ml",        "LIMPEZA", "UN", False, 24.0),
    ("Sabonete 90g",            "HIGIENE", "UN", False, 19.0),
    ("Margarina 500g",          "FRIOS_E_LATICINIOS", "UN", True, 27.0),
]

PERECIVEIS = {"FRIOS_E_LATICINIOS", "PADARIA", "HORTIFRUTI", "ACOUGUE"}

FAIXA_PRECO: dict[str, tuple[float, float]] = {
    "MERCEARIA": (2.50, 22.00),
    "BEBIDAS": (1.80, 26.00),
    "HIGIENE": (1.50, 21.00),
    "LIMPEZA": (1.90, 17.00),
    "FRIOS_E_LATICINIOS": (2.20, 32.00),
    "PADARIA": (0.60, 14.00),
    "HORTIFRUTI": (1.20, 9.50),
    "ACOUGUE": (8.00, 62.00),
}

MARCAS = ["Bom Preco", "Da Casa", "Sabor Real", "Vale Mais", "Nobre",
          "Campo Verde", "Estrela", "Dona Rosa", "Puro Sabor", "Tradicao"]

TAMANHOS = ["200g", "350g", "500g", "1kg", "2kg", "1L", "500ml", "2L", "4un", "10un"]

# Quantidade media de uma linha de cupom para item vendido por peso.
# Calibrado com o habito de compra de hortifruti/acougue em mercadinho:
# o cliente leva entre 300 g e 800 g por vez, media ~0,5 kg.
KG_POR_LINHA = 0.50


# =====================================================================
# Utilitarios de codigo de barras / documento
# =====================================================================

def ean13_dv(base12: str) -> int:
    """Digito verificador EAN-13 (modulo 10, pesos 1 e 3)."""
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base12))
    return (10 - soma % 10) % 10


def gerar_ean13(rng: np.random.Generator) -> str:
    base = "789" + "".join(str(d) for d in rng.integers(0, 10, size=9))
    return base + str(ean13_dv(base))


def ean13_valido(codigo: str) -> bool:
    if not (isinstance(codigo, str) and len(codigo) == 13 and codigo.isdigit()):
        return False
    return ean13_dv(codigo[:12]) == int(codigo[12])


def cnpj_dv(base12: str) -> str:
    """Dois digitos verificadores do CNPJ."""
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(int(d) * p for d, p in zip(base12, pesos1))
    d1 = 11 - s1 % 11
    d1 = 0 if d1 >= 10 else d1
    base13 = base12 + str(d1)
    s2 = sum(int(d) * p for d, p in zip(base13, pesos2))
    d2 = 11 - s2 % 11
    d2 = 0 if d2 >= 10 else d2
    return str(d1) + str(d2)


def gerar_cnpj(rng: np.random.Generator) -> str:
    base = "".join(str(d) for d in rng.integers(0, 10, size=8)) + "0001"
    return base + cnpj_dv(base)


def cnpj_valido(cnpj: str) -> bool:
    if not (isinstance(cnpj, str) and len(cnpj) == 14 and cnpj.isdigit()):
        return False
    return cnpj_dv(cnpj[:12]) == cnpj[12:]


# =====================================================================
# Calendario e sazonalidade
# =====================================================================

def feriados_nacionais(ano: int) -> list[tuple[date, str]]:
    """Feriados nacionais brasileiros: fixos e moveis (calendario cristao)."""
    fixos = [
        (date(ano, 1, 1), "Confraternizacao Universal"),
        (date(ano, 4, 21), "Tiradentes"),
        (date(ano, 5, 1), "Dia do Trabalho"),
        (date(ano, 9, 7), "Independencia"),
        (date(ano, 10, 12), "Nossa Senhora Aparecida"),
        (date(ano, 11, 2), "Finados"),
        (date(ano, 11, 15), "Proclamacao da Republica"),
        (date(ano, 11, 20), "Consciencia Negra"),
        (date(ano, 12, 25), "Natal"),
    ]
    # Pascoa pelo algoritmo de Meeus/Jones/Butcher.
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    pascoa = date(ano, mes, dia)

    moveis = [
        (pascoa - timedelta(days=48), "Carnaval"),
        (pascoa - timedelta(days=47), "Carnaval"),
        (pascoa - timedelta(days=2), "Sexta-feira Santa"),
        (pascoa + timedelta(days=60), "Corpus Christi"),
    ]
    return fixos + moveis


def fator_sazonal_mensal(mes: int) -> float:
    """Sazonalidade anual do varejo alimentar brasileiro.

    Dezembro forte (festas), janeiro fraco (pos-festa e viagem),
    julho levemente alto (ferias escolares).
    """
    return {1: 0.90, 2: 0.94, 3: 0.98, 4: 1.00, 5: 1.01, 6: 1.00,
            7: 1.05, 8: 1.02, 9: 1.00, 10: 1.03, 11: 1.06, 12: 1.22}[mes]


@dataclass
class DiaCalendario:
    data: date
    iso: str
    ano: int
    mes: int
    dia: int
    dia_semana_iso: int      # 1=segunda .. 7=domingo
    dia_semana_idx: int      # 0=segunda .. 6=domingo
    nome_dia_semana: str
    semana_iso: int
    is_fim_semana: bool
    is_feriado: bool
    nome_feriado: str | None
    is_pagamento: bool


NOMES_DIA = ["Segunda-feira", "Terca-feira", "Quarta-feira", "Quinta-feira",
             "Sexta-feira", "Sabado", "Domingo"]


def gerar_calendario(p: Parametros) -> list[DiaCalendario]:
    feriados: dict[date, str] = {}
    for ano in range(p.data_inicio.year, p.data_fim.year + 1):
        for d, nome in feriados_nacionais(ano):
            feriados[d] = nome

    # Pagamento: dia 5 e dia 20, deslocados para o proximo dia util.
    pagamentos: set[date] = set()
    for ano in range(p.data_inicio.year, p.data_fim.year + 1):
        for mes in range(1, 13):
            for alvo in (5, 20):
                try:
                    d = date(ano, mes, alvo)
                except ValueError:
                    continue
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                pagamentos.add(d)

    out: list[DiaCalendario] = []
    d = p.data_inicio
    while d <= p.data_fim:
        idx = d.weekday()  # 0=segunda
        out.append(DiaCalendario(
            data=d,
            iso=d.isoformat(),
            ano=d.year,
            mes=d.month,
            dia=d.day,
            dia_semana_iso=idx + 1,
            dia_semana_idx=idx,
            nome_dia_semana=NOMES_DIA[idx],
            semana_iso=d.isocalendar()[1],
            is_fim_semana=idx >= 5,
            is_feriado=d in feriados,
            nome_feriado=feriados.get(d),
            is_pagamento=d in pagamentos,
        ))
        d += timedelta(days=1)
    return out


# =====================================================================
# Produtos
# =====================================================================

@dataclass
class Produto:
    produto_id: int
    ean: str
    sku_interno: str
    nome: str
    departamento: str
    classe: str
    unidade: str
    perecivel: bool
    dias_validade: int | None
    preco_custo: float
    preco_venda: float
    demanda_base: float
    e_ancora: bool
    fornecedor_id: int
    # Propensao de leitura no PDV: peso para o sorteio de qual SKU
    # aparece no cupom. NAO e a demanda.
    #
    # Por que separar?
    #   Para item vendido por peso (KG), uma linha do cupom costuma ter
    #   ~0,5 kg, nao 1 kg. Se usassemos a demanda (em kg) como peso do
    #   sorteio, itens KG apareceriam com a mesma frequencia dos itens
    #   vendidos por unidade e venderiam menos que a demanda prevista -
    #   um vies sistematico de -25% que contaminaria a previsao.
    #   propensao = demanda / quantidade media por linha resolve isso.
    propensao: float = 0.0


def gerar_produtos(p: Parametros, rng: np.random.Generator) -> list[Produto]:
    """Gera o catalogo.

    IMPORTANTE - calibracao absoluta da demanda:
    `demanda_base` nasce como uma medida RELATIVA de giro (a curva ABC).
    O nivel absoluto e imposto depois, em `calibrar_demanda`, para que a
    soma da demanda seja compativel com a capacidade do PDV
    (cupons/dia x itens/cupom). Sem essa normalizacao, a demanda dos
    SKUs fica maior que o numero de itens que cabem nos cupons, e cada
    produto "vende" apenas uma fracao da propria demanda - o que faria
    o modelo de previsao aprender um vies sistematico para baixo.
    """
    produtos: list[Produto] = []
    eans_vistos: set[str] = set()

    def novo_ean() -> str:
        while True:
            e = gerar_ean13(rng)
            if e not in eans_vistos:
                eans_vistos.add(e)
                return e

    def precificar(dep: str, ancora: bool) -> tuple[float, float]:
        lo, hi = FAIXA_PRECO[dep]
        custo = round(float(rng.uniform(lo, hi)) * 0.68, 2)
        margem = float(rng.uniform(0.20, 0.42)) if ancora else float(rng.uniform(0.15, 0.48))
        venda = round(custo / (1 - margem), 2)
        return custo, max(venda, round(custo * 1.15, 2))

    pid = 1
    for nome, dep, un, perec, demanda in ANCORAS[: min(len(ANCORAS), p.n_skus)]:
        custo, venda = precificar(dep, True)
        produtos.append(Produto(
            produto_id=pid, ean=novo_ean(), sku_interno=f"SKU{pid:05d}",
            nome=nome, departamento=dep, classe=nome.split()[0],
            unidade=un, perecivel=perec,
            dias_validade=int(rng.choice([3, 5, 7, 10, 15, 30, 60])) if perec else None,
            preco_custo=custo,
            preco_venda=venda,
            demanda_base=round(demanda * float(rng.uniform(0.85, 1.15)), 2),
            e_ancora=True,
            fornecedor_id=int(rng.integers(1, 7)),
        ))
        pid += 1

    deps = list(DEPARTAMENTOS.keys())
    while len(produtos) < p.n_skus:
        dep = deps[int(rng.integers(0, len(deps)))]
        classe = DEPARTAMENTOS[dep][int(rng.integers(0, len(DEPARTAMENTOS[dep])))]
        marca = MARCAS[int(rng.integers(0, len(MARCAS)))]
        tam = TAMANHOS[int(rng.integers(0, len(TAMANHOS)))]
        perec = dep in PERECIVEIS
        unidade = "KG" if (perec and rng.random() < 0.30) else str(
            rng.choice(["UN", "UN", "UN", "PCT", "CX", "DZ"])
        )
        custo, venda = precificar(dep, False)

        # Cauda longa: poucos SKUs giram muito, a maioria gira pouco.
        # Isso e o que produz curva ABC realista em vez de uniforme.
        demanda = max(0.30, float(rng.pareto(1.6)) * 3.2 + 0.4)

        produtos.append(Produto(
            produto_id=pid, ean=novo_ean(), sku_interno=f"SKU{pid:05d}",
            nome=f"{classe} {marca} {tam}", departamento=dep, classe=classe,
            unidade=unidade, perecivel=perec,
            dias_validade=int(rng.choice([3, 5, 7, 10, 15, 30, 45, 90])) if perec else None,
            preco_custo=custo,
            preco_venda=venda,
            demanda_base=round(demanda, 2),
            e_ancora=False,
            fornecedor_id=int(rng.integers(1, 7)),
        ))
        pid += 1

    return produtos


def calibrar_demanda(produtos: list[Produto], p: Parametros) -> None:
    """Ajusta o nivel absoluto da demanda para caber na capacidade do PDV.

    A demanda relativa (curva ABC) vem de `produtos`. Aqui normalizamos
    para que a demanda total de um dia tipico cubra exatamente a
    quantidade de itens que os cupons comportam.

    Fatores considerados:
      - cupons/dia x itens/cupom = itens vendidos por dia por loja
      - fator medio de dia da semana (seg..dom)
      - fator medio sazonal anual
      - fator de perecivel (alguns SKUs giram mais)
      - lift medio de promocao (18% dos SKUs na primeira semana)

    O resultado e que `demanda_base` passa a significar "unidades
    esperadas por dia, em media", tornando as consultas de previsao
    interpretaveis em unidades reais.
    """
    n = len(produtos)
    if n == 0:
        return

    itens_por_dia = p.cupons_por_dia_loja * p.itens_por_cupom

    fator_dia_medio = sum(p.fator_dia_semana) / 7.0
    fator_mes_medio = sum(fator_sazonal_mensal(m) for m in range(1, 13)) / 12.0
    fator_pg_medio = 1.0 + (p.fator_pagamento - 1.0) * (2.0 / 30.0)
    fator_fer_medio = 1.0 + (p.fator_feriado - 1.0) * (11.0 / 365.0)
    # 7 dias de promocao por mes em ~18% dos SKUs
    fator_promo_medio = 1.0 + (p.lift_promocao - 1.0) * p.prob_sku_promocao * (7.0 / 30.0)

    escala = (fator_dia_medio * fator_mes_medio * fator_pg_medio
              * fator_fer_medio * fator_promo_medio)

    pereciveis = sum(1 for x in produtos if x.perecivel)
    fator_medio = 1.0 + (p.fator_perecivel - 1.0) * (pereciveis / n)

    relativa_total = sum(x.demanda_base for x in produtos) * fator_medio
    if relativa_total <= 0:
        return

    k = itens_por_dia / (relativa_total * escala)
    for prod in produtos:
        prod.demanda_base = round(max(0.02, prod.demanda_base * k), 4)

    # Propensao de leitura: quantas LINHAS de cupom o SKU recebe por dia.
    # Item KG gera uma linha com ~0,5 kg; logo, precisa de 2x mais
    # linhas para realizar a mesma demanda em kg.
    for prod in produtos:
        qtd_media_linha = KG_POR_LINHA if prod.unidade == "KG" else 1.0
        prod.propensao = round(prod.demanda_base / qtd_media_linha, 4)


def gerar_fornecedores(p: Parametros, rng: np.random.Generator) -> list[dict]:
    nomes = ["Distribuidora Central", "Atacadao Sul", "Comercial Bom Dia",
             "Alimentos Horizonte", "Logistica Vale Verde", "Atacarejo Uniao"]
    cidades = [("Santos", "SP"), ("Sao Vicente", "SP"), ("Praia Grande", "SP"),
               ("Guaruja", "SP"), ("Cubatao", "SP"), ("Sao Paulo", "SP")]
    out = []
    for i in range(6):
        cidade, uf = cidades[i]
        out.append({
            "fornecedor_id": i + 1,
            "cnpj": gerar_cnpj(rng),
            "razao_social": nomes[i] + " LTDA",
            "nome_fantasia": nomes[i],
            "cidade": cidade,
            "uf": uf,
            "lead_time_dias_padrao": int(rng.integers(3, 15)),
            "pedido_minimo_valor": round(float(rng.uniform(150, 900)), 2),
            "ativo": True,
        })
    return out


def gerar_lojas(p: Parametros) -> list[dict]:
    dados = [
        ("LJ01", "Mercado Sao Jorge", "Santos", "SP", 210.0, date(2015, 3, 10)),
        ("LJ02", "Mercado Bom Preco", "Sao Vicente", "SP", 165.0, date(2018, 8, 22)),
        ("LJ03", "Mercadinho da Familia", "Praia Grande", "SP", 128.0, date(2020, 11, 5)),
    ]
    # Porte relativo de cada loja: afeta o volume de cupons.
    return [
        {
            "loja_id": i + 1, "codigo": c, "nome": n, "cnpj": None,
            "cidade": cid, "uf": uf, "area_m2": area,
            "data_abertura": dt.isoformat(), "data_fechamento": None, "ativa": True,
        }
        for i, (c, n, cid, uf, area, dt) in enumerate(dados[: p.n_lojas])
    ]


# =====================================================================
# Escrita em CSV (streaming)
# =====================================================================

class EscritorCSV:
    """Escritor CSV que escreve linha a linha, sem acumular em memoria."""

    def __init__(self, caminho: Path, colunas: list[str]):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        self._f = caminho.open("w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._f, fieldnames=colunas, extrasaction="ignore")
        self._w.writeheader()
        self.n = 0

    def escrever(self, linha: dict) -> None:
        self._w.writerow(linha)
        self.n += 1

    def escrever_muitos(self, linhas) -> None:
        for linha in linhas:
            self.escrever(linha)

    def fechar(self) -> None:
        self._f.close()

    def __enter__(self) -> "EscritorCSV":
        return self

    def __exit__(self, *exc) -> None:
        self.fechar()

    @property
    def sha256(self) -> str:
        h = hashlib.sha256()
        with self.caminho.open("rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        return h.hexdigest()


# =====================================================================
# Geracao principal
# =====================================================================

@dataclass
class Resumo:
    tabelas: dict[str, int] = field(default_factory=dict)
    ruins: dict[str, float] = field(default_factory=dict)
    arquivos: dict[str, dict] = field(default_factory=dict)

    def como_dict(self) -> dict:
        return {"tabelas": self.tabelas, "indicadores_base": self.ruins,
                "arquivos": self.arquivos}


def _escrever_calendario(cal: list[DiaCalendario], destino: Path) -> EscritorCSV:
    cols = ["data", "ano", "mes", "dia", "dia_semana", "nome_dia_semana",
            "semana_iso", "is_fim_semana", "is_feriado", "nome_feriado",
            "is_pagamento"]
    e = EscritorCSV(destino / "calendario.csv", cols)
    for d in cal:
        e.escrever({
            "data": d.iso, "ano": d.ano, "mes": d.mes, "dia": d.dia,
            "dia_semana": d.dia_semana_iso, "nome_dia_semana": d.nome_dia_semana,
            "semana_iso": d.semana_iso,
            "is_fim_semana": str(d.is_fim_semana).lower(),
            "is_feriado": str(d.is_feriado).lower(),
            "nome_feriado": d.nome_feriado or "",
            "is_pagamento": str(d.is_pagamento).lower(),
        })
    return e


def gerar(p: Parametros, destino: Path, verbose: bool = True) -> Resumo:
    """Gera o dataset limpo em `destino` (camada bronze)."""
    destino.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(p.semente)
    resumo = Resumo()

    if verbose:
        print(f"  janela: {p.data_inicio} a {p.data_fim} ({p.dias} dias)")

    produtos = gerar_produtos(p, rng)
    calibrar_demanda(produtos, p)
    fornecedores = gerar_fornecedores(p, rng)
    lojas = gerar_lojas(p)
    calendario = gerar_calendario(p)

    n_prod = len(produtos)
    prod_demanda = np.array([x.demanda_base for x in produtos], dtype=float)
    prod_propensao = np.array([x.propensao for x in produtos], dtype=float)
    prod_perecivel = np.array([x.perecivel for x in produtos], dtype=bool)
    prod_custo = np.array([x.preco_custo for x in produtos], dtype=float)
    prod_venda = np.array([x.preco_venda for x in produtos], dtype=float)
    prod_unidade = [x.unidade for x in produtos]
    prod_kg = np.array([u == "KG" for u in prod_unidade], dtype=bool)
    prod_fator_perec = np.where(prod_perecivel, p.fator_perecivel, 1.0)

    # Classifica cada SKU como bem ou mal gerido. A decisao e tomada uma
    # vez, nao por dia: o dono tem SKUs cronicamente negligenciados.
    rng_gestao = np.random.default_rng(p.semente + 977)
    mal_gerido = rng_gestao.random(n_prod) < p.fracao_sku_mal_gerido

    prod_estoque_min = np.where(
        mal_gerido,
        prod_demanda * p.ponto_reposicao_mal_gerido_dias,
        prod_demanda * p.ponto_reposicao_dias,
    )
    prod_cobertura = prod_demanda * p.cobertura_dias
    prod_prob_pedido = np.where(mal_gerido, p.prob_pedido_mal_gerido, p.prob_pedido_dia)

    # Episodios de negligencia por SKU-lOJA. Renovados quando expiram.
    # Isso evita o artefato de acumulacao com o horizonte de simulacao.
    rng_episodio = np.random.default_rng(p.semente + 4231)
    episodio_ativo: dict[int, np.ndarray] = {
        loja: np.zeros(n_prod, dtype=bool) for loja in range(1, p.n_lojas + 1)
    }
    episodio_fim: dict[int, np.ndarray] = {
        loja: np.full(n_prod, -1, dtype=int) for loja in range(1, p.n_lojas + 1)
    }

    # --- escritores -------------------------------------------------
    escritores: dict[str, EscritorCSV] = {}
    escritores["loja"] = EscritorCSV(
        destino / "loja.csv",
        ["loja_id", "codigo", "nome", "cnpj", "cidade", "uf", "area_m2",
         "data_abertura", "data_fechamento", "ativa"])
    escritores["fornecedor"] = EscritorCSV(
        destino / "fornecedor.csv",
        ["fornecedor_id", "cnpj", "razao_social", "nome_fantasia", "cidade",
         "uf", "lead_time_dias_padrao", "pedido_minimo_valor", "ativo"])
    escritores["produto"] = EscritorCSV(
        destino / "produto.csv",
        ["produto_id", "ean", "sku_interno", "nome", "departamento", "classe",
         "unidade", "perecivel", "dias_validade", "preco_custo", "preco_venda",
         "fornecedor_id"])
    escritores["venda"] = EscritorCSV(
        destino / "venda.csv",
        ["venda_id", "loja_id", "data_venda", "hora_venda", "numero_cupom",
         "serie_cupom", "canal", "valor_bruto", "valor_desconto",
         "valor_liquido", "qtd_itens", "status"])
    escritores["item_venda"] = EscritorCSV(
        destino / "item_venda.csv",
        ["venda_id", "data_venda", "item_seq", "produto_id", "quantidade",
         "preco_unitario", "valor_desconto", "valor_total", "promocao_id",
         "custo_unitario"])
    escritores["estoque_snapshot"] = EscritorCSV(
        destino / "estoque_snapshot.csv",
        ["loja_id", "produto_id", "data_ref", "qtd_inicio", "qtd_entradas",
         "qtd_saidas", "qtd_ajustes", "qtd_fim", "qtd_contada", "custo_medio",
         "houve_ruptura", "horas_sem_estoque"])
    escritores["pedido_compra"] = EscritorCSV(
        destino / "pedido_compra.csv",
        ["pedido_id", "loja_id", "fornecedor_id", "numero_pedido", "data_pedido",
         "data_previsao", "data_entrega", "valor_total", "status"])
    escritores["item_pedido"] = EscritorCSV(
        destino / "item_pedido.csv",
        ["pedido_id", "item_seq", "produto_id", "quantidade_pedida",
         "quantidade_entregue", "custo_unitario", "valor_total"])
    escritores["movimentacao_estoque"] = EscritorCSV(
        destino / "movimentacao_estoque.csv",
        ["loja_id", "produto_id", "data_movimento", "tipo", "quantidade",
         "custo_unitario", "documento_ref"])
    escritores["promocao"] = EscritorCSV(
        destino / "promocao.csv",
        ["promocao_id", "codigo", "descricao", "tipo", "data_inicio",
         "data_fim", "percentual_desconto"])
    escritores["promocao_produto"] = EscritorCSV(
        destino / "promocao_produto.csv",
        ["promocao_id", "produto_id"])

    # --- referencia -------------------------------------------------
    escritores["loja"].escrever_muitos(lojas)
    escritores["fornecedor"].escrever_muitos(fornecedores)

    for prod in produtos:
        escritores["produto"].escrever({
            "produto_id": prod.produto_id, "ean": prod.ean,
            "sku_interno": prod.sku_interno, "nome": prod.nome,
            "departamento": prod.departamento, "classe": prod.classe,
            "unidade": prod.unidade,
            "perecivel": str(prod.perecivel).lower(),
            "dias_validade": prod.dias_validade if prod.dias_validade else "",
            "preco_custo": f"{prod.preco_custo:.2f}",
            "preco_venda": f"{prod.preco_venda:.2f}",
            "fornecedor_id": prod.fornecedor_id,
        })

    _escrever_calendario(calendario, destino)

    # --- promocoes: 1 campanha por mes por loja, primeira semana -------
    promocoes: list[dict] = []
    promo_produto: list[dict] = []
    promo_por_mes_loja: dict[tuple[int, int, int], int] = {}
    promo_id = 1
    for ano, mes in sorted({(d.ano, d.mes) for d in calendario}):
        for loja in range(1, p.n_lojas + 1):
            primeiro = date(ano, mes, 1)
            fim = date(ano, mes, 7)
            promocoes.append({
                "promocao_id": promo_id,
                "codigo": f"PR{ano}{mes:02d}L{loja}",
                "descricao": f"Ofertas da semana {mes:02d}/{ano} - loja {loja}",
                "tipo": "DESCONTO",
                "data_inicio": primeiro.isoformat(),
                "data_fim": fim.isoformat(),
                "percentual_desconto": f"{rng.uniform(p.desconto_promocao_min, p.desconto_promocao_max):.2f}",
            })
            promo_por_mes_loja[(ano, mes, loja)] = promo_id
            escolhidos = np.flatnonzero(rng.random(n_prod) < p.prob_sku_promocao)
            for pid in escolhidos:
                promo_produto.append({
                    "promocao_id": promo_id,
                    "produto_id": int(pid) + 1,
                })
            promo_id += 1
    escritores["promocao"].escrever_muitos(promocoes)
    escritores["promocao_produto"].escrever_muitos(promo_produto)

    promo_produtos_por_id: dict[int, set[int]] = {}
    for pp in promo_produto:
        promo_produtos_por_id.setdefault(pp["promocao_id"], set()).add(pp["produto_id"])

    # --- estado por loja -------------------------------------------
    # estoque[loja] = vetor de quantidade disponivel por produto
    estoque: dict[int, np.ndarray] = {}
    for loja in range(1, p.n_lojas + 1):
        estoque[loja] = np.round(
            prod_cobertura * rng.uniform(0.6, 1.4, size=n_prod), 3
        ).astype(float)

    # Pedidos em transito: (loja, produto, qtd, data_prevista, pedido_id)
    em_transito: dict[int, list[dict]] = {l: [] for l in range(1, p.n_lojas + 1)}
    sangria: list[dict] = []          # pedidos que chegaram (para o CSV)
    itens_pedido_linhas: list[dict] = []
    pedido_id = 1
    venda_id = 1

    # Estatisticas de apoio
    stat_rupturas = 0
    stat_skus_dia = 0

    dias_idx = np.arange(7, dtype=int)

    if verbose:
        print(f"  simulando {p.dias} dias x {p.n_lojas} lojas "
              f"(~{p.cupons_por_dia_loja} cupons/dia/loja)...")

    for i_dia, dia in enumerate(calendario):
        fator_dia = p.fator_dia_semana[dia.dia_semana_idx]
        fator_mes = fator_sazonal_mensal(dia.mes)
        fator_pg = p.fator_pagamento if dia.is_pagamento else 1.0
        fator_fer = p.fator_feriado if dia.is_feriado else 1.0
        fator_global = fator_dia * fator_mes * fator_pg * fator_fer
        em_semana_promo = dia.dia <= 7

        # vendidos_do_dia[loja] e consumido na etapa de snapshot, que
        # roda num segundo laco. Sem isso, o snapshot usaria o vetor da
        # ultima loja processada - bug de escopo que corromperia a
        # equacao de estoque de todas as outras lojas.
        vendidos_do_dia: dict[int, np.ndarray] = {}

        for loja in range(1, p.n_lojas + 1):
            disp = estoque[loja]
            porte = 0.82 + 0.18 * loja

            # ---- demanda esperada do dia por produto ----------------
            fator_promo = np.ones(n_prod, dtype=float)
            promo_atual: int | None = None
            if em_semana_promo:
                promo_atual = promo_por_mes_loja.get((dia.ano, dia.mes, loja))
                if promo_atual is not None:
                    ids = promo_produtos_por_id.get(promo_atual, set())
                    if ids:
                        idx = np.fromiter((x - 1 for x in ids), dtype=int, count=len(ids))
                        fator_promo[idx] = p.lift_promocao

            # Demanda (em unidade de medida do produto) e propensao
            # (em linhas de cupom) sao coisas diferentes para itens KG.
            demanda = (prod_demanda * prod_fator_perec * fator_global * fator_promo)
            propensao = (prod_propensao * prod_fator_perec * fator_global * fator_promo)
            # Produto em ruptura nao vende
            demanda = np.where(disp > 0, demanda, 0.0)
            propensao = np.where(disp > 0, propensao, 0.0)

            total_propensao = propensao.sum()
            n_cupons = int(round(
                p.cupons_por_dia_loja * fator_global * porte
                * float(rng.uniform(0.90, 1.10))
            ))
            if total_propensao <= 0 or n_cupons <= 0:
                continue

            # ---- quantos itens cada cupom tem ----------------------
            itens_por_cupom = np.clip(
                np.round(rng.normal(p.itens_por_cupom, 2.8, size=n_cupons)),
                1, 30,
            ).astype(int)
            total_itens = int(itens_por_cupom.sum())

            # ---- amostragem vetorizada de SKUs ---------------------
            # np.random.Generator.choice com p= e O(n) por chamada e
            # resolve os ~1800 itens do dia de uma vez, em vez de um
            # loop Python sobre cupons.
            probs = propensao / total_propensao
            escolhidos = rng.choice(n_prod, size=total_itens, p=probs)

            # ---- devolve aos cupons: cumsum dos tamanhos -----------
            limites = np.cumsum(itens_por_cupom)
            inicio_item = np.concatenate(([0], limites[:-1]))

            hora_base = np.array([9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
            pesos_hora = np.array([1, 2, 3, 4, 5, 7, 9, 8, 6, 4, 2], dtype=float)
            pesos_hora = pesos_hora / pesos_hora.sum()
            horas = rng.choice(hora_base, size=n_cupons, p=pesos_hora)
            minutos = rng.integers(0, 60, size=n_cupons)
            segundos = rng.integers(0, 60, size=n_cupons)

            tem_promocao = fator_promo > 1.0

            # vendidos[prod] acumula a quantidade vendida no dia
            vendidos = np.zeros(n_prod, dtype=float)

            for c in range(n_cupons):
                a, b = inicio_item[c], limites[c]
                if b <= a:
                    continue
                produtos_cupom = escolhidos[a:b]

                # Agrupa SKUs repetidos no mesmo cupom (PDV bipa 2x o
                # mesmo item e o sistema soma na mesma linha).
                uniq, contagem = np.unique(produtos_cupom, return_counts=True)

                itens: list[dict] = []
                bruto = Decimal("0.00")
                desconto_total = Decimal("0.00")
                seq = 0

                for pid0, n_aparicoes in zip(uniq, contagem):
                    pidx = int(pid0)
                    if disp[pidx] <= 0:
                        continue

                    # Quantidade por aparicao: 1 unidade para itens
                    # fracionados por peso, ~0.4-1.2 kg para KG.
                    if prod_kg[pidx]:
                        qtd = float(n_aparicoes) * float(rng.uniform(0.25, 0.9))
                        qtd = round(max(0.05, qtd), 3)
                    else:
                        qtd = float(n_aparicoes)

                    if disp[pidx] < qtd:
                        qtd = round(float(disp[pidx]), 3)
                    if qtd <= 0:
                        continue

                    disp[pidx] = round(float(disp[pidx]) - qtd, 3)
                    vendidos[pidx] += qtd

                    preco = float(prod_venda[pidx])
                    em_promo = bool(tem_promocao[pidx])
                    if em_promo:
                        pct = float(rng.uniform(p.desconto_promocao_min,
                                                p.desconto_promocao_max))
                        desc_un = money(preco * pct / 100)
                    else:
                        desc_un = Decimal("0.00")

                    # Aritmetica inteiramente em Decimal, na mesma ordem
                    # da constraint do banco, para que o valor gravado
                    # seja exatamente o valor validado.
                    qtd_dec = Decimal(str(round(qtd, 3)))
                    preco_dec = money(preco)
                    bruto_item = money(qtd_dec * preco_dec)
                    desc_item = money(qtd_dec * desc_un)
                    total_item = bruto_item - desc_item
                    if total_item <= 0:
                        continue

                    seq += 1
                    itens.append({
                        "venda_id": venda_id,
                        "data_venda": dia.iso,
                        "item_seq": seq,
                        "produto_id": pidx + 1,
                        "quantidade": f"{qtd_dec:.3f}",
                        "preco_unitario": f"{preco_dec:.2f}",
                        "valor_desconto": f"{desc_item:.2f}",
                        "valor_total": f"{total_item:.2f}",
                        "promocao_id": promo_atual if em_promo else "",
                        "custo_unitario": f"{money(float(prod_custo[pidx])):.2f}",
                    })
                    bruto += bruto_item
                    desconto_total += desc_item

                if not itens:
                    continue

                bruto = money(bruto)
                desconto_total = money(desconto_total)
                liquido = bruto - desconto_total

                r = float(rng.random())
                if r < p.taxa_cancelamento:
                    status = "CANCELADA"
                elif r < p.taxa_cancelamento + p.taxa_devolucao:
                    status = "DEVOLVIDA"
                else:
                    status = "CONCLUIDA"

                numero = f"{loja:02d}{dia.data.strftime('%Y%m%d')}{c:05d}"
                escritores["venda"].escrever({
                    "venda_id": venda_id,
                    "loja_id": loja,
                    "data_venda": dia.iso,
                    "hora_venda": f"{int(horas[c]):02d}:{int(minutos[c]):02d}:{int(segundos[c]):02d}",
                    "numero_cupom": numero,
                    "serie_cupom": f"S{loja}",
                    "canal": "PDV" if rng.random() > 0.02 else "APP",
                    "valor_bruto": f"{bruto:.2f}",
                    "valor_desconto": f"{desconto_total:.2f}",
                    "valor_liquido": f"{liquido:.2f}",
                    "qtd_itens": len(itens),
                    "status": status,
                })
                for it in itens:
                    escritores["item_venda"].escrever(it)

                venda_id += 1

            # ---- movimentacao de venda (lancamento agregado por SKU) --
            # Um lancamento por SKU/dia em vez de um por item mantem o
            # livro-razao legivel sem perder a informacao.
            for pidx in np.flatnonzero(vendidos > 0):
                escritores["movimentacao_estoque"].escrever({
                    "loja_id": loja,
                    "produto_id": int(pidx) + 1,
                    "data_movimento": dia.iso,
                    "tipo": "VENDA",
                    "quantidade": f"{-round(float(vendidos[pidx]), 3):.3f}",
                    "custo_unitario": f"{float(prod_custo[pidx]):.2f}",
                    "documento_ref": f"VENDA-{dia.iso}-L{loja}",
                })

            vendidos_do_dia[loja] = vendidos

        # ---- fim do dia: recebimento e snapshot -------------------
        for loja in range(1, p.n_lojas + 1):
            disp = estoque[loja]
            vendidos = vendidos_do_dia.get(loja, np.zeros(n_prod, dtype=float))

            # Recebimento de pedidos em transito
            #
            # O MODELO DE ENTREGA ALIMENTA O OTIF
            # -----------------------------------
            # Tres comportamentos reais, cada um com efeito diferente:
            #   - no prazo e completo (o caso bom)
            #   - atrasado (chega depois da previsao)
            #   - parcial (chega menos do que foi pedido)
            #
            # A primeira versao gravava quantidade_entregue = 0 no
            # momento do pedido e nunca atualizava, entao a Q08 (OTIF)
            # reportava 0% para todos os fornecedores - um bug do
            # gerador lido como se fosse conclusao sobre fornecedores.
            # Agora a entrega e decidida aqui e escrita no registro.
            entradas = np.zeros(n_prod, dtype=float)
            restantes: list[dict] = []
            for ped in em_transito[loja]:
                if ped["data_prevista"] <= dia.data:
                    # Atraso: 18% dos pedidos chegam depois da previsao.
                    atrasou = float(rng.random()) < p.prob_atraso_fornecedor
                    if atrasou and ped["data_prevista"] == dia.data:
                        ped["data_prevista"] = dia.data + timedelta(
                            days=int(rng.integers(1, 6)))
                        restantes.append(ped)
                        continue

                    # Entrega parcial: 12% chegam incompletos.
                    parcial = float(rng.random()) < 0.12
                    if parcial:
                        entregue = round(ped["quantidade"] * float(
                            rng.uniform(0.55, 0.92)), 3)
                    else:
                        entregue = ped["quantidade"]

                    ped["entregue"] = entregue
                    ped["entregue_em"] = dia.data

                    pidx = ped["produto_id"] - 1
                    entradas[pidx] += entregue
                    disp[pidx] = round(float(disp[pidx]) + entregue, 3)
                    sangria.append({
                        "pedido_id": ped["pedido_id"],
                        "loja_id": loja,
                        "fornecedor_id": ped["fornecedor_id"],
                        "numero_pedido": ped["numero_pedido"],
                        "data_pedido": ped["data_pedido"].isoformat(),
                        "data_previsao": ped["data_prevista_original"].isoformat(),
                        "data_entrega": dia.iso,
                        "valor_total": f"{money(Decimal(str(entregue)) * money(float(ped['custo']))):.2f}",
                        "status": "PARCIAL" if parcial else "ENTREGUE",
                        # `entregue` precisa viajar junto: e a fonte da
                        # coluna quantidade_entregue em item_pedido.
                        "entregue": entregue,
                    })
                    escritores["movimentacao_estoque"].escrever({
                        "loja_id": loja,
                        "produto_id": ped["produto_id"],
                        "data_movimento": dia.iso,
                        "tipo": "COMPRA",
                        "quantidade": f"{entregue:.3f}",
                        "custo_unitario": f"{ped['custo']:.2f}",
                        "documento_ref": ped["numero_pedido"],
                    })
                else:
                    restantes.append(ped)
            em_transito[loja] = restantes

            # Reposicao: dispara pedido quando abaixo do ponto de pedido.
            #
            # O ponto de pedido e em DIAS DE DEMANDA, e a decisao imita a
            # pratica do dono: dispara quando "parece baixo", nao todo dia.
            # SKU em episodio de negligencia tem ponto mais baixo e menor
            # chance de pedir - e assim que nasce a ruptura.
            ativo = episodio_ativo[loja]
            # Renova episodios expirados
            expirados = ativo & (episodio_fim[loja] <= i_dia)
            ativo[expirados] = False
            novos = (rng_episodio.random(n_prod) < (p.fracao_sku_mal_gerido
                                                    / p.dias_medio_negligencia)) & ~ativo
            ativo[novos] = True
            episodio_fim[loja][novos] = i_dia + rng_episodio.integers(
                5, int(p.dias_medio_negligencia * 2), size=int(novos.sum()))

            ponto = np.where(ativo, prod_demanda * p.ponto_reposicao_mal_gerido_dias,
                             prod_demanda * p.ponto_reposicao_dias)
            prob_pedir = np.where(ativo, p.prob_pedido_mal_gerido, p.prob_pedido_dia)

            abaixo = np.flatnonzero(disp < ponto)
            for pid0 in abaixo:
                pidx = int(pid0)
                if rng.random() > prod_prob_pedido[pidx] * 0 + prob_pedir[pidx]:
                    continue
                # Evita empilhar pedidos do mesmo SKU
                if any(x["produto_id"] == pidx + 1 for x in em_transito[loja]):
                    continue
                qtd = float(np.round(prod_cobertura[pidx] * rng.uniform(0.8, 1.3), 3))
                if qtd <= 0:
                    continue
                # Arredonda a quantidade e o valor com a MESMA regra que
                # a constraint do banco usa (NUMERIC + half-up). Sem isso,
                # a validacao falha em ~1 a cada 300 linhas.
                qtd = float(money(qtd))
                custo_dec = money(float(prod_custo[pidx]))
                valor_dec = money(Decimal(str(qtd)) * custo_dec)
                lead = int(rng.integers(p.lead_time_min, p.lead_time_max + 1))
                prevista = dia.data + timedelta(days=lead)
                fornecedor_id = produtos[pidx].fornecedor_id
                numero = f"P{pedido_id:08d}"
                em_transito[loja].append({
                    "pedido_id": pedido_id,
                    "produto_id": pidx + 1,
                    "quantidade": qtd,
                    "custo": float(prod_custo[pidx]),
                    "data_pedido": dia.data,
                    "data_prevista": prevista,
                    "data_prevista_original": prevista,
                    "fornecedor_id": fornecedor_id,
                    "numero_pedido": numero,
                })
                escritores["pedido_compra"].escrever({
                    "pedido_id": pedido_id,
                    "loja_id": loja,
                    "fornecedor_id": fornecedor_id,
                    "numero_pedido": numero,
                    "data_pedido": dia.iso,
                    "data_previsao": prevista.isoformat(),
                    "data_entrega": "",
                    "valor_total": f"{valor_dec:.2f}",
                    "status": "ENVIADO",
                })
                itens_pedido_linhas.append({
                    "pedido_id": pedido_id,
                    "item_seq": 1,
                    "produto_id": pidx + 1,
                    "quantidade_pedida": f"{qtd:.3f}",
                    # quantidade_entregue e preenchida ao final, quando o
                    # pedido efetivamente chega (ou nao). Ver a nota no
                    # fechamento do gerador.
                    "quantidade_entregue": None,
                    "custo_unitario": f"{custo_dec:.2f}",
                    "valor_total": f"{valor_dec:.2f}",
                })
                pedido_id += 1

            # ---- snapshot do dia ----------------------------------
            # Equacao: fim = inicio + entradas + saidas + ajustes
            # saidas e negativo. Como ja debitamos da disp durante as
            # vendas, reconstruimos inicio a partir do estado atual.
            fim = disp
            inicio = np.round(fim - entradas + vendidos, 3)
            inicio = np.clip(inicio, 0.0, None)

            # Contagem de inventario ciclico em uma amostra de SKUs.
            contagem = rng.random(n_prod) < p.prob_inventario
            # 4% dos SKUs contados apresentam divergencia real de 1-8%.
            divergencia = contagem & (rng.random(n_prod) < 0.04)
            fator_div = np.where(divergencia, rng.uniform(-0.08, 0.08, size=n_prod), 0.0)
            contada = np.where(contagem, np.round(fim * (1 + fator_div), 3), np.nan)
            contada = np.clip(contada, 0.0, None)

            ruptura = fim <= 0.001
            stat_rupturas += int(ruptura.sum())
            stat_skus_dia += n_prod

            for pidx in range(n_prod):
                escritores["estoque_snapshot"].escrever({
                    "loja_id": loja,
                    "produto_id": pidx + 1,
                    "data_ref": dia.iso,
                    "qtd_inicio": f"{float(inicio[pidx]):.3f}",
                    "qtd_entradas": f"{float(entradas[pidx]):.3f}",
                    "qtd_saidas": f"{float(vendidos[pidx]):.3f}",
                    "qtd_ajustes": "0.000",
                    "qtd_fim": f"{float(fim[pidx]):.3f}",
                    "qtd_contada": ("" if np.isnan(contada[pidx])
                                    else f"{float(contada[pidx]):.3f}"),
                    "custo_medio": f"{float(prod_custo[pidx]):.2f}",
                    "houve_ruptura": "true" if ruptura[pidx] else "false",
                    "horas_sem_estoque": ("24.00" if ruptura[pidx] else "0.00"),
                })

        if verbose and (i_dia + 1) % 60 == 0:
            print(f"    {dia.iso}: {venda_id - 1:>9,} vendas | "
                  f"{escritores['item_venda'].n:>10,} itens")

    # Pedidos que nao chegaram ate o fim da janela: ficam ENVIADO.
    for loja in range(1, p.n_lojas + 1):
        for ped in em_transito[loja]:
            sangria.append({
                "pedido_id": ped["pedido_id"],
                "loja_id": loja,
                "fornecedor_id": ped["fornecedor_id"],
                "numero_pedido": ped["numero_pedido"],
                "data_pedido": ped["data_pedido"].isoformat(),
                "data_previsao": ped["data_prevista_original"].isoformat(),
                "data_entrega": "",
                "valor_total": f"{money(Decimal(str(ped['quantidade'])) * money(float(ped['custo']))):.2f}",
                "status": "ENVIADO",
            })

    # O CSV de pedido_compra ja foi escrito com status ENVIADO no momento
    # da criacao. Reordenamos para incluir os entregues de forma correta:
    # reescrevemos o arquivo inteiro ao final, a partir de `sangria`.
    escritores["pedido_compra"].fechar()
    escritores["pedido_compra"] = EscritorCSV(
        destino / "pedido_compra.csv",
        ["pedido_id", "loja_id", "fornecedor_id", "numero_pedido", "data_pedido",
         "data_previsao", "data_entrega", "valor_total", "status"])
    escritores["pedido_compra"].escrever_muitos(
        sorted(sangria, key=lambda x: x["pedido_id"])
    )

    # ------------------------------------------------------------------
    # quantidade_entregue real por pedido.
    #
    # O item de pedido e escrito no momento em que o pedido e criado,
    # mas a entrega so acontece dias depois. A primeira versao deixava
    # "0.000" fixo e nunca voltava para atualizar - resultado: 36.015
    # linhas com entrega zero e OTIF de 0% para todos os fornecedores.
    #
    # Correcao: `sangria` guarda o desfecho de cada pedido (entregue em,
    # quanto chegou). Aqui cruzamos por pedido_id e reescrevemos o CSV
    # inteiro. Pedido que nunca chegou fica com 0 e status ENVIADO -
    # que e informacao legitima (pedido em aberto no fim da janela).
    # ------------------------------------------------------------------
    desfecho = {int(s["pedido_id"]): s for s in sangria}
    for linha in itens_pedido_linhas:
        ped = desfecho.get(int(linha["pedido_id"]))
        if ped is None or not ped.get("data_entrega"):
            linha["quantidade_entregue"] = "0.000"
        else:
            linha["quantidade_entregue"] = f"{ped.get('entregue', 0) or 0:.3f}"

    escritores["item_pedido"].escrever_muitos(itens_pedido_linhas)

    for e in escritores.values():
        if not e._f.closed:
            e.fechar()

    resumo.tabelas = {
        "loja": len(lojas),
        "fornecedor": len(fornecedores),
        "produto": n_prod,
        "calendario": len(calendario),
        "promocao": len(promocoes),
        "promocao_produto": len(promo_produto),
        "venda": escritores["venda"].n,
        "item_venda": escritores["item_venda"].n,
        "estoque_snapshot": escritores["estoque_snapshot"].n,
        "movimentacao_estoque": escritores["movimentacao_estoque"].n,
        "pedido_compra": escritores["pedido_compra"].n,
        "item_pedido": escritores["item_pedido"].n,
    }
    resumo.ruins = {
        "taxa_ruptura_sku_dia_pct": round(stat_rupturas / max(1, stat_skus_dia) * 100, 4),
        "ticket_medio_brl": None,  # calculado no ETL a partir do CSV
    }

    if verbose:
        print("  gerado:")
        for tabela, n in resumo.tabelas.items():
            print(f"    {tabela:<24} {n:>10,}")
        print(f"    taxa de ruptura: "
              f"{resumo.ruins['taxa_ruptura_sku_dia_pct']:.3f}% dos SKU-dia")

    return resumo
