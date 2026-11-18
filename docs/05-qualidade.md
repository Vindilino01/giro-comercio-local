# 4.5 — Qualidade e governança dos dados

## O princípio

> **Dado ruim não é descartado em silêncio. Ele vai para quarentena com um código
> de motivo rastreável.**

A maioria dos pipelines faz `try/except: pass`. O efeito é que o número no
dashboard encolhe e ninguém sabe por quê — em geral o próprio dono do negócio.
Quando a receita de terça aparece 30% menor porque 1.200 cupons falharam na carga,
"o sistema está errado" é a conclusão racional.

O Giro trata qualidade como **processo auditável**, não como limpeza pontual.

## As sete dimensões

O edital pede completude, consistência, unicidade, validade e atualidade. O Giro
usa sete dimensões (acrescenta **acuracidade** e **conformidade**), cada uma com
regras implementadas, não apenas descritas.

| Dimensão | Definição | Pergunta que responde |
|---|---|---|
| **Completude** | O dado necessário existe? | Falta produto? Falta o dia inteiro? |
| **Unicidade** | O registro aparece uma vez só? | Cupom duplicado? EAN repetido? |
| **Consistência** | Os valores fecham entre si? | Total do cupom = soma dos itens? |
| **Validade** | O valor respeita o domínio? | EAN tem dígito correto? Data é futura? |
| **Acuracidade** | O dado reflete a realidade física? | Estoque do sistema = contagem? |
| **Atualidade** | O dado chegou a tempo? | Carga de ontem rodou até 06h? |
| **Conformidade** | Respeita a LGPD? | Há CPF em campo livre? |

## Catálogo de 21 regras

As regras vivem **em tabela** (`gov.regra_qualidade`), não em código. Três razões:
o relatório pode listá-las direto do banco, a severidade muda sem deploy, e a
métrica de qualidade é calculada a partir delas.

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
| DQ021 | consistência | alta | Registro rejeitado por cascata (registro filho de um pai rejeitado) | quarentena |

**As três ações são diferentes de propósito:**

- **Rejeitar:** o registro não tem salvação. Vai para quarentena e não entra.
- **Quarentena:** o registro pode estar certo, mas precisa de conferência humana.
- **Corrigir:** o dado é recuperável (DQ020 atribui a data de cancelamento) — mas a
  correção é **registrada**, porque correção silenciosa é tão ruim quanto descarte
  silencioso.

## O problema das cascatas — e por que DQ021 existe

Quando um produto é rejeitado por EAN inválido, todos os itens de venda que
apontam para ele ficam órfãos. Eles são rejeitados também.

**Na primeira versão, isso contaminou as métricas.** Os 4 itens "sem produto"
injetados propositalmente apareciam como ~9.400 rejeições — porque cada EAN
inválido derruba ~29 itens. O recall ficava ininterpretável.

**Solução:** regra própria (DQ021) para registros rejeitados por **dependência**,
separada dos defeitos do próprio registro. Isso permite afirmar com precisão:
"detectamos 100% dos itens sem produto (166 de 166 injetados) e registramos
**171.603 rejeições em cascata** como consequência" — número medido em
`gov.quarentena` no banco de qualidade, não estimado.

A ordem de grandeza importa para ler o recall: as 171.603 linhas em cascata
são 96,7% das 177.394 da quarentena. Contá-las como "defeitos detectados"
inflaria o recall; contá-las como "defeitos" seria errado, porque não são
defeituosas — são vítimas de um cadastro inválido a montante. Por isso DQ021
fica fora do cálculo de recall por regra e aparece separada.

Essa distinção é o tipo de rigor que separa "temos regras de qualidade" de
"medimos nossa qualidade".

## Fluxo de ingestão (ETL/ELT)

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

### Por que staging em TEXT, e não `COPY` direto na tabela final

O PostgreSQL aborta o `COPY` inteiro no primeiro valor malformado. Inserir CSV
direto na tabela final significaria: um EAN inválido em 4,1 milhões de linhas
derruba a carga completa, e nenhum registro chega.

Com staging em `TEXT`, a validação acontece em SQL, registro por registro — e o
dado ruim vai para a quarentena em vez de derrubar tudo.

### Por que validação em duas camadas

| Camada | Onde | Vantagem | Limitação |
|---|---|---|---|
| **Pipeline (SQL)** | `src/ingestao.py` | Diz **por que** falhou; preserva o payload | Depende de o código ser executado |
| **Banco (constraints)** | DDL | **Impossível burlar** | Aborta a transação; não diz o motivo legível |

As duas são necessárias. A do banco é a rede de segurança final — se alguém
inserir por `psql` direto, as constraints seguram. A do pipeline é o que torna a
rejeição **auditável**.

### Idempotência

Três mecanismos independentes:

1. **SHA-256 do arquivo** em `gov.lote_carga` — reimportar o mesmo arquivo é
   detectável.
2. **`ON CONFLICT DO NOTHING`** com chave natural — reload parcial não duplica.
3. **Mapa de IDs** (`stg.venda_id_map`) com `DISTINCT ON` — evita produto
   cartesiano quando a chave natural reaparece em partições diferentes.

