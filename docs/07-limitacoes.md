# 4.7 — Limitações e próximos passos

## Onde a escolha atual pode falhar

Nenhuma arquitetura é universal. Esta seção lista os cenários em que o PostgreSQL
monolítico deixaria de ser a escolha correta. Cada cenário traz o gatilho concreto
de mudança.

### Limitação 1 — Varredura analítica acima de ~500M de linhas

**O sintoma.** O painel passa de 3 segundos para carregar, e `EXPLAIN ANALYZE`
mostra `Seq Scan` em `fato_vendas` dominando o tempo.

**Por que acontece.** O PostgreSQL armazena linha a linha. Uma agregação que lê 3
colunas de 500M de linhas paga o custo de ler todas as colunas dessas linhas.

**O que muda.** Camada colunar para o caminho analítico. O benchmark medido
(`docs/evidencias/benchmark_duckdb.md`) mostra a magnitude:

<!-- BENCHMARK_INICIO -->

Benchmark medido com `4,134,291`
linhas em `fato_vendas` (896 MB no PostgreSQL).
Parquet exportado com compressão ZSTD: `fato_vendas` 34.8 MB, `dim_tempo` 0.01 MB, `dim_produto` 0.01 MB.

| Consulta | PostgreSQL | DuckDB | Razão | Vencedor |
|---|---|---|---|---|
| Receita por mes em 24 meses | 668 ms | 63 ms | 10.53× | **DUCKDB** |
| Curva ABC completa (420 SKUs) | 436 ms | 21 ms | 20.53× | **DUCKDB** |
| Vendas de um SKU em um mes | 1 ms | 10 ms | 0.09× | **POSTGRES** |

**Leitura do resultado:** PostgreSQL venceu 1 de 3
consultas e DuckDB venceu 2. O padrão tem explicação:

- **Varredura ampla** (agregação de 24 meses) favorece o colunar, que lê
  só as colunas usadas e comprime por coluna.
- **Filtro seletivo** (um SKU em um mês) favorece o row store, que usa o
  índice B-tree e toca poucas páginas.

A conclusão da seção 4.7 **separa as duas cargas**, em vez de trocar de banco. Um
benchmark que mostrasse só o caso favorável seria propaganda. O cenário real tem
os dois padrões convivendo.

<!-- BENCHMARK_FIM -->

**Decisão.** A camada colunar complementa, não substitui. O transacional continua
no PostgreSQL porque estoque exige ACID.

### Limitação 2 — Ingestão em tempo real

**O sintoma.** O cliente quer "ver a venda aparecer no painel em segundos".

**Por que não está no MVP.** A decisão de compra é semanal. Processar em tempo
real resolveria um problema que ninguém tem. Adicionaria Kafka, schema registry,
consumer, monitoramento de lag e mais um ponto de falha.

**O que muda se for necessário.** `LISTEN/NOTIFY` do PostgreSQL resolve até ~100
eventos/s sem componente novo. Acima disso, CDC com Debezium e Kafka. O modelo já
suporta: `venda` tem PK ordenável e não há update destrutivo.

### Limitação 3 — Multi-tenant com isolamento forte (>50 lojas)

**O sintoma.** Uma rede com 300 lojas exige que o dado de uma loja não seja
visível para outra em nível de processo, não só de permissão.

**Por que não está no MVP.** RLS resolve isolamento lógico, não físico. Para
isolamento físico, cada cliente precisaria de schema ou banco próprio. O
`pg_dump` por cliente fica inviável em 300.

**O que muda.** Citus com sharding por `loja_id`, ou banco por tenant com
provisionamento automatizado. O modelo já tem `loja_id` em todas as tabelas de
fato, o que torna o sharding possível sem redesenho.

### Limitação 4 — Previsão em SKUs com histórico curto

**O sintoma.** Produto novo entra na loja e a previsão é ruído, porque há 5 dias
de histórico e não 28. Pior: produto que nunca vendeu no período ficaria sem
previsão, e portanto sem sugestão de compra.

