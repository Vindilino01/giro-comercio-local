# Q06 — Acuracidade Inventario

**Pergunta de negocio:** Posso confiar no estoque do sistema?

**Linhas retornadas:** 3  
**Tempo de execucao:** 80.8 ms

## Consulta

```sql
-- =====================================================================
-- Q06 - ACURACIDADE DE INVENTARIO
--
-- PERGUNTA DE NEGOCIO
--   "Posso confiar no estoque que o sistema diz que eu tenho?"
--
-- POR QUE ESTA CONSULTA E O CORACAO DO SELO DE CONFIANCA
--   A previsao inteira depende do estoque atual. Se o estoque do
--   sistema esta 20% errado, a sugestao de compra esta 20% errada,
--   por mais correto que o modelo esteja. Medir a acuracidade e
--   pre-condicao para confiar em qualquer numero a jusante.
--
-- METRICA CLASSICA DE VAREJO
--   acuracidade = 1 - |contado - sistema| / sistema
--   Acima de 95% e considerado bom; abaixo de 90% e critico.
--
-- KPI: acuracidade por loja e por departamento.
-- =====================================================================

WITH contagens AS (
    SELECT
        e.loja_id,
        e.produto_id,
        e.data_ref,
        e.qtd_fim,
        e.qtd_contada,
        e.divergencia_inventario,
        e.divergencia_pct,
        -- Divergencia percentual efetiva.
        --
        -- ARMADILHA: divergencia_pct e NULL quando qtd_fim = 0 (a view
        -- evita divisao por zero), e NULL nunca satisfaz
        -- abs(x) <= 5. A versao anterior tratava esses casos como
        -- falha, derrubando a acuracidade de 98,4% para 86-93% - e
        -- entrando em contradicao com o selo de confianca exibido na
        -- mesma tela.
        --
        -- Regra correta: se o sistema diz 0 e a contagem diz 0, NAO ha
        -- divergencia. Se diz 0 e conta 5, a divergencia e total (100%).
        CASE
            WHEN e.qtd_fim = 0 AND e.qtd_contada = 0 THEN 0::numeric
            WHEN e.qtd_fim = 0 AND e.qtd_contada > 0 THEN 100::numeric
            ELSE abs(e.divergencia_pct)
        END AS div_pct
      FROM ouro.fato_estoque_diario e
     WHERE e.qtd_contada IS NOT NULL
)
SELECT
    l.nome                                    AS loja,
    count(*)                                  AS contagens,
    round(avg(c.div_pct), 2)                  AS divergencia_media_pct,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY c.div_pct)::numeric, 2)
                                              AS divergencia_p95_pct,
    round(avg(CASE WHEN c.div_pct <= 5 THEN 1.0 ELSE 0.0 END) * 100, 2)
                                              AS acuracidade_pct,
    count(*) FILTER (WHERE c.div_pct > 5)     AS contagens_divergentes,
    CASE
        WHEN avg(CASE WHEN c.div_pct <= 5 THEN 1.0 ELSE 0.0 END) >= 0.95
            THEN 'CONFIAVEL'
        WHEN avg(CASE WHEN c.div_pct <= 5 THEN 1.0 ELSE 0.0 END) >= 0.90
            THEN 'ATENCAO'
        ELSE 'CRITICO'
    END AS classificacao
  FROM contagens c
  JOIN ouro.dim_loja l ON l.loja_id = c.loja_id
 GROUP BY l.nome
 ORDER BY acuracidade_pct DESC;
```

## Resultado

| loja                  | contagens | divergencia_media_pct | divergencia_p95_pct | acuracidade_pct | contagens_divergentes | classificacao |
|-----------------------|-----------|-----------------------|---------------------|-----------------|-----------------------|---------------|
| Mercadinho da Familia | 6 168     | 0.14                  | 0.00                | 98.77           | 76                    | CONFIAVEL     |
| Mercado Bom Preco     | 5 946     | 0.14                  | 0.00                | 98.71           | 77                    | CONFIAVEL     |
| Mercado Sao Jorge     | 6 117     | 0.14                  | 0.00                | 98.66           | 82                    | CONFIAVEL     |
