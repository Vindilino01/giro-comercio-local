-- =====================================================================
-- 006 - Indices
--
-- REGRA: nenhum indice entra aqui sem uma consulta que o justifique.
-- Indice nao e gratuito: ocupa disco, aumenta o custo de INSERT e
-- precisa ser mantido no UPDATE. Num PDV que grava a cada venda, isso
-- importa. Cada bloco abaixo nomeia a consulta de negocio que atende.
--
-- Nomenclatura: ix_<tabela>_<colunas>  /  ux_ = unico  /  brin_ = brin
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- VENDA
-- ---------------------------------------------------------------------

-- Q01 (ruptura e demanda perdida), Q06 (acuracidade), Q10 (qualidade):
-- filtram por loja e intervalo de data. E a consulta mais frequente
-- do produto e a mais cara sem indice.
-- Ordem (loja_id, data_venda) e nao (data_venda, loja_id) porque a
-- seletividade comeca pela loja: o dono sempre olha a propria loja.
CREATE INDEX ix_venda_loja_data
    ON prata.venda (loja_id, data_venda);

-- Q05/Q07: serie temporal de venda por dia para o dashboard.
-- Indice parcial: cupom cancelado nao entra em nenhuma metrica de
-- receita, entao nao precisa ocupar o indice.
CREATE INDEX ix_venda_data_concluida
    ON prata.venda (data_venda)
    WHERE status = 'CONCLUIDA';

-- Deduplicacao na carga: o ETL pergunta "este cupom ja existe?".
-- A UNIQUE constraint (loja_id, data_venda, serie_cupom, numero_cupom)
-- ja cria um indice para isso. Nao duplicar aqui.

-- ---------------------------------------------------------------------
-- ITEM_VENDA
-- ---------------------------------------------------------------------

-- Q02 (curva ABC), Q04 (giro), Q03 (previsao por SKU):
-- filtram por produto e periodo. Consulta central do produto.
-- INCLUDE (quantidade, valor_total) permite index-only scan: o
-- indice ja tem o que a agregacao precisa, sem ir ao heap.
CREATE INDEX ix_item_venda_produto_data
    ON prata.item_venda (produto_id, data_venda)
    INCLUDE (quantidade, valor_total);

-- Q01/Q06: agregacao por venda (quais itens compoem o cupom).
-- A FK composta (venda_id, data_venda) ja tem indice pela PK.
-- Nao duplicar.

-- Q05 (lift de promocao): encontra itens que participaram de promocao.
-- Indice parcial porque a esmagadora maioria dos itens NAO tem promocao:
-- um indice cheio seria quase todo NULL e nao seria usado.
CREATE INDEX ix_item_venda_promocao
    ON prata.item_venda (promocao_id, data_venda)
    WHERE promocao_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- ESTOQUE_SNAPSHOT
-- ---------------------------------------------------------------------

-- PK ja e (loja_id, produto_id, data_ref) - cobre o acesso por chave.

-- Q01/Q03/Q04: serie diaria de estoque por SKU para uma loja.
-- O indice (loja_id, produto_id, data_ref) e identico a PK; o que
-- falta e o caminho por data para varredura de periodo (Q10).
CREATE INDEX ix_snapshot_data
    ON prata.estoque_snapshot (data_ref)
    INCLUDE (loja_id, produto_id, qtd_fim, houve_ruptura);

-- Q01: encontrar rupturas rapidamente. Indice parcial: ruptura e
-- excecao (poucos SKUs por dia), entao o indice fica minusculo e a
-- busca e direta em vez de varrer todos os snapshots.
CREATE INDEX ix_snapshot_ruptura
    ON prata.estoque_snapshot (loja_id, data_ref)
    WHERE houve_ruptura;

-- ---------------------------------------------------------------------
-- MOVIMENTACAO_ESTOQUE
-- ---------------------------------------------------------------------

-- Q06: reconciliacao saldo (movimentacao) x snapshot.
-- Filtro por loja+produto em intervalo de datas.
CREATE INDEX ix_mov_loja_produto_data
    ON prata.movimentacao_estoque (loja_id, produto_id, data_movimento);

-- Q09: relatorio de perdas por tipo (vencimento, avaria) por periodo.
-- Parcial: so interessam os tipos de perda, que sao minoria dos eventos.
CREATE INDEX ix_mov_perdas
    ON prata.movimentacao_estoque (data_movimento, tipo)
    WHERE tipo IN ('PERDA','VENCIMENTO','AVARIA');

-- ---------------------------------------------------------------------
-- PRODUTO
-- ---------------------------------------------------------------------

-- Busca por nome no dashboard (autocomplete do dono digitando "arroz").
-- GIN com pg_trgm suporta ILIKE '%arroz%' sem seq scan.
CREATE INDEX ix_produto_nome_trgm
    ON prata.produto USING gin (nome gin_trgm_ops);

-- Listagem de catalogo ativo. Parcial porque produto inativo e
-- historico e nao aparece em tela nenhuma.
CREATE INDEX ix_produto_ativo_categoria
    ON prata.produto (categoria_id, nome)
    WHERE ativo;

-- ---------------------------------------------------------------------
-- CALENDARIO / PROMOCAO / PEDIDO
-- ---------------------------------------------------------------------

-- Q07: quais dias sao feriado no periodo.
CREATE INDEX ix_calendario_feriado
    ON prata.calendario (data)
    WHERE is_feriado;

-- Q05: promocoes vigentes em uma data.
CREATE INDEX ix_promocao_vigencia
    ON prata.promocao (data_inicio, data_fim);

-- Q08 (OTIF): pedidos por fornecedor com previsao vencida e sem entrega.
CREATE INDEX ix_pedido_fornecedor_status
    ON prata.pedido_compra (fornecedor_id, status, data_previsao);

-- ---------------------------------------------------------------------
-- indice BRIN em data_venda (complementar, nao substituto)
--
-- Por que BRIN alem da arvore B?
--   BRIN guarda apenas min/max por bloco de 128 paginas: ocupa ~1% do
--   tamanho de um btree. Como venda e inserida em ordem cronologica,
--   a correlacao fisica e altissima e o BRIN funciona muito bem para
--   varredura de intervalo amplo (relatorio anual, exportacao).
--   Para busca pontual, o btree continua sendo usado.
--   Os dois coexistem: o planejador escolhe.
-- ---------------------------------------------------------------------
CREATE INDEX brin_venda_data
    ON prata.venda USING brin (data_venda)
    WITH (pages_per_range = 64);

CREATE INDEX brin_item_venda_data
    ON prata.item_venda USING brin (data_venda)
    WITH (pages_per_range = 64);

COMMIT;
