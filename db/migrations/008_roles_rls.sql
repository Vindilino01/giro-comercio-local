-- =====================================================================
-- 008 - Controle de acesso e Row-Level Security
--
-- PRINCIPIO DO MENOR PRIVILEGIO
-- -----------------------------
-- Cada papel recebe apenas o que precisa para a sua funcao. Nenhum
-- papel de aplicacao tem DELETE: excluir dado e operacao administrativa
-- e deve ser rara, auditada e deliberada.
--
-- POR QUE RLS E NAO APENAS GRANT
-- ------------------------------
-- GRANT controla QUAIS TABELAS um papel pode ler. RLS controla QUAIS
-- LINHAS. Sem RLS, um gerente da loja 1 usando a credencial do
-- dashboard veria os dados das 3 lojas. Com RLS, o mesmo usuario do
-- banco recebe apenas as linhas da loja a que esta vinculado.
--
-- A loja do usuario vem de uma configuracao de sessao
-- (app.loja_id), definida pelo backend ao abrir a conexao. Isso
-- mantem o modelo simples: nao precisamos de um usuario de banco por
-- gerente.
--
-- ATENCAO: o papel dono da tabela (postgres) IGNORA RLS por padrao,
-- a menos que FORCE ROW LEVEL SECURITY seja declarado.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Papéis
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'giro_app') THEN
        CREATE ROLE giro_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'giro_bi') THEN
        CREATE ROLE giro_bi NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'giro_admin') THEN
        CREATE ROLE giro_admin NOLOGIN;
    END IF;
END
$$;

COMMENT ON ROLE giro_app IS
  'Aplicacao e ETL. Le e insere na prata. Nao deleta, nao altera DDL.';
COMMENT ON ROLE giro_bi IS
  'Dashboard e analise. Somente leitura, com RLS por loja.';
COMMENT ON ROLE giro_admin IS
  'Administracao. Acesso total, inclusive DDL. Uso restrito e auditado.';

-- ---------------------------------------------------------------------
-- Permissoes
--
-- Os GRANT estao em 009_grants.sql, que roda DEPOIS das migrations 010
-- e 011. Conceder `ON ALL TABLES IN SCHEMA ouro` aqui nao funcionaria:
-- o schema ainda estaria vazio, e as tabelas criadas depois nasceriam
-- sem privilegio. Medido com has_table_privilege: giro_bi em
-- ouro.fato_vendas = false. Ver o cabecalho de 009.
-- ---------------------------------------------------------------------

COMMIT;

-- =====================================================================
-- Row-Level Security
--
-- O backend define app.loja_id ao abrir a conexao:
--     SET LOCAL app.loja_id = '2';
--
-- Se nao definir, current_setting devolve NULL e a policy nega tudo
-- (fail closed). Isso e proposital: esquecer de definir a loja deve
-- resultar em "sem acesso", nao em "acesso total".
-- =====================================================================

BEGIN;

-- Funcao auxiliar: le a loja da sessao, tolerando ausencia.
CREATE OR REPLACE FUNCTION gov.loja_da_sessao()
RETURNS BIGINT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v TEXT;
BEGIN
    v := current_setting('app.loja_id', TRUE);
    IF v IS NULL OR v = '' THEN
        RETURN NULL;
    END IF;
    RETURN v::BIGINT;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

COMMENT ON FUNCTION gov.loja_da_sessao() IS
  'Loja vinculada a sessao (app.loja_id). NULL se nao definida.';

-- ---------------------------------------------------------------------
-- venda
-- ---------------------------------------------------------------------
ALTER TABLE prata.venda ENABLE ROW LEVEL SECURITY;
ALTER TABLE prata.venda FORCE ROW LEVEL SECURITY;

CREATE POLICY venda_por_loja ON prata.venda
    USING (loja_id = gov.loja_da_sessao());

-- ---------------------------------------------------------------------
-- estoque_snapshot
-- ---------------------------------------------------------------------
ALTER TABLE prata.estoque_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE prata.estoque_snapshot FORCE ROW LEVEL SECURITY;

CREATE POLICY estoque_por_loja ON prata.estoque_snapshot
    USING (loja_id = gov.loja_da_sessao());

-- ---------------------------------------------------------------------
-- movimentacao_estoque
-- ---------------------------------------------------------------------
ALTER TABLE prata.movimentacao_estoque ENABLE ROW LEVEL SECURITY;
ALTER TABLE prata.movimentacao_estoque FORCE ROW LEVEL SECURITY;

CREATE POLICY movimentacao_por_loja ON prata.movimentacao_estoque
    USING (loja_id = gov.loja_da_sessao());

-- ---------------------------------------------------------------------
-- pedido_compra
-- ---------------------------------------------------------------------
ALTER TABLE prata.pedido_compra ENABLE ROW LEVEL SECURITY;
ALTER TABLE prata.pedido_compra FORCE ROW LEVEL SECURITY;

CREATE POLICY pedido_por_loja ON prata.pedido_compra
    USING (loja_id = gov.loja_da_sessao());

-- ---------------------------------------------------------------------
-- Política administrativa
--
-- As policies acima são *fail-closed*: sem `app.loja_id` na sessão, o
-- papel não vê linha nenhuma. Esse é o comportamento certo para o
-- caminho de aplicação, mas impediria `giro_admin` de operar.
--
-- A saída NÃO é afrouxar a policy de loja (era o bug da primeira
-- versão: `OR ... IS NULL` liberava tudo quando o backend esquecia o
-- SET LOCAL). É uma policy separada, restrita ao papel de
-- administração. O PostgreSQL aplica OR entre policies do mesmo
-- comando: `giro_bi` vê a própria loja; `giro_admin` vê tudo.
-- ---------------------------------------------------------------------
CREATE POLICY venda_admin ON prata.venda
    TO giro_admin USING (true);
CREATE POLICY estoque_admin ON prata.estoque_snapshot
    TO giro_admin USING (true);
CREATE POLICY movimentacao_admin ON prata.movimentacao_estoque
    TO giro_admin USING (true);
CREATE POLICY pedido_admin ON prata.pedido_compra
    TO giro_admin USING (true);

COMMIT;

-- =====================================================================
-- Nota sobre operacao
--
-- Em producao, o backend conecta como um usuario que e membro de
-- giro_bi (para o dashboard) ou giro_app (para o ETL), e executa:
--
--     SET LOCAL app.loja_id = '<id da loja do usuario logado>';
--
-- `SET LOCAL` vale apenas para a transacao, o que evita vazamento de
-- estado entre requisicoes quando se usa pool de conexoes. Usar SET
-- sem LOCAL deixaria a loja "grudada" na conexao e o proximo cliente
-- do pool herdaria o contexto - um bug classico e silencioso de
-- multi-tenancy.
-- =====================================================================
