# Dicionário de dados

> **Documento gerado automaticamente** a partir do catálogo do PostgreSQL
> (`src/dicionario.py`). Reflete o banco real, não uma versão idealizada.

**Schemas:** `prata`, `ouro`, `gov`  
**Tabelas:** 28  
**Views materializadas:** 5

## Convenções

| Convenção | Regra | Motivo |
|---|---|---|
| PK | `BIGINT GENERATED ALWAYS AS IDENTITY` | Chave surrogate estável, sem semântica embutida |
| Chave natural | Sempre `UNIQUE`, além da surrogate | Permite deduplicação idempotente |
| Dinheiro | `NUMERIC(14,2)` | Nunca `FLOAT` — erro de arredondamento |
| Quantidade | `NUMERIC(14,3)` | kg e litro fracionam |
| Data/hora | `TIMESTAMPTZ` | Brasil tem 4 fusos horários |
| Nomes | português, sem acento | Evita problema de encoding em exportação |
| Enum | `CHECK`, não tipo `ENUM` | Permite alteração sem lock de catálogo |

## Resumo por schema

| Schema | Tabelas | Propósito |
|---|---|---|
| `prata` | 15 | Camada prata — modelo OLTP normalizado em 3FN. Fonte de verdade transacional. |
| `ouro` | 8 | Camada ouro — star schema e views materializadas para consulta analítica. |
| `gov` | 5 | Governança — quarentena, linhagem, métricas de qualidade e auditoria. |

---

# Schema `prata`

Camada prata — modelo OLTP normalizado em 3FN. Fonte de verdade transacional.

## `prata.calendario`

Calendário com feriados e dias de pagamento. Dimensão de tempo materializada.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `data` | `date` | não |  |
| `ano` | `smallint(16,0)` | não |  |
| `mes` | `smallint(16,0)` | não |  |
| `dia` | `smallint(16,0)` | não |  |
| `dia_semana` | `smallint(16,0)` | não |  |
| `nome_dia_semana` | `text` | não |  |
| `semana_iso` | `smallint(16,0)` | não |  |
| `is_fim_semana` | `boolean` | não |  |
| `is_feriado` | `boolean` | não |  |
| `nome_feriado` | `text` | sim |  |
| `is_pagamento` | `boolean` | não |  |
| `is_feriado_nacional` | `boolean` | não |  |

**Constraints:**

- `calendario_ano_ck` (CHECK): `CHECK (((ano >= 2000) AND (ano <= 2100)))`
- `calendario_dia_ck` (CHECK): `CHECK (((dia >= 1) AND (dia <= 31)))`
- `calendario_ds_ck` (CHECK): `CHECK (((dia_semana >= 1) AND (dia_semana <= 7)))`
- `calendario_feriado_ck` (CHECK): `CHECK (((is_feriado = false) OR (nome_feriado IS NOT NULL)))`
- `calendario_mes_ck` (CHECK): `CHECK (((mes >= 1) AND (mes <= 12)))`
- `calendario_ano_not_null` (n): `NOT NULL ano`
- `calendario_data_not_null` (n): `NOT NULL data`
- `calendario_dia_not_null` (n): `NOT NULL dia`
- `calendario_dia_semana_not_null` (n): `NOT NULL dia_semana`
- `calendario_is_feriado_nacional_not_null` (n): `NOT NULL is_feriado_nacional`
- `calendario_is_feriado_not_null` (n): `NOT NULL is_feriado`
- `calendario_is_fim_semana_not_null` (n): `NOT NULL is_fim_semana`
- `calendario_is_pagamento_not_null` (n): `NOT NULL is_pagamento`
- `calendario_mes_not_null` (n): `NOT NULL mes`
- `calendario_nome_dia_semana_not_null` (n): `NOT NULL nome_dia_semana`
- `calendario_semana_iso_not_null` (n): `NOT NULL semana_iso`
- `calendario_pkey` (PK): `PRIMARY KEY (data)`

**Índices adicionais:**

- `ix_calendario_feriado`: `CREATE INDEX ix_calendario_feriado ON prata.calendario USING btree (data) WHERE is_feriado`

---

## `prata.categoria`

Hierarquia de categorias (departamento > classe > subclasse). Auto-referenciada para permitir profundidade variável.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `categoria_id` | `bigint(64,0)` | não |  |
| `categoria_pai_id` | `bigint(64,0)` | sim |  |
| `codigo` | `text` | não |  |
| `nome` | `text` | não |  |
| `nivel` | `smallint(16,0)` | não |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `categoria_nao_autopai` (CHECK): `CHECK (((categoria_pai_id IS NULL) OR (categoria_pai_id <> categoria_id)))`
- `categoria_nivel_ck` (CHECK): `CHECK (((nivel >= 1) AND (nivel <= 4)))`
- `categoria_categoria_pai_id_fkey` (FK): `FOREIGN KEY (categoria_pai_id) REFERENCES prata.categoria(categoria_id) ON DELETE RESTRICT`
- `categoria_categoria_id_not_null` (n): `NOT NULL categoria_id`
- `categoria_codigo_not_null` (n): `NOT NULL codigo`
- `categoria_criado_em_not_null` (n): `NOT NULL criado_em`
- `categoria_nivel_not_null` (n): `NOT NULL nivel`
- `categoria_nome_not_null` (n): `NOT NULL nome`
- `categoria_pkey` (PK): `PRIMARY KEY (categoria_id)`
- `categoria_codigo_uk` (UNIQUE): `UNIQUE (codigo)`

**Índices adicionais:**

- `categoria_codigo_uk`: `CREATE UNIQUE INDEX categoria_codigo_uk ON prata.categoria USING btree (codigo)`

---

## `prata.estoque_snapshot`

