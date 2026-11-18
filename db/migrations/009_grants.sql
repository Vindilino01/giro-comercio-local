-- =====================================================================
-- 009 - Concessao de privilegios (depois que os objetos existem)
--
-- POR QUE ESTE ARQUIVO EXISTE SEPARADO DO 008
-- -------------------------------------------
-- A versao anterior concedia `GRANT SELECT ON ALL TABLES IN SCHEMA ouro`
-- dentro do 008, que roda ANTES das migrations 010 e 011. No PostgreSQL,
-- `ALL TABLES` e um retrato do momento: quando o 010/011 criavam as
-- tabelas e views materializadas, elas nasciam SEM privilegio. Medido
-- com has_table_privilege: giro_bi em ouro.fato_vendas = false.
--
-- A correcao tem duas partes:
--   1. rodar a concessao DEPOIS de todos os objetos existirem (este
--      arquivo, ultimo do build);
--   2. ALTER DEFAULT PRIVILEGES, para objetos criados no futuro
--      (particoes mensais novas, por exemplo) ja nascerem legiveis.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- giro_app: ETL e aplicacao
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA prata, ouro, gov TO giro_app;

GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA prata TO giro_app;
GRANT SELECT ON ALL TABLES IN SCHEMA ouro  TO giro_app;
GRANT SELECT, INSERT ON gov.lote_carga, gov.quarentena,
      gov.metrica_qualidade TO giro_app;
GRANT UPDATE (resolvido, resolvido_em, resolvido_por) ON gov.quarentena
      TO giro_app;
GRANT UPDATE (ativo, atualizado_em) ON prata.produto TO giro_app;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA prata TO giro_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gov   TO giro_app;

-- ---------------------------------------------------------------------
-- giro_bi: leitura para dashboard e analise
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA prata, ouro, gov TO giro_bi;

GRANT SELECT ON ALL TABLES IN SCHEMA prata TO giro_bi;
GRANT SELECT ON ALL TABLES IN SCHEMA ouro  TO giro_bi;
GRANT SELECT ON ALL TABLES IN SCHEMA gov   TO giro_bi;

-- ---------------------------------------------------------------------
-- giro_admin: manutencao
-- ---------------------------------------------------------------------
GRANT USAGE, CREATE ON SCHEMA prata, ouro, gov, bronze TO giro_admin;
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA prata, ouro, gov TO giro_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA prata, ouro, gov TO giro_admin;

-- ---------------------------------------------------------------------
-- Objetos futuros ja nascem com privilegio.
--
-- Sem isto, cada particao mensal criada por gov.criar_particoes_mensais
-- ficaria inacessivel ao giro_bi ate a proxima execucao deste script.
-- ---------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES IN SCHEMA prata
    GRANT SELECT, INSERT ON TABLES TO giro_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA prata
    GRANT SELECT ON TABLES TO giro_bi;
ALTER DEFAULT PRIVILEGES IN SCHEMA prata
    GRANT ALL ON TABLES TO giro_admin;

ALTER DEFAULT PRIVILEGES IN SCHEMA ouro
    GRANT SELECT ON TABLES TO giro_app, giro_bi;
ALTER DEFAULT PRIVILEGES IN SCHEMA ouro
    GRANT ALL ON TABLES TO giro_admin;

ALTER DEFAULT PRIVILEGES IN SCHEMA gov
    GRANT SELECT ON TABLES TO giro_app, giro_bi;
ALTER DEFAULT PRIVILEGES IN SCHEMA gov
    GRANT ALL ON TABLES TO giro_admin;

COMMIT;
