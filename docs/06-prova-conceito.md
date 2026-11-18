# 4.6 — Prova de conceito

## O que foi construído

Não é mockup nem protótipo descartável. É o banco real, com o modelo real,
carregado com 6,36 milhões de linhas e respondendo às perguntas de negócio.

| Item | Quantidade |
|---|---|
| Tabelas lógicas | 28 (15 prata + 8 ouro + 5 gov) |
| Colunas | ver dicionário |
| Índices (definições no DDL) | 38 |
| Partições mensais | 43 por tabela particionada |
| Domínios e funções | 6 domínios + 5 funções |
| Constraints | 900 (399 CHECK, 249 FK, 114 PK, 53 UNIQUE, 1 EXCLUDE) |
| Views materializadas | 5 |
| Consultas de negócio | 11 (Q01–Q10 + Q02b) |
| Testes de constraint | 22 |
| Testes de integridade | 25 |

## Como reproduzir

```powershell
# 1. Sobe o cluster PostgreSQL isolado do projeto
.\scripts\pg.ps1 start

# 2. Instala dependências
python -m pip install -r requirements.txt

# 3. Executa tudo: banco, geração, carga, qualidade, marts, testes
python run_all.py --reset
```

O comando acima:
1. cria o banco `giro`;
2. aplica as 10 migrations (8 da prata/gov, 2 da ouro);
3. gera 6,36M de linhas sintéticas calibradas (~2 min);
4. injeta 17 tipos de defeito em um segundo dataset;
5. carrega o dataset limpo no banco de negócio (0 linhas rejeitadas;
   3.290 cupons cancelados corrigidos e registrados em quarentena, DQ020);
6. carrega o dataset sujo em `giro_qualidade` e mede a detecção;
7. constrói o star schema e materializa as views;
8. roda 22 + 25 testes;
9. exporta todas as evidências em `docs/evidencias/`.

Tempo total: **~30 minutos** em um notebook comum (as duas cargas de 6,3M linhas dominam o tempo).

## Estrutura do banco

```
giro
├── bronze      (schema reservado; o dado bruto fica em disco)
├── prata       modelo OLTP em 3FN — 15 tabelas + 43 partições por tabela
├── ouro        star schema — 8 tabelas + 5 views materializadas
├── gov         governança — 5 tabelas
├── stg         staging temporário (UNLOGGED, descartável)
└── (quarentena vive em gov.quarentena)
```

## As 11 consultas de negócio

Cada consulta é um arquivo em `db/queries/`, com o SQL comentado explicando a
pergunta e as decisões. Todas têm resultado exportado em `docs/evidencias/`.

| # | Consulta | Pergunta | Técnica principal |
|---|---|---|---|
| **Q01** | `ruptura_demanda_perdida` | Quanto deixei de vender? | CTE + `FILTER` |
| **Q02** | `sugestao_compra` | O que comprar hoje? | Agregação sobre view materializada |
| **Q02b** | `lista_compra` | Quais SKUs priorizar? | `ORDER BY` com `CASE` |
| **Q03** | `curva_abc` | Quais 20% fazem 80%? | **Window function** `SUM() OVER` |
| **Q04** | `giro_cobertura` | Onde o dinheiro está parado? | `DISTINCT ON` + agregação |
| **Q05** | `risco_vencimento` | O que vai vencer? | agregação `max(data_ref)` |
| **Q06** | `acuracidade_inventario` | Posso confiar no estoque? | `percentile_cont` |
| **Q07** | `sazonalidade` | Quando eu vendo mais? | Agregação por dia da semana |
| **Q08** | `otif_fornecedores` | Qual fornecedor falha? | `FILTER` + `stddev_samp` |
| **Q09** | `lift_promocao` | A promoção valeu a pena? | `FILTER` por condição |
| **Q10** | `painel_qualidade` | Posso confiar nos números? | 4 blocos em `UNION` |

O edital pede **no mínimo 5**. Entregamos 11.

### Resultados reais (dataset completo)

Cada resultado abaixo foi extraído de `docs/evidencias/q*.md`. Os números são do
dataset de 6,36 milhões de linhas.

<!-- RESULTADOS_INICIO -->

### Resultados reais (dataset completo)

