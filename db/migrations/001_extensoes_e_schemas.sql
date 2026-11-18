-- =====================================================================
-- GIRO - Previsao de estoque e vendas para pequenos mercados
-- A3 - Analise de Dados e Big Data
--
-- 001 - Extensoes, schemas e convencoes
--
-- Arquitetura: persistencia poliglota apenas quando justificada.
--   bronze  = dado bruto imutavel (tabelas de texto, sem constraint)
--   prata   = OLTP normalizado em 3FN (fonte de verdade transacional)
--   ouro    = star schema / marts analiticos
--   gov     = governanca: qualidade, auditoria, linhagem
--   quarentena = registros rejeitados com reason_code
-- =====================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS prata;
CREATE SCHEMA IF NOT EXISTS ouro;
CREATE SCHEMA IF NOT EXISTS gov;

COMMENT ON SCHEMA bronze IS
  'Camada bronze: dado bruto como recebido do PDV/planilha/XML. Imutavel, sem transformacao.';
COMMENT ON SCHEMA prata IS
  'Camada prata: modelo OLTP normalizado em 3FN. Fonte de verdade transacional.';
COMMENT ON SCHEMA ouro IS
  'Camada ouro: star schema e marts analiticos derivados da prata.';
COMMENT ON SCHEMA gov IS
  'Governanca: quarentena, auditoria de carga, linhagem e metricas de qualidade.';

-- Extensoes
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- evidencia de consultas caras
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- busca fuzzy em nome de produto

-- ---------------------------------------------------------------------
-- Convencoes
-- ---------------------------------------------------------------------
-- 1. PK surrogate: BIGINT GENERATED ALWAYS AS IDENTITY
-- 2. Toda tabela transacional tem chave natural UNIQUE alem da surrogate,
--    para permitir deduplicacao idempotente.
-- 3. Dinheiro em NUMERIC(14,2). Nunca FLOAT (erro de arredondamento).
-- 4. Quantidade em NUMERIC(14,3) porque kg/litro fraciona.
-- 5. Timestamps com timezone (TIMESTAMPTZ). O Brasil tem 4 fusos.
-- 6. Nomes de coluna em portugues sem acento, para evitar problema de
--    encoding em qualquer ferramenta de exportacao.
-- 7. Toda FK declarada com ON DELETE/UPDATE explicito.
-- 8. Dominio de enum declarado como CHECK (nao como ENUM type) para
--    permitir ALTER sem lock de catalogo.

COMMIT;
