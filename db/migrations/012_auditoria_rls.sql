-- =====================================================================
-- 012 - Auditoria ativa e RLS em item_venda
--
-- DOIS ACHADOS DE AUDITORIA CORRIGIDOS AQUI
-- -----------------------------------------
-- 1. gov.auditoria existia com 0 linhas e nenhum trigger. O relatorio
--    afirmava "registra quem alterou o que, quando, com os valores
--    antes e depois" e citava LGPD art. 37. Era promessa sem
--    implementacao.
--
-- 2. prata.item_venda nao tinha RLS. Medido: SET ROLE giro_bi com
--    app.loja_id='1' lia 4.159.608 linhas (todas as lojas) enquanto
--    prata.venda corretamente devolvia 154.339. O isolamento por loja
--    vazava justamente o dado transacional - quantidade, preco, valor.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Auditoria
--
-- Escopo deliberado: as tabelas onde a alteracao muda decisao de
-- negocio e precisa de rastro - produto (soft delete, nome) e o
-- historico de preco. Auditar venda e item_venda seria caro (milhoes
-- de INSERTs por carga) e nao agrega: venda e imutavel por natureza.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION gov.registrar_auditoria()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = gov, prata, public
AS $$
DECLARE
    v_chave TEXT;
BEGIN
    -- Chave legivel do registro afetado, conforme a tabela.
    IF TG_TABLE_NAME = 'produto' THEN
        v_chave := coalesce((to_jsonb(NEW)->>'produto_id'),
                            (to_jsonb(OLD)->>'produto_id'));
    ELSIF TG_TABLE_NAME = 'produto_preco_historico' THEN
        v_chave := coalesce(to_jsonb(NEW)->>'produto_id',
                            to_jsonb(OLD)->>'produto_id')
                   || '@' || coalesce(to_jsonb(NEW)->>'data_inicio',
                                      to_jsonb(OLD)->>'data_inicio');
    ELSE
        v_chave := coalesce(to_jsonb(NEW)->>'id', to_jsonb(OLD)->>'id');
    END IF;

    INSERT INTO gov.auditoria
        (usuario, acao, entidade, chave, dados_antes, dados_depois)
    VALUES (
        current_user,
        TG_OP,
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
        v_chave,
        CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN to_jsonb(NEW) END
    );

    RETURN coalesce(NEW, OLD);
END;
$$;

COMMENT ON FUNCTION gov.registrar_auditoria() IS
  'Trigger de auditoria: grava antes/depois em gov.auditoria. '
  'SECURITY DEFINER para funcionar com o papel de aplicacao.';

DROP TRIGGER IF EXISTS audit_produto ON prata.produto;
CREATE TRIGGER audit_produto
    AFTER INSERT OR UPDATE OR DELETE ON prata.produto
    FOR EACH ROW EXECUTE FUNCTION gov.registrar_auditoria();

DROP TRIGGER IF EXISTS audit_preco ON prata.produto_preco_historico;
CREATE TRIGGER audit_preco
    AFTER INSERT OR UPDATE OR DELETE ON prata.produto_preco_historico
    FOR EACH ROW EXECUTE FUNCTION gov.registrar_auditoria();

-- ---------------------------------------------------------------------
-- 2. RLS em item_venda
--
-- O item nao guarda loja_id (a PK e venda_id + data_venda + item_seq, e
-- o particionamento e por data). A policy resolve por existencia: o
-- item so e visivel se a venda a que pertence for da loja da sessao.
--
-- Indice de apoio: a subconsulta roda por linha; sem indice em
-- (venda_id, data_venda) o custo seria proibitivo. A PK de venda ja
-- cobre esse par.
-- ---------------------------------------------------------------------
ALTER TABLE prata.item_venda ENABLE ROW LEVEL SECURITY;
ALTER TABLE prata.item_venda FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS item_por_loja ON prata.item_venda;
CREATE POLICY item_por_loja ON prata.item_venda
    USING (EXISTS (
        SELECT 1 FROM prata.venda v
         WHERE v.venda_id = item_venda.venda_id
           AND v.data_venda = item_venda.data_venda
           AND v.loja_id = gov.loja_da_sessao()
    ));

DROP POLICY IF EXISTS item_admin ON prata.item_venda;
CREATE POLICY item_admin ON prata.item_venda
    TO giro_admin USING (true);

COMMIT;
