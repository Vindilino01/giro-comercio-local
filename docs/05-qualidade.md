# 4.5 — Qualidade e governança dos dados

## O princípio

> **Dado ruim não é descartado em silêncio. Ele vai para quarentena com um código
> de motivo rastreável.**

A maioria dos pipelines faz `try/except: pass`. O número no painel encolhe e
ninguém sabe por quê. A receita de terça aparece 30% menor porque 1.200 cupons
falharam na carga. O dono conclui que o sistema está errado. Ele não tem como
saber que faltou carga.

O Giro trata qualidade como processo auditável. Cada rejeição tem motivo, lote e
payload guardados.

## As sete dimensões

O edital pede cinco. O Giro usa sete: acrescenta **acuracidade** e
**conformidade**. Todas têm regra implementada, não só descrita.

| Dimensão | Definição | Pergunta |
|---|---|---|
| **Completude** | o dado necessário existe? | falta produto? falta o dia inteiro? |
| **Unicidade** | o registro aparece uma vez só? | cupom duplicado? EAN repetido? |
| **Consistência** | os valores fecham entre si? | total do cupom = soma dos itens? |
| **Validade** | o valor respeita o domínio? | EAN tem dígito correto? data é futura? |
| **Acuracidade** | o dado reflete a realidade física? | estoque do sistema = contagem? |
| **Atualidade** | o dado chegou a tempo? | carga de ontem rodou até 06h? |
| **Conformidade** | respeita a LGPD? | há CPF em campo livre? |

## Catálogo de 21 regras

As regras vivem em tabela (`gov.regra_qualidade`), não em código. Três razões. O
relatório lista direto do banco. A severidade muda sem deploy. A métrica de
qualidade é calculada a partir delas.

| Código | Dimensão | Severidade | Regra | Ação |
|---|---|---|---|---|
| DQ001 | completude | crítica | Venda sem data, loja ou cupom | rejeitar |
| DQ002 | completude | crítica | Item sem produto identificado | rejeitar |
| DQ003 | completude | alta | Snapshot ausente em dia de loja aberta | quarentena |
| DQ004 | unicidade | crítica | Cupom duplicado (loja, data, série, número) | rejeitar |
| DQ005 | unicidade | alta | Item duplicado no mesmo cupom | rejeitar |
| DQ006 | unicidade | crítica | EAN duplicado no cadastro | quarentena |
| DQ007 | consistência | crítica | `liquido ≠ bruto − desconto` | rejeitar |
| DQ008 | consistência | crítica | Soma dos itens ≠ total do cupom | rejeitar |
| DQ009 | consistência | crítica | Equação de estoque não fecha | quarentena |
| DQ010 | consistência | alta | Saída de estoque sem venda correspondente | alertar |
| DQ011 | validade | crítica | EAN-13 com dígito verificador errado | quarentena |
| DQ012 | validade | alta | Quantidade negativa ou zero | rejeitar |
| DQ013 | validade | alta | Data de venda no futuro | rejeitar |
| DQ014 | validade | alta | Preço unitário ≤ 0 | rejeitar |
| DQ015 | validade | média | UF inexistente | quarentena |
| DQ016 | acuracidade | alta | Divergência sistema × contagem > 5% | alertar |
| DQ017 | atualidade | alta | Carga não concluída até 06h (D+1) | alertar |
| DQ018 | atualidade | média | Dia de loja aberta sem venda | quarentena |
| DQ019 | conformidade | crítica | CPF em campo livre (LGPD) | rejeitar |
| DQ020 | consistência | média | Cancelada sem data de cancelamento | **corrigir** |
| DQ021 | consistência | alta | Rejeitado por cascata (filho de pai rejeitado) | quarentena |

As três ações são diferentes de propósito.

**Rejeitar:** o registro não tem salvação. Não entra.

**Quarentena:** o registro pode estar certo e precisa de conferência humana.

**Corrigir:** o dado é recuperável. DQ020 atribui a data de cancelamento. A
correção fica registrada, porque correção silenciosa é tão ruim quanto descarte
silencioso.

## Cascatas: por que DQ021 existe

Quando um produto é rejeitado por EAN inválido, todos os itens de venda que
apontam para ele ficam órfãos. Eles caem junto.