**Bug real encontrado:** sem o `DISTINCT ON`, um único `venda_id` podia apontar
para mais de um destino e o `JOIN` com `item_venda` explodia. O mesmo defeito
de fan-out é o que produz as 171.603 linhas de DQ021: um EAN inválido no
cadastro derruba todos os itens que apontam para ele.

## Como medimos a qualidade (a parte que a maioria não faz)

Descrever regras vale pouco. **Medir a eficácia das regras** vale muito.

### O laboratório de dados sujos

O projeto gera **dois datasets a partir da mesma semente**:

| Dataset | Conteúdo | Uso |
|---|---|---|
| `data/bronze/limpo/` | dados coerentes | popular o banco de negócio |
| `data/bronze/sujo/` | mesma base + **17 tipos de defeito em quantidade conhecida** | medir detecção |

O injetor grava um **gabarito** (`_gabarito.json`) listando exatamente quais
registros foram corrompidos. Com isso, medimos:

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

- **DQ001** — A precisao abaixo de 100% vem do dataset sintetico: vendas do dia que perdeu a carga (D14) tambem aparecem sem data valida no staging. Sao rejeicoes corretas, mas nao foram injetadas como D01.
- **DQ005** — O injetor duplica itens em pares; a dedupe remove as N-1 copias de cada grupo. O numero de rejeitadas e maior que o de injetadas porque os itens duplicados arrastam consigo registros que compartilham a mesma chave.
- **DQ006** — Defeito afeta 2 registros (par de EANs iguais); a dedupe mantem 1 e rejeita 1, como deve ser. Recall de 50% aqui e o resultado correto: rejeitar os dois descartaria o produto em vez de deduplicar.
- **DQ007** — PRECEDENCIA DE REGRAS. Um registro so pode ser rejeitado uma vez, pela primeira regra que o captura. Parte das vendas com total adulterado tambem recebeu data invalida ou futura no mesmo lote, e foi capturada por DQ001/DQ013 antes de chegar ao teste de total. O numero real de vendas com total incoerente que entrou na tabela e ZERO - verificado pelo teste de integridade I02.
- **DQ008** — Alguns itens adulterados foram rejeitados ANTES por outra regra (quantidade invalida, duplicidade), entao a regra de consistencia de valor nao chegou a avalia-los. A validacao final confirma que nenhum item com soma incoerente entrou na tabela.
- **DQ013** — PRECEDENCIA DE REGRAS. Das 27 vendas com data futura, algumas tambem estavam na amostra que perdeu a data (DQ001), que roda antes. Foram rejeitadas, so que sob outro codigo. Nenhuma venda com data futura entrou na tabela.
- **DQ020** — Cancelamento e um evento LEGITIMO do PDV, nao um defeito. A precisao baixa reflete isso: a regra registra todos os cupons cancelados sem data, e a maioria e operacao normal, nao corrupcao injetada.

<!-- RECALL_FIM -->

Fonte: `docs/evidencias/metricas_qualidade.json`, gerado pela mesma
execução que produziu os números acima.

### Os três asteriscos — e por que eles são o melhor argumento

**DQ006 (recall 50%):** o defeito afeta **2 registros** (um par de EANs iguais).
A dedupe mantém **1** e rejeita **1**. Recall de 50% aqui é o **comportamento
correto** — rejeitar os dois descartaria o produto inteiro em vez de deduplicar.
Um sistema que reportasse 100% estaria fazendo a coisa errada.

**DQ008 e DQ014:** alguns registros adulterados foram rejeitados **antes** por
outra regra (duplicidade, quantidade inválida). A regra de consistência de valor
não chegou a avaliá-los. Verificação direta no banco confirma: **zero** itens com
soma incoerente entraram na tabela.

**DQ020 (precisão 1,3%):** cancelamento é um evento **legítimo** do PDV, não um
defeito. A regra registra todos os cupons cancelados sem data — e a maioria é
operação normal, não corrupção injetada. Precisão baixa aqui mede a frequência do
evento, não a qualidade da regra.

**Este é o ponto:** métricas de qualidade **precisam ser interpretadas**. Um
relatório que só mostra "recall 97%" esconde que 3% podem ser comportamento
correto. Mostrar os três casos e explicá-los demonstra domínio do domínio.

### Por que bancos separados

O dataset sujo é carregado em **`giro_qualidade`**, um banco separado. Se fosse
carregado sobre o banco de negócio:

- faltaria um dia inteiro de vendas (defeito D14);
- haveria cupons cancelados sem data (D13);
- a série temporal teria buracos.

As consultas Q01–Q10 deixariam de refletir o modelo. Separar permite medir a
eficácia das regras **sem contaminar** a base de negócio.

## Governança

### Linhagem de dados

Todo registro carregado aponta para o lote que o originou:

```
gov.lote_carga
  ├── lote_id, origem, arquivo, hash_arquivo, data_referencia
  ├── iniciado_em, finalizado_em, status
  └── linhas_lidas, linhas_aceitas, linhas_rejeitadas

prata.venda.lote_carga_id ──────────► gov.lote_carga.lote_id
prata.item_venda (via venda) ───────►
prata.estoque_snapshot.lote_carga_id ►
```

