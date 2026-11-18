# Q10 — Painel Qualidade

**Pergunta de negocio:** Posso confiar nos numeros que estou vendo?

**Linhas retornadas:** 24  
**Tempo de execucao:** 52.8 ms

## Consulta

```sql
-- =====================================================================
-- Q10 - PAINEL DE QUALIDADE DOS DADOS
--
-- PERGUNTA DE NEGOCIO
--   "Posso confiar nos numeros que estou vendo?"
--
-- ESTA E A CONSULTA QUE SUSTENTA O SELO DE CONFIANCA.
-- Sem ela, o dashboard seria uma caixa-preta que o dono nao tem como
-- auditar. Com ela, cada numero tem procedencia.
--
-- CORRECAO IMPORTANTE (v2)
-- ------------------------
-- A versao anterior tinha quatro SELECT independentes, sem UNION. O
-- driver devolve apenas o primeiro resultado: as partes 2, 3 e 4
-- (score por dimensao, atualidade, selo por loja) NUNCA chegavam ao
-- relatorio, embora o documento descrevesse a consulta como "4 blocos
-- em UNION".
--
-- Agora e um unico SELECT com UNION ALL sobre colunas homogeneas.
-- O bloco 1 tem 4 colunas numericas que nao fazem sentido nos outros
-- blocos; elas vao como NULL para manter a uniformidade.
--
-- ANCORAGEM NA DATA DO DADO
-- -------------------------
-- A idade da carga e calculada contra max(data_venda), nao contra
-- CURRENT_DATE. O banco e um retrato historico: com CURRENT_DATE a
-- "idade" apareceria como ~380 dias para uma carga de outubro/2025
-- consultada em novembro/2026, virando alarme falso permanente.
--
-- KPI: taxa de aceite por tabela, recall de deteccao, idade do dado.
-- =====================================================================

WITH referencia AS (
    SELECT max(data_venda) AS fim FROM prata.venda
),
rejeicoes AS (
    SELECT
        'REJEICOES_POR_REGRA'::text        AS bloco,
        rq.codigo                          AS item,
        rq.dimensao                        AS categoria,
        count(q.quarentena_id)::bigint     AS ocorrencias,
        round(count(q.quarentena_id)::numeric
              / nullif((SELECT count(*) FROM gov.quarentena), 0) * 100, 2)
                                           AS pct_do_total,
        NULL::numeric                      AS score_medio,
        NULL::date                         AS ultima_carga,
        NULL::int                          AS idade_dias
      FROM gov.regra_qualidade rq
      LEFT JOIN gov.quarentena q USING (regra_id)
     GROUP BY rq.codigo, rq.dimensao
    HAVING count(q.quarentena_id) > 0
),
scores AS (
    SELECT
        'SCORE_POR_DIMENSAO'               AS bloco,
        dimensao                           AS item,
        dimensao                           AS categoria,
        count(*)::bigint                   AS ocorrencias,
        NULL::numeric                      AS pct_do_total,
        round(avg(score_pct), 2)           AS score_medio,
        NULL::date                         AS ultima_carga,
        NULL::int                          AS idade_dias
      FROM gov.metrica_qualidade
     GROUP BY dimensao
),
atualidade AS (
    SELECT
        'ATUALIDADE'                       AS bloco,
        origem                             AS item,
        'carga'                            AS categoria,
        count(*)::bigint                   AS ocorrencias,
        round(avg(linhas_aceitas::numeric
                  / nullif(linhas_lidas, 0) * 100), 2) AS pct_do_total,
        NULL::numeric                      AS score_medio,
        (SELECT fim FROM referencia)       AS ultima_carga,
        -- Idade medida contra a REFERENCIA DO DADO, nao contra o
        -- relogio. O banco e um retrato historico: com CURRENT_DATE a
        -- idade de uma carga de out/2025 consultada em nov/2026
        -- apareceria como -383 dias, virando alarme falso permanente.
        ((SELECT fim FROM referencia)
         - (SELECT max(data_referencia) FROM gov.lote_carga
             WHERE data_referencia IS NOT NULL))::int AS idade_dias
      FROM gov.lote_carga
     GROUP BY origem
),
selo AS (
    SELECT
        'SELO_LOJA'                        AS bloco,
        loja                               AS item,
        selo                               AS categoria,
        dimensoes_medidas::bigint          AS ocorrencias,
        NULL::numeric                      AS pct_do_total,
        score_medio_pct                    AS score_medio,
        NULL::date                         AS ultima_carga,
        NULL::int                          AS idade_dias
      FROM ouro.mv_qualidade_loja
)
SELECT bloco, item, categoria, ocorrencias, pct_do_total,
       score_medio, ultima_carga, idade_dias
  FROM rejeicoes
 UNION ALL
SELECT bloco, item, categoria, ocorrencias, pct_do_total,
       score_medio, ultima_carga, idade_dias
  FROM scores
 UNION ALL
SELECT bloco, item, categoria, ocorrencias, pct_do_total,
       score_medio, ultima_carga, idade_dias
  FROM atualidade
 UNION ALL
SELECT bloco, item, categoria, ocorrencias, pct_do_total,
       score_medio, ultima_carga, idade_dias
  FROM selo
 ORDER BY bloco, score_medio NULLS FIRST, ocorrencias DESC;
```

## Resultado

| bloco               | item                  | categoria    | ocorrencias | pct_do_total | score_medio | ultima_carga | idade_dias |
|---------------------|-----------------------|--------------|-------------|--------------|-------------|--------------|------------|
| ATUALIDADE          | CSV_PROMOCAO_PRODUTO  | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_FORNECEDOR        | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_ITEM_VENDA        | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_LOJA              | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_ESTOQUE           | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_CALENDARIO        | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_VENDA             | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_PRODUTO_PRECO     | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_PROMOCAO          | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_PRODUTO           | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_MOVIMENTACAO      | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_ITEM_PEDIDO       | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| ATUALIDADE          | CSV_PEDIDO            | carga        | 1           | 100.00       | —           | 2025-10-31   | 0          |
| REJEICOES_POR_REGRA | DQ020                 | consistencia | 3 290       | 100.00       | —           | —            | —          |
| SCORE_POR_DIMENSAO  | acuracidade           | acuracidade  | 3           | —            | 98.71       | —            | —          |
| SCORE_POR_DIMENSAO  | consistencia          | consistencia | 3           | —            | 99.93       | —            | —          |
| SCORE_POR_DIMENSAO  | validade              | validade     | 3           | —            | 100.00      | —            | —          |
| SCORE_POR_DIMENSAO  | completude            | completude   | 3           | —            | 100.00      | —            | —          |
| SCORE_POR_DIMENSAO  | unicidade             | unicidade    | 3           | —            | 100.00      | —            | —          |
| SCORE_POR_DIMENSAO  | atualidade            | atualidade   | 3           | —            | 100.00      | —            | —          |
| SCORE_POR_DIMENSAO  | conformidade          | conformidade | 3           | —            | 100.00      | —            | —          |
| SELO_LOJA           | Mercado Sao Jorge     | CONFIAVEL    | 7           | —            | 99.80       | —            | —          |
| SELO_LOJA           | Mercado Bom Preco     | CONFIAVEL    | 7           | —            | 99.81       | —            | —          |
| SELO_LOJA           | Mercadinho da Familia | CONFIAVEL    | 7           | —            | 99.81       | —            | —          |
