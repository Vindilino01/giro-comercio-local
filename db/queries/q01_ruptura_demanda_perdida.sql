-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q01 - RUPTURA E DEMANDA PERDIDA
--
-- PERGUNTA DE NEGOCIO
--   "Quanto eu deixei de vender por falta de produto nos ultimos 12
--    meses, e em quais SKUs isso doi mais?"
--
-- POR QUE ESTA CONSULTA IMPORTA
--   E a consulta que sustenta o diferencial do Giro. Todo mundo mede
--   venda; quase ninguem mede a venda que NAO aconteceu. Sem esse
--   numero, o dono nao tem incentivo para investir em previsao -
--   a ruptura parece "normal".
--
-- COMO O NUMERO E CALCULADO
--   demanda_perdida = max(0, media_historica_sem_ruptura - vendido)
--   A media usa somente dias SEM ruptura do mesmo SKU e dia da semana,
--   para nao contaminar a referencia com o proprio periodo de falta.
--
-- ANCORAGEM NA DATA DO DADO, NAO NO RELOGIO
--   A janela e definida a partir de max(data_venda) da propria base,
--   nao de CURRENT_DATE. Motivo: o banco e um retrato historico. Com
--   CURRENT_DATE, um dataset que termina em out/2025 e consultado em
--   nov/2026 devolveria janela vazia - foi exatamente o bug observado
--   na primeira execucao (0 rupturas).
--
-- KPI: taxa de ruptura (% SKU-dia) e receita perdida estimada (R$).
-- BENCHMARK: 8,3% global (Nielsen), 10-12% no Brasil (Neogrid).
-- =====================================================================

WITH parametros AS (
    SELECT
        (SELECT max(data_venda) FROM ouro.fato_vendas) - INTERVAL '12 months'
            AS inicio,
        (SELECT max(data_venda) FROM ouro.fato_vendas) AS fim
),
rupturas AS (
    SELECT r.*
      FROM ouro.mv_rupturas r, parametros p
     WHERE r.data_venda > p.inicio::date
       AND r.data_venda <= p.fim
),
total AS (
    SELECT
        count(*)                                          AS sku_dia_ruptura,
        (SELECT count(*) FROM ouro.fato_estoque_diario e, parametros p
          WHERE e.data_ref > p.inicio::date AND e.data_ref <= p.fim)
                                                          AS sku_dia_total,
        sum(r.demanda_perdida_un)                         AS unidades_perdidas,
        sum(r.receita_perdida_estimada)                   AS receita_perdida
      FROM rupturas r
)
SELECT
    round(sku_dia_ruptura::numeric / nullif(sku_dia_total, 0) * 100, 2)
        AS taxa_ruptura_pct,
    sku_dia_ruptura,
    sku_dia_total,
    round(unidades_perdidas, 0)          AS unidades_perdidas,
    round(cast(receita_perdida as numeric), 2) AS receita_perdida,
    round(receita_perdida / nullif(sku_dia_ruptura, 0), 2) AS perda_media_por_evento
  FROM total;
