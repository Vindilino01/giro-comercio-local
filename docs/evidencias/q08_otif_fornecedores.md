# Q08 — Otif Fornecedores

**Pergunta de negocio:** Qual fornecedor me deixa na mao?

**Linhas retornadas:** 6  
**Tempo de execucao:** 27.3 ms

## Consulta

```sql
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
```

## Resultado

| fornecedor                 | entregas | no_prazo_pct | completo_pct | otif_pct | atraso_medio_dias | atraso_maximo_dias | desvio_atraso | valor_total_comprado | classificacao |
|----------------------------|----------|--------------|--------------|----------|-------------------|--------------------|---------------|----------------------|---------------|
| Atacadao Sul LTDA          | 6 319    | 82.80        | 88.50        | 73.10    | 3.60              | 14                 | 1.61          | 9 925 726.28         | C - CRITICO   |
| Alimentos Horizonte LTDA   | 6 134    | 82.00        | 88.60        | 72.70    | 3.60              | 18                 | 1.71          | 4 922 031.88         | C - CRITICO   |
| Atacarejo Uniao LTDA       | 5 608    | 81.50        | 88.70        | 72.20    | 3.60              | 16                 | 1.66          | 4 278 972.61         | C - CRITICO   |
| Logistica Vale Verde LTDA  | 6 456    | 82.50        | 87.70        | 72.20    | 3.70              | 16                 | 1.68          | 10 984 321.81        | C - CRITICO   |
| Distribuidora Central LTDA | 6 125    | 81.80        | 88.40        | 72.00    | 3.60              | 17                 | 1.69          | 6 762 157.54         | C - CRITICO   |
| Comercial Bom Dia LTDA     | 6 216    | 81.60        | 87.40        | 71.30    | 3.60              | 16                 | 1.71          | 5 482 814.09         | C - CRITICO   |
