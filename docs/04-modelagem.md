# 4.4 — Organização e modelagem dos dados (Eixo 2)

## Visão geral: três camadas, três propósitos

O projeto usa **arquitetura em camadas** dentro de um único banco. Cada camada
existe para resolver um problema que as outras não resolvem.

| Camada | Formato | Modelo | Propósito |
|---|---|---|---|
| **Bronze** | CSV/XML imutável em disco | — | Preservar o dado como veio; permitir reprocessamento |
| **Prata** | Tabelas PostgreSQL | **3ª Forma Normal** | Fonte de verdade transacional |
| **Ouro** | Tabelas + views materializadas | **Star schema** | Consulta analítica |

**Por que não uma só?** Porque normalizar e desnormalizar resolvem problemas
opostos:

- **3FN evita anomalia de atualização.** Se o nome de uma categoria mudasse numa
  tabela desnormalizada de 4,1 milhões de linhas, seria preciso atualizar milhões
  de registros e o risco de inconsistência seria alto. Normalizado, é uma linha.
- **Star schema evita joins caros na leitura.** O analista não deveria precisar
  conhecer 15 tabelas normalizadas para responder "curva ABC".

Não é duplicação: é a **mesma informação organizada para dois padrões de acesso
diferentes**. A prata é a fonte de verdade; o ouro é derivado e reconstruível a
qualquer momento (`python run_all.py --etapa marts`).

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

Entidades de apoio: `CALENDARIO` (dimensão de tempo materializada),
`PROMOCAO` e `PROMOCAO_PRODUTO` (N:N).

## Modelo lógico: decisões de projeto

### Chaves

**Surrogate + natural, sempre as duas.** Cada tabela tem:

- `BIGINT GENERATED ALWAYS AS IDENTITY` como PK — estável, compacta, sem
  Semântica embutida;
- Uma ou mais **chaves naturais `UNIQUE`** — é o que permite **deduplicação
  idempotente**.

Exemplo: `prata.produto` tem `produto_id` (surrogate) e `ean` (natural, único).
Sem a chave natural, reimportar um arquivo criaria produtos duplicados sem que o
banco percebesse; com ela, `ON CONFLICT (ean) DO NOTHING` resolve.

**Por que não usar a chave natural como PK?** Porque EAN muda (o fabricante
reformula), CNPJ muda (venda de loja) e o cupom pode ser reemitido. Surrogate
isola o modelo dessas mudanças. A chave natural continua sendo a **regra de
negócio**, expressa como `UNIQUE`.

**Caso real encontrado por teste — `NULLS NOT DISTINCT`:** a chave natural de
venda é `(loja_id, data_venda, serie_cupom, numero_cupom)`. `serie_cupom` é
nullable. No PostgreSQL, a `UNIQUE` padrão considera cada `NULL` distinto, então
dois cupons idênticos com série NULL **passariam** — duplicando receita em
silêncio. Corrigido com:

```sql
CONSTRAINT venda_chave_natural_uk
    UNIQUE NULLS NOT DISTINCT (loja_id, data_venda, serie_cupom, numero_cupom)
```

A evidência está em `tests/test_constraints.py`, caso C11, e o bug está
documentado no próprio DDL.

### Relacionamentos e integridade

| Relacionamento | Cardinalidade | Regra de exclusão | Justificativa |
|---|---|---|---|
| Loja → Venda | 1:N | `RESTRICT` | Não se apaga loja com histórico |
| Venda → Item | 1:N | `CASCADE` | Item não existe sem cupom |
| Produto → Item | 1:N | `RESTRICT` | Produto é soft-deleted (`ativo`), nunca apagado |
| Produto → Categoria | N:1 | `RESTRICT` | Categoria em uso não é removida |
| Produto ↔ Fornecedor | N:N | `CASCADE` | Vínculo é descartável |
| Produto → Preço histórico | 1:N | `CASCADE` | Histórico acompanha o produto |

**Soft delete em produto:** `ativo = FALSE` em vez de `DELETE`. Motivo: apagar um
produto quebraria a FK de 4 milhões de itens históricos e destruiria a série
temporal usada na previsão.

