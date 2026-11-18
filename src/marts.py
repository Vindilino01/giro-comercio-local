"""
Construcao da camada ouro (star schema + views materializadas).

Estrategia: TRUNCATE + INSERT em vez de DROP + CREATE. Motivo: as views
materializadas dependem das tabelas de dimensao, e recriar tabela
quebraria essas dependencias. TRUNCATE preserva a estrutura e as FKs.

Ordem obrigatoria (dimensoes antes dos fatos, por causa das FKs):
  dim_tempo -> dim_loja -> dim_produto -> dim_fornecedor -> dim_promocao
  -> fato_vendas -> fato_estoque_diario -> fato_compras
  -> metrica_qualidade -> views materializadas
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import psycopg


@dataclass
class Etapa:
    nome: str
    sql: str
    linhas_esperadas: bool = True


DIMENSOES: list[Etapa] = [
    Etapa("dim_tempo", """
        INSERT INTO ouro.dim_tempo
            (data, ano, trimestre, mes, nome_mes, dia, dia_semana_iso,
             nome_dia_semana, is_fim_semana, is_feriado, nome_feriado,
             is_pagamento, ano_mes, semanas_no_mes)
        SELECT c.data, c.ano, extract(quarter FROM c.data)::smallint, c.mes,
               trim(to_char(c.data, 'TMMonth')),
               c.dia, c.dia_semana, c.nome_dia_semana, c.is_fim_semana,
               c.is_feriado, c.nome_feriado, c.is_pagamento,
               to_char(c.data, 'YYYY-MM'),
               extract(week FROM (date_trunc('month', c.data)
                                  + interval '1 month - 1 day'))::smallint
          FROM prata.calendario c
        ON CONFLICT (data) DO NOTHING
    """),

    Etapa("dim_loja", """
        INSERT INTO ouro.dim_loja
            (loja_id, codigo, nome, cidade, uf, area_m2, porte,
             data_abertura, ativa)
        SELECT loja_id, codigo, nome, cidade, uf, area_m2,
               CASE WHEN area_m2 >= 180 THEN 'GRANDE'
                    WHEN area_m2 >= 120 THEN 'MEDIO'
                    ELSE 'PEQUENO' END,
               data_abertura, ativa
          FROM prata.loja
        ON CONFLICT (loja_id) DO NOTHING
    """),

    Etapa("dim_produto", """
        -- ------------------------------------------------------------------
        -- Hierarquia de categoria.
        --
        -- A prata tem DOIS niveis: departamento (nivel 1) e classe
        -- (nivel 2). O produto aponta para a classe.
        --
        -- A primeira versao desta query assumia TRES niveis e fazia
        -- tres LEFT JOINs encadeados (categoria -> pai -> avo). Como o
        -- avo nao existe, `departamento` saia NULL em todas as 420
        -- linhas - e a dimensao inteira ficava "SEM DEPARTAMENTO".
        -- O bug so apareceu porque a consulta Q09 agrupou por
        -- departamento e devolveu uma unica linha.
        --
        -- Correcao: COALESCE entre o pai (departamento) e o proprio
        -- no (classe). Se o produto um dia apontar para um nivel 1,
        -- o COALESCE cobre; se apontar para nivel 2, pega o pai.
        --
        -- `classe` e o nome do proprio no do produto; `departamento`
        -- e o pai. Isso mantem a semantica correta em qualquer
        -- profundidade.
        -- ------------------------------------------------------------------
        INSERT INTO ouro.dim_produto
            (produto_id, ean, sku_interno, nome, departamento, classe,
             unidade_medida, e_perecivel, dias_validade, preco_custo_atual,
             preco_venda_atual, fornecedor_principal, lead_time_dias, ativo)
        SELECT p.produto_id, p.ean, p.sku_interno, p.nome,
               coalesce(pai.nome, c.nome, 'SEM DEPARTAMENTO')      AS departamento,
               coalesce(c.nome, 'SEM CLASSE')                      AS classe,
               p.unidade_medida, p.e_perecivel, p.dias_validade,
               pf.custo_unitario,
               coalesce(
                   pv.preco_venda,
                   round(coalesce(pf.custo_unitario, 0)
                         / nullif(1 - coalesce(mg.margem, 0.30), 0), 2)
               ),
               f.razao_social, pf.lead_time_dias, p.ativo
          FROM prata.produto p
          LEFT JOIN prata.categoria c ON c.categoria_id = p.categoria_id
          LEFT JOIN prata.categoria pai ON pai.categoria_id = c.categoria_pai_id
          LEFT JOIN prata.produto_fornecedor pf
                 ON pf.produto_id = p.produto_id AND pf.preferencial
          LEFT JOIN prata.fornecedor f ON f.fornecedor_id = pf.fornecedor_id
          -- Preco de venda: usa o HISTORICO (fonte da verdade temporal).
          -- Antes esta subconsulta era ancorada em CURRENT_DATE, que contra
          -- um dataset historico devolve zero linhas e fazia todos os 420
          -- SKUs cairem no fallback custo/0,7 - 11,6% de erro medio contra
          -- o preco realmente praticado nas vendas.
          LEFT JOIN LATERAL (
              SELECT h.preco_venda
                FROM prata.produto_preco_historico h
               WHERE h.produto_id = p.produto_id
                 AND h.data_inicio <= (SELECT max(data_venda)
                                         FROM prata.venda)
                 AND (h.data_fim IS NULL
                      OR h.data_fim > (SELECT max(data_venda)
                                         FROM prata.venda))
               ORDER BY h.data_inicio DESC
               LIMIT 1
          ) pv ON TRUE
          -- Fallback: margem tipica observada nas vendas deste SKU. So e
          -- lida quando o historico nao tem faixa vigente.
          LEFT JOIN LATERAL (
              SELECT avg(1 - (i.custo_unitario
                              / nullif(i.preco_unitario, 0))) AS margem
                FROM prata.item_venda i
               WHERE i.produto_id = p.produto_id
                 AND i.preco_unitario > 0
                 AND i.custo_unitario IS NOT NULL
          ) mg ON TRUE
        ON CONFLICT (produto_id) DO NOTHING
    """),

    Etapa("dim_fornecedor", """
        INSERT INTO ouro.dim_fornecedor
            (fornecedor_id, cnpj, razao_social, cidade, uf, lead_time_padrao)
        SELECT fornecedor_id, cnpj, razao_social, cidade, uf, lead_time_dias_padrao
          FROM prata.fornecedor
        ON CONFLICT (fornecedor_id) DO NOTHING
    """),

    Etapa("dim_promocao", """
        INSERT INTO ouro.dim_promocao
            (promocao_id, codigo, descricao, tipo, data_inicio, data_fim,
             duracao_dias, desconto_pct)
        SELECT promocao_id, codigo, descricao, tipo, data_inicio, data_fim,
               (data_fim - data_inicio) + 1, percentual_desconto
          FROM prata.promocao
        ON CONFLICT (promocao_id) DO NOTHING
    """),
]

FATOS: list[Etapa] = [
    Etapa("fato_vendas", """
        INSERT INTO ouro.fato_vendas
            (venda_id, item_seq, data_venda, loja_id, produto_id, promocao_id,
             quantidade, valor_bruto, valor_desconto, valor_liquido,
             custo_total, margem_liquida, em_promocao)
        SELECT i.venda_id, i.item_seq, i.data_venda, v.loja_id, i.produto_id,
               i.promocao_id, i.quantidade,
               round(i.quantidade * i.preco_unitario, 2),
               i.valor_desconto, i.valor_total,
               round(coalesce(i.custo_unitario, 0) * i.quantidade, 2),
               round(i.valor_total
                     - coalesce(i.custo_unitario, 0) * i.quantidade, 2),
               i.promocao_id IS NOT NULL
          FROM prata.item_venda i
          JOIN prata.venda v ON v.venda_id = i.venda_id
                            AND v.data_venda = i.data_venda
         WHERE v.status = 'CONCLUIDA'
    """),

    Etapa("fato_estoque_diario", """
        INSERT INTO ouro.fato_estoque_diario
            (data_ref, loja_id, produto_id, qtd_inicio, qtd_entradas,
             qtd_saidas, qtd_ajustes, qtd_fim, qtd_contada,
             divergencia_inventario, divergencia_pct, houve_ruptura,
             horas_sem_estoque, valor_estoque)
        SELECT e.data_ref, e.loja_id, e.produto_id, e.qtd_inicio,
               e.qtd_entradas, e.qtd_saidas, e.qtd_ajustes, e.qtd_fim,
               e.qtd_contada,
               CASE WHEN e.qtd_contada IS NOT NULL
                    THEN e.qtd_contada - e.qtd_fim END,
               CASE WHEN e.qtd_contada IS NOT NULL AND e.qtd_fim > 0
                    THEN round((e.qtd_contada - e.qtd_fim) / e.qtd_fim * 100, 3)
                    WHEN e.qtd_contada IS NOT NULL AND e.qtd_fim = 0
                         AND e.qtd_contada > 0 THEN 100 END,
               e.houve_ruptura, e.horas_sem_estoque,
               round(e.qtd_fim * coalesce(e.custo_medio, 0), 2)
          FROM prata.estoque_snapshot e
        ON CONFLICT (data_ref, loja_id, produto_id) DO NOTHING
    """),

    Etapa("fato_compras", """
        INSERT INTO ouro.fato_compras
            (pedido_id, item_seq, data_pedido, data_previsao, data_entrega,
             loja_id, produto_id, fornecedor_id, quantidade_pedida,
             quantidade_entregue, valor_total, dias_atraso,
             entrega_completa, no_prazo)
        SELECT pc.pedido_id, ip.item_seq, pc.data_pedido, pc.data_previsao,
               pc.data_entrega, pc.loja_id, ip.produto_id, pc.fornecedor_id,
               ip.quantidade_pedida, ip.quantidade_entregue, ip.valor_total,
               CASE WHEN pc.data_entrega IS NOT NULL
                    THEN (pc.data_entrega - pc.data_previsao) END,
               ip.quantidade_entregue >= ip.quantidade_pedida,
               CASE WHEN pc.data_entrega IS NOT NULL
                    THEN pc.data_entrega <= pc.data_previsao END
          FROM prata.item_pedido ip
          JOIN prata.pedido_compra pc ON pc.pedido_id = ip.pedido_id
        ON CONFLICT (pedido_id, item_seq) DO NOTHING
    """),
]

VIEWS = [
    "ouro.mv_demanda_diaria",
    "ouro.mv_previsao_demanda",
    "ouro.mv_sugestao_compra",
    "ouro.mv_rupturas",
    "ouro.mv_qualidade_loja",
]


def construir(conn: psycopg.Connection, verbose: bool = True) -> dict:
    """Constroi as dimensoes, os fatos e materializa as views."""
    tempos: dict[str, float] = {}

    with conn.cursor() as cur:
        # Limpa na ordem inversa das FKs
        cur.execute("""
            TRUNCATE ouro.fato_compras, ouro.fato_estoque_diario,
                     ouro.fato_vendas, ouro.dim_promocao, ouro.dim_fornecedor,
                     ouro.dim_produto, ouro.dim_loja, ouro.dim_tempo
            RESTART IDENTITY CASCADE
        """)
    conn.commit()

    for etapa in DIMENSOES + FATOS:
        t0 = time.time()
        with conn.cursor() as cur:
            cur.execute(etapa.sql)
            n = cur.rowcount
        conn.commit()
        tempos[etapa.nome] = round(time.time() - t0, 2)
        if verbose:
            print(f"    {etapa.nome:<24} {n:>10,} linhas  "
                  f"{tempos[etapa.nome]:>6.2f}s")

    # Views materializadas: recriadas sempre, porque a definicao muda
    # durante o desenvolvimento e um REFRESH nao pega alteracao de SQL.
    if verbose:
        print("    views materializadas:")
    for view in VIEWS:
        t0 = time.time()
        with conn.cursor() as cur:
            cur.execute(f"REFRESH MATERIALIZED VIEW {view}")
        conn.commit()
        tempos[view] = round(time.time() - t0, 2)
        if verbose:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {view}")
                n = cur.fetchone()[0]
            print(f"      {view.split('.')[1]:<26} {n:>10,} linhas  "
                  f"{tempos[view]:>6.2f}s")

    return tempos
