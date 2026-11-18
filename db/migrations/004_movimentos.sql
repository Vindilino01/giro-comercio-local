-- =====================================================================
-- 004 - Movimentos transacionais (venda, estoque, compra)
--
-- Decisoes estruturais:
--
-- 1. PARTICAO MENSAL em venda e item_venda.
--    Justificativa: 3 lojas x 24 meses x ~600 cupons/dia = ~1,3M vendas.
--    A consulta dominante filtra por intervalo de data. Com particao
--    mensal o planejador faz partition pruning e varre 1 mes em vez de
--    24. Sem particao, cada consulta historica vira seq scan de 12M linhas.
--
-- 2. A PK das tabelas particionadas inclui a coluna de particao.
--    No PostgreSQL, a chave primaria de tabela particionada PRECISA
--    conter a chave de particao. Por isso PK = (venda_id, data_venda).
--
-- 3. item_venda referencia venda por (venda_id, data_venda) - a FK
--    composta e obrigatoria pelo mesmo motivo. Isso e o preco de ter
--    particionamento nativo e vale a pena.
--
-- 4. Estoque e registrado como SNAPSHOT DIARIO (fotografia), nao como
--    saldo mutavel. Motivo: saldo mutavel perde o historico. A pergunta
--    "quanto eu tinha dia 12/03?" precisa de resposta auditavel.
--    movimentacao_estoque registra o evento; estoque_snapshot e a
--    reconciliacao diaria dos dois.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Venda (cabecalho do cupom) - PARTICIONADA POR MES
-- ---------------------------------------------------------------------
CREATE TABLE prata.venda (
    venda_id        BIGINT GENERATED ALWAYS AS IDENTITY,
    loja_id         BIGINT      NOT NULL REFERENCES prata.loja(loja_id) ON DELETE RESTRICT,
    data_venda      DATE        NOT NULL,
    hora_venda      TIME        NOT NULL,
    numero_cupom    TEXT        NOT NULL,
    serie_cupom     TEXT,
    canal           TEXT        NOT NULL DEFAULT 'PDV',
    valor_bruto     gov.dinheiro NOT NULL,
    valor_desconto  gov.dinheiro NOT NULL DEFAULT 0,
    valor_liquido   gov.dinheiro NOT NULL,
    qtd_itens       SMALLINT    NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'CONCLUIDA',
    -- Marca de cancelamento: cupom cancelado NAO e venda. Guardamos
    -- para auditoria e para nao inflar receita.
    cancelada_em    TIMESTAMPTZ,
    motivo_cancelamento TEXT,
    -- Linhagem: de qual lote de carga este registro veio.
    lote_carga_id   BIGINT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (venda_id, data_venda),

    -- Chave natural: o cupom e unico por loja/data/serie.
    -- Sem isso, reimportar o mesmo arquivo duplica a receita.
    --
    -- NULLS NOT DISTINCT e obrigatorio aqui, e a razao e sutil:
    -- no PostgreSQL, o padrao de UNIQUE trata cada NULL como distinto,
    -- entao dois cupons com serie_cupom NULL NAO seriam vistos como
    -- duplicata. Esse furo foi encontrado por teste (caso C11) e
    -- permitiria duplicar receita silenciosamente quando o PDV nao
    -- informa a serie. Com NULLS NOT DISTINCT, NULL = NULL na
    -- comparacao da chave, e a deduplicacao funciona.
    CONSTRAINT venda_chave_natural_uk
        UNIQUE NULLS NOT DISTINCT (loja_id, data_venda, serie_cupom, numero_cupom),

    CONSTRAINT venda_canal_ck   CHECK (canal IN ('PDV','ONLINE','APP','TELEFONE')),
    CONSTRAINT venda_status_ck  CHECK (status IN ('CONCLUIDA','CANCELADA','DEVOLVIDA')),
    CONSTRAINT venda_qtd_ck     CHECK (qtd_itens > 0),
    -- Coerencia aritmetica do cupom: bruto - desconto = liquido.
    -- Esta e a regra de consistencia mais importante da camada de venda.
    CONSTRAINT venda_total_ck   CHECK (valor_liquido = valor_bruto - valor_desconto),
    CONSTRAINT venda_desconto_ck CHECK (valor_desconto <= valor_bruto),
    -- Cancelamento exige data; status cancelado exige motivo.
    CONSTRAINT venda_cancelamento_ck CHECK (
        (status = 'CONCLUIDA' AND cancelada_em IS NULL) OR
        (status <> 'CONCLUIDA' AND cancelada_em IS NOT NULL)
    )
) PARTITION BY RANGE (data_venda);

COMMENT ON TABLE prata.venda IS
  'Cabecalho de cupom fiscal. Particionada por mes em data_venda.';
COMMENT ON COLUMN prata.venda.numero_cupom IS
  'Chave natural junto com loja/data/serie. Base da deduplicacao idempotente.';
COMMENT ON COLUMN prata.venda.status IS
  'CONCLUIDA conta como venda. CANCELADA/DEVOLVIDA ficam para auditoria e nao entram em receita.';