Na primeira versão isso contaminou as métricas. Os 166 itens "sem produto"
injetados apareciam misturados a **171.603** linhas em cascata. Cada EAN inválido
no cadastro derruba mais de dez mil itens de venda. O recall ficava
ininterpretável: 166 defeitos reais diluídos em 171.603 rejeições.

A solução foi uma regra própria. DQ021 marca registros rejeitados por
**dependência**, separada dos defeitos do próprio registro. Com isso é possível
afirmar: "detectamos 100% dos itens sem produto (166 de 166) e registramos
171.603 rejeições em cascata como consequência". O número vem de `gov.quarentena`
no banco de qualidade, não de estimativa.

A ordem de grandeza importa. As 171.603 linhas são 96,7% das 177.394 da
quarentena. Contá-las como defeito detectado inflaria o recall. Contá-las como
defeito seria errado: não são defeituosas, são vítimas de um cadastro inválido a
montante.

## Ingestão

```
                        ┌─────────────────────┐
   PDV (CSV)  ─────────►│  data/bronze/       │  dado bruto imutável
   NF-e (XML) ─────────►│  com hash SHA-256   │  (linhagem preservada)
   Planilhas  ─────────►└──────────┬──────────┘
                                   │
                              COPY para staging
                            (~20 s para 4,1M linhas)
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │  stg.* (UNLOGGED)   │  todas as colunas TEXT
                        │  staging temporário │  sem validação de tipo
                        └──────────┬──────────┘
                                   │
                      ┌────────────┴────────────┐
                      │  Regras DQ em SQL       │
                      │  de conjunto            │
                      └────────────┬────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
          ┌─────────────────┐          ┌──────────────────┐
          │ prata.*         │          │ gov.quarentena   │
          │ (constraints    │          │ payload JSONB +  │
          │  como rede de   │          │ reason_code      │
          │  segurança)     │          └──────────────────┘
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ ouro.*          │  star schema +
          │ (marts)         │  views materializadas
          └─────────────────┘
```

### Por que staging em TEXT

O PostgreSQL aborta o `COPY` inteiro no primeiro valor malformado. Inserir CSV
direto na tabela final teria um efeito. Um único EAN inválido em 4,1 milhões de
linhas derruba a carga completa, e nenhum registro chega.

Com staging em `TEXT`, a validação acontece em SQL, registro por registro. O dado
ruim vai para a quarentena em vez de derrubar tudo.

### Duas camadas de validação

| Camada | Onde | Vantagem | Limitação |
|---|---|---|---|
| **Pipeline (SQL)** | `src/ingestao.py` | diz **por que** falhou; preserva o payload | depende de o código rodar |
| **Banco (constraints)** | DDL | **impossível burlar** | aborta a transação; não diz o motivo legível |

As duas são necessárias. A do banco é a rede final. Se alguém inserir por `psql`
direto, as constraints seguram. A do pipeline é o que torna a rejeição auditável.

### Idempotência

Três mecanismos independentes.

1. **SHA-256 do arquivo** em `gov.lote_carga`. Reimportar o mesmo arquivo é
   detectável.
2. **`ON CONFLICT DO NOTHING`** com chave natural. Reload parcial não duplica.
3. **Mapa de IDs** (`stg.venda_id_map`) com `DISTINCT ON`. Evita produto
   cartesiano quando a chave reaparece em partições diferentes.

**Bug real encontrado.** Sem o `DISTINCT ON`, um `venda_id` podia apontar para
mais de um destino, e o `JOIN` com `item_venda` explodia. O mesmo defeito de
fan-out produz as 171.603 linhas de DQ021. Um EAN inválido derruba todos os itens
que apontam para ele.

## Como medimos a qualidade

Descrever regras vale pouco. Medir a eficácia das regras vale muito.

### O laboratório de dados sujos

O projeto gera dois datasets da mesma semente.

| Dataset | Conteúdo | Uso |
|---|---|---|
| `data/bronze/limpo/` | dados coerentes | popular o banco de negócio |
| `data/bronze/sujo/` | mesma base + **17 tipos de defeito em quantidade conhecida** | medir detecção |

O injetor grava um gabarito (`_gabarito.json`) com os registros corrompidos. Com
isso dá para medir:

$$\text{recall} = \frac{\text{detectados}}{\text{injetados}} \qquad
\text{precisão} = \frac{\text{detectados}}{\text{rejeitados}} \qquad
F_1 = \frac{2PR}{P+R}$$

