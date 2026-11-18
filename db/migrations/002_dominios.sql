-- =====================================================================
-- 002 - Dominios e funcoes de validacao reutilizaveis
--
-- Decisao de projeto: usamos DOMAIN em vez de CHECK repetido em cada
-- tabela. Vantagens:
--   - a regra existe uma vez so (single source of truth);
--   - alterar a regra e um ALTER DOMAIN, sem tocar em 20 tabelas;
--   - o dicionario de dados pode listar os dominios como referencia.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Validacao de EAN-13 pelo digito verificador (modulo 10).
-- EAN invalido e uma das principais causas de produto duplicado em
-- mercadinho: o operador digita errado e nasce um SKU fantasma.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION gov.ean13_valido(p_ean TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    v_digitos TEXT;
    v_soma    INT := 0;
    v_digito  INT;
    v_dv      INT;
    i         INT;
BEGIN
    -- Aceita apenas 13 digitos. EAN-8 e UPC-A sao normalizados para EAN-13
    -- na camada de ingestao, portanto aqui so entra o formato final.
    IF p_ean !~ '^[0-9]{13}$' THEN
        RETURN FALSE;
    END IF;

    v_digitos := substring(p_ean FROM 1 FOR 12);
    v_dv      := substring(p_ean FROM 13 FOR 1)::INT;

    FOR i IN 1..12 LOOP
        -- Posicoes impares peso 1, pares peso 3 (da esquerda para a direita)
        IF i % 2 = 1 THEN
            v_soma := v_soma + substring(v_digitos FROM i FOR 1)::INT;
        ELSE
            v_soma := v_soma + 3 * substring(v_digitos FROM i FOR 1)::INT;
        END IF;
    END LOOP;

    v_digito := (10 - (v_soma % 10)) % 10;
    RETURN v_digito = v_dv;
END;
$$;

COMMENT ON FUNCTION gov.ean13_valido(TEXT) IS
  'Valida EAN-13 pelo digito verificador (modulo 10). Usada no DOMAIN ean13.';

-- ---------------------------------------------------------------------
-- Dominios de negocio
-- ---------------------------------------------------------------------

-- EAN-13 com digito verificador conferido.
CREATE DOMAIN gov.ean13 AS TEXT
    CHECK (gov.ean13_valido(VALUE));

COMMENT ON DOMAIN gov.ean13 IS
  'Codigo de barras EAN-13 valido (13 digitos + digito verificador correto).';

-- Quantidade: aceita fracao (kg, litro) mas nao aceita negativo.
-- Zero e permitido em estoque_snapshot (produto em ruptura).
CREATE DOMAIN gov.quantidade AS NUMERIC(14,3)
    CHECK (VALUE >= 0);

COMMENT ON DOMAIN gov.quantidade IS
  'Quantidade nao negativa em NUMERIC(14,3). Permite kg/litro fracionado.';

-- Quantidade estritamente positiva: usada em item de venda e de compra.
CREATE DOMAIN gov.quantidade_positiva AS NUMERIC(14,3)
    CHECK (VALUE > 0);

COMMENT ON DOMAIN gov.quantidade_positiva IS
  'Quantidade maior que zero. Usada em itens de venda/compra.';

-- Valor monetario: nao negativo, 2 casas.
CREATE DOMAIN gov.dinheiro AS NUMERIC(14,2)
    CHECK (VALUE >= 0);

COMMENT ON DOMAIN gov.dinheiro IS
  'Valor monetario em BRL, 2 casas decimais, nao negativo.';

-- Percentual 0..100 (desconto, margem, imposto).
CREATE DOMAIN gov.percentual AS NUMERIC(7,4)
    CHECK (VALUE >= 0 AND VALUE <= 100);

COMMENT ON DOMAIN gov.percentual IS
  'Percentual entre 0 e 100 com 4 casas.';

-- ---------------------------------------------------------------------
-- UF: lista fechada das 27 unidades federativas.
--
-- Por que nao usar CHECK (uf ~ '^[A-Z]{2}$')?
--   Porque 'XX', 'ZZ' e 'AB' casam com o regex e nao existem. Um teste
--   de constraint provou isso: a versao por regex aceitava UF invalida.
--   Lista fechada e a unica forma de garantir o dominio de verdade.
-- ---------------------------------------------------------------------
CREATE DOMAIN gov.uf AS CHAR(2)
    CHECK (VALUE IN (
        'AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT',
        'PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO'
    ));

COMMENT ON DOMAIN gov.uf IS
  'Sigla de unidade federativa. Lista fechada das 27 UFs brasileiras.';

COMMIT;
