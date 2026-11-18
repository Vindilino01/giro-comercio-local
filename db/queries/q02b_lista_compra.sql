-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q02b - LISTA DE COMPRA DETALHADA (top ofensores)
--
-- Complementa Q02: a agregacao diz "quanto"; esta diz "o que".
-- Ordenada por risco (ruptura primeiro) e por valor em risco.
-- =====================================================================

SELECT
    s.loja_id,
    s.produto,
    s.departamento,
    s.situacao,
    s.estoque_atual,
    s.demanda_dia_prevista,
    s.cobertura_dias,
    s.ponto_pedido,
    s.quantidade_sugerida,
    round(cast(s.valor_compra_sugerido as numeric), 2) AS valor,
    s.fornecedor,
    s.lead_time_dias,
    s.score_qualidade_loja
  FROM ouro.mv_sugestao_compra s
 WHERE s.situacao IN ('RUPTURA','CRITICO','REPOR')
 ORDER BY CASE s.situacao
              WHEN 'RUPTURA' THEN 1
              WHEN 'CRITICO' THEN 2
              ELSE 3 END,
          s.valor_compra_sugerido DESC
 LIMIT 25;
