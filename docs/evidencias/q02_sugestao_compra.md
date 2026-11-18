# Q02 — Sugestao Compra

**Pergunta de negocio:** O que comprar hoje e quanto custa?

**Linhas retornadas:** 4  
**Tempo de execucao:** 1.1 ms

## Consulta

```sql
-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q02 - SUGESTAO DE COMPRA (O PRODUTO)
--
-- PERGUNTA DE NEGOCIO
--   "O que eu compro hoje, quanto, e de quem?"
--
-- ESTA E A CONSULTA QUE O DONO USA TODA SEMANA.
-- Todas as outras existem para justificar esta. Ela combina:
--   - previsao de demanda (EWMA + fator dia da semana)
--   - lead time do fornecedor preferencial
--   - estoque de seguranca (z = 1,65 => 95% de nivel de servico)
--   - lote minimo e multiplo de compra
--   - selo de confianca da loja
--
-- KPI: valor total a comprar e quantos SKUs estao em ruptura/critico.
-- =====================================================================

SELECT
    situacao,
    count(*)                                   AS skus,
    round(sum(estoque_atual), 0)               AS unidades_em_estoque,
    round(sum(quantidade_sugerida), 0)         AS unidades_a_comprar,
    round(cast(sum(valor_compra_sugerido) as numeric), 2) AS valor_total,
    round(avg(cobertura_dias), 1)              AS cobertura_media_dias
  FROM ouro.mv_sugestao_compra
 GROUP BY situacao
 ORDER BY CASE situacao
              WHEN 'RUPTURA' THEN 1
              WHEN 'CRITICO' THEN 2
              WHEN 'REPOR'   THEN 3
              ELSE 4 END;
```

## Resultado

| situacao | skus | unidades_em_estoque | unidades_a_comprar | valor_total | cobertura_media_dias |
|----------|------|---------------------|--------------------|-------------|----------------------|
| RUPTURA  | 118  | 0.00                | 7 356.00           | 87 854.90   | 0.00                 |
| CRITICO  | 446  | 13 972.00           | 15 944.00          | 161 352.10  | 6.70                 |
| REPOR    | 217  | 7 330.00            | 962.00             | 10 370.64   | 15.40                |
| OK       | 479  | 69 423.00           | 0.00               | 0.00        | 26.20                |
