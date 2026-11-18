-- =====================================================================
-- GIRO - Script de build do banco
--
-- Executa todas as migrations em ordem e garante as particoes.
-- Chamado por run_all.py e por scripts/build_db.ps1.
--
-- Idempotente no sentido de "pode rodar a partir de um banco vazio".
-- Para recriar do zero, use run_all.py --reset.
-- =====================================================================

\set ON_ERROR_STOP on
\set QUIET on

\echo '  [1/8] extensoes e schemas'
\i db/migrations/001_extensoes_e_schemas.sql

\echo '  [2/8] dominios e funcoes de validacao'
\i db/migrations/002_dominios.sql

\echo '  [3/8] cadastros'
\i db/migrations/003_cadastros.sql

\echo '  [4/8] movimentos transacionais'
\i db/migrations/004_movimentos.sql

\echo '  [5/8] gestao de particoes'
\i db/migrations/005_particoes.sql

\echo '  [6/8] indices'
\i db/migrations/006_indices.sql

\echo '  [7/8] governanca e qualidade'
\i db/migrations/007_governanca.sql

\echo '  [7.1] controle de acesso e RLS'
\i db/migrations/008_roles_rls.sql

\echo '  [8/8] particoes iniciais (24 meses atras ate 6 a frente)'
SELECT gov.criar_particoes_mensais(
    (CURRENT_DATE - INTERVAL '24 months')::date,
    (CURRENT_DATE + INTERVAL '6 months')::date
) AS meses_criados;

\echo '  [extra] camada ouro: star schema'
\i db/migrations/010_ouro_star.sql

\echo '  [extra] camada ouro: views materializadas'
\i db/migrations/011_ouro_views.sql

\echo '  [extra] privilegios (depois de todos os objetos existirem)'
\i db/migrations/009_grants.sql

\echo '  [extra] auditoria ativa e RLS em item_venda'
\i db/migrations/012_auditoria_rls.sql

\echo ''
\echo 'Build concluido.'
