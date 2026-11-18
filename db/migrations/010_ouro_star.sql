-- =====================================================================
-- 010 - Camada ouro: star schema
--
-- POR QUE UM STAR SCHEMA SE O DADO JA ESTA EM 3FN NA PRATA?
--
-- 3FN e a forma certa de GUARDAR (evita anomalia de atualizacao: mudar
-- o nome de uma categoria nao exige varrer 4 milhoes de linhas).
-- Star schema e a forma certa de CONSULTAR agregados: menos joins,
-- varredura mais previsivel, e o analista de negocio nao precisa
-- conhecer 14 tabelas normalizadas.
--
-- Nao e duplicacao gratuita: e a mesma informacao organizada para dois
-- padroes de acesso diferentes. A prata e a fonte de verdade; o ouro e
-- derivado e pode ser reconstruido a qualquer momento.
--
-- DESNORMALIZACAO DELIBERADA NAS DIMENSOES
-- ----------------------------------------
-- dim_produto achata departamento > classe > subclasse numa linha so,
-- e resolve o preco vigente. Isso viola 3FN de proposito: e o preco de
-- uma leitura sem join. Como o volume de produto e baixo (~420 linhas)
-- e o de fatos e alto (4,1M), o trade-off vale.
-- =====================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ouro;

-- ---------------------------------------------------------------------
-- Dimensao tempo
-- ---------------------------------------------------------------------
CREATE TABLE ouro.dim_tempo (
    data             DATE PRIMARY KEY,
    ano              SMALLINT NOT NULL,
    trimestre        SMALLINT NOT NULL,
    mes              SMALLINT NOT NULL,
    nome_mes         TEXT NOT NULL,
    dia              SMALLINT NOT NULL,
    dia_semana_iso   SMALLINT NOT NULL,
    nome_dia_semana  TEXT NOT NULL,
    is_fim_semana    BOOLEAN NOT NULL,
    is_feriado       BOOLEAN NOT NULL,
    nome_feriado     TEXT,
    is_pagamento     BOOLEAN NOT NULL,
    ano_mes          TEXT NOT NULL,
    semanas_no_mes   SMALLINT NOT NULL
);

COMMENT ON TABLE ouro.dim_tempo IS
  'Dimensao de tempo derivada de prata.calendario. Desnormalizada para leitura.';

-- ---------------------------------------------------------------------
-- Dimensao loja
-- ---------------------------------------------------------------------
CREATE TABLE ouro.dim_loja (
    loja_id      BIGINT PRIMARY KEY,
    codigo       TEXT NOT NULL,
    nome         TEXT NOT NULL,
    cidade       TEXT NOT NULL,
    uf           CHAR(2) NOT NULL,
    area_m2      NUMERIC(8,2),
    porte        TEXT NOT NULL,
    data_abertura DATE NOT NULL,
    ativa        BOOLEAN NOT NULL
);

-- ---------------------------------------------------------------------
-- Dimensao produto (hierarquia achatada + SCD de preco)
--
-- `preco_vigente` e um retrato do preco atual, util para leitura rapida.
-- A analise de margem HISTORICA usa item_venda.custo_unitario, que
-- guarda o custo do momento da venda - e a unica forma correta de
-- calcular margem de um periodo passado.
-- ---------------------------------------------------------------------
CREATE TABLE ouro.dim_produto (
    produto_id       BIGINT PRIMARY KEY,
    ean              TEXT NOT NULL,
    sku_interno      TEXT NOT NULL,
    nome             TEXT NOT NULL,
    departamento     TEXT NOT NULL,
    classe           TEXT NOT NULL,
    unidade_medida   TEXT NOT NULL,
    e_perecivel      BOOLEAN NOT NULL,
    dias_validade    SMALLINT,
    preco_custo_atual NUMERIC(14,2),
    preco_venda_atual NUMERIC(14,2),
    fornecedor_principal TEXT,
    lead_time_dias   SMALLINT,
    ativo            BOOLEAN NOT NULL
);

CREATE INDEX ix_dim_produto_departamento
    ON ouro.dim_produto (departamento, classe);
CREATE INDEX ix_dim_produto_perecivel
    ON ouro.dim_produto (e_perecivel) WHERE e_perecivel;

-- ---------------------------------------------------------------------
-- Dimensao fornecedor
-- ---------------------------------------------------------------------
CREATE TABLE ouro.dim_fornecedor (
    fornecedor_id       BIGINT PRIMARY KEY,
    cnpj                TEXT NOT NULL,
    razao_social        TEXT NOT NULL,
    cidade              TEXT,
    uf                  CHAR(2),
    lead_time_padrao    SMALLINT NOT NULL
);

-- ---------------------------------------------------------------------
-- Dimensao promocao
-- ---------------------------------------------------------------------
CREATE TABLE ouro.dim_promocao (
    promocao_id     BIGINT PRIMARY KEY,
    codigo          TEXT NOT NULL,
    descricao       TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    data_inicio     DATE NOT NULL,
    data_fim        DATE NOT NULL,
    duracao_dias    INTEGER NOT NULL,
    desconto_pct    NUMERIC(7,4)
);

