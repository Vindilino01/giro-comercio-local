-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q05 - RISCO DE VENCIMENTO (pereciveis)
--
-- PERGUNTA DE NEGOCIO
--   "O que vai vencer na prateleira e virar prejuizo?"
--
-- O PROBLEMA ESPECIFICO DO MERCADINHO
--   Produto nao perecivel em excesso e capital parado. Perecivel em
--   excesso e PERDA SECA: o dinheiro ja foi gasto e o produto vira
--   lixo. Por isso a cobertura aceitavel de um perecivel e muito menor.
--
-- COMO CALCULAMOS
--   dias_ate_vencer estimado pela vida util media do SKU, assumindo
--   que o estoque atual entrou agora (premissa declarada).
--   risco = demanda_prevista_no_periodo < estoque_atual
--
-- KPI: valor em risco de vencimento (R$).
-- =====================================================================

WITH estoque_atual AS (
    -- DISTINCT ON com ORDER BY que casa EXATAMENTE com a PK
    -- (loja_id, produto_id, data_ref).
    --
    -- Duas versoes anteriores e o que cada uma custou:
    --   1. row_number() OVER (PARTITION BY loja, produto ORDER BY data):
    --      1,8 s e derramava para disco (temp read=11298 blocos),
    --      porque ordena 921k linhas.
    --   2. DISTINCT ON com ORDER BY (loja, produto, data DESC): o
    --      planejador fez Incremental Sort de 921k linhas (1,2 s) por
    --      causa do DESC.
    --   3. Agregacao com max(data_ref) por SKU: le so o indice
    --      (index-only scan), encontra a data maxima e depois busca
    --      apenas 1.260 linhas no heap.
    --
    -- A versao 3 e a correta porque a pergunta e "qual a ULTIMA data
    -- por SKU" - uma agregacao, nao uma janela.
    SELECT e.loja_id, e.produto_id, e.qtd_fim, e.valor_estoque, e.data_ref
      FROM ouro.fato_estoque_diario e
      JOIN (SELECT loja_id, produto_id, max(data_ref) AS ultima
              FROM ouro.fato_estoque_diario
             GROUP BY loja_id, produto_id) u
        ON u.loja_id = e.loja_id
       AND u.produto_id = e.produto_id
       AND u.ultima = e.data_ref
),
demanda AS (
    SELECT loja_id, produto_id,
           coalesce(avg(qtd_demanda), 0) AS demanda_dia
      FROM ouro.mv_demanda_diaria
     GROUP BY loja_id, produto_id
)
SELECT
    p.departamento,
    count(*)                                        AS skus_em_risco,
    round(sum(e.qtd_fim), 0)                        AS unidades_em_risco,
    round(cast(sum(e.valor_estoque) as numeric), 2) AS valor_em_risco,
    round(avg(p.dias_validade), 0)                  AS validade_media_dias,
    round(avg(e.qtd_fim / nullif(d.demanda_dia, 0)), 1) AS cobertura_media_dias,
    round(sum(e.valor_estoque)
          / nullif((SELECT sum(valor_estoque) FROM estoque_atual), 0)
          * 100, 2)                                 AS pct_do_estoque_total
  FROM estoque_atual e
  JOIN ouro.dim_produto p ON p.produto_id = e.produto_id
  JOIN demanda d          ON d.produto_id = e.produto_id
                         AND d.loja_id = e.loja_id
 WHERE p.e_perecivel
   AND p.ativo
   AND e.qtd_fim > 0
   -- Em risco: o estoque cobre mais dias do que a validade restante
   AND e.qtd_fim / nullif(d.demanda_dia, 0) > coalesce(p.dias_validade, 999) * 0.7
 GROUP BY p.departamento
 ORDER BY sum(e.valor_estoque) DESC;
