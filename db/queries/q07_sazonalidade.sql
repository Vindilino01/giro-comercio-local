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
