# Q03 — Curva Abc

**Pergunta de negocio:** Quais 20% dos produtos fazem 80% da receita?

**Linhas retornadas:** 3  
**Tempo de execucao:** 1273.8 ms

## Consulta

```sql
-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q03 - CURVA ABC (classificacao de SKUs por contribuicao)
--
-- PERGUNTA DE NEGOCIO
--   "Quais 20% dos produtos fazem 80% da minha receita?"
--
-- POR QUE IMPORTA
--   O dono nao pode dar atencao igual a 420 SKUs. A curva ABC diz onde
--   o esforco de gestao de estoque paga. Classe A: controle rigoroso,
--   nunca pode faltar. Classe C: pode comprar em lote maior, aceitar
--   mais risco de falta.
--
-- TECNICA: window function SUM() OVER (ORDER BY ...) acumula a receita
-- sem self-join, o que importa num fato de 4M de linhas.
--
-- KPI: concentracao da receita (meta: 20% dos SKUs = 60-80% da receita).
-- =====================================================================

WITH receita_produto AS (
    SELECT
        p.produto_id,
        p.nome AS produto,
        p.departamento,
        p.e_perecivel,
        sum(f.valor_liquido)      AS receita,
        sum(f.quantidade)         AS unidades,
        count(DISTINCT f.data_venda) AS dias_com_venda
      FROM ouro.fato_vendas f
      JOIN ouro.dim_produto p ON p.produto_id = f.produto_id
     GROUP BY p.produto_id, p.nome, p.departamento, p.e_perecivel
),
acumulado AS (
    SELECT
        r.*,
        sum(receita) OVER ()                             AS receita_total,
        sum(receita) OVER (ORDER BY receita DESC
                           ROWS UNBOUNDED PRECEDING)     AS receita_acumulada,
        row_number() OVER (ORDER BY receita DESC)        AS posicao,
        count(*) OVER ()                                 AS total_skus
      FROM receita_produto r
)
SELECT
    CASE
        WHEN receita_acumulada / receita_total <= 0.80 THEN 'A'
        WHEN receita_acumulada / receita_total <= 0.95 THEN 'B'
        ELSE 'C'
    END AS classe,
    count(*)                                                  AS skus,
    round(count(*)::numeric / max(total_skus) * 100, 1)       AS pct_skus,
    round(cast(sum(receita) as numeric), 2)                  AS receita,
    round(sum(receita) / max(receita_total) * 100, 1)         AS pct_receita,
    round(avg(unidades), 0)                                   AS unidades_media,
    round(avg(dias_com_venda), 0)                             AS dias_com_venda_media,
    round(sum(CASE WHEN e_perecivel THEN receita ELSE 0 END)
          / nullif(sum(receita), 0) * 100, 1)                 AS pct_receita_perecivel
  FROM acumulado
 GROUP BY classe
 ORDER BY classe;
```

## Resultado

| classe | skus | pct_skus | receita       | pct_receita | unidades_media | dias_com_venda_media | pct_receita_perecivel |
|--------|------|----------|---------------|-------------|----------------|----------------------|-----------------------|
| A      | 79   | 18.80    | 46 875 080.10 | 79.90       | 36 005.00      | 729.00               | 43.10                 |
| B      | 133  | 31.70    | 8 853 713.48  | 15.10       | 6 099.00       | 707.00               | 53.60                 |
| C      | 208  | 49.50    | 2 940 747.44  | 5.00        | 2 154.00       | 609.00               | 50.80                 |