**O que o sistema faz hoje.** A view `mv_previsao_demanda` cobre o universo
completo de pares SKU-loja ativos (1.260 neste dataset), via `CROSS JOIN` entre
loja e produto. Para um par sem histórico próprio, usa a mediana do departamento
naquela loja. Se o departamento inteiro for novo, usa a mediana da loja. A coluna
`origem_previsao` marca a procedência:

| Origem | Significado |
|---|---|
| `proprio` | o SKU tem série própria; a EWMA foi calculada sobre ela |
| `departamento` | cold start: mediana do departamento na loja |
| `loja` | fallback: mediana da loja |
| `sem_referencia` | nenhum histórico disponível; usa 0,10 un/dia |

**Honestidade sobre a cobertura.** Neste dataset, todos os 1.260 pares têm
histórico (`origem_previsao = 'proprio'`), porque o gerador garante que todo SKU
seja sorteado ao menos uma vez em 24 meses. O caminho de cold start é código
defensivo, não caminho exercitado. Um dataset real com SKU recém-cadastrado é a
forma de testá-lo.

**O que falta.** Um modelo hierárquico que empreste força de séries densas para
séries esparsas. É a técnica correta (hierarchical forecasting), mas exige mais
dados do que o MVP tem.

### Limitação 5 — Sazonalidade não capturada por EWMA

**O sintoma.** Feriado móvel (Carnaval, Páscoa) muda de data todo ano. A EWMA
reage, mas com atraso: ela não sabe que o Carnaval vem.

**O que o sistema faz.** `mv_previsao_demanda` calcula um `fator_feriado` médio
por SKU. Isso captura o efeito médio de feriado, não a data específica.

**O que muda.** Calendário de eventos com data projetada e um modelo que usa o
`fator_feriado` na data correta, não na média. É extensão do que já existe.

### Limitação 6 — Dados sintéticos

**A limitação mais honesta do projeto.**

O dataset é gerado, não observado. Os parâmetros são calibrados com benchmarks
públicos: ruptura de 8,3%, curva ABC de 20/80, ticket médio de mercadinho. Mas
nenhum gerador captura a realidade inteira.

O que o gerador não reproduz:

| Fenômeno real | Consequência |
|---|---|
| Cliente que compra sempre o mesmo dia da semana | subestima a previsibilidade |
| Canibalização entre marcas (preço sobe, troca de marca) | ignora elasticidade cruzada |
| Efeito de vizinhança (concorrente abre ao lado) | não há variável externa |
| Sazonalidade local (praia no verão, interior no inverno) | sazonalidade única para as 3 lojas |
| Mudança de mix ao longo do tempo | demanda base constante por SKU |

**Por que isso não invalida o projeto.** A rubrica avalia arquitetura de dados, não
acurácia preditiva. O que se demonstra é que o modelo sustenta a análise. Também
que as constraints protegem a integridade e que o pipeline detecta defeitos. As
três coisas são independentes da origem do dado.

**Como resolver.** Rodar o mesmo pipeline sobre o dataset público Corporación
Favorita (Kaggle, varejo equatoriano, 125M de linhas) ou o TEVEC (varejista
brasileiro). O modelo já é compatível: é trocar o `Ingestor` de fonte.

#### Defeito do gerador: entrega sempre zero

Encontrado ao construir o painel e registrado aqui em vez de escondido.

**O defeito.** `src/gerador.py` gravava `"quantidade_entregue": "0.000"` no
momento em que o pedido era criado, antes de a entrega acontecer, e nunca voltava
para atualizar. Três consequências medidas na época. As 37.306 linhas de
`prata.item_pedido` tinham entrega zero. `ouro.fato_compras.entrega_completa` era
`false` em todas. A Q08 (OTIF) devolvia 0,0% para os seis fornecedores.

Isso não era um achado sobre os fornecedores. Era um artefato do gerador. Por
isso o painel nunca exibiu OTIF. Mostrar "OTIF 0%" ao lado de um pedido
transformaria um bug em conclusão de negócio. O dono trocaria de fornecedor por
causa disso.