-- ---------------------------------------------------------------------
-- Fato vendas (grao: uma linha de cupom)
--
-- Grao declarado: 1 linha = 1 item de venda de 1 cupom.
-- Por que nao o grao de cupom? Porque a analise e por SKU (curva ABC,
-- previsao, giro). Grao de cupom exigiria agregacao posterior por
-- produto, inviabilizando a maioria das consultas de negocio.
-- ---------------------------------------------------------------------
CREATE TABLE ouro.fato_vendas (
    venda_id        BIGINT NOT NULL,
    item_seq        SMALLINT NOT NULL,
    data_venda      DATE NOT NULL REFERENCES ouro.dim_tempo(data),
    loja_id         BIGINT NOT NULL REFERENCES ouro.dim_loja(loja_id),
    produto_id      BIGINT NOT NULL REFERENCES ouro.dim_produto(produto_id),
    promocao_id     BIGINT REFERENCES ouro.dim_promocao(promocao_id),
    quantidade      NUMERIC(14,3) NOT NULL,
    valor_bruto     NUMERIC(14,2) NOT NULL,
    valor_desconto  NUMERIC(14,2) NOT NULL,
    valor_liquido   NUMERIC(14,2) NOT NULL,
    custo_total     NUMERIC(14,2),
    margem_liquida  NUMERIC(14,2),
    em_promocao     BOOLEAN NOT NULL,

    PRIMARY KEY (data_venda, venda_id, item_seq)
);

-- Indice por produto+data: cobre curva ABC, giro, previsao.
CREATE INDEX ix_fato_vendas_produto ON ouro.fato_vendas (produto_id, data_venda)
    INCLUDE (quantidade, valor_liquido);
CREATE INDEX ix_fato_vendas_loja ON ouro.fato_vendas (loja_id, data_venda);
CREATE INDEX ix_fato_vendas_promocao ON ouro.fato_vendas (promocao_id)
    WHERE em_promocao;

-- ---------------------------------------------------------------------
-- Fato estoque diario
-- ---------------------------------------------------------------------
CREATE TABLE ouro.fato_estoque_diario (
    data_ref        DATE NOT NULL REFERENCES ouro.dim_tempo(data),
    loja_id         BIGINT NOT NULL REFERENCES ouro.dim_loja(loja_id),
    produto_id      BIGINT NOT NULL REFERENCES ouro.dim_produto(produto_id),
    qtd_inicio      NUMERIC(14,3) NOT NULL,
    qtd_entradas    NUMERIC(14,3) NOT NULL,
    qtd_saidas      NUMERIC(14,3) NOT NULL,
    qtd_ajustes     NUMERIC(14,3) NOT NULL,
    qtd_fim         NUMERIC(14,3) NOT NULL,
    qtd_contada     NUMERIC(14,3),
    divergencia_inventario NUMERIC(14,3),
    divergencia_pct NUMERIC(8,3),
    houve_ruptura   BOOLEAN NOT NULL,
    horas_sem_estoque NUMERIC(4,2) NOT NULL,
    valor_estoque   NUMERIC(14,2),

    PRIMARY KEY (data_ref, loja_id, produto_id)
);

CREATE INDEX ix_fato_estoque_produto
    ON ouro.fato_estoque_diario (produto_id, data_ref);
CREATE INDEX ix_fato_estoque_ruptura
    ON ouro.fato_estoque_diario (loja_id, data_ref) WHERE houve_ruptura;

-- ---------------------------------------------------------------------
-- Fato compras
-- ---------------------------------------------------------------------
CREATE TABLE ouro.fato_compras (
    pedido_id       BIGINT NOT NULL,
    item_seq        SMALLINT NOT NULL,
    data_pedido     DATE NOT NULL REFERENCES ouro.dim_tempo(data),
    data_previsao   DATE NOT NULL,
    data_entrega    DATE,
    loja_id         BIGINT NOT NULL REFERENCES ouro.dim_loja(loja_id),
    produto_id      BIGINT NOT NULL REFERENCES ouro.dim_produto(produto_id),
    fornecedor_id   BIGINT NOT NULL REFERENCES ouro.dim_fornecedor(fornecedor_id),
    quantidade_pedida   NUMERIC(14,3) NOT NULL,
    quantidade_entregue NUMERIC(14,3) NOT NULL,
    valor_total     NUMERIC(14,2) NOT NULL,
    dias_atraso     INTEGER,
    entrega_completa BOOLEAN NOT NULL,
    no_prazo        BOOLEAN,

    PRIMARY KEY (pedido_id, item_seq)
);

CREATE INDEX ix_fato_compras_fornecedor
    ON ouro.fato_compras (fornecedor_id, data_pedido);

COMMIT;