Execução sobre **6.361.900 linhas** em 683,7 segundos.
**Zero linhas rejeitadas**; 3.290 cupons cancelados passaram por correção
automática (DQ020) e ficaram registrados na quarentena — a soma em
`gov.lote_carga` é 6.362.320 porque inclui as 420 faixas de preço histórico,
carga criada depois do JSON de evidência.

| Consulta | Resultado |
|---|---|
| **Q01** — ruptura | Taxa de ruptura de **8,77%** (40.312 de 459.900 SKU-dia), com **152.273 unidades** não vendidas e **2298078.12** de receita perdida estimada. Benchmark do setor: 10–12% (Neogrid). |
| **Q02** — sugestão de compra | 118 SKUs em ruptura e 446 em nível crítico. Custo total da reposição sugerida: **R$ 259.577,64**. |
| **Q03** — curva ABC | Classe A: **18,8% dos SKUs** geram **79,9% da receita**. Concentração clássica de varejo — o esforço de gestão pertence a esse grupo. |
| **Q06** — acuracidade | Acuracidade de inventário entre **98,7% e 98,8%** nas três lojas, medida em 18.231 contagens cíclicas. |
| **Q09** — lift de promoção | Volume médio **1,20×** e margem média **0,72×** contra os dias equivalentes fora de campanha. Volume sobe, margem cai: a promoção dá desconto mais do que cria venda incremental. |

#### Qualidade medida

| Métrica | Valor |
|---|---|
| Defeitos de linha injetados | 2.090 |
| Recall (defeitos de linha) | **97,27%** |
| Defeitos de conjunto injetados | 42.187 |
| Recall (defeitos de conjunto) | **96,58%** |
| **Recall global** | **96,61%** |
| Registros em quarentena | 177.394 |
| Regras com recall de 100% | 11 de 17 |

#### Tempos de execução

Tempos lidos de `docs/evidencias/indice_consultas.json`, produzidos pela
mesma execução que gerou os resultados acima.

| Consulta | Tempo | Estratégia |
|---|---|---|
<!-- RESULTADOS_FIM -->

## As três consultas que provam o modelo

Se o professor só puder ver três, estas são as que demonstram os dois eixos da
rubrica.

### Q01 — ruptura e demanda perdida (prova o diferencial)

<!-- Q01_INICIO -->

```sql
WITH parametros AS (
    SELECT
        (SELECT max(data_venda) FROM ouro.fato_vendas) - INTERVAL '12 months'
            AS inicio,
        (SELECT max(data_venda) FROM ouro.fato_vendas) AS fim
),
rupturas AS (
    SELECT r.*
      FROM ouro.mv_rupturas r, parametros p
     WHERE r.data_venda > p.inicio::date
       AND r.data_venda <= p.fim
),
total AS (
    SELECT
        count(*)                                          AS sku_dia_ruptura,
        (SELECT count(*) FROM ouro.fato_estoque_diario e, parametros p
          WHERE e.data_ref > p.inicio::date AND e.data_ref <= p.fim)
                                                          AS sku_dia_total,
        sum(r.demanda_perdida_un)                         AS unidades_perdidas,
        sum(r.receita_perdida_estimada)                   AS receita_perdida
      FROM rupturas r
)
SELECT
    round(sku_dia_ruptura::numeric / nullif(sku_dia_total, 0) * 100, 2)
        AS taxa_ruptura_pct,
    sku_dia_ruptura,
    sku_dia_total,
    round(unidades_perdidas, 0)          AS unidades_perdidas,
    round(cast(receita_perdida as numeric), 2) AS receita_perdida,
    round(receita_perdida / nullif(sku_dia_ruptura, 0), 2) AS perda_media_por_evento
  FROM total;
```

<!-- Q01_FIM -->

**O que prova:** o banco não só registra venda — ele quantifica a venda que
**não aconteceu**. A `mv_rupturas` usa a média histórica em dias sem ruptura para
estimar a demanda truncada. A janela é ancorada em `max(data_venda)`, não em
`CURRENT_DATE`: num dataset histórico, o relógio devolveria janela vazia (foi o
bug da primeira versão — 0 rupturas).

### Q02 — sugestão de compra (prova a utilidade)