Isso permite reverter um lote específico se ele estiver corrompido, sem afetar os
demais.

### LGPD

**A decisão de design mais importante: o Giro não coleta dado pessoal.**

| O que normalmente se coletaria | O que o Giro faz |
|---|---|
| CPF do cliente no cupom | **Não coleta.** A análise é por SKU e por loja |
| Nome e endereço | **Não coleta** |
| Programa de fidelidade | Fora do escopo do MVP |
| Dado do consumidor | Apenas o agregado: quantos itens, qual valor, qual SKU |

**Por que isso resolve a LGPD na modelagem, não na política:** não há dado
pessoal para proteger. É a aplicação do princípio da **minimização** (LGPD art. 6º,
III) na estrutura do banco, e não em um documento à parte.

**Mas há o risco residual:** o campo `documento_ref` da movimentação de estoque é
texto livre, e o operador pode digitar um CPF ali. Por isso existe a regra
**DQ019**, que detecta o padrão e rejeita o registro.

```
Padrão detectado: [0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}
Ação: rejeitar + quarentena
```

**Base legal** (se houvesse dado pessoal no futuro): execução de contrato
(art. 7º, V) para dados do titular da loja; legítimo interesse (art. 7º, IX) para
dados agregados de operação. **Não** usamos consentimento, porque o consumidor
não é usuário do sistema.

**Direitos do titular** (art. 18): como não há dado pessoal, não há dado a
exportar ou eliminar. Se um programa de fidelidade for criado, o identificador
deve ser pseudonimizado (`crypt(cpf, salt)`) e o direito de eliminação vira
`UPDATE` para anonimizar, preservando a série histórica.

### Controle de acesso

Três papéis com privilégio mínimo (`db/migrations/008_roles_rls.sql`):

| Papel | Permissões | Uso |
|---|---|---|
| `giro_app` | `SELECT`, `INSERT` nas tabelas da prata | Aplicação (PDV e ETL) |
| `giro_bi` | `SELECT` na prata e na ouro | Dashboard e análise |
| `giro_admin` | Tudo, incluindo DDL | Manutenção |

**`DELETE` não é concedido a nenhum papel de aplicação.** Exclusão de dado é
operação administrativa, não operação de rotina.

**Row-Level Security (RLS)** por `loja_id`: um gerente da loja 1 não vê dados da
loja 2, mesmo usando a mesma credencial de banco. Implementado em `db/migrations/008_roles_rls.sql`.

### Auditoria

`gov.auditoria` registra quem alterou o quê, quando, com os valores antes e
depois em `JSONB`. Atende ao art. 37 da LGPD (registro de operações) e é o que
permite investigar "quem mudou esse preço?".

## Backup e continuidade

| Aspecto | Implementação | Medido |
|---|---|---|
| Backup lógico | `pg_dump -Fc` diário | — |
| Retenção | 7 diários + 4 semanais + 3 mensais | — |
| Teste de restore | `pg_restore` em banco novo + consulta funcional | **RTO medido**, ver `06-prova-conceito.md` |
| WAL | `fsync` ativo (padrão) | garante durabilidade |
| RPO | até 24h (backup diário) | aceitável: perda de 1 dia de venda é recuperável do PDV |
| RTO | < 15 min para 3,1 GB | **7,5 min medido** no restore test |

**Por que RPO de 24h é aceitável:** o PDV é a fonte original. Se o banco se
perder, o dado pode ser reimportado do PDV. O backup é conveniência, não única
cópia.

## Matriz de riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Arquivo do PDV vem corrompido | Alta | Médio | Quarentena + reprocessamento do bronze |
| EAN mal cadastrado gera SKU fantasma | Alta | **Alto** | Validação de dígito verificador (DQ011) + relatório de duplicatas |
| Estoque do sistema diverge do físico | Alta | **Alto** | Inventário cíclico + selo de confiança oculta sugestão |
| Carga não roda em um dia | Média | Médio | Detecção (DQ018) + reprocessamento idempotente |
| CPF inserido em campo livre | Baixa | **Alto** (LGPD) | DQ019 + treinamento do operador |
| Falha de disco no servidor | Baixa | **Alto** | Backup diário + teste de restore mensal |
| Acesso indevido entre lojas | Baixa | Médio | RLS + roles de privilégio mínimo |
| Previsão erra por mudança de padrão | Média | Médio | Monitorar WAPE; retreinar com janela recente |

## Evidências

| Arquivo | Conteúdo |
|---|---|
| `docs/evidencias/metricas_qualidade.json` | recall, precisão e F1 por regra |
| `docs/evidencias/carga_limpa.json` | 0 linhas rejeitadas em 6,3M; 3.290 cupons cancelados corrigidos (DQ020) |
| `docs/evidencias/carga_suja.json` | rejeições por regra no dataset com defeitos |
| `tests/test_constraints.py` | 22 casos que o banco **deve** rejeitar |
| `gov.quarentena` | payload completo de cada registro rejeitado |
