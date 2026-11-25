# 4.3 — Escolha do banco de dados (Eixo 1)

## Resumo

**PostgreSQL 18 como banco único**, com três camadas internas: bronze em
arquivos, prata em 3FN e ouro em star schema. Os recursos nativos resolvem o que
normalmente se resolveria comprando outro banco.

A seção compara oito alternativas, aplica o CAP com precisão e explica por que
persistência poliglota não foi necessária.

## O que o problema exige

| Requisito | Origem | Peso |
|---|---|---|
| Transação com invariante (estoque ≥ 0, cupom único) | regra de negócio | crítico |
| Integridade referencial (venda → item → produto) | modelo | crítico |
| Agregação por período com janela | Q01–Q10 | alto |
| Consulta ad-hoc | exploração | alto |
| Join entre fato e dimensão | star schema | alto |
| Carga diária em lote | acesso | médio |
| Rodar offline na apresentação | prazo | médio |
| 6,3M linhas hoje, 636M a 100× | projeção | médio |
| Custo próximo de zero | startup | médio |
| Esquema estável | domínio | médio |
| Atributos variáveis de produto | catálogo | baixo |

## Critérios e pesos

Os pesos foram definidos antes da avaliação.

| Critério | Peso | Justificativa |
|---|---|---|
| Consistência (ACID) | 25% | estoque inconsistente é falha grave |
| Adequação à consulta | 20% | o valor está na análise |
| Manutenção | 15% | o cliente não tem TI |
| Custo | 15% | orçamento zero |
| Maturidade | 10% | prazo curto exige ferramenta conhecida |
| Escalabilidade | 10% | 6,3M hoje, 636M a 100× |
| Latência | 5% | nenhuma consulta exige sub-100 ms |

## Matriz de decisão

Notas de 1 a 5 multiplicadas pelo peso. Máximo: 5,00.

| Banco | ACID 25% | Consulta 20% | Manut. 15% | Custo 15% | Matur. 10% | Escala 10% | Lat. 5% | Total |
|---|---|---|---|---|---|---|---|---|
| **PostgreSQL** | 5 | 4 | 5 | 5 | 5 | 4 | 4 | **4,65** |
| SQLite | 5 | 3 | 5 | 5 | 5 | 1 | 3 | 4,10 |
| MongoDB | 3 | 2 | 4 | 4 | 5 | 4 | 4 | 3,45 |
| MySQL/MariaDB | 5 | 3 | 4 | 5 | 5 | 3 | 3 | 4,15 |
| Cassandra | 2 | 1 | 2 | 3 | 3 | 5 | 5 | 2,50 |
| DuckDB | 2 | 5 | 5 | 5 | 4 | 2 | 5 | 3,85 |
| TimescaleDB | 5 | 4 | 3 | 4 | 4 | 4 | 5 | 4,15 |
| BigQuery/Snowflake | 3 | 5 | 3 | 1 | 5 | 5 | 2 | 3,45 |

PostgreSQL vence por 0,50 ponto sobre MySQL e TimescaleDB, empatados em 4,15.
Vence nos critérios de maior peso. O melhor no conjunto ponderado, embora não
lidere nenhum critério isolado.

Conferência da conta do PostgreSQL:

```
5×0,25 + 4×0,20 + 5×0,15 + 5×0,15 + 5×0,10 + 4×0,10 + 4×0,05
= 1,25 + 0,80 + 0,75 + 0,75 + 0,50 + 0,40 + 0,20 = 4,65
```

## As oito alternativas descartadas

O edital pede duas. Documentamos oito, uma para cada linha da tabela de tipos.

