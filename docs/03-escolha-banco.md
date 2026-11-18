# 4.3 — Escolha do banco de dados (Eixo 1)

## Resumo da decisão

**PostgreSQL 18 como banco único**, com três camadas internas (bronze em
arquivos, prata em 3FN, ouro em star schema) e recursos nativos usados para
resolver o que normalmente se resolveria comprando mais um banco.

Esta seção justifica a escolha, compara **oito alternativas** descartadas,
aplica o Teorema CAP com precisão e explica por que a persistência poliglota
**não** foi necessária neste projeto — apesar de ser a resposta "esperada" para
arquiteturas modernas.

## O que o problema exige

Da seção 4.2, os requisitos concretos:

| Requisito | Origem | Peso na decisão |
|---|---|---|
| Transação com invariante (estoque ≥ 0, cupom único) | regra de negócio | **crítico** |
| Integridade referencial (venda → item → produto) | modelo de dados | **crítico** |
| Agregação por período com janela (média móvel, ABC) | consultas Q01–Q10 | alto |
| Consulta ad-hoc pelo analista | exploração | alto |
| Join entre fatos e dimensões | star schema | alto |
| Carga diária em lote | padrão de acesso | médio |
| Rodar offline na apresentação | restrição de prazo | médio |
| Volume de 6,3M linhas hoje, 636M a 100× | projeção | médio |
| Custo próximo de zero no MVP | startup | médio |
| Esquema estável e bem definido | natureza do domínio | médio |
| Atributos variáveis de produto | catálogo heterogêneo | baixo |

## Critérios de decisão

Pesos definidos antes da avaliação, para evitar escolha conveniente:

| Critério | Peso | Justificativa do peso |
|---|---|---|
| Consistência (ACID) | **25%** | estoque inconsistente é falha grave, não degradação |
| Adequação ao tipo de consulta | **20%** | o valor do produto é a análise, não o registro |
| Facilidade de manutenção | **15%** | o cliente não tem TI; o time tem 11 dias |
| Custo | **15%** | startup, orçamento zero |
| Maturidade do ecossistema | **10%** | prazo curto exige ferramenta conhecida |
| Escalabilidade | **10%** | 6,3M hoje; 636M no cenário 100× |
| Latência | **5%** | nenhuma consulta exige sub-100 ms |

## Matriz de decisão

Notas de 1 a 5, multiplicadas pelo peso. Máximo possível: 5,00. Coluna
"Total" recalculada a partir da fórmula — verificação: 5×0,25 + 4×0,20 +
5×0,15 + 5×0,15 + 5×0,10 + 4×0,10 + 4×0,05 = **4,65**.

| Banco | ACID 25% | Consulta 20% | Manut. 15% | Custo 15% | Matur. 10% | Escala 10% | Latência 5% | **Total** |
|---|---|---|---|---|---|---|---|---|
| **PostgreSQL** | 5 | 4 | 5 | 5 | 5 | 4 | 4 | **4,65** |
| SQLite | 5 | 3 | 5 | 5 | 5 | 1 | 3 | **4,10** |
| MongoDB | 3 | 2 | 4 | 4 | 5 | 4 | 4 | **3,45** |
| MySQL/MariaDB | 5 | 3 | 4 | 5 | 5 | 3 | 3 | **4,15** |
| Cassandra | 2 | 1 | 2 | 3 | 3 | 5 | 5 | **2,50** |
| DuckDB | 2 | 5 | 5 | 5 | 4 | 2 | 5 | **3,85** |
| TimescaleDB | 5 | 4 | 3 | 4 | 4 | 4 | 5 | **4,15** |
| BigQuery/Snowflake | 3 | 5 | 3 | 1 | 5 | 5 | 2 | **3,45** |

**PostgreSQL vence com folga de 0,50 ponto** sobre o segundo colocado
(MySQL e TimescaleDB, empatados em 4,15), e vence nos critérios de maior peso.
Note que ele não é o melhor em nenhum critério isolado — é o melhor no
**conjunto ponderado**. Essa é a natureza de uma decisão de arquitetura.

**Verificação da conta** (para quem quiser conferir): cada total é
`Σ (nota do critério × peso)`. Exemplo do PostgreSQL:
`5×0,25 + 4×0,20 + 5×0,15 + 5×0,15 + 5×0,10 + 4×0,10 + 4×0,05`
`= 1,25 + 0,80 + 0,75 + 0,75 + 0,50 + 0,40 + 0,20 = 4,65`.

