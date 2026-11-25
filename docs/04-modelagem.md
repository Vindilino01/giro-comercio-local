# 4.4 — Organização e modelagem dos dados (Eixo 2)

## Três camadas, três propósitos

O projeto usa arquitetura em camadas dentro de um único banco.

| Camada | Formato | Modelo | Propósito |
|---|---|---|---|
| **Bronze** | CSV/XML imutável em disco | — | preservar o dado original |
| **Prata** | tabelas PostgreSQL | **3ª Forma Normal** | fonte de verdade transacional |
| **Ouro** | tabelas e views materializadas | **star schema** | consulta analítica |

Normalizar e desnormalizar resolvem problemas opostos.

A 3FN evita anomalia de atualização. Numa tabela desnormalizada de 4,1 milhões de
linhas, mudar o nome de uma categoria exigiria atualizar milhões de registros.
Normalizado, é uma linha.

O star schema evita join caro na leitura. O analista não deveria conhecer 15
tabelas normalizadas para responder "curva ABC".

Isso evita a duplicação: é a mesma informação organizada para dois padrões de
acesso. A prata é a fonte de verdade e o ouro é reconstruível a qualquer momento.

## Modelo conceitual

```
        ┌──────────┐           ┌────────────┐
        │  LOJA    │           │ CATEGORIA  │◄──┐ (hierarquia
        └────┬─────┘           └─────┬──────┘   │  auto-referenciada)
             │ 1                     │ 1        │
             │                       │          │
             │ N                     │ N        │
        ┌────▼─────────┐        ┌────▼──────┐   │
        │    VENDA     │        │  PRODUTO  ├───┘
        └────┬─────────┘        └─────┬─────┘
             │ 1                     │ 1
             │                       │
             │ N                     │ N
        ┌────▼─────────┐        ┌────▼──────────────┐
        │  ITEM_VENDA  ├───────►│ PRODUTO_FORNECEDOR│◄──┐
        └──────────────┘   N:1  └───────────────────┘   │ N
                                                    ┌───┴────────┐
        ┌──────────────────┐                        │ FORNECEDOR │
        │ ESTOQUE_SNAPSHOT │                        └───┬────────┘
        └────────┬─────────┘                            │ 1
                 │ N                                    │
                 │                                ┌─────▼──────┐
        ┌────────▼─────────┐                      │PEDIDO_COMPRA│
        │    PRODUTO       │◄─────────────────────┤            │
        └──────────────────┘        N:1           └─────┬──────┘
                                                       │ 1
                                                  ┌────▼────────┐
                                                  │ ITEM_PEDIDO │
                                                  └─────────────┘
```

Entidades de apoio: `CALENDARIO` (dimensão de tempo), `PROMOCAO` e
`PROMOCAO_PRODUTO` (N:N).

## Modelo lógico

### Chaves

Cada tabela tem duas chaves.

Uma `BIGINT GENERATED ALWAYS AS IDENTITY` como PK: estável, compacta, sem
semântica embutida. E uma ou mais chaves naturais `UNIQUE`, que permitem
deduplicação idempotente.

`prata.produto` tem `produto_id` e `ean` único. Sem a chave natural, reimportar um
arquivo criaria produtos duplicados. Com ela, `ON CONFLICT (ean) DO NOTHING`
resolve.

Por que não usar a natural como PK? Porque EAN muda quando o fabricante reformula,
CNPJ muda quando a loja é vendida, e o cupom pode ser reemitido. O surrogate isola
o modelo dessas mudanças. A natural continua sendo a regra de negócio, expressa
como `UNIQUE`.

**Bug encontrado por teste.** A chave natural de venda é
`(loja_id, data_venda, serie_cupom, numero_cupom)`, e `serie_cupom` é nullable. A
`UNIQUE` padrão considera cada `NULL` distinto. Dois cupons idênticos com série
NULL passariam, duplicando receita em silêncio. Corrigido com:

```sql
CONSTRAINT venda_chave_natural_uk
    UNIQUE NULLS NOT DISTINCT (loja_id, data_venda, serie_cupom, numero_cupom)
```

Evidência no caso C11 de `tests/test_constraints.py`.

### Relacionamentos

