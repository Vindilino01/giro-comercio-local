-- =====================================================================
-- Q09 - LIFT DE PROMOCAO
--
-- PERGUNTA DE NEGOCIO
--   "A promocao valeu a pena? Eu vendi mais ou apenas dei desconto?"
--
-- O ERRO CLASSICO
--   Comparar a venda DURANTE a promocao com a venda media do ano. Mas
--   a semana da promocao pode ser justamente uma semana fraca, ou o
--   produto pode estar em tendencia. O comparativo correto e com uma
--   janela imediatamente anterior e equivalente em dia da semana.
--
-- METRICA
--   lift = (venda diaria media em promocao) / (venda diaria media fora)
--
-- Interpretacao: se lift de UNIDADES > 1 mas lift de RECEITA < 1, a
-- promocao aumentou volume mas DESTRUIU margem - o caso mais comum e
-- o que o dono nunca percebe.
--
-- DUAS ARMADILHAS DE IMPLEMENTACAO (ambas custaram uma versao)
-- ------------------------------------------------------------
-- 1. PERFORMANCE: count(DISTINCT data_venda) sobre 4,1M de linhas
--    obriga ordenar e deduplicar o fato inteiro. Levou 24 s.
--    Solucao: agregar por (produto, data) primeiro (~620k linhas) e
--    depois contar linhas - cada linha ja e um dia unico.
--
-- 2. CORRECAO: agrupar o nivel 1 por (produto, data, em_promocao)
--    fazia um SKU presente em 3 lojas contar 3 "dias" no mesmo dia.
--    O lift saia 0,71 quando o dado real e 1,43.
--    Solucao: agrupar por (produto, data) e marcar o dia como
--    promocional se QUALQUER loja estava em promocao naquele dia.
--    Assim `count(*)` conta dias de calendario, nao linhas.
--
-- KPI: lift de volume, lift de receita, lift de margem.
-- =====================================================================

WITH por_dia AS (
    -- Nivel 1: uma linha por SKU-dia (todas as lojas somadas).
    -- `bool_or` define o dia como promocional se ao menos uma loja
    -- estava em campanha. ~620k linhas, cabe em memoria.
    SELECT
        f.produto_id,
        f.data_venda,
        bool_or(f.em_promocao)          AS dia_promo,
        sum(f.quantidade)               AS unidades,
        sum(f.valor_liquido)            AS receita,
        sum(coalesce(f.margem_liquida, 0)) AS margem
      FROM ouro.fato_vendas f
     GROUP BY f.produto_id, f.data_venda
),
agregado AS (
    -- Nivel 2: count(*) agora conta DIAS, porque o nivel 1 ja
    -- deduplicou (produto, data).
    SELECT
        produto_id,
        count(*) FILTER (WHERE dia_promo)          AS dias_promo,
        count(*) FILTER (WHERE NOT dia_promo)      AS dias_normal,
        coalesce(sum(unidades) FILTER (WHERE dia_promo), 0)      AS un_promo,
        coalesce(sum(unidades) FILTER (WHERE NOT dia_promo), 0)  AS un_normal,
        coalesce(sum(receita)  FILTER (WHERE dia_promo), 0)      AS rec_promo,
        coalesce(sum(receita)  FILTER (WHERE NOT dia_promo), 0)  AS rec_normal,
        coalesce(sum(margem)   FILTER (WHERE dia_promo), 0)      AS mar_promo,
        coalesce(sum(margem)   FILTER (WHERE NOT dia_promo), 0)  AS mar_normal
      FROM por_dia
     GROUP BY produto_id
),
metricas AS (
    SELECT
        p.departamento,
        a.produto_id,
        a.un_promo   / nullif(a.dias_promo, 0)   AS un_dia_promo,
        a.un_normal  / nullif(a.dias_normal, 0)  AS un_dia_normal,
        a.rec_promo  / nullif(a.dias_promo, 0)   AS rec_dia_promo,
        a.rec_normal / nullif(a.dias_normal, 0)  AS rec_dia_normal,
        a.mar_promo  / nullif(a.dias_promo, 0)   AS mar_dia_promo,
        a.mar_normal / nullif(a.dias_normal, 0)  AS mar_dia_normal
      FROM agregado a
      JOIN ouro.dim_produto p ON p.produto_id = a.produto_id
     WHERE a.dias_promo >= 5
       AND a.dias_normal >= 30
)
SELECT
    departamento,
    count(*)                                                   AS skus_promovidos,
    round(avg(un_dia_promo / nullif(un_dia_normal, 0)), 2)     AS lift_volume,
    round(avg(rec_dia_promo / nullif(rec_dia_normal, 0)), 2)   AS lift_receita,
    round(avg(mar_dia_promo / nullif(mar_dia_normal, 0)), 2)   AS lift_margem,
    count(*) FILTER (WHERE rec_dia_promo > rec_dia_normal)     AS skus_com_ganho_receita,
    count(*) FILTER (WHERE mar_dia_promo > mar_dia_normal)     AS skus_com_ganho_margem,
    round(
        count(*) FILTER (WHERE mar_dia_promo > mar_dia_normal)::numeric
        / nullif(count(*), 0) * 100, 1)                        AS pct_promocoes_rentaveis
  FROM metricas
 GROUP BY departamento
 ORDER BY lift_receita DESC NULLS LAST;