Fotografia diária de estoque por loja/SKU. A constraint `snapshot_equacao_ck` garante integridade.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `loja_id` | `bigint(64,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `data_ref` | `date` | não |  |
| `qtd_inicio` | `numeric(14,3)` | não |  |
| `qtd_entradas` | `numeric(14,3)` | não |  |
| `qtd_saidas` | `numeric(14,3)` | não |  |
| `qtd_ajustes` | `numeric(14,3)` | não |  |
| `qtd_fim` | `numeric(14,3)` | não |  |
| `qtd_contada` | `numeric(14,3)` | sim | Contagem fisica do inventario ciclico. NULL quando nao houve contagem. Base da acuracidade. |
| `custo_medio` | `numeric(14,2)` | sim |  |
| `houve_ruptura` | `boolean` | não | TRUE quando o SKU ficou zerado. Venda do dia e subestimada, nao e demanda real. |
| `horas_sem_estoque` | `numeric(4,2)` | não |  |
| `lote_carga_id` | `bigint(64,0)` | sim |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `snapshot_equacao_ck` (CHECK): `CHECK ((round((qtd_fim)::numeric, 3) = round(((((qtd_inicio)::numeric + (qtd_entradas)::numeric) - (qtd_saidas)::numeric) + qtd_ajustes), 3)))`
- `snapshot_horas_ck` (CHECK): `CHECK (((horas_sem_estoque >= (0)::numeric) AND (horas_sem_estoque <= (24)::numeric)))`
- `snapshot_ruptura_ck` (CHECK): `CHECK (((houve_ruptura = false) OR ((qtd_fim)::numeric = (0)::numeric) OR (horas_sem_estoque > (0)::numeric)))`
- `estoque_snapshot_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES prata.loja(loja_id) ON DELETE RESTRICT`
- `estoque_snapshot_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE RESTRICT`
- `estoque_snapshot_criado_em_not_null` (n): `NOT NULL criado_em`
- `estoque_snapshot_data_ref_not_null` (n): `NOT NULL data_ref`
- `estoque_snapshot_horas_sem_estoque_not_null` (n): `NOT NULL horas_sem_estoque`
- `estoque_snapshot_houve_ruptura_not_null` (n): `NOT NULL houve_ruptura`
- `estoque_snapshot_loja_id_not_null` (n): `NOT NULL loja_id`
- `estoque_snapshot_produto_id_not_null` (n): `NOT NULL produto_id`
- `estoque_snapshot_qtd_ajustes_not_null` (n): `NOT NULL qtd_ajustes`
- `estoque_snapshot_qtd_entradas_not_null` (n): `NOT NULL qtd_entradas`
- `estoque_snapshot_qtd_fim_not_null` (n): `NOT NULL qtd_fim`
- `estoque_snapshot_qtd_inicio_not_null` (n): `NOT NULL qtd_inicio`
- `estoque_snapshot_qtd_saidas_not_null` (n): `NOT NULL qtd_saidas`
- `estoque_snapshot_pkey` (PK): `PRIMARY KEY (loja_id, produto_id, data_ref)`

**Índices adicionais:**

- `ix_snapshot_data`: `CREATE INDEX ix_snapshot_data ON prata.estoque_snapshot USING btree (data_ref) INCLUDE (loja_id, produto_id, qtd_fim, houve_ruptura)`
- `ix_snapshot_ruptura`: `CREATE INDEX ix_snapshot_ruptura ON prata.estoque_snapshot USING btree (loja_id, data_ref) WHERE houve_ruptura`

---

## `prata.fornecedor`

Fornecedor/distribuidor. `lead_time` alimenta a sugestão de compra.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `fornecedor_id` | `bigint(64,0)` | não |  |
| `cnpj` | `text` | não |  |
| `razao_social` | `text` | não |  |
| `nome_fantasia` | `text` | sim |  |
| `cidade` | `text` | sim |  |
| `uf` | `character(2)` | sim |  |
| `lead_time_dias_padrao` | `smallint(16,0)` | não |  |
| `pedido_minimo_valor` | `numeric(14,2)` | não |  |
| `ativo` | `boolean` | não |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `fornecedor_cnpj_ck` (CHECK): `CHECK ((cnpj ~ '^[0-9]{14}$'::text))`
- `fornecedor_lead_ck` (CHECK): `CHECK (((lead_time_dias_padrao >= 0) AND (lead_time_dias_padrao <= 180)))`
- `fornecedor_ativo_not_null` (n): `NOT NULL ativo`
- `fornecedor_cnpj_not_null` (n): `NOT NULL cnpj`
- `fornecedor_criado_em_not_null` (n): `NOT NULL criado_em`
- `fornecedor_fornecedor_id_not_null` (n): `NOT NULL fornecedor_id`
- `fornecedor_lead_time_dias_padrao_not_null` (n): `NOT NULL lead_time_dias_padrao`
- `fornecedor_pedido_minimo_valor_not_null` (n): `NOT NULL pedido_minimo_valor`
- `fornecedor_razao_social_not_null` (n): `NOT NULL razao_social`
- `fornecedor_pkey` (PK): `PRIMARY KEY (fornecedor_id)`
- `fornecedor_cnpj_uk` (UNIQUE): `UNIQUE (cnpj)`

**Índices adicionais:**

- `fornecedor_cnpj_uk`: `CREATE UNIQUE INDEX fornecedor_cnpj_uk ON prata.fornecedor USING btree (cnpj)`

---

## `prata.item_pedido`

Linha do pedido. `quantidade_entregue` < pedida caracteriza entrega parcial.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `pedido_id` | `bigint(64,0)` | não |  |
| `item_seq` | `smallint(16,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `quantidade_pedida` | `numeric(14,3)` | não |  |
| `quantidade_entregue` | `numeric(14,3)` | não |  |
| `custo_unitario` | `numeric(14,2)` | não |  |
| `valor_total` | `numeric(14,2)` | não |  |

**Constraints:**

- `item_pedido_entrega_ck` (CHECK): `CHECK (((quantidade_entregue)::numeric <= ((quantidade_pedida)::numeric * 1.5)))`
- `item_pedido_total_ck` (CHECK): `CHECK (((valor_total)::numeric = round(((quantidade_pedida)::numeric * (custo_unitario)::numeric), 2)))`
- `item_pedido_pedido_id_fkey` (FK): `FOREIGN KEY (pedido_id) REFERENCES prata.pedido_compra(pedido_id) ON DELETE CASCADE`
- `item_pedido_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE RESTRICT`
- `item_pedido_custo_unitario_not_null` (n): `NOT NULL custo_unitario`
- `item_pedido_item_seq_not_null` (n): `NOT NULL item_seq`
- `item_pedido_pedido_id_not_null` (n): `NOT NULL pedido_id`
- `item_pedido_produto_id_not_null` (n): `NOT NULL produto_id`
- `item_pedido_quantidade_entregue_not_null` (n): `NOT NULL quantidade_entregue`
- `item_pedido_quantidade_pedida_not_null` (n): `NOT NULL quantidade_pedida`
- `item_pedido_valor_total_not_null` (n): `NOT NULL valor_total`
- `item_pedido_pkey` (PK): `PRIMARY KEY (pedido_id, item_seq)`

---

## `prata.item_venda`

Linha do cupom. PK inclui `data_venda` por exigência do particionamento.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `venda_id` | `bigint(64,0)` | não |  |
| `data_venda` | `date` | não |  |
| `item_seq` | `smallint(16,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `quantidade` | `numeric(14,3)` | não |  |
| `preco_unitario` | `numeric(14,2)` | não |  |
| `valor_desconto` | `numeric(14,2)` | não |  |
| `valor_total` | `numeric(14,2)` | não |  |
| `promocao_id` | `bigint(64,0)` | sim |  |
| `custo_unitario` | `numeric(14,2)` | sim |  |

**Constraints:**

- `item_venda_item_seq_ck` (CHECK): `CHECK ((item_seq > 0))`
- `item_venda_total_ck` (CHECK): `CHECK (((valor_total)::numeric = (round(((quantidade)::numeric * (preco_unitario)::numeric), 2) - (valor_desconto)::numeric)))`
- `item_venda_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE RESTRICT`
- `item_venda_promocao_id_fkey` (FK): `FOREIGN KEY (promocao_id) REFERENCES prata.promocao(promocao_id) ON DELETE SET NULL`
- `item_venda_venda_fk` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_1` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_11(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_10` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_08(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_11` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_09(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_12` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_10(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_13` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_11(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_14` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_12(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_15` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_01(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_16` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_02(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_17` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_03(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_18` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_04(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_19` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_05(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_2` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_12(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_20` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_06(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_21` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_07(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_22` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_08(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_23` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_09(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_24` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_10(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_25` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_11(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_26` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2026_12(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_27` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2027_01(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_28` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2027_02(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_29` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2027_03(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_3` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_01(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_30` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2027_04(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_31` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2027_05(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_32` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2023_11(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_33` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2023_12(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_34` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_01(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_35` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_02(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_36` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_03(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_37` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_04(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_38` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_05(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_39` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_06(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_4` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_02(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_40` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_07(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_41` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_08(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_42` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_09(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_43` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2024_10(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_5` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_03(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_6` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_04(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_7` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_05(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_8` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_06(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_venda_fk_9` (FK): `FOREIGN KEY (venda_id, data_venda) REFERENCES prata.venda_2025_07(venda_id, data_venda) ON DELETE CASCADE`
- `item_venda_data_venda_not_null` (n): `NOT NULL data_venda`
- `item_venda_item_seq_not_null` (n): `NOT NULL item_seq`
- `item_venda_preco_unitario_not_null` (n): `NOT NULL preco_unitario`
- `item_venda_produto_id_not_null` (n): `NOT NULL produto_id`
- `item_venda_quantidade_not_null` (n): `NOT NULL quantidade`
- `item_venda_valor_desconto_not_null` (n): `NOT NULL valor_desconto`
- `item_venda_valor_total_not_null` (n): `NOT NULL valor_total`
- `item_venda_venda_id_not_null` (n): `NOT NULL venda_id`
- `item_venda_pkey` (PK): `PRIMARY KEY (venda_id, data_venda, item_seq)`

**Índices adicionais:**

- `brin_item_venda_data`: `CREATE INDEX brin_item_venda_data ON ONLY prata.item_venda USING brin (data_venda) WITH (pages_per_range='64')`
- `ix_item_venda_produto_data`: `CREATE INDEX ix_item_venda_produto_data ON ONLY prata.item_venda USING btree (produto_id, data_venda) INCLUDE (quantidade, valor_total)`
- `ix_item_venda_promocao`: `CREATE INDEX ix_item_venda_promocao ON ONLY prata.item_venda USING btree (promocao_id, data_venda) WHERE (promocao_id IS NOT NULL)`

---

## `prata.loja`

Unidade física do mercado. Multi-loja desde o início.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `loja_id` | `bigint(64,0)` | não |  |
| `codigo` | `text` | não | Chave natural: codigo da loja no PDV. |
| `nome` | `text` | não |  |
| `cnpj` | `text` | sim | CNPJ sem mascara. Unico quando informado. |
| `cidade` | `text` | não |  |
| `uf` | `character(2)` | não |  |
| `area_m2` | `numeric(8,2)` | sim |  |
| `data_abertura` | `date` | não |  |
| `data_fechamento` | `date` | sim |  |
| `ativa` | `boolean` | não |  |
| `criado_em` | `timestamptz` | não |  |
| `atualizado_em` | `timestamptz` | não |  |

**Constraints:**

- `loja_area_ck` (CHECK): `CHECK (((area_m2 IS NULL) OR (area_m2 > (0)::numeric)))`
- `loja_cnpj_ck` (CHECK): `CHECK (((cnpj IS NULL) OR (cnpj ~ '^[0-9]{14}$'::text)))`
- `loja_datas_ck` (CHECK): `CHECK (((data_fechamento IS NULL) OR (data_fechamento >= data_abertura)))`
- `loja_ativa_not_null` (n): `NOT NULL ativa`
- `loja_atualizado_em_not_null` (n): `NOT NULL atualizado_em`
- `loja_cidade_not_null` (n): `NOT NULL cidade`
- `loja_codigo_not_null` (n): `NOT NULL codigo`
- `loja_criado_em_not_null` (n): `NOT NULL criado_em`
- `loja_data_abertura_not_null` (n): `NOT NULL data_abertura`
- `loja_loja_id_not_null` (n): `NOT NULL loja_id`
- `loja_nome_not_null` (n): `NOT NULL nome`
- `loja_uf_not_null` (n): `NOT NULL uf`
- `loja_pkey` (PK): `PRIMARY KEY (loja_id)`
- `loja_cnpj_uk` (UNIQUE): `UNIQUE (cnpj)`
- `loja_codigo_uk` (UNIQUE): `UNIQUE (codigo)`

**Índices adicionais:**

- `loja_cnpj_uk`: `CREATE UNIQUE INDEX loja_cnpj_uk ON prata.loja USING btree (cnpj)`
- `loja_codigo_uk`: `CREATE UNIQUE INDEX loja_codigo_uk ON prata.loja USING btree (codigo)`

---

## `prata.movimentacao_estoque`

Livro-razão de eventos de estoque (event sourcing). Saldo = SUM(quantidade).

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `movimentacao_id` | `bigint(64,0)` | não |  |
| `loja_id` | `bigint(64,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `data_movimento` | `date` | não |  |
| `tipo` | `text` | não |  |
| `quantidade` | `numeric(14,3)` | não |  |
| `custo_unitario` | `numeric(14,2)` | sim |  |
| `documento_ref` | `text` | sim |  |
| `venda_id` | `bigint(64,0)` | sim |  |
| `pedido_id` | `bigint(64,0)` | sim |  |
| `lote_carga_id` | `bigint(64,0)` | sim |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `mov_qtd_nao_zero_ck` (CHECK): `CHECK ((quantidade <> (0)::numeric))`
- `mov_sinal_ck` (CHECK): `CHECK ((((tipo = ANY (ARRAY['COMPRA'::text, 'TRANSFERENCIA_ENTRADA'::text, 'DEVOLUCAO_CLIENTE'::text, 'AJUSTE_INVENTARIO'::text])) AND (quantidade >= (0)::numeric)) OR ((tipo = ANY (ARRAY['VENDA'::text, 'PERDA'::text, 'VENCIMENTO'::text, 'AVARIA'::text, 'TRANSFERENCIA_SAIDA'::text, 'DEVOLUCAO_FORNECEDOR'::text, 'CONSUMO_INTERNO'::text])) AND (quantidade <= (0)::numeric))))`
- `mov_tipo_ck` (CHECK): `CHECK ((tipo = ANY (ARRAY['VENDA'::text, 'COMPRA'::text, 'PERDA'::text, 'VENCIMENTO'::text, 'AVARIA'::text, 'AJUSTE_INVENTARIO'::text, 'TRANSFERENCIA_ENTRADA'::text, 'TRANSFERENCIA_SAIDA'::text, 'DEVOLUCAO_CLIENTE'::text, 'DEVOLUCAO_FORNECEDOR'::text, 'CONSUMO_INTERNO'::text])))`
- `movimentacao_estoque_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES prata.loja(loja_id) ON DELETE RESTRICT`
- `movimentacao_estoque_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE RESTRICT`
- `movimentacao_estoque_criado_em_not_null` (n): `NOT NULL criado_em`
- `movimentacao_estoque_data_movimento_not_null` (n): `NOT NULL data_movimento`
- `movimentacao_estoque_loja_id_not_null` (n): `NOT NULL loja_id`
- `movimentacao_estoque_movimentacao_id_not_null` (n): `NOT NULL movimentacao_id`
- `movimentacao_estoque_produto_id_not_null` (n): `NOT NULL produto_id`
- `movimentacao_estoque_quantidade_not_null` (n): `NOT NULL quantidade`
- `movimentacao_estoque_tipo_not_null` (n): `NOT NULL tipo`
- `movimentacao_estoque_pkey` (PK): `PRIMARY KEY (movimentacao_id)`

**Índices adicionais:**

- `ix_mov_loja_produto_data`: `CREATE INDEX ix_mov_loja_produto_data ON prata.movimentacao_estoque USING btree (loja_id, produto_id, data_movimento)`
- `ix_mov_perdas`: `CREATE INDEX ix_mov_perdas ON prata.movimentacao_estoque USING btree (data_movimento, tipo) WHERE (tipo = ANY (ARRAY['PERDA'::text, 'VENCIMENTO'::text, 'AVARIA'::text]))`

---

## `prata.pedido_compra`

Pedido ao fornecedor. `data_entrega` vs `data_previsao` mede o OTIF.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `pedido_id` | `bigint(64,0)` | não |  |
| `loja_id` | `bigint(64,0)` | não |  |
| `fornecedor_id` | `bigint(64,0)` | não |  |
| `numero_pedido` | `text` | não |  |
| `data_pedido` | `date` | não |  |
| `data_previsao` | `date` | não |  |
| `data_entrega` | `date` | sim |  |
| `valor_total` | `numeric(14,2)` | não |  |
| `status` | `text` | não |  |
| `lote_carga_id` | `bigint(64,0)` | sim |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `pedido_datas_ck` (CHECK): `CHECK ((data_previsao >= data_pedido))`
- `pedido_entrega_ck` (CHECK): `CHECK (((data_entrega IS NULL) OR (data_entrega >= data_pedido)))`
- `pedido_status_ck` (CHECK): `CHECK ((status = ANY (ARRAY['RASCUNHO'::text, 'ENVIADO'::text, 'CONFIRMADO'::text, 'ENTREGUE'::text, 'PARCIAL'::text, 'CANCELADO'::text])))`
- `pedido_compra_fornecedor_id_fkey` (FK): `FOREIGN KEY (fornecedor_id) REFERENCES prata.fornecedor(fornecedor_id) ON DELETE RESTRICT`
- `pedido_compra_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES prata.loja(loja_id) ON DELETE RESTRICT`
- `pedido_compra_criado_em_not_null` (n): `NOT NULL criado_em`
- `pedido_compra_data_pedido_not_null` (n): `NOT NULL data_pedido`
- `pedido_compra_data_previsao_not_null` (n): `NOT NULL data_previsao`
- `pedido_compra_fornecedor_id_not_null` (n): `NOT NULL fornecedor_id`
- `pedido_compra_loja_id_not_null` (n): `NOT NULL loja_id`
- `pedido_compra_numero_pedido_not_null` (n): `NOT NULL numero_pedido`
- `pedido_compra_pedido_id_not_null` (n): `NOT NULL pedido_id`
- `pedido_compra_status_not_null` (n): `NOT NULL status`
- `pedido_compra_valor_total_not_null` (n): `NOT NULL valor_total`
- `pedido_compra_pkey` (PK): `PRIMARY KEY (pedido_id)`
- `pedido_numero_uk` (UNIQUE): `UNIQUE (fornecedor_id, numero_pedido)`

**Índices adicionais:**

- `ix_pedido_fornecedor_status`: `CREATE INDEX ix_pedido_fornecedor_status ON prata.pedido_compra USING btree (fornecedor_id, status, data_previsao)`
- `pedido_numero_uk`: `CREATE UNIQUE INDEX pedido_numero_uk ON prata.pedido_compra USING btree (fornecedor_id, numero_pedido)`

---

## `prata.produto`

Cadastro de SKU. Soft delete via `ativo` para preservar histórico.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `produto_id` | `bigint(64,0)` | não |  |
| `ean` | `text` | não | Chave natural de negocio. Validada pelo digito verificador. |
| `sku_interno` | `text` | não |  |
| `nome` | `text` | não |  |
| `categoria_id` | `bigint(64,0)` | não |  |
| `unidade_medida` | `text` | não | UN, KG, L, ML, CX, DZ ou PCT. Nao ha conversao automatica. |
| `e_perecivel` | `boolean` | não | Se TRUE, dias_validade e obrigatorio e a curva de risco de vencimento se aplica. |
| `dias_validade` | `smallint(16,0)` | sim |  |
| `peso_liquido_kg` | `numeric(10,4)` | sim |  |
| `ativo` | `boolean` | não |  |
| `criado_em` | `timestamptz` | não |  |
| `atualizado_em` | `timestamptz` | não |  |

**Constraints:**

- `produto_peso_ck` (CHECK): `CHECK (((peso_liquido_kg IS NULL) OR (peso_liquido_kg > (0)::numeric)))`
- `produto_unidade_ck` (CHECK): `CHECK ((unidade_medida = ANY (ARRAY['UN'::text, 'KG'::text, 'L'::text, 'ML'::text, 'CX'::text, 'DZ'::text, 'PCT'::text])))`
- `produto_validade_ck` (CHECK): `CHECK ((((e_perecivel = true) AND (dias_validade IS NOT NULL) AND (dias_validade > 0)) OR ((e_perecivel = false) AND (dias_validade IS NULL))))`
- `produto_categoria_id_fkey` (FK): `FOREIGN KEY (categoria_id) REFERENCES prata.categoria(categoria_id) ON DELETE RESTRICT`
- `produto_ativo_not_null` (n): `NOT NULL ativo`
- `produto_atualizado_em_not_null` (n): `NOT NULL atualizado_em`
- `produto_categoria_id_not_null` (n): `NOT NULL categoria_id`
- `produto_criado_em_not_null` (n): `NOT NULL criado_em`
- `produto_e_perecivel_not_null` (n): `NOT NULL e_perecivel`
- `produto_ean_not_null` (n): `NOT NULL ean`
- `produto_nome_not_null` (n): `NOT NULL nome`
- `produto_produto_id_not_null` (n): `NOT NULL produto_id`
- `produto_sku_interno_not_null` (n): `NOT NULL sku_interno`
- `produto_unidade_medida_not_null` (n): `NOT NULL unidade_medida`
- `produto_pkey` (PK): `PRIMARY KEY (produto_id)`
- `produto_ean_uk` (UNIQUE): `UNIQUE (ean)`
- `produto_sku_uk` (UNIQUE): `UNIQUE (sku_interno)`

**Índices adicionais:**

- `ix_produto_ativo_categoria`: `CREATE INDEX ix_produto_ativo_categoria ON prata.produto USING btree (categoria_id, nome) WHERE ativo`
- `ix_produto_nome_trgm`: `CREATE INDEX ix_produto_nome_trgm ON prata.produto USING gin (nome gin_trgm_ops)`
- `produto_ean_uk`: `CREATE UNIQUE INDEX produto_ean_uk ON prata.produto USING btree (ean)`
- `produto_sku_uk`: `CREATE UNIQUE INDEX produto_sku_uk ON prata.produto USING btree (sku_interno)`

---

## `prata.produto_fornecedor`

Preço e prazo por par produto-fornecedor. Índice parcial garante um preferencial por SKU.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `produto_id` | `bigint(64,0)` | não |  |
| `fornecedor_id` | `bigint(64,0)` | não |  |
| `custo_unitario` | `numeric(14,2)` | não |  |
| `lead_time_dias` | `smallint(16,0)` | não |  |
| `lote_minimo` | `numeric(14,3)` | não |  |
| `multiplo_compra` | `numeric(14,3)` | não |  |
| `preferencial` | `boolean` | não |  |
| `atualizado_em` | `timestamptz` | não |  |

**Constraints:**

- `produto_fornecedor_lead_ck` (CHECK): `CHECK (((lead_time_dias >= 0) AND (lead_time_dias <= 180)))`
- `produto_fornecedor_fornecedor_id_fkey` (FK): `FOREIGN KEY (fornecedor_id) REFERENCES prata.fornecedor(fornecedor_id) ON DELETE CASCADE`
- `produto_fornecedor_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE CASCADE`
- `produto_fornecedor_atualizado_em_not_null` (n): `NOT NULL atualizado_em`
- `produto_fornecedor_custo_unitario_not_null` (n): `NOT NULL custo_unitario`
- `produto_fornecedor_fornecedor_id_not_null` (n): `NOT NULL fornecedor_id`
- `produto_fornecedor_lead_time_dias_not_null` (n): `NOT NULL lead_time_dias`
- `produto_fornecedor_lote_minimo_not_null` (n): `NOT NULL lote_minimo`
- `produto_fornecedor_multiplo_compra_not_null` (n): `NOT NULL multiplo_compra`
- `produto_fornecedor_preferencial_not_null` (n): `NOT NULL preferencial`
- `produto_fornecedor_produto_id_not_null` (n): `NOT NULL produto_id`
- `produto_fornecedor_pkey` (PK): `PRIMARY KEY (produto_id, fornecedor_id)`

**Índices adicionais:**

- `produto_fornecedor_um_preferencial`: `CREATE UNIQUE INDEX produto_fornecedor_um_preferencial ON prata.produto_fornecedor USING btree (produto_id) WHERE preferencial`

---

## `prata.produto_preco_historico`

Vigência de preço de custo e venda (SCD tipo 2). Faixas não se sobrepõem (EXCLUDE).

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `produto_id` | `bigint(64,0)` | não |  |
| `data_inicio` | `date` | não |  |
| `data_fim` | `date` | sim |  |
| `preco_custo` | `numeric(14,2)` | não |  |
| `preco_venda` | `numeric(14,2)` | não |  |
| `margem_pct` | `numeric(7,4)` | sim |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `preco_venda_positivo_ck` (CHECK): `CHECK (((preco_venda)::numeric > (0)::numeric))`
- `preco_vigencia_ck` (CHECK): `CHECK (((data_fim IS NULL) OR (data_fim > data_inicio)))`
- `produto_preco_historico_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE CASCADE`
- `produto_preco_historico_criado_em_not_null` (n): `NOT NULL criado_em`
- `produto_preco_historico_data_inicio_not_null` (n): `NOT NULL data_inicio`
- `produto_preco_historico_preco_custo_not_null` (n): `NOT NULL preco_custo`
- `produto_preco_historico_preco_venda_not_null` (n): `NOT NULL preco_venda`
- `produto_preco_historico_produto_id_not_null` (n): `NOT NULL produto_id`
- `produto_preco_historico_pkey` (PK): `PRIMARY KEY (produto_id, data_inicio)`
- `produto_preco_sem_sobreposicao` (EXCLUDE): `EXCLUDE USING gist (produto_id WITH =, daterange(data_inicio, COALESCE(data_fim, 'infinity'::date), '[)'::text) WITH &&)`

**Índices adicionais:**

- `produto_preco_sem_sobreposicao`: `CREATE INDEX produto_preco_sem_sobreposicao ON prata.produto_preco_historico USING gist (produto_id, daterange(data_inicio, COALESCE(data_fim, 'infinity'::date), '[)'::text))`
- `produto_preco_uma_faixa_aberta`: `CREATE UNIQUE INDEX produto_preco_uma_faixa_aberta ON prata.produto_preco_historico USING btree (produto_id) WHERE (data_fim IS NULL)`

---

## `prata.promocao`

Campanha promocional com janela de vigência.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `promocao_id` | `bigint(64,0)` | não |  |
| `codigo` | `text` | não |  |
| `descricao` | `text` | não |  |
| `tipo` | `text` | não |  |
| `data_inicio` | `date` | não |  |
| `data_fim` | `date` | não |  |
| `percentual_desconto` | `numeric(7,4)` | sim |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `promocao_datas_ck` (CHECK): `CHECK ((data_fim >= data_inicio))`
- `promocao_desconto_ck` (CHECK): `CHECK (((tipo <> 'DESCONTO'::text) OR (percentual_desconto IS NOT NULL)))`
- `promocao_tipo_ck` (CHECK): `CHECK ((tipo = ANY (ARRAY['DESCONTO'::text, 'LEVE_PAGUE'::text, 'COMBO'::text, 'CUPOM'::text, 'FIDELIDADE'::text])))`
- `promocao_codigo_not_null` (n): `NOT NULL codigo`
- `promocao_criado_em_not_null` (n): `NOT NULL criado_em`
- `promocao_data_fim_not_null` (n): `NOT NULL data_fim`
- `promocao_data_inicio_not_null` (n): `NOT NULL data_inicio`
- `promocao_descricao_not_null` (n): `NOT NULL descricao`
- `promocao_promocao_id_not_null` (n): `NOT NULL promocao_id`
- `promocao_tipo_not_null` (n): `NOT NULL tipo`
- `promocao_pkey` (PK): `PRIMARY KEY (promocao_id)`
- `promocao_codigo_uk` (UNIQUE): `UNIQUE (codigo)`

**Índices adicionais:**

- `ix_promocao_vigencia`: `CREATE INDEX ix_promocao_vigencia ON prata.promocao USING btree (data_inicio, data_fim)`
- `promocao_codigo_uk`: `CREATE UNIQUE INDEX promocao_codigo_uk ON prata.promocao USING btree (codigo)`

---

## `prata.promocao_produto`

Produtos participantes de cada promoção.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `promocao_id` | `bigint(64,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `preco_promocional` | `numeric(14,2)` | sim |  |

**Constraints:**

- `promocao_produto_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES prata.produto(produto_id) ON DELETE CASCADE`
- `promocao_produto_promocao_id_fkey` (FK): `FOREIGN KEY (promocao_id) REFERENCES prata.promocao(promocao_id) ON DELETE CASCADE`
- `promocao_produto_produto_id_not_null` (n): `NOT NULL produto_id`
- `promocao_produto_promocao_id_not_null` (n): `NOT NULL promocao_id`
- `promocao_produto_pkey` (PK): `PRIMARY KEY (promocao_id, produto_id)`

---

## `prata.venda`

Cabeçalho de cupom fiscal. Particionada por mês em `data_venda`.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `venda_id` | `bigint(64,0)` | não |  |
| `loja_id` | `bigint(64,0)` | não |  |
| `data_venda` | `date` | não |  |
| `hora_venda` | `time without time zone` | não |  |
| `numero_cupom` | `text` | não | Chave natural junto com loja/data/serie. Base da deduplicacao idempotente. |
| `serie_cupom` | `text` | sim |  |
| `canal` | `text` | não |  |
| `valor_bruto` | `numeric(14,2)` | não |  |
| `valor_desconto` | `numeric(14,2)` | não |  |
| `valor_liquido` | `numeric(14,2)` | não |  |
| `qtd_itens` | `smallint(16,0)` | não |  |
| `status` | `text` | não | CONCLUIDA conta como venda. CANCELADA/DEVOLVIDA ficam para auditoria e nao entram em receita. |
| `cancelada_em` | `timestamptz` | sim |  |
| `motivo_cancelamento` | `text` | sim |  |
| `lote_carga_id` | `bigint(64,0)` | sim |  |
| `criado_em` | `timestamptz` | não |  |

**Constraints:**

- `venda_canal_ck` (CHECK): `CHECK ((canal = ANY (ARRAY['PDV'::text, 'ONLINE'::text, 'APP'::text, 'TELEFONE'::text])))`
- `venda_cancelamento_ck` (CHECK): `CHECK ((((status = 'CONCLUIDA'::text) AND (cancelada_em IS NULL)) OR ((status <> 'CONCLUIDA'::text) AND (cancelada_em IS NOT NULL))))`
- `venda_desconto_ck` (CHECK): `CHECK (((valor_desconto)::numeric <= (valor_bruto)::numeric))`
- `venda_qtd_ck` (CHECK): `CHECK ((qtd_itens > 0))`
- `venda_status_ck` (CHECK): `CHECK ((status = ANY (ARRAY['CONCLUIDA'::text, 'CANCELADA'::text, 'DEVOLVIDA'::text])))`
- `venda_total_ck` (CHECK): `CHECK (((valor_liquido)::numeric = ((valor_bruto)::numeric - (valor_desconto)::numeric)))`
- `venda_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES prata.loja(loja_id) ON DELETE RESTRICT`
- `venda_canal_not_null` (n): `NOT NULL canal`
- `venda_criado_em_not_null` (n): `NOT NULL criado_em`
- `venda_data_venda_not_null` (n): `NOT NULL data_venda`
- `venda_hora_venda_not_null` (n): `NOT NULL hora_venda`
- `venda_loja_id_not_null` (n): `NOT NULL loja_id`
- `venda_numero_cupom_not_null` (n): `NOT NULL numero_cupom`
- `venda_qtd_itens_not_null` (n): `NOT NULL qtd_itens`
- `venda_status_not_null` (n): `NOT NULL status`
- `venda_valor_bruto_not_null` (n): `NOT NULL valor_bruto`
- `venda_valor_desconto_not_null` (n): `NOT NULL valor_desconto`
- `venda_valor_liquido_not_null` (n): `NOT NULL valor_liquido`
- `venda_venda_id_not_null` (n): `NOT NULL venda_id`
- `venda_pkey` (PK): `PRIMARY KEY (venda_id, data_venda)`
- `venda_chave_natural_uk` (UNIQUE): `UNIQUE NULLS NOT DISTINCT (loja_id, data_venda, serie_cupom, numero_cupom)`

**Índices adicionais:**

- `brin_venda_data`: `CREATE INDEX brin_venda_data ON ONLY prata.venda USING brin (data_venda) WITH (pages_per_range='64')`
- `ix_venda_data_concluida`: `CREATE INDEX ix_venda_data_concluida ON ONLY prata.venda USING btree (data_venda) WHERE (status = 'CONCLUIDA'::text)`
- `ix_venda_loja_data`: `CREATE INDEX ix_venda_loja_data ON ONLY prata.venda USING btree (loja_id, data_venda)`
- `venda_chave_natural_uk`: `CREATE UNIQUE INDEX venda_chave_natural_uk ON ONLY prata.venda USING btree (loja_id, data_venda, serie_cupom, numero_cupom) NULLS NOT DISTINCT`

---

# Schema `ouro`

Camada ouro — star schema e views materializadas para consulta analítica.

## `ouro.dim_fornecedor`

Dimensão fornecedor.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `fornecedor_id` | `bigint(64,0)` | não |  |
| `cnpj` | `text` | não |  |
| `razao_social` | `text` | não |  |
| `cidade` | `text` | sim |  |
| `uf` | `character(2)` | sim |  |
| `lead_time_padrao` | `smallint(16,0)` | não |  |

**Constraints:**

- `dim_fornecedor_cnpj_not_null` (n): `NOT NULL cnpj`
- `dim_fornecedor_fornecedor_id_not_null` (n): `NOT NULL fornecedor_id`
- `dim_fornecedor_lead_time_padrao_not_null` (n): `NOT NULL lead_time_padrao`
- `dim_fornecedor_razao_social_not_null` (n): `NOT NULL razao_social`
- `dim_fornecedor_pkey` (PK): `PRIMARY KEY (fornecedor_id)`

---

## `ouro.dim_loja`

Dimensão loja com porte derivado da área.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `loja_id` | `bigint(64,0)` | não |  |
| `codigo` | `text` | não |  |
| `nome` | `text` | não |  |
| `cidade` | `text` | não |  |
| `uf` | `character(2)` | não |  |
| `area_m2` | `numeric(8,2)` | sim |  |
| `porte` | `text` | não |  |
| `data_abertura` | `date` | não |  |
| `ativa` | `boolean` | não |  |

**Constraints:**

- `dim_loja_ativa_not_null` (n): `NOT NULL ativa`
- `dim_loja_cidade_not_null` (n): `NOT NULL cidade`
- `dim_loja_codigo_not_null` (n): `NOT NULL codigo`
- `dim_loja_data_abertura_not_null` (n): `NOT NULL data_abertura`
- `dim_loja_loja_id_not_null` (n): `NOT NULL loja_id`
- `dim_loja_nome_not_null` (n): `NOT NULL nome`
- `dim_loja_porte_not_null` (n): `NOT NULL porte`
- `dim_loja_uf_not_null` (n): `NOT NULL uf`
- `dim_loja_pkey` (PK): `PRIMARY KEY (loja_id)`

---

## `ouro.dim_produto`

Dimensão produto com hierarquia achatada e preço vigente.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `produto_id` | `bigint(64,0)` | não |  |
| `ean` | `text` | não |  |
| `sku_interno` | `text` | não |  |
| `nome` | `text` | não |  |
| `departamento` | `text` | não |  |
| `classe` | `text` | não |  |
| `unidade_medida` | `text` | não |  |
| `e_perecivel` | `boolean` | não |  |
| `dias_validade` | `smallint(16,0)` | sim |  |
| `preco_custo_atual` | `numeric(14,2)` | sim |  |
| `preco_venda_atual` | `numeric(14,2)` | sim |  |
| `fornecedor_principal` | `text` | sim |  |
| `lead_time_dias` | `smallint(16,0)` | sim |  |
| `ativo` | `boolean` | não |  |

**Constraints:**

- `dim_produto_ativo_not_null` (n): `NOT NULL ativo`
- `dim_produto_classe_not_null` (n): `NOT NULL classe`
- `dim_produto_departamento_not_null` (n): `NOT NULL departamento`
- `dim_produto_e_perecivel_not_null` (n): `NOT NULL e_perecivel`
- `dim_produto_ean_not_null` (n): `NOT NULL ean`
- `dim_produto_nome_not_null` (n): `NOT NULL nome`
- `dim_produto_produto_id_not_null` (n): `NOT NULL produto_id`
- `dim_produto_sku_interno_not_null` (n): `NOT NULL sku_interno`
- `dim_produto_unidade_medida_not_null` (n): `NOT NULL unidade_medida`
- `dim_produto_pkey` (PK): `PRIMARY KEY (produto_id)`

**Índices adicionais:**

- `ix_dim_produto_departamento`: `CREATE INDEX ix_dim_produto_departamento ON ouro.dim_produto USING btree (departamento, classe)`
- `ix_dim_produto_perecivel`: `CREATE INDEX ix_dim_produto_perecivel ON ouro.dim_produto USING btree (e_perecivel) WHERE e_perecivel`

---

## `ouro.dim_promocao`

Dimensão promoção com duração calculada.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `promocao_id` | `bigint(64,0)` | não |  |
| `codigo` | `text` | não |  |
| `descricao` | `text` | não |  |
| `tipo` | `text` | não |  |
| `data_inicio` | `date` | não |  |
| `data_fim` | `date` | não |  |
| `duracao_dias` | `integer(32,0)` | não |  |
| `desconto_pct` | `numeric(7,4)` | sim |  |

**Constraints:**

- `dim_promocao_codigo_not_null` (n): `NOT NULL codigo`
- `dim_promocao_data_fim_not_null` (n): `NOT NULL data_fim`
- `dim_promocao_data_inicio_not_null` (n): `NOT NULL data_inicio`
- `dim_promocao_descricao_not_null` (n): `NOT NULL descricao`
- `dim_promocao_duracao_dias_not_null` (n): `NOT NULL duracao_dias`
- `dim_promocao_promocao_id_not_null` (n): `NOT NULL promocao_id`
- `dim_promocao_tipo_not_null` (n): `NOT NULL tipo`
- `dim_promocao_pkey` (PK): `PRIMARY KEY (promocao_id)`

---

## `ouro.dim_tempo`

Dimensão de tempo desnormalizada para leitura.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `data` | `date` | não |  |
| `ano` | `smallint(16,0)` | não |  |
| `trimestre` | `smallint(16,0)` | não |  |
| `mes` | `smallint(16,0)` | não |  |
| `nome_mes` | `text` | não |  |
| `dia` | `smallint(16,0)` | não |  |
| `dia_semana_iso` | `smallint(16,0)` | não |  |
| `nome_dia_semana` | `text` | não |  |
| `is_fim_semana` | `boolean` | não |  |
| `is_feriado` | `boolean` | não |  |
| `nome_feriado` | `text` | sim |  |
| `is_pagamento` | `boolean` | não |  |
| `ano_mes` | `text` | não |  |
| `semanas_no_mes` | `smallint(16,0)` | não |  |

**Constraints:**

- `dim_tempo_ano_mes_not_null` (n): `NOT NULL ano_mes`
- `dim_tempo_ano_not_null` (n): `NOT NULL ano`
- `dim_tempo_data_not_null` (n): `NOT NULL data`
- `dim_tempo_dia_not_null` (n): `NOT NULL dia`
- `dim_tempo_dia_semana_iso_not_null` (n): `NOT NULL dia_semana_iso`
- `dim_tempo_is_feriado_not_null` (n): `NOT NULL is_feriado`
- `dim_tempo_is_fim_semana_not_null` (n): `NOT NULL is_fim_semana`
- `dim_tempo_is_pagamento_not_null` (n): `NOT NULL is_pagamento`
- `dim_tempo_mes_not_null` (n): `NOT NULL mes`
- `dim_tempo_nome_dia_semana_not_null` (n): `NOT NULL nome_dia_semana`
- `dim_tempo_nome_mes_not_null` (n): `NOT NULL nome_mes`
- `dim_tempo_semanas_no_mes_not_null` (n): `NOT NULL semanas_no_mes`
- `dim_tempo_trimestre_not_null` (n): `NOT NULL trimestre`
- `dim_tempo_pkey` (PK): `PRIMARY KEY (data)`

---

## `ouro.fato_compras`

Fato de compras. Grão: um item de pedido.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `pedido_id` | `bigint(64,0)` | não |  |
| `item_seq` | `smallint(16,0)` | não |  |
| `data_pedido` | `date` | não |  |
| `data_previsao` | `date` | não |  |
| `data_entrega` | `date` | sim |  |
| `loja_id` | `bigint(64,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `fornecedor_id` | `bigint(64,0)` | não |  |
| `quantidade_pedida` | `numeric(14,3)` | não |  |
| `quantidade_entregue` | `numeric(14,3)` | não |  |
| `valor_total` | `numeric(14,2)` | não |  |
| `dias_atraso` | `integer(32,0)` | sim |  |
| `entrega_completa` | `boolean` | não |  |
| `no_prazo` | `boolean` | sim |  |

**Constraints:**

- `fato_compras_data_pedido_fkey` (FK): `FOREIGN KEY (data_pedido) REFERENCES ouro.dim_tempo(data)`
- `fato_compras_fornecedor_id_fkey` (FK): `FOREIGN KEY (fornecedor_id) REFERENCES ouro.dim_fornecedor(fornecedor_id)`
- `fato_compras_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES ouro.dim_loja(loja_id)`
- `fato_compras_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES ouro.dim_produto(produto_id)`
- `fato_compras_data_pedido_not_null` (n): `NOT NULL data_pedido`
- `fato_compras_data_previsao_not_null` (n): `NOT NULL data_previsao`
- `fato_compras_entrega_completa_not_null` (n): `NOT NULL entrega_completa`
- `fato_compras_fornecedor_id_not_null` (n): `NOT NULL fornecedor_id`
- `fato_compras_item_seq_not_null` (n): `NOT NULL item_seq`
- `fato_compras_loja_id_not_null` (n): `NOT NULL loja_id`
- `fato_compras_pedido_id_not_null` (n): `NOT NULL pedido_id`
- `fato_compras_produto_id_not_null` (n): `NOT NULL produto_id`
- `fato_compras_quantidade_entregue_not_null` (n): `NOT NULL quantidade_entregue`
- `fato_compras_quantidade_pedida_not_null` (n): `NOT NULL quantidade_pedida`
- `fato_compras_valor_total_not_null` (n): `NOT NULL valor_total`
- `fato_compras_pkey` (PK): `PRIMARY KEY (pedido_id, item_seq)`

**Índices adicionais:**

- `ix_fato_compras_fornecedor`: `CREATE INDEX ix_fato_compras_fornecedor ON ouro.fato_compras USING btree (fornecedor_id, data_pedido)`

---

## `ouro.fato_estoque_diario`

Fato de estoque. Grão: um SKU-loja-dia.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `data_ref` | `date` | não |  |
| `loja_id` | `bigint(64,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `qtd_inicio` | `numeric(14,3)` | não |  |
| `qtd_entradas` | `numeric(14,3)` | não |  |
| `qtd_saidas` | `numeric(14,3)` | não |  |
| `qtd_ajustes` | `numeric(14,3)` | não |  |
| `qtd_fim` | `numeric(14,3)` | não |  |
| `qtd_contada` | `numeric(14,3)` | sim |  |
| `divergencia_inventario` | `numeric(14,3)` | sim |  |
| `divergencia_pct` | `numeric(8,3)` | sim |  |
| `houve_ruptura` | `boolean` | não |  |
| `horas_sem_estoque` | `numeric(4,2)` | não |  |
| `valor_estoque` | `numeric(14,2)` | sim |  |

**Constraints:**

- `fato_estoque_diario_data_ref_fkey` (FK): `FOREIGN KEY (data_ref) REFERENCES ouro.dim_tempo(data)`
- `fato_estoque_diario_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES ouro.dim_loja(loja_id)`
- `fato_estoque_diario_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES ouro.dim_produto(produto_id)`
- `fato_estoque_diario_data_ref_not_null` (n): `NOT NULL data_ref`
- `fato_estoque_diario_horas_sem_estoque_not_null` (n): `NOT NULL horas_sem_estoque`
- `fato_estoque_diario_houve_ruptura_not_null` (n): `NOT NULL houve_ruptura`
- `fato_estoque_diario_loja_id_not_null` (n): `NOT NULL loja_id`
- `fato_estoque_diario_produto_id_not_null` (n): `NOT NULL produto_id`
- `fato_estoque_diario_qtd_ajustes_not_null` (n): `NOT NULL qtd_ajustes`
- `fato_estoque_diario_qtd_entradas_not_null` (n): `NOT NULL qtd_entradas`
- `fato_estoque_diario_qtd_fim_not_null` (n): `NOT NULL qtd_fim`
- `fato_estoque_diario_qtd_inicio_not_null` (n): `NOT NULL qtd_inicio`
- `fato_estoque_diario_qtd_saidas_not_null` (n): `NOT NULL qtd_saidas`
- `fato_estoque_diario_pkey` (PK): `PRIMARY KEY (data_ref, loja_id, produto_id)`

**Índices adicionais:**

- `ix_fato_estoque_produto`: `CREATE INDEX ix_fato_estoque_produto ON ouro.fato_estoque_diario USING btree (produto_id, data_ref)`
- `ix_fato_estoque_ruptura`: `CREATE INDEX ix_fato_estoque_ruptura ON ouro.fato_estoque_diario USING btree (loja_id, data_ref) WHERE houve_ruptura`

---

## `ouro.fato_vendas`

Fato de vendas. Grão: uma linha de cupom.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `venda_id` | `bigint(64,0)` | não |  |
| `item_seq` | `smallint(16,0)` | não |  |
| `data_venda` | `date` | não |  |
| `loja_id` | `bigint(64,0)` | não |  |
| `produto_id` | `bigint(64,0)` | não |  |
| `promocao_id` | `bigint(64,0)` | sim |  |
| `quantidade` | `numeric(14,3)` | não |  |
| `valor_bruto` | `numeric(14,2)` | não |  |
| `valor_desconto` | `numeric(14,2)` | não |  |
| `valor_liquido` | `numeric(14,2)` | não |  |
| `custo_total` | `numeric(14,2)` | sim |  |
| `margem_liquida` | `numeric(14,2)` | sim |  |
| `em_promocao` | `boolean` | não |  |

**Constraints:**

- `fato_vendas_data_venda_fkey` (FK): `FOREIGN KEY (data_venda) REFERENCES ouro.dim_tempo(data)`
- `fato_vendas_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES ouro.dim_loja(loja_id)`
- `fato_vendas_produto_id_fkey` (FK): `FOREIGN KEY (produto_id) REFERENCES ouro.dim_produto(produto_id)`
- `fato_vendas_promocao_id_fkey` (FK): `FOREIGN KEY (promocao_id) REFERENCES ouro.dim_promocao(promocao_id)`
- `fato_vendas_data_venda_not_null` (n): `NOT NULL data_venda`
- `fato_vendas_em_promocao_not_null` (n): `NOT NULL em_promocao`
- `fato_vendas_item_seq_not_null` (n): `NOT NULL item_seq`
- `fato_vendas_loja_id_not_null` (n): `NOT NULL loja_id`
- `fato_vendas_produto_id_not_null` (n): `NOT NULL produto_id`
- `fato_vendas_quantidade_not_null` (n): `NOT NULL quantidade`
- `fato_vendas_valor_bruto_not_null` (n): `NOT NULL valor_bruto`
- `fato_vendas_valor_desconto_not_null` (n): `NOT NULL valor_desconto`
- `fato_vendas_valor_liquido_not_null` (n): `NOT NULL valor_liquido`
- `fato_vendas_venda_id_not_null` (n): `NOT NULL venda_id`
- `fato_vendas_pkey` (PK): `PRIMARY KEY (data_venda, venda_id, item_seq)`

**Índices adicionais:**

- `ix_fato_vendas_loja`: `CREATE INDEX ix_fato_vendas_loja ON ouro.fato_vendas USING btree (loja_id, data_venda)`
- `ix_fato_vendas_produto`: `CREATE INDEX ix_fato_vendas_produto ON ouro.fato_vendas USING btree (produto_id, data_venda) INCLUDE (quantidade, valor_liquido)`
- `ix_fato_vendas_promocao`: `CREATE INDEX ix_fato_vendas_promocao ON ouro.fato_vendas USING btree (promocao_id) WHERE em_promocao`

---

# Schema `gov`

Governança — quarentena, linhagem, métricas de qualidade e auditoria.

## `gov.auditoria`

Trilha de auditoria. Base para LGPD art. 37.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `auditoria_id` | `bigint(64,0)` | não |  |
| `ocorrido_em` | `timestamptz` | não |  |
| `usuario` | `text` | não |  |
| `acao` | `text` | não |  |
| `entidade` | `text` | não |  |
| `chave` | `text` | sim |  |
| `dados_antes` | `jsonb` | sim |  |
| `dados_depois` | `jsonb` | sim |  |
| `ip` | `inet` | sim |  |

**Constraints:**

- `auditoria_acao_ck` (CHECK): `CHECK ((acao = ANY (ARRAY['INSERT'::text, 'UPDATE'::text, 'DELETE'::text, 'SELECT_SENSIVEL'::text, 'LOGIN'::text, 'EXPORT'::text])))`
- `auditoria_acao_not_null` (n): `NOT NULL acao`
- `auditoria_auditoria_id_not_null` (n): `NOT NULL auditoria_id`
- `auditoria_entidade_not_null` (n): `NOT NULL entidade`
- `auditoria_ocorrido_em_not_null` (n): `NOT NULL ocorrido_em`
- `auditoria_usuario_not_null` (n): `NOT NULL usuario`
- `auditoria_pkey` (PK): `PRIMARY KEY (auditoria_id)`

**Índices adicionais:**

- `ix_auditoria_data`: `CREATE INDEX ix_auditoria_data ON gov.auditoria USING btree (ocorrido_em DESC)`
- `ix_auditoria_entidade`: `CREATE INDEX ix_auditoria_entidade ON gov.auditoria USING btree (entidade, chave)`

---

## `gov.lote_carga`

Auditoria de cada execução de carga. `lote_carga_id` é a chave de linhagem de todo dado.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `lote_id` | `bigint(64,0)` | não |  |
| `origem` | `text` | não |  |
| `arquivo` | `text` | sim |  |
| `hash_arquivo` | `text` | sim | SHA-256 do arquivo. Reimportar o mesmo arquivo e detectavel e idempotente. |
| `data_referencia` | `date` | sim |  |
| `iniciado_em` | `timestamptz` | não |  |
| `finalizado_em` | `timestamptz` | sim |  |
| `status` | `text` | não |  |
| `linhas_lidas` | `integer(32,0)` | não |  |
| `linhas_aceitas` | `integer(32,0)` | não |  |
| `linhas_rejeitadas` | `integer(32,0)` | não |  |
| `mensagem` | `text` | sim |  |

**Constraints:**

- `lote_contagem_ck` (CHECK): `CHECK (((linhas_aceitas + linhas_rejeitadas) <= linhas_lidas))`
- `lote_status_ck` (CHECK): `CHECK ((status = ANY (ARRAY['EM_ANDAMENTO'::text, 'CONCLUIDO'::text, 'FALHOU'::text, 'PARCIAL'::text])))`
- `lote_carga_iniciado_em_not_null` (n): `NOT NULL iniciado_em`
- `lote_carga_linhas_aceitas_not_null` (n): `NOT NULL linhas_aceitas`
- `lote_carga_linhas_lidas_not_null` (n): `NOT NULL linhas_lidas`
- `lote_carga_linhas_rejeitadas_not_null` (n): `NOT NULL linhas_rejeitadas`
- `lote_carga_lote_id_not_null` (n): `NOT NULL lote_id`
- `lote_carga_origem_not_null` (n): `NOT NULL origem`
- `lote_carga_status_not_null` (n): `NOT NULL status`
- `lote_carga_pkey` (PK): `PRIMARY KEY (lote_id)`

---

## `gov.metrica_qualidade`

Score de qualidade por loja e dimensão. Alimenta o selo de confiança.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `metrica_id` | `bigint(64,0)` | não |  |
| `lote_id` | `bigint(64,0)` | sim |  |
| `loja_id` | `bigint(64,0)` | sim |  |
| `data_ref` | `date` | não |  |
| `dimensao` | `text` | não |  |
| `total_registros` | `bigint(64,0)` | não |  |
| `registros_ok` | `bigint(64,0)` | não |  |
| `registros_problema` | `bigint(64,0)` | não |  |
| `score_pct` | `numeric(6,3)` | sim |  |
| `calculado_em` | `timestamptz` | não |  |

**Constraints:**

- `metrica_dimensao_ck` (CHECK): `CHECK ((dimensao = ANY (ARRAY['completude'::text, 'unicidade'::text, 'consistencia'::text, 'validade'::text, 'acuracidade'::text, 'atualidade'::text, 'conformidade'::text])))`
- `metrica_soma_ck` (CHECK): `CHECK (((registros_ok + registros_problema) = total_registros))`
- `metrica_qualidade_loja_id_fkey` (FK): `FOREIGN KEY (loja_id) REFERENCES prata.loja(loja_id) ON DELETE CASCADE`
- `metrica_qualidade_lote_id_fkey` (FK): `FOREIGN KEY (lote_id) REFERENCES gov.lote_carga(lote_id) ON DELETE CASCADE`
- `metrica_qualidade_calculado_em_not_null` (n): `NOT NULL calculado_em`
- `metrica_qualidade_data_ref_not_null` (n): `NOT NULL data_ref`
- `metrica_qualidade_dimensao_not_null` (n): `NOT NULL dimensao`
- `metrica_qualidade_metrica_id_not_null` (n): `NOT NULL metrica_id`
- `metrica_qualidade_registros_ok_not_null` (n): `NOT NULL registros_ok`
- `metrica_qualidade_registros_problema_not_null` (n): `NOT NULL registros_problema`
- `metrica_qualidade_total_registros_not_null` (n): `NOT NULL total_registros`
- `metrica_qualidade_pkey` (PK): `PRIMARY KEY (metrica_id)`

**Índices adicionais:**

- `ix_metrica_loja_data`: `CREATE INDEX ix_metrica_loja_data ON gov.metrica_qualidade USING btree (loja_id, data_ref)`

---

## `gov.quarentena`

Registros rejeitados com `reason_code` e payload original em JSONB. Nunca descarte silencioso.

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `quarentena_id` | `bigint(64,0)` | não |  |
| `lote_id` | `bigint(64,0)` | não |  |
| `regra_id` | `integer(32,0)` | não |  |
| `entidade` | `text` | não |  |
| `chave_registro` | `text` | sim |  |
| `payload` | `jsonb` | não |  |
| `motivo` | `text` | não |  |
| `detectado_em` | `timestamptz` | não |  |
| `resolvido` | `boolean` | não |  |
| `resolvido_em` | `timestamptz` | sim |  |
| `resolvido_por` | `text` | sim |  |

**Constraints:**

- `quarentena_resolucao_ck` (CHECK): `CHECK ((((resolvido = false) AND (resolvido_em IS NULL)) OR ((resolvido = true) AND (resolvido_em IS NOT NULL))))`
- `quarentena_lote_id_fkey` (FK): `FOREIGN KEY (lote_id) REFERENCES gov.lote_carga(lote_id) ON DELETE CASCADE`
- `quarentena_regra_id_fkey` (FK): `FOREIGN KEY (regra_id) REFERENCES gov.regra_qualidade(regra_id) ON DELETE RESTRICT`
- `quarentena_detectado_em_not_null` (n): `NOT NULL detectado_em`
- `quarentena_entidade_not_null` (n): `NOT NULL entidade`
- `quarentena_lote_id_not_null` (n): `NOT NULL lote_id`
- `quarentena_motivo_not_null` (n): `NOT NULL motivo`
- `quarentena_payload_not_null` (n): `NOT NULL payload`
- `quarentena_quarentena_id_not_null` (n): `NOT NULL quarentena_id`
- `quarentena_regra_id_not_null` (n): `NOT NULL regra_id`
- `quarentena_resolvido_not_null` (n): `NOT NULL resolvido`
- `quarentena_pkey` (PK): `PRIMARY KEY (quarentena_id)`

**Índices adicionais:**

- `ix_quarentena_lote`: `CREATE INDEX ix_quarentena_lote ON gov.quarentena USING btree (lote_id)`
- `ix_quarentena_payload`: `CREATE INDEX ix_quarentena_payload ON gov.quarentena USING gin (payload jsonb_path_ops)`
- `ix_quarentena_pendente`: `CREATE INDEX ix_quarentena_pendente ON gov.quarentena USING btree (detectado_em) WHERE (resolvido = false)`
- `ix_quarentena_regra`: `CREATE INDEX ix_quarentena_regra ON gov.quarentena USING btree (regra_id)`

---

## `gov.regra_qualidade`

Catálogo das 21 regras de qualidade (DQ001..DQ021).

| Coluna | Tipo | Nulo | Descrição |
|---|---|---|---|
| `regra_id` | `integer(32,0)` | não |  |
| `codigo` | `text` | não |  |
| `dimensao` | `text` | não |  |
| `descricao` | `text` | não |  |
| `severidade` | `text` | não |  |
| `acao` | `text` | não |  |
| `expressao_sql` | `text` | sim |  |
| `ativa` | `boolean` | não |  |

**Constraints:**

- `dq_acao_ck` (CHECK): `CHECK ((acao = ANY (ARRAY['rejeitar'::text, 'quarentena'::text, 'corrigir'::text, 'alertar'::text])))`
- `dq_dimensao_ck` (CHECK): `CHECK ((dimensao = ANY (ARRAY['completude'::text, 'unicidade'::text, 'consistencia'::text, 'validade'::text, 'acuracidade'::text, 'atualidade'::text, 'conformidade'::text])))`
- `dq_severidade_ck` (CHECK): `CHECK ((severidade = ANY (ARRAY['critica'::text, 'alta'::text, 'media'::text, 'baixa'::text])))`
- `regra_qualidade_acao_not_null` (n): `NOT NULL acao`
- `regra_qualidade_ativa_not_null` (n): `NOT NULL ativa`
- `regra_qualidade_codigo_not_null` (n): `NOT NULL codigo`
- `regra_qualidade_descricao_not_null` (n): `NOT NULL descricao`
- `regra_qualidade_dimensao_not_null` (n): `NOT NULL dimensao`
- `regra_qualidade_regra_id_not_null` (n): `NOT NULL regra_id`
- `regra_qualidade_severidade_not_null` (n): `NOT NULL severidade`
- `regra_qualidade_pkey` (PK): `PRIMARY KEY (regra_id)`
- `regra_qualidade_codigo_key` (UNIQUE): `UNIQUE (codigo)`

**Índices adicionais:**

- `regra_qualidade_codigo_key`: `CREATE UNIQUE INDEX regra_qualidade_codigo_key ON gov.regra_qualidade USING btree (codigo)`

---

# Views materializadas

Views pré-computadas que sustentam o dashboard e a previsão. O `REFRESH` roda ao final de cada carga.

## `ouro.mv_demanda_diaria`

<details><summary>Definição SQL</summary>

```sql
WITH base AS (
         SELECT e.data_ref AS data_venda,
            e.loja_id,
            e.produto_id,
            COALESCE(sum(f.quantidade), (0)::numeric) AS qtd_vendida,
            COALESCE(sum(f.valor_liquido), (0)::numeric) AS receita,
            COALESCE(sum(f.custo_total), (0)::numeric) AS custo,
            COALESCE(bool_or(f.em_promocao), false) AS em_promocao,
            e.houve_ruptura,
            e.qtd_fim,
            e.horas_sem_estoque
           FROM (ouro.fato_estoque_diario e
             LEFT JOIN ouro.fato_vendas f ON (((f.data_venda = e.data_ref) AND (f.loja_id = e.loja_id) AND (f.produto_id = e.produto_id))))
          GROUP BY e.data_ref, e.loja_id, e.produto_id, e.houve_ruptura, e.qtd_fim, e.horas_sem_estoque
        ), referencia AS (
         SELECT b_1.produto_id,
            b_1.loja_id,
            t_1.dia_semana_iso,
            avg(b_1.qtd_vendida) FILTER (WHERE (NOT b_1.houve_ruptura)) AS media_sem_ruptura,
            count(*) FILTER (WHERE (NOT b_1.houve_ruptura)) AS dias_referencia
           FROM (base b_1
             JOIN ouro.dim_tempo t_1 ON ((t_1.data = b_1.data_venda)))
          GROUP BY b_1.produto_id, b_1.loja_id, t_1.dia_semana_iso
        )
 SELECT b.data_venda,
    b.loja_id,
    b.produto_id,
    t.ano_mes,
    t.dia_semana_iso,
    t.is_fim_semana,
    t.is_feriado,
    t.is_pagamento,
    b.qtd_vendida,
    b.receita,
    b.custo,
    b.em_promocao,
    b.houve_ruptura,
    COALESCE(b.horas_sem_estoque, (0)::numeric) AS horas_sem_estoque,
        CASE
            WHEN (b.houve_ruptura AND (r.media_sem_ruptura IS NOT NULL) AND (r.media_sem_ruptura > b.qtd_vendida)) THEN r.media_sem_ruptura
            ELSE b.qtd_vendida
        END AS qtd_demanda,
        CASE
            WHEN (b.houve_ruptura AND (r.media_sem_ruptura > b.qtd_vendida)) THEN 'reconstruida'::text
            WHEN b.houve_ruptura THEN 'observada_em_ruptura'::text
            ELSE 'observada'::text
        END AS fonte_demanda,
    r.media_sem_ruptura,
    COALESCE(r.dias_referencia, (0)::bigint) AS dias_referencia
   FROM ((base b
     JOIN ouro.dim_tempo t ON ((t.data = b.data_venda)))
     LEFT JOIN referencia r ON (((r.produto_id = b.produto_id) AND (r.loja_id = b.loja_id) AND (r.dia_semana_iso = t.dia_semana_iso))));
```

</details>

## `ouro.mv_previsao_demanda`

<details><summary>Definição SQL</summary>

```sql
WITH serie AS (
         SELECT d.loja_id,
            d.produto_id,
            d.data_venda,
            d.qtd_demanda,
            d.dia_semana_iso,
            d.is_feriado,
            row_number() OVER (PARTITION BY d.loja_id, d.produto_id ORDER BY d.data_venda DESC) AS rn
           FROM ouro.mv_demanda_diaria d
        ), ewma AS (
         SELECT serie.loja_id,
            serie.produto_id,
            (sum((serie.qtd_demanda * power(((1)::numeric - (2.0 / (29)::numeric)), ((serie.rn - 1))::numeric))) / NULLIF(sum(power(((1)::numeric - (2.0 / (29)::numeric)), ((serie.rn - 1))::numeric)), (0)::numeric)) AS nivel,
            count(*) AS dias_base
           FROM serie
          WHERE (serie.rn <= 28)
          GROUP BY serie.loja_id, serie.produto_id
        ), fator_dw_base AS (
         SELECT mv_demanda_diaria.loja_id,
            mv_demanda_diaria.produto_id,
            mv_demanda_diaria.dia_semana_iso,
            avg(mv_demanda_diaria.qtd_demanda) AS media_dia
           FROM ouro.mv_demanda_diaria
          GROUP BY mv_demanda_diaria.loja_id, mv_demanda_diaria.produto_id, mv_demanda_diaria.dia_semana_iso
        ), fator_dw AS (
         SELECT fator_dw_base.loja_id,
            fator_dw_base.produto_id,
            fator_dw_base.dia_semana_iso,
            (fator_dw_base.media_dia / NULLIF(avg(fator_dw_base.media_dia) OVER (PARTITION BY fator_dw_base.loja_id, fator_dw_base.produto_id), (0)::numeric)) AS fator
           FROM fator_dw_base
        ), efeito_feriado AS (
         SELECT mv_demanda_diaria.loja_id,
            mv_demanda_diaria.produto_id,
            COALESCE((avg(mv_demanda_diaria.qtd_demanda) FILTER (WHERE mv_demanda_diaria.is_feriado) / NULLIF(avg(mv_demanda_diaria.qtd_demanda) FILTER (WHERE (NOT mv_demanda_diaria.is_feriado)), (0)::numeric)), 1.0) AS fator
           FROM ouro.mv_demanda_diaria
          GROUP BY mv_demanda_diaria.loja_id, mv_demanda_diaria.produto_id
        ), ref_departamento AS (
         SELECT d.loja_id,
            p.departamento,
            percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((d.qtd_demanda)::double precision)) AS mediana
           FROM (ouro.mv_demanda_diaria d
             JOIN ouro.dim_produto p USING (produto_id))
          GROUP BY d.loja_id, p.departamento
        ), ref_loja AS (
         SELECT mv_demanda_diaria.loja_id,
            percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((mv_demanda_diaria.qtd_demanda)::double precision)) AS mediana
           FROM ouro.mv_demanda_diaria
          GROUP BY mv_demanda_diaria.loja_id
        ), universo AS (
         SELECT l.loja_id,
            p.produto_id,
            p.departamento
           FROM (prata.loja l
             CROSS JOIN ouro.dim_produto p)
          WHERE (l.ativa AND p.ativo)
        )
 SELECT u.loja_id,
    u.produto_id,
    ds.dia_semana_iso,
    round(COALESCE(fw.media_dia, (0)::numeric), 4) AS media_dia,
    round(COALESCE(f.fator, 1.0), 4) AS fator_dia_semana,
    round(COALESCE(ef.fator, 1.0), 4) AS fator_feriado,
    round((COALESCE((e.nivel)::double precision, rd.mediana, rl.mediana, (0.10)::double precision))::numeric, 4) AS nivel_ewma,
    COALESCE(e.dias_base, (0)::bigint) AS dias_base,
        CASE
            WHEN (e.nivel IS NOT NULL) THEN 'proprio'::text
            WHEN (rd.mediana IS NOT NULL) THEN 'departamento'::text
            WHEN (rl.mediana IS NOT NULL) THEN 'loja'::text
            ELSE 'sem_referencia'::text
        END AS origem_previsao
   FROM (((((((universo u
     CROSS JOIN generate_series(1, 7) ds(dia_semana_iso))
     LEFT JOIN fator_dw_base fw ON (((fw.loja_id = u.loja_id) AND (fw.produto_id = u.produto_id) AND (fw.dia_semana_iso = ds.dia_semana_iso))))
     LEFT JOIN fator_dw f ON (((f.loja_id = u.loja_id) AND (f.produto_id = u.produto_id) AND (f.dia_semana_iso = ds.dia_semana_iso))))
     LEFT JOIN efeito_feriado ef ON (((ef.loja_id = u.loja_id) AND (ef.produto_id = u.produto_id))))
     LEFT JOIN ewma e ON (((e.loja_id = u.loja_id) AND (e.produto_id = u.produto_id))))
     LEFT JOIN ref_departamento rd ON (((rd.loja_id = u.loja_id) AND (rd.departamento = u.departamento))))
     LEFT JOIN ref_loja rl ON ((rl.loja_id = u.loja_id)));
```

</details>

## `ouro.mv_qualidade_loja`

<details><summary>Definição SQL</summary>

```sql
WITH por_loja AS (
         SELECT metrica_qualidade.loja_id,
            count(*) AS dimensoes_medidas,
            round(avg(metrica_qualidade.score_pct), 2) AS score_medio_pct,
            round(min(metrica_qualidade.score_pct), 2) AS pior_dimensao_pct,
            (array_agg(metrica_qualidade.dimensao ORDER BY metrica_qualidade.score_pct))[1] AS dimensao_critica
           FROM gov.metrica_qualidade
          GROUP BY metrica_qualidade.loja_id
        )
 SELECT l.loja_id,
    l.nome AS loja,
    COALESCE(pl.dimensoes_medidas, (0)::bigint) AS dimensoes_medidas,
    pl.score_medio_pct,
    pl.pior_dimensao_pct,
    pl.dimensao_critica,
        CASE
            WHEN (pl.pior_dimensao_pct >= (95)::numeric) THEN 'CONFIAVEL'::text
            WHEN (pl.pior_dimensao_pct >= (85)::numeric) THEN 'ATENCAO'::text
            ELSE 'NAO_CONFIAVEL'::text
        END AS selo
   FROM (ouro.dim_loja l
     LEFT JOIN por_loja pl ON ((pl.loja_id = l.loja_id)));
```

</details>

## `ouro.mv_rupturas`

<details><summary>Definição SQL</summary>

```sql
WITH referencia AS (
         SELECT d.produto_id,
            d.loja_id,
            d.dia_semana_iso,
            avg(d.qtd_demanda) AS media_sem_ruptura,
            count(*) AS dias_referencia
           FROM ouro.mv_demanda_diaria d
          WHERE (NOT d.houve_ruptura)
          GROUP BY d.produto_id, d.loja_id, d.dia_semana_iso
        ), ruptura AS (
         SELECT e.data_ref AS data_venda,
            t.ano_mes,
            e.loja_id,
            e.produto_id,
            COALESCE(sum(f.quantidade), (0)::numeric) AS qtd_vendida,
            COALESCE(sum(f.valor_liquido), (0)::numeric) AS receita,
            t.dia_semana_iso
           FROM ((ouro.fato_estoque_diario e
             JOIN ouro.dim_tempo t ON ((t.data = e.data_ref)))
             LEFT JOIN ouro.fato_vendas f ON (((f.data_venda = e.data_ref) AND (f.loja_id = e.loja_id) AND (f.produto_id = e.produto_id))))
          WHERE e.houve_ruptura
          GROUP BY e.data_ref, t.ano_mes, e.loja_id, e.produto_id, t.dia_semana_iso
        )
 SELECT r.data_venda,
    r.ano_mes,
    r.loja_id,
    l.nome AS loja,
    r.produto_id,
    p.nome AS produto,
    p.departamento,
    r.qtd_vendida,
    COALESCE(ref.media_sem_ruptura, (0)::numeric) AS demanda_esperada,
    round(GREATEST((0)::numeric, (COALESCE(ref.media_sem_ruptura, (0)::numeric) - r.qtd_vendida)), 3) AS demanda_perdida_un,
    round((GREATEST((0)::numeric, (COALESCE(ref.media_sem_ruptura, (0)::numeric) - r.qtd_vendida)) * p.preco_venda_atual), 2) AS receita_perdida_estimada
   FROM (((ruptura r
     JOIN ouro.dim_loja l ON ((l.loja_id = r.loja_id)))
     JOIN ouro.dim_produto p ON ((p.produto_id = r.produto_id)))
     LEFT JOIN referencia ref ON (((ref.produto_id = r.produto_id) AND (ref.loja_id = r.loja_id) AND (ref.dia_semana_iso = r.dia_semana_iso))));
```

</details>

## `ouro.mv_sugestao_compra`

<details><summary>Definição SQL</summary>

```sql
WITH ultimo AS (
         SELECT e.loja_id,
            e.produto_id,
            e.qtd_fim,
            e.data_ref,
            e.houve_ruptura,
            row_number() OVER (PARTITION BY e.loja_id, e.produto_id ORDER BY e.data_ref DESC) AS rn
           FROM ouro.fato_estoque_diario e
        ), previsao_diaria AS (
         SELECT mv_previsao_demanda.loja_id,
            mv_previsao_demanda.produto_id,
            avg((mv_previsao_demanda.nivel_ewma * mv_previsao_demanda.fator_dia_semana)) AS demanda_dia
           FROM ouro.mv_previsao_demanda
          GROUP BY mv_previsao_demanda.loja_id, mv_previsao_demanda.produto_id
        ), volatilidade AS (
         SELECT mv_demanda_diaria.loja_id,
            mv_demanda_diaria.produto_id,
            COALESCE(stddev_samp(mv_demanda_diaria.qtd_demanda), (0)::numeric) AS sigma_dia
           FROM ouro.mv_demanda_diaria
          GROUP BY mv_demanda_diaria.loja_id, mv_demanda_diaria.produto_id
        ), info AS (
         SELECT pf.produto_id,
            pf.fornecedor_id,
            pf.lead_time_dias,
            pf.lote_minimo,
            pf.multiplo_compra,
            pf.custo_unitario,
            f.razao_social
           FROM (prata.produto_fornecedor pf
             JOIN ouro.dim_fornecedor f ON ((f.fornecedor_id = pf.fornecedor_id)))
          WHERE pf.preferencial
        )
 SELECT u.loja_id,
    u.produto_id,
    dp.nome AS produto,
    dp.departamento,
    dp.e_perecivel,
    u.data_ref AS referencia_estoque,
    round(u.qtd_fim, 3) AS estoque_atual,
    round(pd.demanda_dia, 3) AS demanda_dia_prevista,
    i.lead_time_dias,
    round((pd.demanda_dia * (i.lead_time_dias)::numeric), 2) AS demanda_lead_time,
    round(((((1.65 * v.sigma_dia))::double precision * sqrt((i.lead_time_dias)::double precision)))::numeric, 2) AS estoque_seguranca,
    round(((((pd.demanda_dia * (i.lead_time_dias)::numeric))::double precision + (((1.65 * v.sigma_dia))::double precision * sqrt((i.lead_time_dias)::double precision))))::numeric, 2) AS ponto_pedido,
    round(GREATEST((0)::numeric, (ceil(((GREATEST((0)::double precision, ((((pd.demanda_dia * (i.lead_time_dias)::numeric))::double precision + (((1.65 * v.sigma_dia))::double precision * sqrt((i.lead_time_dias)::double precision))) - (u.qtd_fim)::double precision)))::numeric / NULLIF((i.multiplo_compra)::numeric, (0)::numeric))) * (i.multiplo_compra)::numeric)), 2) AS quantidade_sugerida,
    round((u.qtd_fim / NULLIF(pd.demanda_dia, (0)::numeric)), 1) AS cobertura_dias,
        CASE
            WHEN (u.qtd_fim <= (0)::numeric) THEN 'RUPTURA'::text
            WHEN (u.qtd_fim < (pd.demanda_dia * (i.lead_time_dias)::numeric)) THEN 'CRITICO'::text
            WHEN ((u.qtd_fim)::double precision < (((pd.demanda_dia * (i.lead_time_dias)::numeric))::double precision + (((1.65 * v.sigma_dia))::double precision * sqrt((i.lead_time_dias)::double precision)))) THEN 'REPOR'::text
            ELSE 'OK'::text
        END AS situacao,
    i.razao_social AS fornecedor,
    round((GREATEST((0)::numeric, (ceil(((GREATEST((0)::double precision, ((((pd.demanda_dia * (i.lead_time_dias)::numeric))::double precision + (((1.65 * v.sigma_dia))::double precision * sqrt((i.lead_time_dias)::double precision))) - (u.qtd_fim)::double precision)))::numeric / NULLIF((i.multiplo_compra)::numeric, (0)::numeric))) * (i.multiplo_compra)::numeric)) * (i.custo_unitario)::numeric), 2) AS valor_compra_sugerido,
    ( SELECT round(avg(mq.score_pct), 1) AS round
           FROM gov.metrica_qualidade mq
          WHERE (mq.loja_id = u.loja_id)) AS score_qualidade_loja
   FROM ((((ultimo u
     JOIN ouro.dim_produto dp ON ((dp.produto_id = u.produto_id)))
     JOIN previsao_diaria pd ON (((pd.loja_id = u.loja_id) AND (pd.produto_id = u.produto_id))))
     JOIN volatilidade v ON (((v.loja_id = u.loja_id) AND (v.produto_id = u.produto_id))))
     JOIN info i ON ((i.produto_id = u.produto_id)))
  WHERE ((u.rn = 1) AND dp.ativo);
```

</details>