## As oito alternativas descartadas

O edital pede pelo menos duas. Documentamos sete, uma para cada linha da tabela
de tipos de banco da seção 4.3.

### 1. MongoDB (documentos) — descartado

**O que atrairia:** o catálogo de produto tem atributos que variam (peso, validade,
unidade, marca). Esquema livre facilitaria.

**Por que não:**

- **O problema é relacional, não documental.** Venda → item → produto → categoria
  é um grafo de entidades bem definidas com cardinalidade clara. Isso é o caso de
  uso canônico de modelo relacional.
- **Estoque exige invariante transacional.** "Não posso vender o que não tenho" e
  "o valor do cupom é a soma dos itens" são restrições que o MongoDB não expressa
  nativamente. Teríamos que implementar toda a validação na aplicação — e a
  aplicação é justamente o que muda com mais frequência.
- **Agregação por período é custosa.** As consultas Q01–Q10 usam `JOIN`, `GROUP
  BY`, janelas e CTEs. No MongoDB isso vira `$lookup` + `$group` no aggregation
  pipeline, mais difícil de escrever, mais difícil de otimizar e mais difícil de
  explicar no relatório.
- **`JSONB` no PostgreSQL cobre o caso.** Se um produto precisar de atributo
  extra, uma coluna `JSONB` resolve sem abandonar ACID nem joins.

**Custo estimado da escolha errada:** 30–40% do tempo de desenvolvimento
reimplementando constraints na aplicação, com risco de corrupção silenciosa do
estoque.

### 2. SQLite — descartado

**O que atrairia:** zero instalação, zero configuração, arquivo único — ótimo para
demonstração e para o pitch.

**Por que não:**

- **Concorrência limitada.** Um escritor bloqueia o banco inteiro. Com 3 lojas
  gravando em paralelo, isso vira contenção. Mesmo no MVP, o cenário é
  multi-loja.
- **Sem `RIGHT JOIN` nem `FULL OUTER JOIN`** em versões antigas, e sem suporte
  completo a janelas em versões muito antigas (resolvido nas recentes, mas o
  ecossistema assume limitações).
- **Escalabilidade nula.** Não suporta múltiplas instâncias nem replicação. No
  cenário 100×, é inviável.