| Alternativa | O que atrairia | Por que não |
|---|---|---|
| **MongoDB** (documentos) | atributos variáveis de produto | O problema é relacional: venda → item → produto tem cardinalidade clara. Estoque exige invariante transacional, e o Mongo não expressa isso nativamente. `JSONB` no PostgreSQL cobre o atributo variável sem abrir mão de ACID. Custo da escolha errada: 30–40% do tempo reimplementando constraints na aplicação. |
| **SQLite** (arquivo) | zero instalação, bom para demo | Um escritor bloqueia o banco inteiro; com 3 lojas gravando, vira contenção. Sem `EXCLUDE USING gist`, sem RLS, sem particionamento declarativo. Seria defensável num protótipo descartável, não num produto com 3 lojas. |
| **MySQL/MariaDB** | popularidade e maturidade | Recursos analíticos inferiores: sem `EXCLUDE`, sem RLS, sem `FILTER` em agregação, sem `NULLS NOT DISTINCT`, views materializadas ausentes ou limitadas. JSONB indexável com GIN e `btree_gist` não têm equivalente direto. Viável, mas cada recurso exigiria gambiarra. |
| **Cassandra/DynamoDB** | escala horizontal linear | Modelo BASE com consistência eventual. Estoque não pode ser eventual: leitura defasada mostraria produto já vendido. As consultas precisam ser definidas antes do modelo, e o Giro depende de consulta ad-hoc. Resolve petabytes; o problema tem 6,3 milhões de linhas. |
| **Neo4j** (grafos) | relação entre produtos | A travessia mais profunda é produto → categoria (2 níveis) e venda → item → produto (2 saltos). Isso é `JOIN`, não grafo. Recomendação de cesta não está no escopo. Tecnologia procurando problema. |
| **BigQuery/Snowflake** | escala infinita, sem operação | Não resolvem o transacional: entrariam como camada extra. Custo por bytes varridos penaliza exatamente o padrão do Giro. Não roda offline. Latência de segundos contra milissegundos da view materializada. |
| **Redis** | latência sub-milissegundo | É cache, não fonte de verdade. Não resolve problema atual: as consultas rodam de 1 ms a 3,6 s, sem gargalo de latência. Adicionaria um componente e um ponto de falha no pitch. |
| **TimescaleDB** | séries temporais com hypertables | Ver abaixo: foi a alternativa mais séria. |

### TimescaleDB — a alternativa mais séria

O Giro tem dados temporais reais. `estoque_snapshot` e `item_venda` são séries por
item e por dia. TimescaleDB adiciona hypertables com particionamento automático e
agregação contínua. Seria a escolha natural para monitoramento.

Por que não.

Primeiro, a consulta dominante não é janela deslizante de sensor. TimescaleDB
brilha em "média dos últimos 5 minutos por dispositivo". O Giro faz demanda média
por dia da semana, por item, nos últimos 28 dias. Isso é `GROUP BY` sobre partição
mensal.

Segundo, o particionamento nativo resolve. `PARTITION BY RANGE (data_venda)` com
partições mensais dá o mesmo *partition pruning*, sem extensão e sem migração.

Terceiro, retenção e compressão não são necessidade. 24 meses ocupam 3,1 GB, sem
pressão de retenção no MVP.

Quarto, custo de dependência. Exige instalar a extensão no servidor, o que é um
ponto de falha a mais na apresentação.

Por fim, TimescaleDB é PostgreSQL. A escolha real é "com extensão" contra "puro".
Com prazo curto e uma máquina de apresentação, puro é melhor.

Se o Giro evoluir para monitoramento com granularidade de hora, TimescaleDB passa
a ser correta. Está na seção 4.7 como gatilho de migração.

## Por que não usamos persistência poliglota

O edital pede explicação quando há mais de um banco. A pergunta real é: cada
banco cumpre papel que os outros não cumprem?

No Giro, não.

| Necessidade | Solução com um banco | Banco que "resolveria" |
|---|---|---|
| Análise colunar rápida | views materializadas e índices | DuckDB / ClickHouse |
| Atributos flexíveis | coluna `JSONB` | MongoDB |
| Cache de painel | views materializadas | Redis |
| Busca por nome | `pg_trgm` com índice GIN | Elasticsearch |
| Série temporal | particionamento mensal | TimescaleDB / InfluxDB |

Cada linha seria um banco a instalar, configurar, sincronizar e monitorar. Cada
sincronização é uma fonte de inconsistência.

A camada bronze cumpre o papel de data lake sem servidor adicional. São CSV e XML
brutos em `data/bronze/`, com linhagem e reprocessamento.

## Teorema CAP

CAP trata de sistema **distribuído**. Ele não garante ao mesmo tempo
Consistência, Disponibilidade e Tolerância a Partição sob partição de rede.

O MVP roda em um nó PostgreSQL. Não é distribuído, então **CAP não se aplica**.
Escrever "escolhemos CP" seria erro conceitual.

A análise correta é condicional.

### Se houvesse réplica de leitura

| Caminho | Escolha | Justificativa |
|---|---|---|
| Baixa de estoque | **CP** | Recusar a venda é aceitável: o operador repete. Vender o que não existe não é. |
| Dashboard | **AP** | Número de 2 minutos atrás é aceitável. Ficar sem painel não é. |

A decisão é por caminho, não do sistema inteiro. O PostgreSQL suporta réplica
síncrona para o transacional e assíncrona para o analítico.