### Resultado medido

<!-- RECALL_INICIO -->

| Regra | Tabela | Injetados | Rejeitados | Recall | Precisão | F1 |
|---|---|---|---|---|---|---|
| DQ001 | venda | 21 | 21 | 100,0% | 100,0% | 100,0 |
| DQ002 | item_venda | 166 | 166 | 100,0% | 100,0% | 100,0 |
| DQ003 | estoque_snapshot | 1 | 189 | 100,0% | 0,5% | 1,1 |
| DQ004 | venda | 109 | 108 | 99,1% | 100,0% | 99,5 |
| DQ005 | item_venda | 519 | 992 | 100,0% | 52,3% | 68,7 |
| DQ006 | produto | 2 | 1 | 50,0% | 100,0% | 66,7 |
| DQ007 | venda | 77 | 77 | 100,0% | 100,0% | 100,0 |
| DQ008 | item_venda | 346 | 335 | 96,8% | 100,0% | 98,4 |
| DQ009 | estoque_snapshot | 153 | 153 | 100,0% | 100,0% | 100,0 |
| DQ011 | produto | 16 | 16 | 100,0% | 100,0% | 100,0 |
| DQ012 | item_venda | 416 | 388 | 93,3% | 100,0% | 96,5 |
| DQ013 | venda | 27 | 27 | 100,0% | 100,0% | 100,0 |
| DQ014 | item_venda | 208 | 192 | 92,3% | 100,0% | 96,0 |
| DQ016 | estoque_snapshot | 42.185 | 40.742 | 96,6% | 100,0% | 98,3 |
| DQ018 | venda | 1 | 189 | 100,0% | 0,5% | 1,1 |
| DQ019 | movimentacao_estoque | 3 | 3 | 100,0% | 100,0% | 100,0 |
| DQ020 | venda | 27 | 3.312 | 100,0% | 0,8% | 1,6 |

**Recall global: 96,61%** (42.777 de 44.277 registros injetados).  
Defeitos de linha: 97,27% · defeitos de conjunto: 96,58%.  
Registros em quarentena: 177.394.

**Observações metodológicas por regra:**

- **DQ001** — A precisao abaixo de 100% vem do dataset sintetico. Vendas do dia que perdeu a carga (D14) tambem aparecem sem data valida no staging. Sao rejeicoes corretas, mas nao foram injetadas como D01.
- **DQ005** — O injetor duplica itens em pares, e a dedupe remove as N-1 copias de cada grupo. O numero de rejeitadas supera o de injetadas porque os itens duplicados arrastam registros que compartilham a mesma chave.
- **DQ006** — Defeito afeta 2 registros, um par de EANs iguais. A dedupe mantem 1 e rejeita 1, como deve ser. Recall de 50% aqui e o resultado correto. Rejeitar os dois descartaria o produto em vez de deduplicar.
- **DQ007** — PRECEDENCIA DE REGRAS. Um registro so pode ser rejeitado uma vez, pela primeira regra que o captura. Parte das vendas com total adulterado tambem recebeu data invalida ou futura no mesmo lote. Foram capturadas por DQ001/DQ013 antes do teste de total. O numero real de vendas com total incoerente na tabela e ZERO, verificado pelo teste I02.
- **DQ008** — Alguns itens adulterados foram rejeitados ANTES por outra regra (quantidade invalida, duplicidade). A regra de consistencia de valor nao chegou a avalia-los. A validacao final confirma que nenhum item com soma incoerente entrou na tabela.
- **DQ013** — PRECEDENCIA DE REGRAS. Das 27 vendas com data futura, algumas tambem estavam na amostra que perdeu a data (DQ001), que roda antes. Foram rejeitadas, so que sob outro codigo. Nenhuma venda com data futura entrou na tabela.
- **DQ020** — Cancelamento e um evento LEGITIMO do PDV, nao um defeito. A precisao baixa reflete isso. A regra registra todos os cupons cancelados sem data, e a maioria e operacao normal, nao corrupcao injetada.

<!-- RECALL_FIM -->

Fonte: `docs/evidencias/metricas_qualidade.json`, gerado pela mesma execução que
produziu os números acima.

### Os três asteriscos