| Relacionamento | Cardinalidade | Exclusão | Justificativa |
|---|---|---|---|
| Loja → Venda | 1:N | `RESTRICT` | não se apaga loja com histórico |
| Venda → Item | 1:N | `CASCADE` | item não existe sem cupom |
| Produto → Item | 1:N | `RESTRICT` | produto usa soft delete |
| Produto → Categoria | N:1 | `RESTRICT` | categoria em uso não é removida |
| Produto ↔ Fornecedor | N:N | `CASCADE` | vínculo é descartável |
| Produto → Preço | 1:N | `CASCADE` | histórico acompanha o produto |

Produto usa `ativo = FALSE` em vez de `DELETE`. Apagar quebraria a FK de 4 milhões
de itens e destruiria a série temporal da previsão.

A FK de item de venda é composta: `(venda_id, data_venda)`. É exigência do
particionamento, não escolha estética.

### Domínios

Seis domínios e quatro funções reutilizáveis em `002_dominios.sql` e
`005_particoes.sql`.

| Domínio | Tipo base | Regra | Onde |
|---|---|---|---|
| `gov.ean13` | TEXT | 13 dígitos e **dígito verificador válido** | produto |
| `gov.quantidade` | NUMERIC(14,3) | ≥ 0 | estoque |
| `gov.quantidade_positiva` | NUMERIC(14,3) | > 0 | item de venda e pedido |
| `gov.dinheiro` | NUMERIC(14,2) | ≥ 0 | todos os valores |
| `gov.percentual` | NUMERIC(7,4) | 0–100 | desconto, margem |
| `gov.uf` | CHAR(2) | lista fechada das 27 UFs | loja, fornecedor |

Três decisões merecem justificativa.

O EAN tem dígito verificador em função PL/pgSQL, e não só uma regex. O EAN é a
chave natural do produto. Um dígito errado cria item fantasma que nunca se funde
com o real. A validação está em `gov.ean13_valido()` e foi conferida contra
implementação independente em Python.

A UF é lista fechada, não regex. A primeira versão usava `CHECK (uf ~ '^[A-Z]{2}$')`,
e um teste provou que `'XX'` passava.

Há duas variantes de quantidade. `quantidade` aceita zero (ruptura) e
`quantidade_positiva` não (item de venda). Um `CHECK` único forçaria o mais
permissivo em todos os lugares.

### Normalização

A prata está em 3FN.

| Forma | Como é atendida |
|---|---|
| 1FN | todo atributo é atômico; sem grupo repetido |
| 2FN | PK sempre atômica; sem dependência parcial |
| 3FN | sem dependência transitiva |

Guardar `preco_venda` em `item_venda` não é desnormalização. O preço praticado
naquela venda é fato histórico, não cópia do preço atual. Guardar apenas em
`produto` tornaria impossível calcular margem de período passado.

A ouro é desnormalizada de propósito. `ouro.dim_produto` achata a hierarquia de
dois níveis e resolve o preço vigente.

| Aspecto | Valor |
|---|---|
| Custo | ~420 linhas, recriadas por `TRUNCATE`/`INSERT` |
| Benefício | consulta sem self-join em `categoria` |
| Lado do fato | 4,1 milhões de linhas |
| Conclusão | desnormalizar 420 linhas para evitar joins em 4,1M compensa |

### Preço histórico

`produto_preco_historico` usa faixas meio-abertas.

```sql
PRIMARY KEY (produto_id, data_inicio)
CONSTRAINT preco_vigencia_ck CHECK (data_fim IS NULL OR data_fim > data_inicio)
```

Duas garantias com recursos nativos:

```sql
-- 1. No máximo uma faixa aberta por produto
CREATE UNIQUE INDEX produto_preco_uma_faixa_aberta
    ON prata.produto_preco_historico (produto_id) WHERE data_fim IS NULL;

-- 2. Faixas nunca se sobrepõem
ALTER TABLE prata.produto_preco_historico
    ADD CONSTRAINT produto_preco_sem_sobreposicao
    EXCLUDE USING gist (
        produto_id WITH =,
        daterange(data_inicio, COALESCE(data_fim, 'infinity'::date), '[)') WITH &&
    );
```

O `EXCLUDE` resolve, com uma constraint, o que a maioria dos sistemas resolve com
trigger. Usa índice GiST e precisa de `btree_gist` para combinar `=` com `&&`.

**O que existe hoje.** As duas garantias estão ativas e testadas (I08, I09). Há uma
faixa por item: 420 faixas, 420 itens. A estrutura suporta várias faixas, mas o CSV
traz um preço por produto, não uma série.