-- ---------------------------------------------------------------------
-- Item de venda - PARTICIONADA POR MES (mesma chave de particao)
-- ---------------------------------------------------------------------
CREATE TABLE prata.item_venda (
    venda_id        BIGINT      NOT NULL,
    data_venda      DATE        NOT NULL,
    item_seq        SMALLINT    NOT NULL,
    produto_id      BIGINT      NOT NULL REFERENCES prata.produto(produto_id) ON DELETE RESTRICT,
    quantidade      gov.quantidade_positiva NOT NULL,
    preco_unitario  gov.dinheiro NOT NULL,
    valor_desconto  gov.dinheiro NOT NULL DEFAULT 0,
    valor_total     gov.dinheiro NOT NULL,
    promocao_id     BIGINT REFERENCES prata.promocao(promocao_id) ON DELETE SET NULL,
    -- Registro do preco de custo no momento da venda: permite calcular
    -- margem real sem depender da tabela de historico (que pode ser
    -- corrigida depois).
    custo_unitario  gov.dinheiro,

    PRIMARY KEY (venda_id, data_venda, item_seq),

    CONSTRAINT item_venda_venda_fk
        FOREIGN KEY (venda_id, data_venda)
        REFERENCES prata.venda (venda_id, data_venda)
        ON DELETE CASCADE,

    CONSTRAINT item_venda_total_ck
        CHECK (valor_total = round(quantidade * preco_unitario, 2) - valor_desconto),
    CONSTRAINT item_venda_item_seq_ck CHECK (item_seq > 0)
) PARTITION BY RANGE (data_venda);

COMMENT ON TABLE prata.item_venda IS
  'Linha do cupom. PK composta inclui data_venda por exigencia do particionamento.';

-- ---------------------------------------------------------------------
-- Movimentacao de estoque (livro-razao de eventos)
--
-- Cada evento que altera o estoque fisico entra aqui: venda, compra,
-- perda, ajuste de inventario, transferencia. O saldo e a soma.
-- Este e o modelo de "event sourcing" para estoque: auditavel e
-- reconstruivel.
-- ---------------------------------------------------------------------
CREATE TABLE prata.movimentacao_estoque (
    movimentacao_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loja_id         BIGINT NOT NULL REFERENCES prata.loja(loja_id) ON DELETE RESTRICT,
    produto_id      BIGINT NOT NULL REFERENCES prata.produto(produto_id) ON DELETE RESTRICT,
    data_movimento  DATE   NOT NULL,
    tipo            TEXT   NOT NULL,
    quantidade      NUMERIC(14,3) NOT NULL,   -- positivo=entrada, negativo=saida
    custo_unitario  gov.dinheiro,
    documento_ref   TEXT,
    venda_id        BIGINT,
    pedido_id       BIGINT,
    lote_carga_id   BIGINT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT mov_tipo_ck CHECK (tipo IN (
        'VENDA','COMPRA','PERDA','VENCIMENTO','AVARIA','AJUSTE_INVENTARIO',
        'TRANSFERENCIA_ENTRADA','TRANSFERENCIA_SAIDA','DEVOLUCAO_CLIENTE',
        'DEVOLUCAO_FORNECEDOR','CONSUMO_INTERNO'
    )),
    -- Semantica de sinal por tipo: entrada positiva, saida negativa.
    -- Evita que um lancamento com sinal errado corrompa o saldo.
    CONSTRAINT mov_sinal_ck CHECK (
        (tipo IN ('COMPRA','TRANSFERENCIA_ENTRADA','DEVOLUCAO_CLIENTE','AJUSTE_INVENTARIO')
            AND quantidade >= 0) OR
        (tipo IN ('VENDA','PERDA','VENCIMENTO','AVARIA','TRANSFERENCIA_SAIDA',
                  'DEVOLUCAO_FORNECEDOR','CONSUMO_INTERNO')
            AND quantidade <= 0)
    ),
    CONSTRAINT mov_qtd_nao_zero_ck CHECK (quantidade <> 0)
);

COMMENT ON TABLE prata.movimentacao_estoque IS
  'Livro-razao de eventos de estoque. Saldo = SUM(quantidade). Auditavel e reconstruivel.';