- **Recursos que usamos não existem:** `EXCLUDE USING gist` para impedir
  sobreposição de faixas de preço, RLS para controle de acesso por loja,
  particionamento declarativo, `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

**Honestidade:** SQLite seria uma escolha **defensável** para um protótipo
descartável. Não é para um produto que se propõe a rodar em produção com 3 lojas.

### 3. MySQL / MariaDB — descartado

**O que atrairia:** é o banco relacional mais popular do mundo, maturidade
equivalente ao PostgreSQL.

**Por que não:**

- **Recursos analíticos inferiores.** `EXCLUDE`, RLS, `FILTER` em agregação,
  `NULLS NOT DISTINCT`, particionamento declarativo nativo e views materializadas
  **nativas** (MySQL não tem; MariaDB tem, com limitações) são todos recentes ou
  ausentes. O projeto usa todos.
- **JSONB é melhor que JSON.** O PostgreSQL indexa JSONB com GIN; o MySQL indexa
  JSON apenas via colunas geradas.
- **Extensibilidade.** `pg_trgm` para busca fuzzy e `btree_gist` para o
  `EXCLUDE` não têm equivalente direto.

**Veredito:** tecnicamente viável, mas cada recurso usado exigiria gambiarra. Com
11 dias, gambiarra custa ponto.

### 4. Cassandra / DynamoDB (chave-valor e wide-column) — descartado

**O que atrairia:** escalabilidade horizontal linear; é o que "grandes" usam.

**Por que não:**

- **Modelo BASE, consistência eventual.** Estoque **não pode** ter consistência
  eventual. Uma leitura defasada mostraria produto disponível que já foi vendido.
- **Consultas precisam ser definidas antes do modelo.** Em Cassandra, a tabela é
  desenhada em torno de uma query. O Giro precisa de consulta ad-hoc
  (`GROUP BY`, janela, join) — que é justamente o que Cassandra não faz.
- **Escala desnecessária.** Cassandra resolve petabytes com milhares de nós. O
  problema tem 6,3 milhões de linhas.
- **Custo operacional.** Cluster de 3 nós mínimo para produção. Startup sem TI
  não opera isso.

**Anti-padrão clássico:** escolher tecnologia pela escala que **talvez** se
atinja, em vez de pela necessidade que **se tem**.

### 5. Neo4j (grafos) — descartado

**O que atrairia:** existe relação entre produtos ("quem compra arroz também leva
feijão"), o que sugere grafo.

**Por que não:**

- **Não há travessia de profundidade variável.** O relacionamento mais complexo
  do domínio é produto → categoria (2 níveis) e venda → item → produto (2
  saltos). Isso é `JOIN`, não travessia de grafo.
- **Recomendação não está no escopo.** O produto não recomenda ao consumidor;
  prevê demanda para o dono.
- **Agregação numérica é fraca.** Somar receita por mês no Neo4j é possível, mas
  não é o que ele faz bem.

**Veredito:** tecnologia procurando problema. Se o Giro evoluísse para
recomendação de cesta, um grafo passaria a ter papel — mas seria **complementar**,
não substituto.

### 6. TimescaleDB (séries temporais) — descartado, e foi o mais difícil

**Esta foi a alternativa mais séria, e merece justificativa completa.**

**O que atrairia:** o Giro tem dados temporais genuínos — `estoque_snapshot` e
`item_venda` são séries por SKU e por dia. TimescaleDB é uma extensão do
PostgreSQL que adiciona hypertables com particionamento automático por tempo e
funções de agregação contínua. É tecnicamente elegante e seria a escolha natural
para um sistema de monitoramento.

**Por que não:**

- **A consulta dominante não é agregação em janela deslizante de sensor.**
  TimescaleDB brilha em "média dos últimos 5 minutos, por dispositivo, a cada
  minuto". O Giro faz "demanda média por dia da semana, por SKU, nos últimos 28
  dias" — que é `GROUP BY` comum sobre partição mensal.
- **O particionamento nativo do PostgreSQL já resolve.** `PARTITION BY RANGE
  (data_venda)` com partições mensais dá o mesmo *partition pruning*, sem
  extensão, sem dependência, sem migração futura.
- **Retenção e compressão automáticas não são necessidade.** 24 meses de dados
  são 3,1 GB em disco; não há pressão de retenção no MVP.
- **Custo de dependência.** TimescaleDB exige instalação da extensão no servidor.
  Em ambiente de apresentação, é um ponto de falha a mais.
- **Não é um banco diferente.** TimescaleDB **é** PostgreSQL. A escolha real é
  "PostgreSQL com extensão" vs "PostgreSQL puro". Com 11 dias e uma máquina de
  apresentação, puro é melhor.

**Registro honesto:** se o Giro crescesse para monitoramento contínuo de estoque
com granularidade de hora, TimescaleDB passaria a ser a escolha correta. Está
listado em `docs/07-limitacoes.md` como gatilho de migração.

### 7. BigQuery / Snowflake / Spark (data warehouse em nuvem) — descartado

**O que atrairia:** é o padrão da indústria para análise. Escala infinita,
custo por uso, sem operação.

**Por que não:**

- **Não resolvem o transacional.** Precisamos de ACID para estoque. Um data
  warehouse analítico não substitui o OLTP; entraria como camada adicional.
- **Custo imprevisível.** Cobrança por bytes varridos penaliza exatamente o
  padrão de acesso do Giro (varredura ampla de histórico). Um dashboard aberto 20
  vezes por dia pode gerar fatura inesperada.
- **Não roda offline.** A apresentação depende de internet e de conta ativa.
- **Latência de início.** BigQuery leva segundos para consulta interativa;
  PostgreSQL com view materializada leva milissegundos.
- **Complexidade de credenciais.** Chave de serviço, IAM, projeto, faturamento —
  para um MVP de 11 dias, é risco sem retorno.

**Quando faria sentido:** no cenário 100×, com múltiplas fontes e equipe de dados
dedicada. Ver seção 4.7.

### 8. Redis (chave-valor em memória) — descartado

**O que atrairia:** latência sub-milissegundo para o dashboard.

**Por que não:**

- **É cache, não fonte de verdade.** Redis pode perder dados em falha de
  configuração; não tem o modelo de consulta necessário.
- **Não resolve nenhum problema atual.** As consultas rodam em 1–90 ms. Não há
  gargalo de latência para resolver.
- **Adicionaria um componente a operar** — e um ponto de falha no pitch.

**Veredito:** otimização prematura. Se um dia houver necessidade, entra como
cache **na frente** do PostgreSQL, não no lugar dele.

## Por que NÃO usamos persistência poliglota

Arquiteturas modernas costumam justapor bancos ("Postgres para transação, Mongo
para catálogo, Redis para cache, Elastic para busca"). Isso é frequentemente
sintoma de arquitetura orientada a moda, não a requisito.

O edital é explícito: *"Se usar mais de um banco (persistência poliglota),
explicar o papel de cada um."* A pergunta implícita é: **cada banco tem papel
que os outros não cumprem?**

No Giro, a resposta honesta é não, pelos seguintes motivos:

| Necessidade | Solução com um banco | Banco adicional que "resolveria" |
|---|---|---|
| Análise colunar rápida | Views materializadas + índices | DuckDB / ClickHouse |
| Atributos flexíveis de produto | Coluna `JSONB` | MongoDB |
| Cache de dashboard | Views materializadas | Redis |
| Busca por nome de produto | `pg_trgm` + índice GIN | Elasticsearch |
| Série temporal | Particionamento mensal | TimescaleDB / InfluxDB |

Cada linha acima seria um banco a mais para instalar, configurar, sincronizar,
monitorar e explicar. Cada sincronização é uma fonte de inconsistência. Com 11
dias e um cliente sem TI, o custo supera o benefício em todos os casos.

**A camada bronze como "poliglota barata":** mantemos CSV e XML brutos em disco
(`data/bronze/`). Isso dá linhagem e reprocessamento — o papel que um data lake
cumpriria — sem nenhum servidor adicional. É a versão honesta de "data lake" para
o porte do projeto.

## Teorema CAP — aplicado com precisão

CAP afirma que um sistema **distribuído** não pode garantir simultaneamente
Consistência, Disponibilidade e Tolerância a Partição sob uma partição de rede.

**Ponto crucial que muitos trabalhos erram:** o MVP do Giro roda em **um único nó
PostgreSQL**. Não é um sistema distribuído, portanto **CAP não se aplica a ele**.
Escrever "escolhemos CP" seria erro conceitual.

A análise correta é condicional — o que aconteceria **se** houvesse distribuição:

### Cenário: réplica de leitura

Se adicionarmos uma réplica para o dashboard:

| Caminho | Escolha sob partição | Justificativa |
|---|---|---|
| **Baixa de estoque** (escrita) | **CP** — consistência | Recusar a venda é aceitável: o operador repete. Vender produto que não existe não é. |
| **Dashboard** (leitura) | **AP** — disponibilidade | Mostrar número de 2 minutos atrás é aceitável. Ficar sem painel não é. |

Isso **não** é "o sistema é CP" nem "o sistema é AP". É uma decisão **por
caminho**, e é o que um arquiteto sênior faria. O PostgreSQL suporta esse desenho:
réplica síncrona para o caminho transacional e assíncrona para o analítico.

### Cenário: camada analítica externa (100×)

Se migrássemos a análise para Parquet + DuckDB, ou para um warehouse:

- **Parquet/DuckDB:** não há dilema de disponibilidade. O problema é **staleness
  por construção** — o arquivo é um retrato do momento do `COPY`. É outra
  categoria de compromisso, não CAP.
- **Warehouse em nuvem (BigQuery):** é CP na prática — prioriza consistência e
  tolerância a partição em detrimento de disponibilidade durante falha regional.

### O que o MVP realmente garante

| Garantia | Como é obtida |
|---|---|
| Atomicidade | `BEGIN`/`COMMIT` em cada lote de carga |
| Consistência | Constraints, domínios, FKs, `EXCLUDE`, equação de estoque |
| Isolamento | Nível `READ COMMITTED` (padrão), adequado ao padrão de acesso |
| Durabilidade | WAL com `fsync` (padrão); backup por `pg_dump` |
| Leitura consistente para análise | Snapshots MVCC do PostgreSQL |

Isso é **ACID completo em nó único** — mais forte do que qualquer sistema BASE
ofereceria, e é exatamente o que o domínio exige.

## Como o PostgreSQL resolve cada requisito

Escolher o banco não basta; é preciso mostrar que ele é **usado** de forma
adequada. Cada recurso abaixo está implementado e é verificável no repositório.

### Consistência (25%)

| Recurso | Onde | O que garante |
|---|---|---|
| `DOMAIN` com `CHECK` | `002_dominios.sql` | EAN-13 válido, quantidade ≥ 0, dinheiro ≥ 0, UF real |
| `CHECK` de equação | `004_movimentos.sql` | `fim = inicio + entradas − saídas + ajustes` |
| `CHECK` de total | `004_movimentos.sql` | `liquido = bruto − desconto`; item = qtd × preço − desconto |
| `UNIQUE NULLS NOT DISTINCT` | `004_movimentos.sql` | Cupom único mesmo quando `serie_cupom` é NULL |
| `EXCLUDE USING gist` | `003_cadastros.sql` | Faixas de preço não se sobrepõem |
| Índice único parcial | `003_cadastros.sql` | Um fornecedor preferencial por SKU |
| FK composta | `004_movimentos.sql` | Item pertence a venda existente |

**Um bug real encontrado por teste:** a `UNIQUE` padrão trata `NULL` como
distinto, permitindo dois cupons idênticos com `serie_cupom` NULL — o que
duplicaria receita silenciosamente. Corrigido com `NULLS NOT DISTINCT`. A
evidência está em `tests/test_constraints.py`, caso C11.

### Consulta analítica (20%)

| Recurso | Onde | Ganho |
|---|---|---|
| Particionamento mensal | `005_particoes.sql` | *Partition pruning*: consulta de 30 dias lê 1 partição de 31 |
| Índices `INCLUDE` | `006_indices.sql` | *Index-only scan* para agregação por produto |
| Índices BRIN | `006_indices.sql` | Varredura histórica: **0,8% do tamanho do B-tree** em `item_venda` (2 MB vs 247 MB), 35% em `venda` (2 MB vs 5,96 MB) |
| Índices parciais | `006_indices.sql` | Índice de ruptura ocupa fração do espaço |
| Views materializadas | `011_ouro_views.sql` | Previsão e sugestão pré-computadas |
| Window functions | `q03`, `q04` | Curva ABC e giro sem self-join |
| CTEs | todas as queries | Legibilidade sem perda de desempenho (PG12+) |

### Manutenção (15%)

Operação de um único processo. `pg_dump`/`pg_restore` para backup. `EXPLAIN
ANALYZE` para diagnóstico. Nenhuma ferramenta adicional para instalar.

### Custo (15%)

Software livre, sem licença. Roda na máquina do desenvolvedor e no notebook da
apresentação. Custo de infraestrutura do MVP: **R$ 0**.

### Maturidade (10%)

quase 40 anos de linhagem (Postgres desde 1986), ecossistema Python maduro (`psycopg`, SQLAlchemy,
pandas), documentação extensa. Em 11 dias, isso importa mais do que qualquer
benchmark.

### Escalabilidade (10%)

Três caminhos, em ordem de custo:

1. **Vertical** — mais RAM e CPU. Resolve até ~100M de linhas com folga.
2. **Particionamento + retenção** — arquivar partições antigas em Parquet.
3. **Citus / réplica de leitura** — escala horizontal quando necessário.

O modelo de dados já está preparado (`loja_id` em tudo, partição por tempo), o
que significa que a migração futura não exige redesenho.

### Latência (5%)

Medido com `EXPLAIN ANALYZE` no dataset completo. Resultados em
`docs/06-prova-conceito.md`.

## Conclusão

PostgreSQL é a escolha porque:

1. **O domínio é relacional e transacional** — e ele é o melhor nisso.
2. **Ele cobre os requisitos analíticos** com particionamento, índices adequados
   e views materializadas, sem precisar de um segundo banco.
3. **A escala atual não justifica nada mais complexo** — e a arquitetura já
   prevê o caminho de crescimento.
4. **O custo operacional é o menor possível** — um processo, zero licença, roda
   offline.
5. **As alternativas falham em critérios de peso alto**, não em detalhes.

A escolha é conservadora de propósito. O edital valoriza justificativa, não
novidade — e a justificativa mais forte aqui é que a necessidade real não pede
nada mais complexo.