### Se a análise saísse para fora

Parquet com DuckDB não tem dilema de disponibilidade. O problema é *staleness*
por construção: o arquivo é um retrato do `COPY`. É outra categoria de
compromisso.

Warehouse em nuvem opera como CP: prioriza consistência e tolerância a partição,
com disponibilidade menor durante falha regional.

### O que o MVP garante

| Garantia | Como |
|---|---|
| Atomicidade | `BEGIN`/`COMMIT` por lote |
| Consistência | constraints, domínios, FKs, `EXCLUDE`, equação de estoque |
| Isolamento | `READ COMMITTED` |
| Durabilidade | WAL com `fsync`; backup por `pg_dump` |
| Leitura consistente | snapshots MVCC |

É ACID completo em nó único, mais forte do que qualquer BASE ofereceria.

## Como o PostgreSQL resolve cada requisito

### Consistência (25%)

| Recurso | Onde | Garante |
|---|---|---|
| `DOMAIN` com `CHECK` | `002_dominios.sql` | EAN-13 válido, quantidade ≥ 0, dinheiro ≥ 0, UF real |
| `CHECK` de equação | `004_movimentos.sql` | `fim = início + entradas − saídas + ajustes` |
| `CHECK` de total | `004_movimentos.sql` | `líquido = bruto − desconto` |
| `UNIQUE NULLS NOT DISTINCT` | `004_movimentos.sql` | cupom único mesmo com série NULL |
| `EXCLUDE USING gist` | `003_cadastros.sql` | faixas de preço não se sobrepõem |
| Índice único parcial | `003_cadastros.sql` | um fornecedor preferencial por item |
| FK composta | `004_movimentos.sql` | item pertence a venda existente |

Um bug real foi encontrado por teste. A `UNIQUE` padrão trata `NULL` como
distinto. Isso permitia dois cupons idênticos com série NULL, duplicando receita em
silêncio. Corrigido com `NULLS NOT DISTINCT`. Evidência no caso C11 de
`tests/test_constraints.py`.

### Consulta analítica (20%)

| Recurso | Onde | Ganho |
|---|---|---|
| Particionamento mensal | `005_particoes.sql` | consulta de 30 dias lê 1 partição de 31 |
| Índices `INCLUDE` | `006_indices.sql` | *index-only scan* na agregação por item |
| Índices BRIN | `006_indices.sql` | 0,8% do tamanho do B-tree em `item_venda` (2 MB contra 247 MB); 35% em `venda` |
| Índices parciais | `006_indices.sql` | índice de falta ocupa fração do espaço |
| Views materializadas | `011_ouro_views.sql` | previsão e sugestão pré-computadas |
| Window functions | `q03`, `q04` | curva ABC e giro sem self-join |
| CTEs | todas | legibilidade sem perda de desempenho |

### Manutenção (15%)

Um processo. `pg_dump` e `pg_restore` para backup. `EXPLAIN ANALYZE` para
diagnóstico. Nenhuma ferramenta extra para instalar.

### Custo (15%)

Software livre, sem licença. Roda na máquina do desenvolvedor e no notebook da
apresentação. Custo de infraestrutura: R$ 0.

### Maturidade (10%)

Quase 40 anos de linhagem, desde o Postgres de 1986. O conjunto de ferramentas
Python é maduro (`psycopg`, SQLAlchemy, pandas), e a documentação é extensa. Em 11
dias, isso pesa mais que qualquer benchmark.

### Escalabilidade (10%)

Três caminhos, do mais barato ao mais caro:

1. **Vertical** — mais RAM e CPU. Resolve até ~100M de linhas com folga.
2. **Particionamento com retenção** — arquivar partições antigas em Parquet.
3. **Citus ou réplica** — escala horizontal quando necessário.

O modelo já está preparado: `loja_id` em todas as tabelas e partição por tempo. A
migração futura não exige redesenho.

### Latência (5%)

Medido com `EXPLAIN ANALYZE` no dataset completo. Resultados na seção 4.6.

## Conclusão

PostgreSQL é a escolha por quatro motivos.

O domínio é relacional e transacional, e ele é o melhor nisso. Cobre os requisitos
analíticos com particionamento, índices e views materializadas, sem segundo banco.
A escala atual não justifica nada mais complexo, e o caminho de crescimento já
está previsto. O custo operacional é o menor possível: um processo, zero licença,
roda offline.

As alternativas falham em critérios de peso alto, não em detalhes.

A escolha é conservadora de propósito. O edital valoriza justificativa, não
novidade.
