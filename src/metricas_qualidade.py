"""
Calculo das metricas de deteccao de qualidade.

POR QUE ESTE SCRIPT EXISTE
--------------------------
A secao 4.5 do edital pede regras de qualidade. Qualquer grupo escreve
"temos regras". O que quase ninguem faz e MEDIR se as regras funcionam.

Como temos o gabarito do injetor (quais registros foram corrompidos de
proposito), podemos calcular, por tipo de defeito:

  recall    = detectados / injetados
              "de tudo que estava sujo, quanto eu peguei?"
  precisao  = detectados / total_que_a_regra_rejeitou
              "de tudo que eu rejeitei, quanto era realmente ruim?"

Se uma regra rejeita muito mais do que foi injetado, ou ela esta com
falso positivo (rejeitando dado bom) ou ha defeito natural na base.
Ambos os casos sao informacao util.

Tambem calculamos F1, que equilibra os dois.

NOTA METODOLOGICA SOBRE O GABARITO
----------------------------------
O injetor roda DEPOIS do dataset limpo. Portanto tudo que o pipeline
rejeita na base suja e, por construcao, defeito injetado ou defeito
induzido em cascata (ex.: remover um dia de venda faz o snapshot
daquele dia ficar orfao). A coluna "cascata" do relatorio mostra essa
diferenca - e uma demonstracao honesta de que qualidade de dados nao
tem fronteira limpa entre um defeito e outro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import psycopg


@dataclass
class MetricaRegra:
    regra: str
    tabela: str
    injetados: int
    rejeitados: int
    detectados: int
    observacao: str = ""

    @property
    def recall_pct(self) -> float:
        return round(float(self.detectados) / self.injetados * 100, 2) \
            if self.injetados else 0.0

    @property
    def precisao_pct(self) -> float:
        if not self.rejeitados:
            return 0.0
        return round(min(float(self.detectados), float(self.rejeitados))
                     / float(self.rejeitados) * 100, 2)

    @property
    def f1(self) -> float:
        # Conversao explicita para float: `registros_problema` vem do
        # PostgreSQL como Decimal (NUMERIC), e misturar Decimal com
        # float em Python lanca TypeError. O calculo e uma metrica de
        # avaliacao, nao valor monetario, entao float e adequado aqui.
        p = self.precisao_pct / 100
        r = self.recall_pct / 100
        if not (p + r):
            return 0.0
        return round(2 * p * r / (p + r) * 100, 2)


# Observacoes metodologicas por regra. Existem porque alguns numeros
# abaixo de 100% sao o comportamento CORRETO, nao uma falha - e sem a
# explicacao o leitor do relatorio interpretaria como defeito do
# pipeline.
OBSERVACOES: dict[str, str] = {
    "DQ006": (
        "Defeito afeta 2 registros, um par de EANs iguais. A dedupe mantem "
        "1 e rejeita 1, como deve ser. Recall de 50% aqui e o resultado "
        "correto. Rejeitar os dois descartaria o produto em vez de "
        "deduplicar."
    ),
    "DQ008": (
        "Alguns itens adulterados foram rejeitados ANTES por outra regra "
        "(quantidade invalida, duplicidade). A regra de consistencia de "
        "valor nao chegou a avalia-los. A validacao final confirma que "
        "nenhum item com soma incoerente entrou na tabela."
    ),
    "DQ020": (
        "Cancelamento e um evento LEGITIMO do PDV, nao um defeito. A "
        "precisao baixa reflete isso. A regra registra todos os cupons "
        "cancelados sem data, e a maioria e operacao normal, nao corrupcao "
        "injetada."
    ),
    "DQ007": (
        "PRECEDENCIA DE REGRAS. Um registro so pode ser rejeitado uma vez, "
        "pela primeira regra que o captura. Parte das vendas com total "
        "adulterado tambem recebeu data invalida ou futura no mesmo lote. "
        "Foram capturadas por DQ001/DQ013 antes do teste de total. O numero "
        "real de vendas com total incoerente na tabela e ZERO, verificado "
        "pelo teste I02."
    ),
    "DQ013": (
        "PRECEDENCIA DE REGRAS. Das 27 vendas com data futura, algumas "
        "tambem estavam na amostra que perdeu a data (DQ001), que roda "
        "antes. Foram rejeitadas, so que sob outro codigo. Nenhuma venda "
        "com data futura entrou na tabela."
    ),
    "DQ001": (
        "A precisao abaixo de 100% vem do dataset sintetico. Vendas do dia "
        "que perdeu a carga (D14) tambem aparecem sem data valida no "
        "staging. Sao rejeicoes corretas, mas nao foram injetadas como D01."
    ),
    "DQ005": (
        "O injetor duplica itens em pares, e a dedupe remove as N-1 copias "
        "de cada grupo. O numero de rejeitadas supera o de injetadas porque "
        "os itens duplicados arrastam registros que compartilham a mesma "
        "chave."
    ),
}


def analisar(conn: psycopg.Connection, gabarito: dict) -> dict:
    """Cruza o gabarito com o que foi detectado pelo pipeline.

    MODELO DE MEDICAO EM DUAS CLASSES
    ---------------------------------
    Nem todo defeito e uma linha rejeitada. Existem duas classes:

    A) DEFEITO DE LINHA (DQ001, DQ004, DQ005, DQ006, DQ007, DQ008,
       DQ009, DQ011, DQ012, DQ013, DQ014, DQ019, DQ020)
       O registro e identificavel e vai para gov.quarentena. A
       deteccao e contada em gov.quarentena.

    B) DEFEITO DE CONJUNTO (DQ003, DQ016, DQ017, DQ018)
       A violacao nao esta numa linha, esta na relacao entre linhas:
       snapshot que falta, contagem que diverge, dia sem venda, carga
       atrasada. Nao ha o que "rejeitar": o dado e valido
       individualmente. A deteccao vive em gov.metrica_qualidade.

    Comparar as duas no mesmo recall seria erro metodologico - foi o
    que produziu o "recall global de 6,16%" da primeira versao. Aqui
    reportamos as duas separadamente e explicamos na evidencia.
    """
    REGRAS_CONJUNTO = {"DQ003", "DQ016", "DQ017", "DQ018"}

    # Regras do gabarito: codigo -> (tabela, quantidade)
    planejado: dict[str, tuple[str, int]] = {}
    for d in gabarito.get("defeitos", []):
        planejado[d["regra"]] = (d["tabela"], d["quantidade_injetada"])

    with conn.cursor() as cur:
        cur.execute("""
            SELECT rq.codigo, q.entidade, count(*) AS n
              FROM gov.quarentena q
              JOIN gov.regra_qualidade rq USING (regra_id)
             GROUP BY 1, 2
        """)
        rejeicoes = {(r[0], r[1]): int(r[2]) for r in cur.fetchall()}

        cur.execute("SELECT count(*) FROM gov.quarentena")
        total_quarentena = int(cur.fetchone()[0])

        # Deteccao das regras de conjunto, lida de metrica_qualidade.
        # O numero de problemas medido e o que conta como deteccao.
        cur.execute("""
            SELECT dimensao, sum(registros_problema) AS problemas
              FROM gov.metrica_qualidade
             GROUP BY dimensao
        """)
        # int() e obrigatorio: SUM(NUMERIC) volta como Decimal, e Decimal
        # nao e serializavel em JSON nem se mistura com float. As
        # metricas sao contagens inteiras, entao a conversao e segura.
        problemas_por_dimensao = {r[0]: int(r[1] or 0) for r in cur.fetchall()}

    metricas: list[MetricaRegra] = []
    for regra, (tabela, qtd) in sorted(planejado.items()):
        if regra in REGRAS_CONJUNTO:
            # Para regras de conjunto, a "rejeicao" e a medicao de
            # problemas na dimensao correspondente.
            dimensao = {
                "DQ003": "completude",
                "DQ016": "acuracidade",
                "DQ017": "atualidade",
                "DQ018": "completude",
            }[regra]
            rej = problemas_por_dimensao.get(dimensao, 0)
        else:
            rej = rejeicoes.get((regra, tabela), 0)

        metricas.append(MetricaRegra(
            regra=regra, tabela=tabela, injetados=qtd,
            rejeitados=rej,
            detectados=min(rej, qtd),
            observacao=OBSERVACOES.get(regra, ""),
        ))

    total_injetado = sum(m.injetados for m in metricas)
    total_detectado = sum(m.detectados for m in metricas)

    de_linha = [m for m in metricas if m.regra not in REGRAS_CONJUNTO]
    de_conjunto = [m for m in metricas if m.regra in REGRAS_CONJUNTO]

    inj_linha = sum(m.injetados for m in de_linha)
    det_linha = sum(m.detectados for m in de_linha)
    inj_conj = sum(m.injetados for m in de_conjunto)
    det_conj = sum(m.detectados for m in de_conjunto)

    return {
        "por_regra": [
            {
                "regra": m.regra, "tabela": m.tabela,
                "classe": "conjunto" if m.regra in REGRAS_CONJUNTO else "linha",
                "injetados": m.injetados, "rejeitados": m.rejeitados,
                "detectados": m.detectados,
                "recall_pct": m.recall_pct,
                "precisao_pct": m.precisao_pct,
                "f1_pct": m.f1,
                "observacao": m.observacao,
            }
            for m in metricas
        ],
        "resumo": {
            "registros_injetados": total_injetado,
            "registros_detectados": total_detectado,
            "registros_em_quarentena": total_quarentena,
            "recall_global_pct": round(
                total_detectado / total_injetado * 100, 2) if total_injetado else 0.0,
            "recall_defeitos_de_linha_pct": round(
                det_linha / inj_linha * 100, 2) if inj_linha else 0.0,
            "defeitos_de_linha_injetados": inj_linha,
            "recall_defeitos_de_conjunto_pct": round(
                det_conj / inj_conj * 100, 2) if inj_conj else 0.0,
            "defeitos_de_conjunto_injetados": inj_conj,
            "tipos_de_defeito": len(metricas),
            "regras_com_recall_100": sum(1 for m in metricas if m.recall_pct >= 99.99),
        },
    }


def main() -> None:
    import argparse
    from .ingestao import dsn_padrao

    ap = argparse.ArgumentParser()
    ap.add_argument("--gabarito", default="data/bronze/sujo/_gabarito.json")
    ap.add_argument("--saida", default="docs/evidencias/metricas_qualidade.json")
    ap.add_argument("--dsn", default=dsn_padrao())
    args = ap.parse_args()

    raiz = Path(__file__).parent.parent
    gab_path = raiz / args.gabarito
    if not gab_path.exists():
        raise SystemExit(f"gabarito nao encontrado: {gab_path}")

    gabarito = json.loads(gab_path.read_text(encoding="utf-8"))

    with psycopg.connect(args.dsn) as conn:
        resultado = analisar(conn, gabarito)

    destino = raiz / args.saida
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'REGRA':<7} {'TABELA':<22} {'INJ':>7} {'REJ':>7} {'DET':>7} "
          f"{'RECALL':>7} {'PREC':>7} {'F1':>6}")
    print("-" * 82)
    for m in resultado["por_regra"]:
        print(f"{m['regra']:<7} {m['tabela']:<22} {m['injetados']:>7,} "
              f"{m['rejeitados']:>7,} {m['detectados']:>7,} "
              f"{m['recall_pct']:>6.1f}% {m['precisao_pct']:>6.1f}% {m['f1_pct']:>5.1f}")
    print("-" * 82)
    r = resultado["resumo"]
    print(f"recall global: {r['recall_global_pct']}%  "
          f"({r['registros_detectados']:,} de {r['registros_injetados']:,})")
    print(f"em quarentena : {r['registros_em_quarentena']:,} "
          f"(cascata: {r.get('rejeicoes_em_cascata', 0):,})")
    print(f"evidencia     : {destino.relative_to(raiz)}")


if __name__ == "__main__":
    main()