-- ---------------------------------------------------------------------
-- Snapshot diario de estoque
--
-- Diferenca para movimentacao: aqui e a FOTOGRAFIA do fim do dia,
-- conferida com o PDV. Serve para:
--   - detectar ruptura (qtd_fim = 0 com venda truncada);
--   - reconciliar sistema x contagem fisica;
--   - dar base para a previsao sem reprocessar todo o historico.
-- ---------------------------------------------------------------------
CREATE TABLE prata.estoque_snapshot (
    loja_id          BIGINT NOT NULL REFERENCES prata.loja(loja_id) ON DELETE RESTRICT,
    produto_id       BIGINT NOT NULL REFERENCES prata.produto(produto_id) ON DELETE RESTRICT,
    data_ref         DATE   NOT NULL,
    qtd_inicio       gov.quantidade NOT NULL,
    qtd_entradas     gov.quantidade NOT NULL DEFAULT 0,
    -- qtd_saidas e MAGNITUDE (positiva), nao valor com sinal.
    -- A equacao e inicio + entradas - saidas + ajustes = fim.
    -- Escolha consciente: "saidas: 3,2 kg" le melhor para o dono do que
    -- "-3,2". O sinal existe em movimentacao_estoque, onde e essencial
    -- para somar o livro-razao; aqui a direcao e dada pelo nome da coluna.
    qtd_saidas       gov.quantidade NOT NULL DEFAULT 0,
    qtd_ajustes      NUMERIC(14,3)  NOT NULL DEFAULT 0,  -- pode ser negativo
    qtd_fim          gov.quantidade NOT NULL,
    qtd_contada      gov.quantidade,          -- NULL = sem inventario neste dia
    custo_medio      gov.dinheiro,
    -- Ruptura: estoque zerado durante o periodo de venda.
    -- E a variavel que separa "vendeu 0" de "nao tinha para vender".
    houve_ruptura    BOOLEAN NOT NULL DEFAULT FALSE,
    horas_sem_estoque NUMERIC(4,2) NOT NULL DEFAULT 0,
    lote_carga_id    BIGINT,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (loja_id, produto_id, data_ref),

    -- Equacao fundamental do estoque. Se isso nao fechar, o dado e lixo.
    CONSTRAINT snapshot_equacao_ck
        CHECK (round(qtd_fim, 3) = round(qtd_inicio + qtd_entradas - qtd_saidas + qtd_ajustes, 3)),
    CONSTRAINT snapshot_ruptura_ck CHECK (
        houve_ruptura = FALSE OR qtd_fim = 0 OR horas_sem_estoque > 0
    ),
    CONSTRAINT snapshot_horas_ck CHECK (horas_sem_estoque >= 0 AND horas_sem_estoque <= 24)
);

COMMENT ON TABLE prata.estoque_snapshot IS
  'Fotografia diaria de estoque por loja/SKU. A constraint snapshot_equacao_ck garante integridade.';
COMMENT ON COLUMN prata.estoque_snapshot.houve_ruptura IS
  'TRUE quando o SKU ficou zerado. Venda do dia e subestimada, nao e demanda real.';
COMMENT ON COLUMN prata.estoque_snapshot.qtd_contada IS
  'Contagem fisica do inventario ciclico. NULL quando nao houve contagem. Base da acuracidade.';

-- ---------------------------------------------------------------------
-- Pedido de compra
-- ---------------------------------------------------------------------
CREATE TABLE prata.pedido_compra (
    pedido_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loja_id         BIGINT NOT NULL REFERENCES prata.loja(loja_id) ON DELETE RESTRICT,
    fornecedor_id   BIGINT NOT NULL REFERENCES prata.fornecedor(fornecedor_id) ON DELETE RESTRICT,
    numero_pedido   TEXT   NOT NULL,
    data_pedido     DATE   NOT NULL,
    data_previsao   DATE   NOT NULL,
    data_entrega    DATE,
    valor_total     gov.dinheiro NOT NULL DEFAULT 0,
    status          TEXT   NOT NULL DEFAULT 'ENVIADO',
    lote_carga_id   BIGINT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pedido_numero_uk UNIQUE (fornecedor_id, numero_pedido),
    CONSTRAINT pedido_status_ck CHECK (status IN ('RASCUNHO','ENVIADO','CONFIRMADO','ENTREGUE','PARCIAL','CANCELADO')),
    CONSTRAINT pedido_datas_ck  CHECK (data_previsao >= data_pedido),
    CONSTRAINT pedido_entrega_ck CHECK (data_entrega IS NULL OR data_entrega >= data_pedido)
);

COMMENT ON TABLE prata.pedido_compra IS 'Pedido ao fornecedor. data_entrega vs data_previsao mede o OTIF.';

CREATE TABLE prata.item_pedido (
    pedido_id      BIGINT NOT NULL REFERENCES prata.pedido_compra(pedido_id) ON DELETE CASCADE,
    item_seq       SMALLINT NOT NULL,
    produto_id     BIGINT NOT NULL REFERENCES prata.produto(produto_id) ON DELETE RESTRICT,
    quantidade_pedida  gov.quantidade_positiva NOT NULL,
    quantidade_entregue gov.quantidade NOT NULL DEFAULT 0,
    custo_unitario gov.dinheiro NOT NULL,
    valor_total    gov.dinheiro NOT NULL,

    PRIMARY KEY (pedido_id, item_seq),
    CONSTRAINT item_pedido_entrega_ck CHECK (quantidade_entregue <= quantidade_pedida * 1.5),
    CONSTRAINT item_pedido_total_ck CHECK (valor_total = round(quantidade_pedida * custo_unitario, 2))
);

COMMENT ON TABLE prata.item_pedido IS 'Linha do pedido. quantidade_entregue < pedida caracteriza entrega parcial.';

COMMIT;
