-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q08 - OTIF DE FORNECEDORES
--
-- PERGUNTA DE NEGOCIO
--   "Qual fornecedor me deixa na mao?"
--
-- OTIF = On Time, In Full (no prazo, completo).
-- Metrica padrao de logistica, raramente calculada em mercadinho.
--
-- POR QUE IMPORTA PARA A PREVISAO
--   O lead time nao e um numero fixo: e uma distribuicao. Se o
--   fornecedor atrasa 18% das entregas, o estoque de seguranca precisa
--   cobrir esse risco. A formula do ponto de pedido usa 1,65*sigma,
--   e sigma depende da variabilidade REAL do fornecedor - medida aqui,
--   nao estimada.
--
-- KPI: OTIF%, atraso medio em dias, taxa de entrega parcial.
-- =====================================================================

SELECT
    f.razao_social                                       AS fornecedor,
    count(*)                                             AS entregas,
    round(avg(CASE WHEN fc.no_prazo THEN 1.0 ELSE 0.0 END) * 100, 1)
                                                         AS no_prazo_pct,
    round(avg(CASE WHEN fc.entrega_completa THEN 1.0 ELSE 0.0 END) * 100, 1)
                                                         AS completo_pct,
    round(avg(CASE WHEN fc.no_prazo AND fc.entrega_completa
                   THEN 1.0 ELSE 0.0 END) * 100, 1)      AS otif_pct,
    round(avg(fc.dias_atraso) FILTER (WHERE fc.dias_atraso > 0), 1)
                                                         AS atraso_medio_dias,
    max(fc.dias_atraso)                                  AS atraso_maximo_dias,
    round(stddev_samp(fc.dias_atraso), 2)                AS desvio_atraso,
    round(cast(sum(fc.valor_total) as numeric), 2)      AS valor_total_comprado,
    CASE
        WHEN avg(CASE WHEN fc.no_prazo AND fc.entrega_completa
                      THEN 1.0 ELSE 0.0 END) >= 0.90 THEN 'A - CONFORME'
        WHEN avg(CASE WHEN fc.no_prazo AND fc.entrega_completa
                      THEN 1.0 ELSE 0.0 END) >= 0.75 THEN 'B - ATENCAO'
        ELSE 'C - CRITICO'
    END AS classificacao
  FROM ouro.fato_compras fc
  JOIN ouro.dim_fornecedor f ON f.fornecedor_id = fc.fornecedor_id
 WHERE fc.data_entrega IS NOT NULL
 GROUP BY f.razao_social
 ORDER BY otif_pct DESC;