**A correção.** O gerador passou a decidir o desfecho de cada pedido quando ele
chega: 18% atrasam, 12% chegam parciais (55–92% da quantidade), o resto chega
completo. `sangria` guarda o desfecho e `item_pedido` é reescrito com a
quantidade efetivamente entregue.

**Resultado medido hoje:**

| Métrica | Valor |
|---|---|
| Linhas de pedido | 37.306 |
| Com entrega > 0 | 36.858 (98,8%) |
| Entrega completa | 32.513 (87,2%) |
| Entrega parcial | 4.793 (12,8%) |
| **OTIF por fornecedor** | **71,3% – 73,1%** |
| Atraso médio | 3,6 dias |

**Limitação que permanece.** A calibração dá aos seis fornecedores desempenho
praticamente igual, entre 71% e 73%. Os cortes de classificação são 90% e 75%.
Com eles, todos caem em "C – CRÍTICO" e a consulta não os distingue. A pergunta "qual
fornecedor me deixa na mão?" não tem resposta diferenciada neste dataset. É
limitação da simulação, não da consulta. Num dataset real, a dispersão entre
fornecedores é o que faz a Q08 valer.

## O que mudaria se a startup crescesse 100 vezes

Cenário: de 3 lojas para 300 lojas.

### Volumetria projetada

| Métrica | Hoje (3 lojas) | 100× (300 lojas) | Fator |
|---|---|---|---|
| Linhas de item/ano | 2,08M | 208M | 100× |
| Linhas totais (24 meses) | 6,36M | 636M | 100× |
| Tamanho em disco | 3,1 GB | ~150 GB (estimado) | ~48× |
| Cupons/dia | 630 | 63.000 | 100× |
| Escritas/s (pico) | ~0,3 | ~30 | 100× |
| Consultas/dia | ~10 | ~1.000 | 100× |

### O que quebra primeiro

| # | Componente | Por que quebra | Quando |
|---|---|---|---|
| 1 | **Painel (varredura analítica)** | `Seq Scan` de 300× mais linhas | ~30 lojas |
| 2 | Backup (`pg_dump`) | janela de backup cresce linearmente | ~100 lojas |
| 3 | `REFRESH MATERIALIZED VIEW` | recalcula tudo, toda vez | ~100 lojas |
| 4 | `work_mem` por conexão | 1.000 consultas × 32 MB acima da RAM | ~200 lojas |
| 5 | Escrita concorrente | ~30 inserts/s ainda é trivial | acima de 1.000 lojas |

A escrita não é o gargalo, nem a 100×. 30 inserções por segundo é carga leve para
PostgreSQL. Isso confirma a análise da seção 4.2: o problema é leitura analítica,
não transação.

### Arquitetura alvo (100×)

```
                    ┌─────────────────────────────────┐
   PDV (300 lojas)  │  PostgreSQL primário            │
        │           │  - prata (3FN, particionada)    │
        └──────────►│  - ACID no caminho de estoque   │
                    └────────────┬────────────────────┘
                                 │
                    réplica assíncrona (leitura)
                                 │
                    ┌────────────▼────────────────────┐
                    │  Réplica de leitura             │
                    │  - dashboard                    │
                    │  - consultas ad-hoc             │
                    └────────────┬────────────────────┘
                                 │
                    export incremental (partições
                    antigas, Parquet)
                                 │
                    ┌────────────▼────────────────────┐
                    │  Parquet + DuckDB / ClickHouse  │
                    │  - histórico > 6 meses          │
                    │  - benchmark medido: ver acima  │
                    └─────────────────────────────────┘
```

Mudanças concretas, por ordem de implementação.

1. **Réplica de leitura.** Isola a carga analítica na hora. Zero mudança de
   modelo. Resolve os gargalos 1 e 4.
2. **Retenção por partição.** `DETACH` de partições com mais de 6 meses para
   Parquet. Reduz o volume ativo em 75%. Resolve os gargalos 2 e 3.