**FK composta em item de venda:** `FOREIGN KEY (venda_id, data_venda)` — exigência
do particionamento (ver abaixo), não escolha estética.

### Domínios (não apenas `CHECK` repetido)

Seis domínios e quatro funções reutilizáveis em `002_dominios.sql` e `005_particoes.sql`:

| Domínio | Tipo base | Regra | Onde é usado |
|---|---|---|---|
| `gov.ean13` | TEXT | 13 dígitos + **dígito verificador válido** | produto |
| `gov.quantidade` | NUMERIC(14,3) | ≥ 0 | estoque, quantidade entregue |
| `gov.quantidade_positiva` | NUMERIC(14,3) | > 0 | item de venda, item de pedido |
| `gov.dinheiro` | NUMERIC(14,2) | ≥ 0 | todos os valores monetários |
| `gov.percentual` | NUMERIC(7,4) | 0–100 | desconto, margem |
| `gov.uf` | CHAR(2) | **lista fechada das 27 UFs** | loja, fornecedor |

**Três decisões que valem justificativa:**

1. **EAN com dígito verificador em função PL/pgSQL**, não apenas regex. O EAN é a
   chave natural do produto: um dígito errado cria um SKU fantasma que nunca
   mais se funde com o real. A validação está em `gov.ean13_valido()` e foi
   verificada contra implementação independente em Python.

2. **UF como lista fechada, não regex.** A primeira versão usava
   `CHECK (uf ~ '^[A-Z]{2}$')`. Um teste de constraint provou que `'XX'` passava.
   Lista fechada é a única forma de garantir o domínio.

3. **Duas variantes de quantidade.** `quantidade` (≥ 0) e `quantidade_positiva`
   (> 0) parecem redundantes, mas expressam intenções diferentes: estoque pode
   ser zero (ruptura), item de venda não pode. Um `CHECK` único forçaria a
   escolha do mais permissivo em todos os lugares.

### Normalização: onde é 3FN e onde não é

**Prata — 3FN, deliberadamente.**

| Forma normal | Como é atendida |
|---|---|
| 1FN | Todo atributo é atômico; não há grupo repetido nem lista em coluna |
| 2FN | PK é sempre atômica (surrogate); não há dependência parcial |
| 3FN | Não há dependência transitiva: cidade não depende de nada além da loja |

Um exemplo de 3FN que poderia ter sido violado: **preço**. Guardar
`preco_venda` em `item_venda` **é correto**, não desnormalização — porque o preço
praticado naquela venda é um **fato histórico**, não uma cópia do preço atual.
Guardar apenas em `produto` tornaria impossível calcular margem de um período
passado.

**Ouro — desnormalização deliberada e justificada.**

`ouro.dim_produto` achata a hierarquia de dois níveis hoje (departamento > classe),
com auto-referência que permite mais níveis numa única linha, e resolve o preço vigente. Isso viola 3FN.

**Justificativa do trade-off:**

| Aspecto | Valor |
|---|---|
| Custo | ~420 linhas na dimensão, atualizadas por `TRUNCATE`/`INSERT` completo |
| Benefício | Consulta analítica sem join com `categoria` (3 self-joins) |
| Volume do lado do fato | 4,1 milhões de linhas |
| Conclusão | Desnormalizar 420 linhas para evitar 3 joins em 4,1M é ganho claro |

### Preço histórico (SCD tipo 2 simplificado)

A tabela `produto_preco_historico` usa faixas de vigência meio-abertas:

```sql
PRIMARY KEY (produto_id, data_inicio)
CONSTRAINT preco_vigencia_ck CHECK (data_fim IS NULL OR data_fim > data_inicio)
```

Duas garantias implementadas com recursos nativos:

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

O `EXCLUDE` é a solução elegante para um problema que, na maioria dos sistemas,
é resolvido com trigger ou validação na aplicação. Ele usa índice GiST e precisa
da extensão `btree_gist` para combinar igualdade (`=`) com sobreposição (`&&`).

