-- =====================================================================
-- 005 - Gestao de particoes mensais
--
-- Estrategia: particao RANGE por mes em data_venda.
--
-- Por que RANGE por mes e nao HASH por loja?
--   A consulta dominante do Giro e "vendas de tal produto entre duas
--   datas". Range por data permite partition pruning: o planejador
--   abre 1 ou 2 particoes em vez de varrer todas. Hash por loja so
--   ajudaria consultas de uma loja, mas o relatorio multi-loja
--   continuaria varrendo tudo.
--
-- Por que nao particao por ano?
--   O mercado consulta janelas curtas (ultimos 30/90 dias). Com
--   particao anual, uma consulta de 30 dias varre 12 meses. Mensal
--   da granularidade certa para a decisao de compra semanal.
--
-- Custo: particao mensal gera ~36 particoes em 3 anos. Isso e
-- confortavel; acima de ~1000 particoes o catalogo do planejador
-- passa a pesar. Se o Giro crescer para 100 lojas mantendo 3 anos
-- de historico, ainda sao apenas 36 particoes por tabela (o
-- particionamento e por tempo, nao por loja), o que escala bem.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Funcao que cria as particoes de um intervalo de meses.
--
-- Idempotente: usa IF NOT EXISTS. Pode rodar todo dia sem medo.
-- E chamada pelo ETL (src/ingest.py) antes de cada carga, garantindo
-- que sempre existe particao para o mes que vai receber dado.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION gov.criar_particoes_mensais(
    p_data_inicio DATE,
    p_data_fim    DATE
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_inicio   DATE := date_trunc('month', p_data_inicio)::date;
    v_fim      DATE := date_trunc('month', p_data_fim)::date;
    v_prox     DATE;
    v_nome     TEXT;
    v_criadas  INTEGER := 0;
    v_sql      TEXT;
BEGIN
    IF p_data_fim < p_data_inicio THEN
        RAISE EXCEPTION 'data_fim (%) anterior a data_inicio (%)', p_data_fim, p_data_inicio;
    END IF;

    WHILE v_inicio <= v_fim LOOP
        v_prox := (v_inicio + INTERVAL '1 month')::date;
        v_nome := 'venda_' || to_char(v_inicio, 'YYYY_MM');

        v_sql := format(
            'CREATE TABLE IF NOT EXISTS prata.%I
             PARTITION OF prata.venda
             FOR VALUES FROM (%L) TO (%L)',
            v_nome, v_inicio, v_prox
        );
        EXECUTE v_sql;

        v_nome := 'item_venda_' || to_char(v_inicio, 'YYYY_MM');
        v_sql := format(
            'CREATE TABLE IF NOT EXISTS prata.%I
             PARTITION OF prata.item_venda
             FOR VALUES FROM (%L) TO (%L)',
            v_nome, v_inicio, v_prox
        );
        EXECUTE v_sql;

        v_criadas := v_criadas + 1;
        v_inicio  := v_prox;
    END LOOP;

    RETURN v_criadas;
END;
$$;

COMMENT ON FUNCTION gov.criar_particoes_mensais(DATE, DATE) IS
  'Cria particoes mensais de venda/item_venda no intervalo. Idempotente.';

-- ---------------------------------------------------------------------
-- Funcao de manutencao: garante particoes para o passado recente e
-- para os proximos meses. Rodada pelo ETL e por cron.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION gov.garantir_particoes(p_meses_futuros INT DEFAULT 3)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_hoje DATE := CURRENT_DATE;
BEGIN
    RETURN gov.criar_particoes_mensais(
        (v_hoje - INTERVAL '24 months')::date,
        (v_hoje + (p_meses_futuros || ' months')::interval)::date
    );
END;
$$;

COMMENT ON FUNCTION gov.garantir_particoes(INT) IS
  'Garante particoes de 24 meses atras ate N meses a frente. Chamar a cada carga.';

-- ---------------------------------------------------------------------
-- Detach de particao antiga (retencao).
--
-- Nao vamos DELETAR dado historico no MVP; apenas documentamos o
-- procedimento. A politica de retencao esta em docs/05-qualidade.md.
-- A particao vira tabela autonoma e pode ser arquivada em Parquet
-- (cenario 100x descrito na secao 4.7 do relatorio).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION gov.destacar_particao(p_mes DATE)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_nome TEXT;
BEGIN
    v_nome := 'prata.venda_' || to_char(p_mes, 'YYYY_MM');
    EXECUTE format('ALTER TABLE prata.venda DETACH PARTITION %s', v_nome);
    RETURN v_nome;
END;
$$;

COMMENT ON FUNCTION gov.destacar_particao(DATE) IS
  'Destaca a particao do mes para arquivamento. Nao deleta dados.';

COMMIT;