3. **`REFRESH` incremental.** Recalcular só o último mês em vez de tudo. O
   PostgreSQL 15+ não tem `REFRESH` incremental nativo. A solução é manter
   tabelas de agregado incrementais ou usar `pg_ivm`.
4. **Particionamento por loja (Citus).** Só se o isolamento físico for exigido.
   O modelo já tem `loja_id` em todas as tabelas de fato.
5. **Camada colunar.** Quando a varredura histórica dominar. O benchmark acima
   mede o ganho real.

### O que não mudaria

| Componente | Por quê |
|---|---|
| **Modelo 3FN da prata** | normalização é correta em qualquer escala |
| **Star schema da ouro** | é o padrão para análise dimensional |
| **Constraints e domínios** | integridade é requisito, não otimização |
| **Catálogo de regras DQ** | a necessidade de medir qualidade cresce com o volume |
| **Quarentena com payload completo** | guarda a linha inteira, o que permite reprocessar quando a regra mudar |
| **Chave surrogate e natural** | multi-tenant exige ainda mais deduplicação |
| **Idempotência da carga** | com 300 lojas, reprocessar é rotina |

A arquitetura de dados sobrevive intacta ao crescimento de 100×. O que muda é a
infraestrutura: réplica, retenção, colunar. Isso mostra que a modelagem não foi
desenhada para o tamanho de hoje.

## Comparação com o que foi prometido

| Prometido na proposta | Entregue | Status |
|---|---|---|
| Banco criado com amostra | 6,36M linhas, 28 tabelas lógicas | ✅ |
| ≥5 consultas de negócio | 11 consultas | ✅ |
| Justificativa de banco com alternativas | 8 alternativas, matriz ponderada | ✅ |
| Modelo, dicionário, chaves, índices | implementado e gerado do catálogo | ✅ |
| Regras de qualidade | 21 regras e medição de recall | ✅ além do pedido |
| LGPD | minimização na modelagem e DQ019 | ✅ |
| Backup e controle de acesso | roles, RLS, restore test | ✅ |
| Previsão de demanda | SQL (EWMA e sazonalidade) | ✅ escopo reduzido de propósito |
| Painel de decisão | HTML estático gerado do banco | ✅ fora do escopo, mas funcional |
| Machine learning | **não feito** | ⚠️ decisão consciente |

## Aprendizados do grupo

O edital pede esta seção, e normalmente ela diz "aprendemos a trabalhar em
equipe". Aqui vão os aprendizados técnicos que mudaram o projeto.

### 1. Testar constraints revelou dois bugs invisíveis

O caso **C11** (cupom duplicado com série NULL) só apareceu porque o teste
verificava o SQLSTATE esperado. Um teste que apenas chamasse `INSERT` e olhasse
"não deu erro" teria passado. O banco teria duplicado receita em produção.

**Lição:** constraint sem teste é decoração. O valor está em provar que ela
rejeita, não em declará-la.

### 2. Float não serve para dinheiro, e o erro é silencioso

A constraint `valor_total = round(quantidade × preço, 2) − desconto` falhava em
cerca de 1 a cada 200 linhas. Causa: `0,82 × 8,25 = 6,765`. Python arredondava
para 6,76 (representação binária) e PostgreSQL para 6,77 (decimal half-up).

**Lição:** dinheiro é `NUMERIC` e `Decimal` em toda a stack, não só no banco. O
erro não aparece em teste pequeno. Aparece em 4 milhões de linhas.

### 3. Subquery correlacionada com `ctid` é O(n²)

A deduplicação de itens usava `WHERE ctid <> (SELECT min(ctid) ...)`. Com 110 mil
linhas, passou de 90 segundos sem terminar. Reescrita com `ROW_NUMBER() OVER
(PARTITION BY ...)`, rodou em menos de 1 segundo.

**Lição:** em SQL, a forma importa mais que a lógica. A janela transforma O(n²)
em O(n log n).

### 4. Cascata de rejeição distorce métrica de qualidade