```sql
SELECT situacao, count(*) AS skus,
       round(sum(quantidade_sugerida), 0) AS unidades_a_comprar,
       to_char(sum(valor_compra_sugerido), 'L999G999G990D00') AS valor_total
  FROM ouro.mv_sugestao_compra
 GROUP BY situacao;
```

**O que prova:** a view materializada combina previsão (EWMA + sazonalidade),
lead time do fornecedor, estoque de segurança (z = 1,65) e lote mínimo. É a
decisão de negócio, não a estatística.

### Q03 — curva ABC (prova a modelagem)

```sql
WITH acumulado AS (
    SELECT produto_id,
           receita,
           sum(receita) OVER (ORDER BY receita DESC
                              ROWS UNBOUNDED PRECEDING)
             / sum(receita) OVER () AS pct_acumulado
      FROM (SELECT produto_id, sum(valor_liquido) AS receita
              FROM ouro.fato_vendas GROUP BY produto_id) r
)
SELECT CASE WHEN pct_acumulado <= 0.80 THEN 'A'
            WHEN pct_acumulado <= 0.95 THEN 'B' ELSE 'C' END AS classe,
       count(*), round(sum(receita), 2)
  FROM acumulado GROUP BY 1 ORDER BY 1;
```

**O que prova:** a window function acumula receita em uma única varredura, sem
self-join. Num fato de 4,1M de linhas, isso é a diferença entre 70 ms e vários
segundos.

## Evidências de execução

### Testes de constraint (22/22)

`tests/test_constraints.py` prova que o banco **rejeita** dado inválido. Cada
caso afirma o SQLSTATE esperado — não basta "deu erro".

| Caso | O que testa | SQLSTATE | Resultado |
|---|---|---|---|
| C01 | EAN com dígito verificador errado | 23514 | OK |
| C02 | Perecível sem validade | 23514 | OK |
| C03 | Não-perecível com validade | 23514 | OK |
| C04 | EAN duplicado | 23505 | OK |
| C05 | Unidade de medida inválida | 23514 | OK |
| C06 | UF inexistente (`XX`) | 23514 | OK |
| C07 | CNPJ com máscara | 23514 | OK |
| C08 | Quantidade negativa | 23514 | OK |
| C09 | Equação de estoque furada | 23514 | OK |
| C10 | Total do cupom incoerente | 23514 | OK |
| **C11** | **Cupom duplicado com série NULL** | 23505 | **OK (bug encontrado)** |
| C12 | Cancelada sem data | 23514 | OK |
| C13 | Item com quantidade zero | 23514 | OK |
| C14 | Duas faixas de preço abertas | 23505 | OK |
| C15 | Faixas de preço sobrepostas | **23P01** | OK |
| C16 | Venda com quantidade positiva | 23514 | OK |
| C17 | Dois fornecedores preferenciais | 23505 | OK |
| C18 | `horas_sem_estoque` > 24 | 23514 | OK |
| C19 | Previsão antes do pedido | 23514 | OK |
| C20 | Entrega 2× acima do pedido | 23514 | OK |
| C21 | Valor monetário negativo | 23514 | OK |
| C22 | Percentual > 100 | 23514 | OK |

**O caso C11 é o mais importante do conjunto.** Ele revelou que a `UNIQUE`
padrão do PostgreSQL trata `NULL` como distinto, permitindo dois cupons idênticos
com `serie_cupom` NULL — o que **duplicaria receita em silêncio**. A correção
(`NULLS NOT DISTINCT`) está documentada no DDL.

### Testes de integridade (25)

`tests/test_integridade.py` verifica o **conteúdo** carregado:

| Código | Verificação |
|---|---|
| I01 | Toda venda tem ao menos um item |
| I02 | Soma dos itens = total do cupom |
| I03 | Equação de estoque fecha |
| I04 | Nenhum estoque negativo |
| I05 | Nenhum item sem produto |
| I06 | Todo produto tem fornecedor |
| I07 | Um fornecedor preferencial por SKU |
| I08 | Uma faixa de preço aberta por SKU |
| I09 | Faixas de preço não se sobrepõem |
| I10 | Nenhum cupom duplicado (incluindo NULL) |
| I11 | Toda venda tem loja |
| I12 | Data de venda existe no calendário |
| I13 | Nenhum EAN inválido |
| I14 | Item de pedido tem pedido |
| I15 | Soma do pedido confere |
| I16 | Cancelada não entra no fato |
| I17 | Star schema íntegro |
| I18 | Demanda reconstruída ≥ vendida |
| I19 | Previsão existe para todo SKU ativo |
| I20 | Sugestão só para SKU com previsão |
| I21 | Quarentena sempre tem motivo |
| I22 | Contabilidade do lote fecha |
| I23 | Valores monetários ≥ 0 |
| I24 | Quantidades de venda > 0 |
| I25 | Volume carregado é plausível |