**Estado real desta implementação — e o que ela ainda não é.**

As duas garantias acima estão ativas e testadas (I08, I09). O que existe hoje
é **uma faixa aberta por SKU**: 420 faixas, 420 SKUs, nenhum SKU com mais de
uma faixa. A estrutura suporta múltiplas faixas (a PK é `produto_id +
data_inicio`, o `EXCLUDE` impede sobreposição), mas o dataset de origem traz
**um preço por produto**, não uma série temporal de preços.

Isso importa para a leitura do trabalho: o mecanismo de SCD tipo 2 está
implementado e restrito por constraint; o **histórico de mudanças de preço
não está populado** porque a fonte não o tem. Se o CSV trouxesse
`produto_id, data_inicio, preco`, a ingestão já gravaria as N faixas sem
alteração de schema — o que falta é o dado, não o modelo. A coluna
`data_fim` permanece `NULL` em 420 de 420 linhas.

Efeito prático medido da correção: antes, `dim_produto` inventava o preço de
venda como `custo / 0,7` para 420 de 420 SKUs (erro médio de 11,62% contra o
preço praticado no PDV). Agora lê a faixa vigente do histórico, e o erro médio
caiu para **1,13%** — resíduo que corresponde ao desconto promocional (o
histórico guarda o preço de tabela; a comparação usa o preço médio
efetivamente cobrado, que inclui promoção).

## Modelo físico: as decisões que só aparecem no DDL

### Particionamento mensal