O mecanismo está implementado. O histórico de mudanças não está populado porque a
fonte não o tem. Se o CSV trouxesse `produto_id, data_inicio, preco`, a ingestão
gravaria as N faixas sem alterar o schema. A coluna `data_fim` é NULL em 420 de
420 linhas.

Efeito medido: antes, `dim_produto` inventava o preço como `custo / 0,7`. O erro
médio contra o preço do PDV era 11,62%. Agora lê a faixa vigente, e o erro caiu
para 1,13%. O resíduo é o desconto promocional. O histórico guarda o preço de
tabela, e a comparação usa o preço médio cobrado.

## Modelo físico

### Particionamento mensal

```sql
CREATE TABLE prata.venda (...) PARTITION BY RANGE (data_venda);
CREATE TABLE prata.venda_2025_01 PARTITION OF prata.venda
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

| Alternativa | Por que não |
|---|---|
| Sem partição | consulta de 30 dias varre 24 meses |
| Hash por loja | só ajuda consulta de loja única |
| Range por ano | consulta de 30 dias varre 12 meses |
| **Range por mês** | **consulta de 30 dias lê 1 ou 2 partições** |

O custo é que a PK e a FK precisam incluir `data_venda`. Em troca, o *partition
pruning* elimina a maior parte das linhas antes da leitura.

`gov.criar_particoes_mensais(inicio, fim)` é idempotente e roda antes de cada
carga. `gov.garantir_particoes()` mantém janela de 24 meses atrás a 6 à frente.
`gov.destacar_particao(mes)` existe para retenção.

### Índices

Nenhum índice sem consulta que o justifique. Índice ocupa disco e onera `INSERT`,
e o PDV insere o dia todo.

| Índice | Tipo | Consulta |
|---|---|---|
| `(loja_id, data_venda)` em venda | B-tree | Q01, Q04, Q10 |
| `(data_venda) WHERE status='CONCLUIDA'` | parcial | Q05, Q07 |
| `(produto_id, data_venda) INCLUDE (quantidade, valor_liquido)` | covering | Q02, Q03, Q04 |
| `(promocao_id, data_venda) WHERE promocao_id IS NOT NULL` | parcial | Q09 |
| `(loja_id, data_ref) WHERE houve_ruptura` | parcial | Q01 |
| `(data_movimento, tipo) WHERE tipo IN ('PERDA','VENCIMENTO','AVARIA')` | parcial | Q05 |
| `gin(nome gin_trgm_ops)` | GIN trigram | autocomplete |
| `USING brin (data_venda)` | BRIN | varredura histórica |

BRIN complementa o B-tree. Dados inseridos em ordem cronológica têm correlação
física alta. O BRIN guarda mínimo e máximo por bloco de páginas, o que serve para
varredura de intervalo amplo. Para busca pontual, o planejador escolhe o B-tree.

Medição:

| Índice | BRIN | B-tree | Razão |
|---|---|---|---|
| `item_venda` (4,16M linhas) | 2.064 kB | 247 MB | **0,8%** |
| `venda` (545 mil linhas) | incluído | 5.960 kB | **35%** |

O ganho cresce com o tamanho da tabela. Citar só o caso favorável seria escolher o
número conveniente.

### Crescimento

| Estágio | Volume | Estratégia | Custo |
|---|---|---|---|
| **MVP** | 6,3M linhas, 3,1 GB | nó único, partição mensal | R$ 0 |
| **10× (30 lojas)** | 63M, 15 GB | mais RAM; `work_mem` maior | ~R$ 200/mês |
| **100× (300 lojas)** | 636M, ~150 GB | retenção com Parquet; réplica | ~R$ 2.000/mês |
| **1000×** | 6,36B | Citus ou warehouse | avaliar |

O modelo já está preparado. `loja_id` está em todas as tabelas de fato, o que
permite sharding por loja. A partição é por tempo, o que permite retenção. Nenhuma
migração exige mudar o modelo conceitual.

O benchmark PostgreSQL × DuckDB que sustenta a projeção está na seção 4.7.

## Modelo estrela

### Fatos

| Fato | Grão | Linhas | Perguntas |
|---|---|---|---|
| `fato_vendas` | 1 linha de **item** (1 cupom = N) | 4,1M | Q01–Q05, Q07, Q09 |
| `fato_estoque_diario` | 1 item-loja-dia | 921k | Q01, Q04, Q05, Q06 |
| `fato_compras` | 1 item de pedido | 36k | Q08 |

O grão de venda é a linha, não o cupom. Toda análise é por item: curva ABC,
previsão, giro. Grão de cupom exigiria reagregação posterior.

### Dimensões

| Dimensão | Linhas | Atributos |
|---|---|---|
| `dim_tempo` | 731 | ano, trimestre, semana ISO, feriado, dia de pagamento |
| `dim_loja` | 3 | porte derivado de área |
| `dim_produto` | 420 | hierarquia achatada, preço vigente, fornecedor |
| `dim_fornecedor` | 6 | prazo padrão |
| `dim_promocao` | 72 | duração calculada |

### Views materializadas

| View | Papel |
|---|---|
| `mv_demanda_diaria` | **demanda com reconstrução de falta** |
| `mv_previsao_demanda` | EWMA(28d) com fator de dia da semana |
| `mv_sugestao_compra` | ponto de pedido e lote mínimo |
| `mv_rupturas` | faltas com receita perdida |
| `mv_qualidade_loja` | **selo de confiança** |

Uma view comum recalcularia a EWMA sobre 4,1 milhões de linhas a cada consulta.
Materializada, o custo é pago uma vez no `REFRESH`. A decisão de compra é diária,
então um `REFRESH` por dia basta.

### Onde a sazonalidade semanal importa

Uma medição contraria a intuição, e a primeira versão do trabalho narrava errado.

O fator de dia da semana é normalizado pela média dos 7 dias, então `avg(fator) = 1`
por construção. Enquanto a previsão era `avg(nivel_ewma × fator)`, o fator se
cancelava. Dos 1.260 pares item-loja, apenas 6 divergiam de `avg(nivel_ewma)`, e
por arredondamento.

A sazonalidade não serve para dimensionar ponto de pedido. O prazo de 9 a 14 dias
cobre quase duas semanas. Cada dia fraco é compensado por um dia forte. Adotar a
soma dia a dia muda o ponto de pedido em 0,03% em média, com máximo de 1,23%.

Onde o fator tem efeito é no abastecimento diário de gôndola.

| Métrica | Valor |
|---|---|
| Pico da semana / média | **1,315×** |
| Vale da semana / média | **0,773×** |
| Amplitude | **70%** |

Saber que sexta vende 1,3× a média e domingo 0,77× muda quanto repor em cada dia.
Por isso `mv_sugestao_compra` carrega `demanda_pico_dia`, `dia_pico_semana`,
`demanda_vale_dia` e `dia_vale_semana` ao lado do ponto de pedido.

**Limitação.** `fator_feriado` existe em `mv_previsao_demanda` e não entra na
sugestão. Feriado é evento esparso, e a soma num horizonte de 14 dias quase nunca o
captura. Usá-lo exigiria calendário de feriados futuros por loja, que o dataset não
tem.

## Dicionário de dados

O dicionário completo está em
[`docs/dicionario-de-dados.md`](dicionario-de-dados.md). É gerado do catálogo do
PostgreSQL, não escrito à mão, o que garante que nunca fica desatualizado.

## Evidências

| Evidência | Arquivo | O que prova |
|---|---|---|
| 23 testes de constraint | `tests/test_constraints.py` | o banco rejeita 23 tipos de dado inválido |
| Carga limpa | `carga_limpa.json` | 0 linhas rejeitadas; 3.290 cupons corrigidos (DQ020) |
| Equação de estoque | `snapshot_equacao_ck` | nenhum snapshot incoerente |
| Plano de execução | `q*.plan.txt` | as consultas usam os índices previstos |
| Integridade pós-carga | `tests/test_integridade.py` | FKs, somas e séries consistentes |

## Resumo das decisões

| Decisão | Escolha | Rejeitado | Motivo |
|---|---|---|---|
| Normalização da prata | 3FN | desnormalizar | evitar anomalia em 4,1M linhas |
| Modelo da ouro | star schema | manter 3FN | leitura sem 3 joins |
| Chave primária | surrogate + natural única | só natural | natural muda |
| Exclusão de produto | soft delete | `DELETE` | preservar série temporal |
| Histórico de preço | SCD 2 com `EXCLUDE` | trigger | nativo e declarativo |
| Particionamento | RANGE mensal | hash por loja | remove meses não consultados |
| Índices | 38 definições justificadas | indexar tudo | custo de escrita |
| Agregação | views materializadas | calcular na consulta | custo pago 1×/dia |
