# Q07 — Sazonalidade

**Pergunta de negocio:** Quando eu vendo mais?

**Linhas retornadas:** 7  
**Tempo de execucao:** 760.1 ms

## Consulta

```sql
-- =====================================================================
-- Q07 - SAZONALIDADE: DIA DA SEMANA x HORA
--
-- PERGUNTA DE NEGOCIO
--   "Quando eu vendo mais, e como escalo a equipe?"
--
-- POR QUE IMPORTA
--   1. Previsao: o fator dia-da-semana e um dos componentes do modelo.
--      Mostra-lo valida o modelo diante do professor e do dono.
--   2. Operacao: o pico de sabado entre 9h e 12h define quantos
--      operadores de caixa precisam estar na loja. E uma decisao que o
--      dono toma hoje por intuicao.
--   3. Reposicao: saber que sexta vende 1,24x a media justifica
--      abastecer a gondola na quinta a noite.
--
-- KPI: fator de dia da semana e indice de concentracao horaria.
-- =====================================================================

WITH vendas_dia AS (
    SELECT
        t.dia_semana_iso,
        t.nome_dia_semana,
        f.data_venda,
        sum(f.valor_liquido) FILTER (WHERE f.venda_id IS NOT NULL) AS receita
      FROM ouro.fato_vendas f
      JOIN ouro.dim_tempo t ON t.data = f.data_venda
     GROUP BY t.dia_semana_iso, t.nome_dia_semana, f.data_venda
),
media_dia AS (
    SELECT
        dia_semana_iso,
        nome_dia_semana,
        count(*)          AS dias_observados,
        avg(receita)      AS receita_media
      FROM vendas_dia
     GROUP BY dia_semana_iso, nome_dia_semana
),
geral AS (
    SELECT avg(receita_media) AS media_geral FROM media_dia
)
SELECT
    m.dia_semana_iso,
    m.nome_dia_semana,
    round(m.receita_media, 2)                    AS receita_media,
    round(m.receita_media / g.media_geral, 3)    AS fator_dia_semana,
    CASE
        WHEN m.receita_media / g.media_geral >= 1.15 THEN 'PICO'
        WHEN m.receita_media / g.media_geral >= 0.95 THEN 'NORMAL'
        ELSE 'VALE'
    END AS classificacao,
    m.dias_observados
  FROM media_dia m, geral g
 ORDER BY m.dia_semana_iso;
```

## Resultado

| dia_semana_iso | nome_dia_semana | receita_media | fator_dia_semana | classificacao | dias_observados |
|----------------|-----------------|---------------|------------------|---------------|-----------------|
| 1              | Segunda-feira   | 70 420.15     | 0.88             | VALE          | 104             |
| 2              | Terca-feira     | 72 489.23     | 0.90             | VALE          | 104             |
| 3              | Quarta-feira    | 75 933.20     | 0.95             | VALE          | 105             |
| 4              | Quinta-feira    | 82 928.25     | 1.03             | NORMAL        | 105             |
| 5              | Sexta-feira     | 101 238.75    | 1.26             | PICO          | 105             |
| 6              | Sabado          | 95 349.49     | 1.19             | PICO          | 104             |
| 7              | Domingo         | 63 270.17     | 0.79             | VALE          | 104             |