4 itens sem produto injetados apareciam como dezenas de milhares de rejeições,
porque cada EAN inválido derruba todos os dependentes. Medido hoje: 171.603 linhas
em cascata contra 166 defeitos reais de cadastro, fator de mais de mil. O recall
ficava ininterpretável.

**Lição:** quando um registro ruim contamina os dependentes, é preciso separar o
defeito da consequência. Daí nasceu a regra DQ021.

### 5. Ruptura não é distribuição uniforme

A primeira tentativa de calibrar ruptura em 2% fez a taxa crescer com o horizonte
de simulação. Deu 4% em 6 meses e 8% em 24. A causa era estrutural. SKUs negligenciados
drenavam para sempre.

**Lição:** modelo que não está em equilíbrio produz artefato, não fenômeno. A
solução foi tornar a negligência episódica, e a taxa estabilizou.

### 6. O número certo não é o número que impressiona

A primeira meta era "ruptura de 2%". A pesquisa mostrou que a realidade
brasileira é 10–12% e a média global 8,3%. Manter os 2% seria irrealista.
Ajustar para 8,3% é calibrado e defensável.

**Lição:** benchmark público vale mais que alvo intuitivo. E o relatório fica mais
forte quando cita a fonte.

### 7. A decisão de não usar ML foi a mais difícil e a mais acertada

A proposta inicial tinha LightGBM. A leitura da rubrica mostrou que ML vale zero
ponto, e os eixos de banco e modelagem valem 6,0. Trocar 5 dias de modelagem por
5 dias de ML teria custado pontos nos dois eixos avaliados.

**Lição:** ler o edital com atenção é uma habilidade técnica. Otimizar o que não é
avaliado é desperdício, mesmo que seja mais interessante.

### 8. O que não medimos, não sabemos

Antes do laboratório de dados sujos, a afirmação era "temos regras de qualidade".
Depois, é "detectamos 96,61% dos defeitos injetados". A precisão varia por regra,
de 0,5% a 100%, com os três casos fora da curva explicados. A segunda frase é
verificável. A primeira não é.

**Lição:** toda afirmação sobre qualidade de dados precisa de um número atrelado.
Sem medição, é opinião.

### 9. Um documento pode mentir sem que ninguém tenha mentido

O achado mais desconfortável deste projeto não foi técnico. A documentação
afirmava coisas que o código não fazia. Que o preço da dimensão vinha do
histórico, quando vinha de `custo / 0,7`. Que a auditoria registrava alterações,
quando a tabela tinha zero linhas. Que o selo ocultava a sugestão abaixo de 85%,
quando o painel só exibia o selo. Que a sazonalidade entrava na previsão, quando
o fator se cancelava na média.

Nenhuma dessas frases foi escrita com má-fé. Cada uma descrevia a intenção no
momento em que foi escrita, e o código evoluiu sem que o texto acompanhasse. O
resultado é indistinguível de uma mentira para quem lê.

**Lição:** documento é afirmação sobre um estado, nunca especificação. Números
escritos à mão envelhecem. Por isso os deste trabalho saem de `docs/evidencias/`
por script. E há um verificador (`scripts/conferir_numeros.py`) que compara o
texto com o banco. A regra que ficou: se um número aparece no relatório, precisa
de um comando que o produza.

## Próximos passos concretos

| Prioridade | Item | Esforço |
|---|---|---|
| **Alta** | Rodar o pipeline sobre o dataset público Favorita ou TEVEC | 2 dias |
| **Alta** | Integração real com um PDV (CSV para API) | 3 dias |
| **Média** | Previsão hierárquica para SKUs novos (cold start) | 4 dias |
| **Média** | `REFRESH` incremental das views materializadas | 2 dias |
| **Média** | Publicar o painel como app interno (FastAPI e o mesmo HTML) | 2 dias |
| **Baixa** | Alertas por e-mail ou WhatsApp quando a ruptura passa do limiar | 1 dia |
| **Baixa** | Teste de restore automatizado no CI | 1 dia |
| **Futuro** | Sharding por loja com Citus | 1 semana |
| **Futuro** | Camada colunar para histórico (Parquet e DuckDB) | 1 semana |