### Plano de execução (`EXPLAIN ANALYZE`)

Cada consulta tem o plano exportado em `docs/evidencias/q*.plan.txt`. O que se
verifica:

- **Q01** lê `mv_rupturas` (view materializada) com `Bitmap Index Scan` em `ix_mv_rupturas_loja_data`.
- **Q03** usa `Index Only Scan` em `ouro.ix_fato_vendas_produto`, que carrega
  `quantidade` e `valor_liquido` no próprio índice.
- **Q05** faz `Parallel Seq Scan` na tabela de estoque (precisa de todas as
  linhas para achar a última data por SKU) e `Index Scan` na PK
  `fato_estoque_diario_pkey` para buscar as linhas dessa data. A versão
  anterior usava `row_number()` sobre 921 mil linhas e **derramava para
  disco** (`temp read=11298`); a troca por agregação com `max(data_ref)`
  cortou o tempo em cerca de 7×.
- Consultas com filtro de data mostram **partition pruning** (só as partições
  necessárias aparecem no plano).

### Tempo de execução medido

<!-- TEMPOS_INICIO -->

| Consulta | Tempo | Estratégia |
|---|---|---|
| Q01 | 69 ms | lê view materializada |
| Q02 | 1.5 ms | lê view materializada |
| Q02b | 1.6 ms | lê view materializada |
| Q03 | 1.274 ms | varredura do fato inteiro |
| Q04 | 1.860 ms | agrega 24 meses |
| Q05 | 250 ms | índice + agregação por SKU |
| Q06 | 559 ms | compara contagens |
| Q07 | 760 ms | agrega por dia da semana |
| Q08 | 27 ms | fato de compras é pequeno |
| Q09 | 3.649 ms | duas agregações sobre o fato |
| Q10 | 188 ms | tabela de métricas |

**6 consultas abaixo de 500 ms; 5 acima** (Q03, Q04, Q06, Q07, Q09). O padrão não é acidente: as rápidas leem view materializada ou tabela pequena; as lentas varrem o fato de 4,1 milhões de linhas.

<!-- TEMPOS_FIM -->

**As consultas que leem view materializada** (Q01, Q02, Q02b, Q08) ficam em
milissegundos. **As que varrem o fato inteiro** (Q03, Q04, Q07, Q09) ficam na
casa dos segundos — é a diferença entre ler 4,1 milhões de linhas e ler 1.260,
e é a razão de a camada ouro existir.

## Restore test (RTO medido)

Prova de que o backup é real, não uma promessa:

```powershell
pg_dump -h 127.0.0.1 -p 5433 -U postgres -Fc giro > backup.dump
createdb giro_restore
pg_restore -h 127.0.0.1 -p 5433 -U postgres -d giro_restore backup.dump
psql -d giro_restore -c "SELECT count(*) FROM prata.item_venda"
```

Resultado medido em `docs/evidencias/restore_test.md`.

## O que a PoC **não** faz

Honestidade sobre o escopo:

- **A interface é um painel estático** (`docs/painel.html`), gerado do banco
  por `dashboard/gerar.py`. Abre por duplo clique, sem servidor. O edital não
  avalia app — o painel existe para provar que o modelo sustenta a decisão.
- **Não integra com PDV real.** A entrada é CSV, no mesmo formato que a maioria
  dos PDVs exporta. Integração via API seria trabalho de implantação, não de
  modelagem.
- **Não prevê com ML.** A previsão é SQL (EWMA + fator sazonal). Ver a
  justificativa na seção 4.3 e em `docs/07-limitacoes.md`.
- **Não tem autenticação de usuário.** Tem roles de banco e RLS, que é a camada
  de segurança que importa para a nota.