```sql
CREATE TABLE prata.venda (...) PARTITION BY RANGE (data_venda);
CREATE TABLE prata.venda_2025_01 PARTITION OF prata.venda
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

**Por que RANGE por mês:**

| Alternativa | Por que não |
|---|---|
| Sem partição | Cada consulta de 30 dias varre 24 meses |
| Hash por loja | Só ajuda consulta de loja única; relatório multi-loja continua varrendo tudo |
| Range por ano | Consulta de 30 dias ainda varre 12 meses |
| **Range por mês** | **Consulta de 30 dias lê 1 ou 2 partições** |

**Custo do particionamento:** a PK e a FK precisam incluir `data_venda`. Em troca,
o *partition pruning* elimina a maior parte das linhas antes de qualquer leitura.

**Gestão automatizada:** `gov.criar_particoes_mensais(inicio, fim)` é idempotente
e chamada pelo ETL antes de cada carga. `gov.garantir_particoes()` mantém janela
de 24 meses atrás a 6 meses à frente. `gov.destacar_particao(mes)` existe para
retenção — arquiva sem deletar.

### Índices: cada um amarrado a uma consulta

A regra do projeto é **nenhum índice sem consulta que o justifique**. Índice
ocupa disco e onera `INSERT` — e o PDV insere o dia todo.

| Índice | Recurso | Consulta que atende |
|---|---|---|
| `(loja_id, data_venda)` em venda | B-tree | Q01, Q04, Q10 por loja e período |
| `(data_venda) WHERE status='CONCLUIDA'` | B-tree **parcial** | Q05, Q07; cancelada não entra em receita |
| `(produto_id, data_venda) INCLUDE (quantidade, valor_liquido)` | **covering** | Q02, Q03, Q04 — *index-only scan* |
| `(promocao_id, data_venda) WHERE promocao_id IS NOT NULL` | parcial | Q09; maioria dos itens não tem promoção |
| `(loja_id, data_ref) WHERE houve_ruptura` | parcial | Q01; ruptura é exceção, índice fica minúsculo |
| `(data_movimento, tipo) WHERE tipo IN ('PERDA','VENCIMENTO','AVARIA')` | parcial | Q05; perdas são minoria dos eventos |
| `gin(nome gin_trgm_ops)` | **GIN trigram** | autocomplete de produto no dashboard |
| `USING brin (data_venda)` | **BRIN** | varredura histórica ampla: **0,8% do tamanho do B-tree** em `item_venda` |

**Por que BRIN além do B-tree:** dados inseridos em ordem cronológica têm
correlação física altíssima. O BRIN guarda apenas mínimo/máximo por bloco de
páginas, funcionando bem para varredura de intervalo amplo (relatório anual,
exportação). Para busca pontual, o B-tree continua sendo escolhido pelo
planejador. Os dois coexistem.

**Medição que sustenta a afirmação** (era "~1%", que é impreciso):

| Índice | BRIN | B-tree equivalente | BRIN / B-tree |
|---|---|---|---|
| `item_venda` (4,16M linhas) | 2.064 kB | 247 MB (covering) | **0,8%** |
| `venda` (545 mil linhas) | incluído acima | 5.960 kB (`loja_id, data_venda`) | **35%** |

O ganho do BRIN cresce com o tamanho da tabela: 0,8% num fato de 4 milhões de
linhas, 35% numa tabela de 545 mil. Citar "~1%" para os dois casos seria
escolher o número favorável — por isso estão os dois medidos.

### Estratégia de crescimento

O edital pergunta explicitamente sobre isso (seção 4.4).

| Estágio | Volume | Estratégia | Custo |
|---|---|---|---|
| **MVP** | 6,3M linhas, 3,1 GB | Nó único, partição mensal | R$ 0 |
| **10× (30 lojas)** | 63M linhas, 15 GB | Mais RAM; `work_mem` maior | ~R$ 200/mês |
| **100× (300 lojas)** | 636M linhas, ~150 GB | Retenção + Parquet; réplica de leitura | ~R$ 2.000/mês |
| **1000×** | 6,36B linhas | Citus (sharding por `loja_id`) ou warehouse | avaliar |

**O modelo já está preparado para isso:** `loja_id` está em todas as tabelas de
fato (permite sharding por loja sem redesenho), e a partição é por tempo (permite
retenção por arquivamento). Nenhuma migração exige mudar o modelo conceitual.

**Onde está medido:** `docs/07-limitacoes.md` traz o benchmark real
PostgreSQL × DuckDB que sustenta essa projeção com números.

## Modelo físico estrela (camada ouro)

### Fatos

| Fato | Grão | Linhas | Perguntas que responde |
|---|---|---|---|
| `fato_vendas` | 1 linha de **item** de venda (1 cupom = N linhas) | 4,1M | Q01–Q05, Q07, Q09 |
| `fato_estoque_diario` | 1 SKU-loja-dia | 921k | Q01, Q04, Q05, Q06 |
| `fato_compras` | 1 item de pedido | 36k | Q08 |

**Grão de venda é a linha, não o cupom.** Porque toda análise é por SKU (curva
ABC, previsão, giro). Grão de cupom exigiria reagregação posterior por produto,
inviabilizando as consultas que importam.

### Dimensões

| Dimensão | Linhas | Atributos desnormalizados |
|---|---|---|
| `dim_tempo` | 731 | ano, trimestre, mês, semana ISO, feriado, dia de pagamento |
| `dim_loja` | 3 | porte derivado de área |
| `dim_produto` | 420 | hierarquia achatada + preço vigente + fornecedor principal |
| `dim_fornecedor` | 6 | lead time padrão |
| `dim_promocao` | 72 | duração calculada |

### Views materializadas (a camada de decisão)

| View | Papel |
|---|---|
| `mv_demanda_diaria` | **Demanda com reconstrução de ruptura** — o diferencial do produto |
| `mv_previsao_demanda` | Nível EWMA(28d) + fator de dia da semana |
| `mv_sugestao_compra` | Ponto de pedido + estoque de segurança + lote mínimo |
| `mv_rupturas` | Rupturas com receita perdida estimada |
| `mv_qualidade_loja` | **Selo de confiança** por loja |

**Por que materializada e não view comum:** uma view comum recalcularia a EWMA
sobre 4,1 milhões de linhas a cada consulta. Materializada, o custo é pago uma vez
no `REFRESH`. Como a decisão de compra é diária, o dado precisa estar fresco uma
vez por dia — exatamente o que `REFRESH` oferece.

### Onde a sazonalidade semanal realmente importa

Vale registrar uma medição que contraria a intuição — e que a primeira versão
do trabalho narrava errado.

O fator de dia da semana é normalizado pela média dos 7 dias, então
`avg(fator) = 1` por construção. Enquanto a previsão era
`avg(nivel_ewma × fator)`, o fator **se cancelava**: medido no banco, dos 1.260
pares SKU-loja, apenas 6 divergiam de `avg(nivel_ewma)`, e por arredondamento.
A narrativa "EWMA + fator dia da semana" não se sustentava no número final.

Isso não significa que a sazonalidade seja inútil. Significa que ela **não serve
para dimensionar ponto de pedido**, porque o lead time de 9 a 14 dias cobre
quase duas semanas completas — cada dia fraco é compensado por um dia forte, e a
soma volta à média. Medido: adotar a soma dia a dia no horizonte muda o ponto de
pedido em **0,03% em média** (máximo 1,23%), embora 545 pares subam e 555 desçam — o efeito existe, mas se compensa.

Onde o fator tem efeito real é no **abastecimento diário de gôndola**:

| Métrica | Valor medido |
|---|---|
| Pico da semana / média | **1,315×** |
| Vale da semana / média | **0,773×** |
| Amplitude | **70%** |

Saber que sexta vende 1,3× a média e domingo 0,77× muda quanto repor na
prateleira **em cada dia** — decisão diferente da compra de duas semanas. Por
isso `mv_sugestao_compra` carrega `demanda_pico_dia`, `dia_pico_semana`,
`demanda_vale_dia` e `dia_vale_semana` ao lado do ponto de pedido: os dois usos
da sazonalidade ficam explícitos, e nenhum dos dois é vendido como o que não é.

**Limitação declarada:** o `fator_feriado` existe em `mv_previsao_demanda` e não
entra no cálculo da sugestão. Feriado é evento esparso (poucos dias por ano) e a
soma num horizonte de 14 dias quase nunca o captura; usá-lo exigiria um
calendário de feriados futuros por loja, que o dataset não tem. Fica como coluna
disponível e como próximo passo.

## Dicionário de dados

O dicionário completo, campo a campo, com tipo, descrição e regra, está em
[`docs/dicionario-de-dados.md`](dicionario-de-dados.md). Ele é gerado a partir do
catálogo do PostgreSQL (não escrito à mão), o que garante que nunca fica
desatualizado em relação ao banco real.

## Evidências de que o modelo funciona

O modelo não é validado por inspeção visual. É validado por:

| Evidência | Arquivo | O que prova |
|---|---|---|
| 23 testes de constraint | `tests/test_constraints.py` | O banco **rejeita** os 23 tipos de dado inválido |
| Carga limpa 100% | `docs/evidencias/carga_limpa.json` | 0 linhas rejeitadas em 6,3M; 3.290 cupons cancelados corrigidos (DQ020) |
| Equação de estoque | constraint `snapshot_equacao_ck` | Nenhum snapshot com estoque incoerente |
| Plano `EXPLAIN ANALYZE` | `docs/evidencias/q*.plan.txt` | As consultas usam os índices e partições previstos |
| Integridade pós-carga | `tests/test_integridade.py` | FKs, somas e séries consistentes |

## Resumo das decisões

| Decisão | Escolha | Alternativa rejeitada | Motivo |
|---|---|---|---|
| Normalização da prata | 3FN | Desnormalizar tudo | Evitar anomalia de atualização em 4,1M linhas |
| Modelo da ouro | Star schema | Manter 3FN | Leitura analítica sem 3 joins |
| Chave primária | Surrogate + natural única | Só natural | Natural muda; surrogate isola |
| Exclusão de produto | Soft delete | `DELETE` | Preservar série temporal |
| Histórico de preço | SCD tipo 2 com `EXCLUDE` | Trigger de validação | Nativo, declarativo, sem código |
| Particionamento | RANGE mensal | Hash por loja | Remove varredura de meses não consultados |
| Índices | 38 definições, cada uma justificada | Indexar tudo | Custo de escrita no PDV |
| Agregação | Views materializadas | Calcular na consulta | Custo pago 1×/dia, não a cada leitura |
