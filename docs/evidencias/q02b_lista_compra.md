# Q02b — Lista Compra

**Pergunta de negocio:** Quais SKUs priorizar na compra?

**Linhas retornadas:** 25  
**Tempo de execucao:** 1.6 ms

## Consulta

```sql
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
```

## Resultado

| loja_id | produto                        | departamento       | situacao | estoque_atual | demanda_dia_prevista | cobertura_dias | ponto_pedido | quantidade_sugerida | valor     | fornecedor                 | lead_time_dias | score_qualidade_loja |
|---------|--------------------------------|--------------------|----------|---------------|----------------------|----------------|--------------|---------------------|-----------|----------------------------|----------------|----------------------|
| 2       | Peixe Vale Mais 200g           | ACOUGUE            | RUPTURA  | 0.00          | 24.16                | 0.00           | 389.89       | 390.00              | 15 561.00 | Atacarejo Uniao LTDA       | 14             | 99.70                |
| 2       | Carne Bovina Estrela 1kg       | ACOUGUE            | RUPTURA  | 0.00          | 24.54                | 0.00           | 342.29       | 343.00              | 14 231.07 | Logistica Vale Verde LTDA  | 12             | 99.70                |
| 3       | Frango Inteiro                 | ACOUGUE            | RUPTURA  | 0.00          | 19.63                | 0.00           | 272.30       | 273.00              | 11 384.10 | Logistica Vale Verde LTDA  | 12             | 99.70                |
| 3       | Feijao Carioca 1kg             | MERCEARIA          | RUPTURA  | 0.00          | 22.94                | 0.00           | 292.06       | 293.00              | 4 260.22  | Atacadao Sul LTDA          | 11             | 99.70                |
| 1       | Margarina 500g                 | FRIOS_E_LATICINIOS | RUPTURA  | 0.00          | 15.32                | 0.00           | 213.44       | 214.00              | 3 276.34  | Logistica Vale Verde LTDA  | 12             | 99.60                |
| 1       | Pasta de Dente Nobre 1kg       | HIGIENE            | RUPTURA  | 0.00          | 32.80                | 0.00           | 447.31       | 448.00              | 2 266.88  | Distribuidora Central LTDA | 12             | 99.60                |
| 1       | Manteiga Sabor Real 500ml      | FRIOS_E_LATICINIOS | RUPTURA  | 0.00          | 5.65                 | 0.00           | 82.62        | 83.00               | 1 790.31  | Logistica Vale Verde LTDA  | 12             | 99.60                |
| 2       | Sabonete Dona Rosa 1kg         | HIGIENE            | RUPTURA  | 0.00          | 9.34                 | 0.00           | 135.55       | 136.00              | 1 423.92  | Logistica Vale Verde LTDA  | 12             | 99.70                |
| 3       | Peixe Nobre 1kg                | ACOUGUE            | RUPTURA  | 0.00          | 6.12                 | 0.00           | 88.05        | 89.00               | 1 406.20  | Distribuidora Central LTDA | 12             | 99.70                |
| 3       | Rosca Dona Rosa 350g           | PADARIA            | RUPTURA  | 0.00          | 9.25                 | 0.00           | 132.49       | 133.00              | 1 155.77  | Distribuidora Central LTDA | 12             | 99.70                |
| 3       | Queijo Sabor Real 1kg          | FRIOS_E_LATICINIOS | RUPTURA  | 0.00          | 8.21                 | 0.00           | 118.35       | 119.00              | 1 140.02  | Logistica Vale Verde LTDA  | 12             | 99.70                |
| 3       | Batata Nobre 2kg               | HORTIFRUTI         | RUPTURA  | 0.00          | 19.16                | 0.00           | 204.58       | 205.00              | 1 074.20  | Alimentos Horizonte LTDA   | 9              | 99.70                |
| 3       | Laranja Bom Preco 200g         | HORTIFRUTI         | RUPTURA  | 0.00          | 28.27                | 0.00           | 300.40       | 301.00              | 1 068.55  | Alimentos Horizonte LTDA   | 9              | 99.70                |
| 3       | Peixe Campo Verde 2L           | ACOUGUE            | RUPTURA  | 0.00          | 2.32                 | 0.00           | 33.40        | 34.00               | 994.50    | Atacadao Sul LTDA          | 11             | 99.70                |
| 2       | Banana Prata                   | HORTIFRUTI         | RUPTURA  | 0.00          | 30.76                | 0.00           | 425.87       | 426.00              | 988.32    | Distribuidora Central LTDA | 12             | 99.70                |
| 2       | Laranja Bom Preco 200g         | HORTIFRUTI         | RUPTURA  | 0.00          | 25.80                | 0.00           | 272.28       | 273.00              | 969.15    | Alimentos Horizonte LTDA   | 9              | 99.70                |
| 2       | Detergente Sabor Real 500g     | LIMPEZA            | RUPTURA  | 0.00          | 11.57                | 0.00           | 124.56       | 125.00              | 883.75    | Alimentos Horizonte LTDA   | 9              | 99.70                |
| 1       | Banana Prata                   | HORTIFRUTI         | RUPTURA  | 0.00          | 26.84                | 0.00           | 364.72       | 365.00              | 846.80    | Distribuidora Central LTDA | 12             | 99.60                |
| 1       | Carne Bovina Tradicao 2kg      | ACOUGUE            | RUPTURA  | 0.00          | 2.28                 | 0.00           | 27.70        | 28.00               | 843.64    | Alimentos Horizonte LTDA   | 9              | 99.60                |
| 2       | Iogurte Da Casa 200g           | FRIOS_E_LATICINIOS | RUPTURA  | 0.00          | 2.65                 | 0.00           | 40.03        | 41.00               | 814.67    | Distribuidora Central LTDA | 12             | 99.70                |
| 3       | Tomate Campo Verde 350g        | HORTIFRUTI         | RUPTURA  | 0.00          | 13.25                | 0.00           | 216.94       | 217.00              | 813.75    | Atacarejo Uniao LTDA       | 14             | 99.70                |
| 3       | Linguica Nobre 2kg             | ACOUGUE            | RUPTURA  | 0.00          | 1.41                 | 0.00           | 18.72        | 19.00               | 784.70    | Alimentos Horizonte LTDA   | 9              | 99.70                |
| 3       | Agua Sanitaria Puro Sabor 500g | LIMPEZA            | RUPTURA  | 0.00          | 7.13                 | 0.00           | 110.14       | 111.00              | 738.15    | Comercial Bom Dia LTDA     | 13             | 99.70                |
| 3       | Iogurte Nobre 1kg              | FRIOS_E_LATICINIOS | RUPTURA  | 0.00          | 2.48                 | 0.00           | 38.47        | 39.00               | 716.04    | Distribuidora Central LTDA | 12             | 99.70                |
| 3       | Suco Puro Sabor 1L             | BEBIDAS            | RUPTURA  | 0.00          | 6.16                 | 0.00           | 84.51        | 85.00               | 695.30    | Atacadao Sul LTDA          | 11             | 99.70                |
