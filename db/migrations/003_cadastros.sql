-- =====================================================================
-- 003 - Cadastros (entidades de referencia)
--
-- Modelo conceitual:
--   LOJA 1---N VENDA 1---N ITEM_VENDA N---1 PRODUTO
--   PRODUTO N---1 CATEGORIA (hierarquica)
--   PRODUTO N---N FORNECEDOR  (via PRODUTO_FORNECEDOR)
--   LOJA/PRODUTO 1---N ESTOQUE_SNAPSHOT
--   LOJA 1---N PEDIDO_COMPRA N---1 FORNECEDOR
--
-- Normalizacao: 3FN. Cada atributo depende da chave, do todo e de
-- nada alem dela. Nao ha grupo repetido, nao ha dependencia parcial
-- (a PK e atomica) nem transitiva (cidade nao fica em LOJA, fica em
-- um cadastro de municipio se necessario - aqui usamos text direto
-- porque o volume e baixo e nao ha atualizacao).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Loja
-- ---------------------------------------------------------------------
CREATE TABLE prata.loja (
    loja_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo          TEXT        NOT NULL,          -- codigo no PDV (ex.: 'LJ01')
    nome            TEXT        NOT NULL,
    cnpj            TEXT,                          -- 14 digitos, sem mascara
    cidade          TEXT        NOT NULL,
    uf              gov.uf      NOT NULL,
    area_m2         NUMERIC(8,2),
    data_abertura   DATE        NOT NULL,
    data_fechamento DATE,
    ativa           BOOLEAN     NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT loja_codigo_uk      UNIQUE (codigo),
    CONSTRAINT loja_cnpj_uk        UNIQUE (cnpj),
    CONSTRAINT loja_cnpj_ck        CHECK (cnpj IS NULL OR cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT loja_datas_ck       CHECK (data_fechamento IS NULL OR data_fechamento >= data_abertura),
    CONSTRAINT loja_area_ck        CHECK (area_m2 IS NULL OR area_m2 > 0)
);

COMMENT ON TABLE  prata.loja IS 'Unidade fisica do mercado. Multi-loja desde o inicio.';
COMMENT ON COLUMN prata.loja.codigo IS 'Chave natural: codigo da loja no PDV.';
COMMENT ON COLUMN prata.loja.cnpj IS 'CNPJ sem mascara. Unico quando informado.';

-- ---------------------------------------------------------------------
-- Categoria (hierarquia auto-referenciada: departamento > classe > subclasse)
--
-- Por que auto-referencia em vez de tres tabelas?
--   A profundidade e fixa em 3 hoje, mas auto-referencia permite 4+
--   sem migracao. A view ouro.dim_produto achata a hierarquia, entao
--   o custo de consulta fica no ETL, nao no analista.
-- ---------------------------------------------------------------------
CREATE TABLE prata.categoria (
    categoria_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    categoria_pai_id BIGINT REFERENCES prata.categoria(categoria_id) ON DELETE RESTRICT,
    codigo        TEXT    NOT NULL,
    nome          TEXT    NOT NULL,
    nivel         SMALLINT NOT NULL,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT categoria_codigo_uk UNIQUE (codigo),
    CONSTRAINT categoria_nivel_ck  CHECK (nivel BETWEEN 1 AND 4),
    CONSTRAINT categoria_nao_autopai CHECK (categoria_pai_id IS NULL OR categoria_pai_id <> categoria_id)
);

COMMENT ON TABLE prata.categoria IS
  'Hierarquia de categorias: nivel 1 = departamento, 2 = classe, 3 = subclasse.';

-- ---------------------------------------------------------------------
-- Fornecedor
-- ---------------------------------------------------------------------
CREATE TABLE prata.fornecedor (
    fornecedor_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnpj          TEXT NOT NULL,
    razao_social  TEXT NOT NULL,
    nome_fantasia TEXT,
    cidade        TEXT,
    uf            gov.uf,
    lead_time_dias_padrao SMALLINT NOT NULL DEFAULT 7,
    pedido_minimo_valor   gov.dinheiro NOT NULL DEFAULT 0,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fornecedor_cnpj_uk UNIQUE (cnpj),
    CONSTRAINT fornecedor_cnpj_ck CHECK (cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT fornecedor_lead_ck CHECK (lead_time_dias_padrao BETWEEN 0 AND 180)
);

COMMENT ON TABLE prata.fornecedor IS 'Fornecedor/distribuidor. lead_time alimenta a sugestao de compra.';

-- ---------------------------------------------------------------------
-- Produto (SKU)
--
-- Sobre 'ativo': soft delete. Produto nunca e deletado porque
-- historico de venda precisa continuar integro. Desativar preserva
-- a FK e a serie temporal.
-- ---------------------------------------------------------------------
CREATE TABLE prata.produto (
    produto_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ean             gov.ean13 NOT NULL,
    sku_interno     TEXT NOT NULL,
    nome            TEXT NOT NULL,
    categoria_id    BIGINT NOT NULL REFERENCES prata.categoria(categoria_id) ON DELETE RESTRICT,
    unidade_medida  TEXT NOT NULL,
    e_perecivel     BOOLEAN NOT NULL DEFAULT FALSE,
    dias_validade   SMALLINT,
    peso_liquido_kg NUMERIC(10,4),
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT produto_ean_uk        UNIQUE (ean),
    CONSTRAINT produto_sku_uk        UNIQUE (sku_interno),
    CONSTRAINT produto_unidade_ck    CHECK (unidade_medida IN ('UN','KG','L','ML','CX','DZ','PCT')),
    -- Perecivel precisa de validade, e nao-perecivel nao deve ter
    CONSTRAINT produto_validade_ck   CHECK (
        (e_perecivel = TRUE  AND dias_validade IS NOT NULL AND dias_validade > 0) OR
        (e_perecivel = FALSE AND dias_validade IS NULL)
    ),
    CONSTRAINT produto_peso_ck       CHECK (peso_liquido_kg IS NULL OR peso_liquido_kg > 0)
);

COMMENT ON TABLE  prata.produto IS 'Cadastro de SKU. Soft delete via ativo para preservar historico.';
COMMENT ON COLUMN prata.produto.ean IS 'Chave natural de negocio. Validada pelo digito verificador.';
COMMENT ON COLUMN prata.produto.unidade_medida IS 'UN, KG, L, ML, CX, DZ ou PCT. Nao ha conversao automatica.';
COMMENT ON COLUMN prata.produto.e_perecivel IS 'Se TRUE, dias_validade e obrigatorio e a curva de risco de vencimento se aplica.';

-- ---------------------------------------------------------------------
-- Produto x Fornecedor (N:N)
--
-- Um SKU pode ter mais de um fornecedor. Guardamos custo e prazo por
-- combinacao, porque o mesmo produto custa diferente em cada um.
-- 'preferencial' evita ambiguidade na sugestao de compra.
-- ---------------------------------------------------------------------
CREATE TABLE prata.produto_fornecedor (
    produto_id             BIGINT NOT NULL REFERENCES prata.produto(produto_id) ON DELETE CASCADE,
    fornecedor_id          BIGINT NOT NULL REFERENCES prata.fornecedor(fornecedor_id) ON DELETE CASCADE,
    custo_unitario         gov.dinheiro NOT NULL,
    lead_time_dias         SMALLINT NOT NULL,
    lote_minimo            gov.quantidade_positiva NOT NULL DEFAULT 1,
    multiplo_compra        gov.quantidade_positiva NOT NULL DEFAULT 1,
    preferencial           BOOLEAN NOT NULL DEFAULT FALSE,
    atualizado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (produto_id, fornecedor_id),
    CONSTRAINT produto_fornecedor_lead_ck CHECK (lead_time_dias BETWEEN 0 AND 180)
);

-- Regra: no maximo um fornecedor preferencial por produto.
-- Implementada com indice parcial unico, nao com trigger.
CREATE UNIQUE INDEX produto_fornecedor_um_preferencial
    ON prata.produto_fornecedor (produto_id)
    WHERE preferencial;

COMMENT ON TABLE prata.produto_fornecedor IS
  'Preco e prazo por par produto-fornecedor. Indice parcial garante 1 preferencial por SKU.';

-- ---------------------------------------------------------------------
-- Historico de preco e custo (SCD tipo 2 simplificado)
--
-- Por que nao guardar preco apenas em PRODUTO?
--   Porque a margem de janeiro calculada com o preco de novembro e
--   uma mentira. O relatorio precisa do preco vigente NA DATA DA VENDA.
--   Esta tabela e a fonte da verdade temporal de preco.
--
-- Vigencia por intervalo fechado no inicio e aberto no fim:
--   [data_inicio, data_fim). Assim nao ha sobreposicao nem buraco.
-- ---------------------------------------------------------------------
CREATE TABLE prata.produto_preco_historico (
    produto_id    BIGINT NOT NULL REFERENCES prata.produto(produto_id) ON DELETE CASCADE,
    data_inicio   DATE   NOT NULL,
    data_fim      DATE,                                  -- NULL = vigente
    preco_custo   gov.dinheiro NOT NULL,
    preco_venda   gov.dinheiro NOT NULL,
    margem_pct    NUMERIC(7,4) GENERATED ALWAYS AS (
        CASE WHEN preco_venda > 0
             THEN round((preco_venda - preco_custo) / preco_venda * 100, 4)
             ELSE 0 END
    ) STORED,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (produto_id, data_inicio),
    CONSTRAINT preco_vigencia_ck CHECK (data_fim IS NULL OR data_fim > data_inicio),
    CONSTRAINT preco_venda_positivo_ck CHECK (preco_venda > 0)
);

COMMENT ON TABLE prata.produto_preco_historico IS
  'Vigencia de preco de custo e venda. [data_inicio, data_fim). alimenta margem historica.';

-- Impede duas faixas abertas para o mesmo produto.
CREATE UNIQUE INDEX produto_preco_uma_faixa_aberta
    ON prata.produto_preco_historico (produto_id)
    WHERE data_fim IS NULL;

-- Impede sobreposicao de faixas do mesmo produto.
-- EXCLUDE precisa de btree_gist para misturar igualdade (=) e range (&&).
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE prata.produto_preco_historico
    ADD CONSTRAINT produto_preco_sem_sobreposicao
    EXCLUDE USING gist (
        produto_id WITH =,
        daterange(data_inicio, COALESCE(data_fim, 'infinity'::date), '[)') WITH &&
    );

-- ---------------------------------------------------------------------
-- Calendario
--
-- Por que uma tabela de calendario e nao funcoes de data na consulta?
--   1. Feriado municipal nao existe em funcao nativa.
--   2. Dia de pagamento (5o dia util) afeta o fluxo de caixa do
--      mercadinho e explica picos de venda.
--   3. Materializar evita repetir CASE por dia em toda consulta.
-- ---------------------------------------------------------------------
CREATE TABLE prata.calendario (
    data              DATE PRIMARY KEY,
    ano               SMALLINT NOT NULL,
    mes               SMALLINT NOT NULL,
    dia               SMALLINT NOT NULL,
    dia_semana        SMALLINT NOT NULL,   -- 0=domingo .. 6=sabado (ISO: 1=segunda)
    nome_dia_semana   TEXT NOT NULL,
    semana_iso        SMALLINT NOT NULL,
    is_fim_semana     BOOLEAN NOT NULL,
    is_feriado        BOOLEAN NOT NULL DEFAULT FALSE,
    nome_feriado      TEXT,
    is_pagamento      BOOLEAN NOT NULL DEFAULT FALSE,
    is_feriado_nacional BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT calendario_ano_ck  CHECK (ano BETWEEN 2000 AND 2100),
    CONSTRAINT calendario_mes_ck  CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT calendario_dia_ck  CHECK (dia BETWEEN 1 AND 31),
    -- ISO 8601: 1=segunda ... 7=domingo. Usamos ISO e nao 0-6 porque
    -- o PostgreSQL ja trabalha com extract(dow) e extract(isodow) no
    -- padrao ISO, e misturar as duas convencoes e fonte classica de
    -- erro de um dia na serie temporal.
    CONSTRAINT calendario_ds_ck   CHECK (dia_semana BETWEEN 1 AND 7),
    CONSTRAINT calendario_feriado_ck CHECK (is_feriado = FALSE OR nome_feriado IS NOT NULL)
);

COMMENT ON TABLE prata.calendario IS
  'Calendario com feriados e dias de pagamento. Dimensao de tempo materializada.';

-- ---------------------------------------------------------------------
-- Promocao
-- ---------------------------------------------------------------------
CREATE TABLE prata.promocao (
    promocao_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo            TEXT NOT NULL,
    descricao         TEXT NOT NULL,
    tipo              TEXT NOT NULL,
    data_inicio       DATE NOT NULL,
    data_fim          DATE NOT NULL,
    percentual_desconto gov.percentual,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT promocao_codigo_uk UNIQUE (codigo),
    CONSTRAINT promocao_tipo_ck CHECK (tipo IN ('DESCONTO','LEVE_PAGUE','COMBO','CUPOM','FIDELIDADE')),
    CONSTRAINT promocao_datas_ck CHECK (data_fim >= data_inicio),
    CONSTRAINT promocao_desconto_ck CHECK (
        tipo <> 'DESCONTO' OR percentual_desconto IS NOT NULL
    )
);

COMMENT ON TABLE prata.promocao IS 'Campanha promocional com janela de vigencia.';

-- Quais produtos participam de qual promocao e com qual preco.
CREATE TABLE prata.promocao_produto (
    promocao_id    BIGINT NOT NULL REFERENCES prata.promocao(promocao_id) ON DELETE CASCADE,
    produto_id     BIGINT NOT NULL REFERENCES prata.produto(produto_id) ON DELETE CASCADE,
    preco_promocional gov.dinheiro,

    PRIMARY KEY (promocao_id, produto_id)
);

COMMIT;