**DQ006 (recall 50%).** O defeito afeta 2 registros, um par de EANs iguais. A
dedupe mantém 1 e rejeita 1. Recall de 50% é o comportamento correto. Rejeitar
os dois descartaria o produto inteiro em vez de deduplicar. Um sistema que
reportasse 100% estaria fazendo a coisa errada.

**DQ008 e DQ014.** Alguns registros adulterados foram rejeitados antes por outra
regra: duplicidade, quantidade inválida. A regra de consistência de valor não
chegou a avaliá-los. A verificação direta no banco confirma zero itens com soma
incoerente na tabela.

**DQ020 (precisão 0,8%).** Cancelamento é evento legítimo do PDV. A regra
registra todos os cupons cancelados sem data, e a maioria é operação normal. A
precisão baixa mede a frequência do evento, não a qualidade da regra.

Métrica de qualidade precisa ser interpretada. Um relatório que mostra "recall
97%" esconde que 3% podem ser comportamento correto. Mostrar os três casos e
explicá-los demonstra domínio do domínio.

### Por que bancos separados

O dataset sujo é carregado em **`giro_qualidade`**, um banco separado. Carregado
sobre o banco de negócio, ele produziria três efeitos. Faltaria um dia inteiro de
vendas (defeito D14), haveria cupons cancelados sem data (D13), e a série
temporal teria buracos. As consultas Q01–Q10 deixariam de refletir o modelo.
Separar permite medir a eficácia das regras sem contaminar a base de negócio.

## Governança

### Linhagem

Todo registro carregado aponta para o lote que o originou.

```
gov.lote_carga
  ├── lote_id, origem, arquivo, hash_arquivo, data_referencia
  ├── iniciado_em, finalizado_em, status
  └── linhas_lidas, linhas_aceitas, linhas_rejeitadas

prata.venda.lote_carga_id ──────────► gov.lote_carga.lote_id
prata.item_venda (via venda) ───────►
prata.estoque_snapshot.lote_carga_id ►
```

Isso permite reverter um lote específico sem afetar os demais.

### LGPD

**A decisão de design mais importante: o Giro não coleta dado pessoal.**

| O que normalmente se coletaria | O que o Giro faz |
|---|---|
| CPF do cliente no cupom | **não coleta**; a análise é por SKU e por loja |
| Nome e endereço | **não coleta** |
| Programa de fidelidade | fora do escopo do MVP |
| Dado do consumidor | apenas agregado: quantos itens, qual valor, qual SKU |

Isso resolve a LGPD na modelagem, não na política. Não há dado pessoal para
proteger. É o princípio da **minimização** (LGPD art. 6º, III) aplicado à
estrutura do banco, e não a um documento à parte.

**Risco residual.** O campo `documento_ref` da movimentação é texto livre, e o
operador pode digitar um CPF ali. Por isso existe DQ019, que detecta o padrão e
rejeita o registro.

```
Padrão detectado: [0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}
Ação: rejeitar + quarentena
```

**Base legal**, se houvesse dado pessoal no futuro: execução de contrato (art.
7º, V) para dados do titular da loja, e legítimo interesse (art. 7º, IX) para
dados agregados de operação. Não usamos consentimento, porque o consumidor não é
usuário do sistema.

**Direitos do titular** (art. 18). Como não há dado pessoal, não há dado a
exportar ou eliminar. Se um programa de fidelidade for criado, o identificador
deve ser pseudonimizado (`crypt(cpf, salt)`). O direito de eliminação vira
`UPDATE` para anonimizar, preservando a série histórica.

### Controle de acesso

Três papéis com privilégio mínimo (`db/migrations/008_roles_rls.sql`).

| Papel | Permissões | Uso |
|---|---|---|
| `giro_app` | `SELECT`, `INSERT` na prata | aplicação (PDV e ETL) |
| `giro_bi` | `SELECT` na prata e na ouro | painel e análise |
| `giro_admin` | tudo, incluindo DDL | manutenção |

Nenhum papel de aplicação recebe `DELETE`. Exclusão é operação administrativa,
não rotina.

**Row-Level Security por `loja_id`**, com um limite que precisa ser dito sem
rodeio.

O RLS está ativo e testado nas quatro tabelas transacionais da prata: `venda`,
`item_venda`, `estoque_snapshot` e `movimentacao_estoque`. Com `SET ROLE giro_bi`
e `app.loja_id = '1'`, o gerente vê 1.189.273 itens. Com `'2'`, 1.390.282. Sem
`app.loja_id`, zero: o padrão é fail-closed. Provado por `python
scripts/test_rls.py` e pelo caso C23 da suíte de constraints.

