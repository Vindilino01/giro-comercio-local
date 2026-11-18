# Q04 — Giro Cobertura

**Pergunta de negocio:** Onde meu dinheiro esta parado?

**Linhas retornadas:** 8  
**Tempo de execucao:** 1843.4 ms

## Consulta

```sql
-- FORMATACAO MONETARIA: os valores saem como numeric, nao
-- como texto. `to_char(..., 'L...')` dependia de lc_monetary
-- do cluster, que em 'C' produz o padrao americano e faz um
-- leitor pt-BR interpretar 87.701,67 como 87,70167.
-- A moeda e formatada na apresentacao (consultas.py, painel).

-- =====================================================================
-- Q04 - GIRO E COBERTURA DE ESTOQUE
--
-- PERGUNTA DE NEGOCIO
--   "Onde meu dinheiro esta parado?"
--
-- Giro      = vendas no periodo / estoque medio  -> quantas vezes o
--             estoque "rodou" em 12 meses.
-- Cobertura = estoque atual / demanda diaria     -> quantos dias o
--             estoque aguenta.
--
-- POR QUE AS DUAS JUNTAS
--   Cobertura alta com giro baixo = capital imobilizado (o problema do
--   excesso). Cobertura baixa com giro alto = risco de ruptura (o
--   problema da falta). E o mesmo trade-off que o Giro resolve.
--
-- KPI: giro anual e cobertura em dias, por departamento.
-- =====================================================================

WITH parametros AS (
    -- Ancora na data do DADO, nao no relogio. Ver nota em Q01.
    SELECT (SELECT max(data_venda) FROM ouro.fato_vendas) - INTERVAL '12 months' AS inicio
),
vendas AS (
    SELECT
        f.produto_id,
        p.departamento,
        sum(f.valor_liquido) AS receita,
        sum(f.quantidade)    AS unidades
      FROM ouro.fato_vendas f
      JOIN ouro.dim_produto p ON p.produto_id = f.produto_id,
           parametros pr
     WHERE f.data_venda > pr.inicio::date
     GROUP BY f.produto_id, p.departamento
),
estoque AS (
    SELECT
        e.produto_id,
        avg(e.qtd_fim)                AS estoque_medio,
        avg(e.valor_estoque)          AS valor_medio,
        max(e.valor_estoque)          AS valor_data_atual
      FROM ouro.fato_estoque_diario e,
           parametros pr
     WHERE e.data_ref > pr.inicio::date
     GROUP BY e.produto_id
),
atual AS (
    SELECT DISTINCT ON (produto_id)
        produto_id, qtd_fim, valor_estoque
      FROM ouro.fato_estoque_diario
     ORDER BY produto_id, data_ref DESC
)
SELECT
    v.departamento,
    count(*)                                              AS skus,
    round(cast(sum(v.receita) as numeric), 2)            AS receita_12m,
    round(cast(sum(e.valor_medio) as numeric), 2)        AS estoque_medio_valor,
    round(sum(v.receita) / nullif(sum(e.valor_medio), 0), 2)   AS giro_anual,
    round(365 / nullif(sum(v.receita) / nullif(sum(e.valor_medio), 0), 0), 0)
                                                          AS cobertura_dias,
    round(cast(sum(a.valor_estoque) as numeric), 2)      AS estoque_atual_valor,
    count(*) FILTER (WHERE a.qtd_fim <= 0)                AS skus_em_ruptura
  FROM vendas v
  JOIN estoque e ON e.produto_id = v.produto_id
  JOIN atual a   ON a.produto_id = v.produto_id
 GROUP BY v.departamento
 ORDER BY sum(v.receita) DESC;
```

## Resultado

| departamento       | skus | receita_12m  | estoque_medio_valor | giro_anual | cobertura_dias | estoque_atual_valor | skus_em_ruptura |
|--------------------|------|--------------|---------------------|------------|----------------|---------------------|-----------------|
| ACOUGUE            | 59   | 7 741 610.60 | 60 526.65           | 127.90     | 3.00           | 59 776.22           | 6               |
| BEBIDAS            | 50   | 6 159 212.67 | 61 793.27           | 99.67      | 4.00           | 57 331.29           | 5               |
| LIMPEZA            | 61   | 5 127 202.99 | 58 726.47           | 87.31      | 4.00           | 79 093.05           | 5               |
| FRIOS_E_LATICINIOS | 50   | 2 626 724.27 | 19 631.27           | 133.80     | 3.00           | 20 226.50           | 9               |
| MERCEARIA          | 41   | 2 530 677.09 | 24 984.16           | 101.29     | 4.00           | 26 797.82           | 1               |
| HIGIENE            | 52   | 2 339 989.36 | 24 656.34           | 94.90      | 4.00           | 23 864.06           | 4               |
| HORTIFRUTI         | 53   | 1 430 402.72 | 10 571.48           | 135.31     | 3.00           | 10 662.76           | 8               |
| PADARIA            | 54   | 1 395 123.51 | 10 281.29           | 135.70     | 3.00           | 5 071.36            | 8               |