**O que o RLS não cobre.** A camada ouro. `fato_vendas`,
`fato_estoque_diario` e as cinco views materializadas não têm policy. Materialized
view não aceita `ROW LEVEL SECURITY` no PostgreSQL: o comando falha com "not
supported for materialized views". Além disso, `fato_vendas` é o nível agregado
onde o painel do dono da rede lê as três lojas de propósito.

São dois públicos com necessidades opostas.

| Quem | Papel | O que vê |
|---|---|---|
| Gerente de uma loja | `giro_bi` | só a própria loja (RLS na prata) |
| Dono da rede / painel gerencial | `giro_admin` | as três lojas (ouro) |

A afirmação correta tem duas partes. O RLS isola o dado transacional por loja
para o papel de gerente. O painel gerencial usa papel administrativo e vê a rede
inteira. Dizer que "a mesma credencial não vê outra loja" seria falso na camada
ouro.

Se o produto evoluir para um painel por loja, o caminho é view comum. Ela filtra
com `WHERE loja_id = gov.loja_da_sessao()` em vez de materializar. O custo é
recalcular a cada consulta.

### Auditoria

`gov.auditoria` registra quem alterou o quê, quando, com os valores antes e depois
em `JSONB`. Atende ao art. 37 da LGPD e permite investigar "quem mudou esse
preço?".

## Backup e continuidade

| Aspecto | Implementação | Medido |
|---|---|---|
| Backup lógico | `scripts/backup.ps1` com `pg_dump -Fc` e retenção | **35,4 s**, dump de 179 MB |
| Retenção | 7 diários, 4 semanais, 3 mensais | aplicada pelo próprio script |
| Agendamento | tarefa do Windows, instruções no README | não configurado no repositório |
| Teste de restore | `pg_restore` em banco novo e consulta funcional | **RTO 7,5 min** |
| WAL | `fsync` ativo (padrão) | garante durabilidade |
| RPO | até 24h (backup diário) | perda de 1 dia de venda é recuperável do PDV |
| RTO | < 15 min para 3,1 GB | **7,5 min medido** |

**O que existe.** `scripts/backup.ps1` executa o dump, aplica a retenção e
verifica que o arquivo abre com `pg_restore -l`. Rodá-lo é um comando.

**O que não existe.** O agendamento. O script não se registra sozinho no
Agendador de Tarefas. Isso exige decisão de infraestrutura: conta de serviço,
janela de execução e onde guardar a cópia fora da máquina. O README traz o comando
`schtasks` pronto para quem for operar. Dizer que o backup é "diário" sem a tarefa
configurada descreveria uma intenção, não um fato.

**Por que RPO de 24h é aceitável.** O PDV é a fonte original. Se o banco se
perder, o dado pode ser reimportado. O backup é conveniência, não a única cópia.

## Matriz de riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Arquivo do PDV corrompido | Alta | Médio | quarentena e reprocessamento do bronze |
| EAN mal cadastrado gera SKU fantasma | Alta | **Alto** | DQ011 e relatório de duplicatas |
| Estoque do sistema diverge do físico | Alta | **Alto** | inventário cíclico e selo de confiança |
| Carga não roda em um dia | Média | Médio | DQ018 e reprocessamento idempotente |
| CPF em campo livre | Baixa | **Alto** (LGPD) | DQ019 e treinamento do operador |
| Falha de disco no servidor | Baixa | **Alto** | backup diário e teste de restore |
| Acesso indevido entre lojas | Baixa | Médio | RLS e privilégio mínimo |
| Previsão erra por mudança de padrão | Média | Médio | monitorar WAPE e retreinar |

## Evidências

| Arquivo | Conteúdo |
|---|---|
| `docs/evidencias/metricas_qualidade.json` | recall, precisão e F1 por regra |
| `docs/evidencias/carga_limpa.json` | 0 linhas rejeitadas em 6,3M; 3.290 cupons cancelados corrigidos |
| `docs/evidencias/carga_suja.json` | rejeições por regra no dataset com defeitos |
| `tests/test_constraints.py` | 23 casos que o banco **deve** rejeitar |
| `gov.quarentena` | payload completo de cada registro rejeitado |
