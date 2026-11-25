# 4.6 — Prova de conceito

## O que foi construído

O banco real, com o modelo real, carregado com 6,36 milhões de linhas. Ele responde
às perguntas de negócio.

| Item | Quantidade |
|---|---|
| Tabelas lógicas | 28 (15 prata, 8 ouro, 5 gov) |
| Índices (definições no DDL) | 38 |
| Partições mensais | 43 por tabela particionada |
| Domínios e funções | 6 domínios e 6 funções |
| Constraints nomeadas | 311 (41 CHECK, 30 FK, 26 PK, 9 UNIQUE, 1 EXCLUDE) e 204 NOT NULL |
| Views materializadas | 5 |
| Consultas de negócio | 11 (Q01–Q10 e Q02b) |
| Testes de constraint | 23 |
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

O comando acima faz nove coisas.

1. Cria o banco `giro`.
2. Aplica as 12 migrations: 8 de prata e gov, 2 da ouro, grants e auditoria.
3. Gera 6,36M de linhas sintéticas calibradas, em cerca de 2 minutos.
4. Injeta 17 tipos de defeito num segundo dataset.
5. Carrega o dataset limpo no banco de negócio. Zero linhas rejeitadas, 3.290
   cupons cancelados corrigidos e registrados (DQ020).
6. Carrega o dataset sujo em `giro_qualidade` e mede a detecção.
7. Constrói o star schema e materializa as views.
8. Roda 23 e 25 testes.
9. Exporta as evidências em `docs/evidencias/`.

Tempo total: cerca de 30 minutos num notebook comum. As duas cargas de 6,3M
linhas dominam o tempo.

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

Cada consulta é um arquivo em `db/queries/`, com o SQL comentado. Todas têm
resultado exportado em `docs/evidencias/`.

| # | Consulta | Pergunta | Técnica |
|---|---|---|---|
| **Q01** | `ruptura_demanda_perdida` | quanto deixei de vender? | CTE e `FILTER` |
| **Q02** | `sugestao_compra` | o que comprar hoje? | agregação sobre view materializada |
| **Q02b** | `lista_compra` | quais SKUs priorizar? | `ORDER BY` com `CASE` |
| **Q03** | `curva_abc` | quais 20% fazem 80%? | window function `SUM() OVER` |
| **Q04** | `giro_cobertura` | onde o dinheiro está parado? | `DISTINCT ON` |
| **Q05** | `risco_vencimento` | o que vai vencer? | agregação `max(data_ref)` |
| **Q06** | `acuracidade_inventario` | posso confiar no estoque? | `percentile_cont` |
| **Q07** | `sazonalidade` | quando eu vendo mais? | agregação por dia da semana |
| **Q08** | `otif_fornecedores` | qual fornecedor falha? | `FILTER` e `stddev_samp` |
| **Q09** | `lift_promocao` | a promoção valeu a pena? | `FILTER` por condição |
| **Q10** | `painel_qualidade` | posso confiar nos números? | 4 blocos em `UNION` |

O edital pede no mínimo 5. Entregamos 11.

<!-- RESULTADOS_INICIO -->

### Resultados reais (dataset completo)

Execução sobre **6.361.900 linhas** em 683,7 segundos.
**Zero linhas rejeitadas.** Além disso, 3.290 cupons cancelados passaram por
correção automática (DQ020) e ficaram na quarentena. A soma em `gov.lote_carga`
chega a 6.362.320. A diferença são as 420 faixas de preço histórico, carga
criada depois do JSON de evidência.

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
<!-- RESULTADOS_FIM -->

## As três consultas que provam o modelo

Se a banca só puder ver três, são estas: elas cobrem os dois eixos da rubrica.

### Q01 — ruptura e demanda perdida

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

**O que prova.** O banco não registra só a venda. Ele quantifica a venda que não
aconteceu. A `mv_rupturas` usa a média histórica em dias sem ruptura para estimar
a demanda truncada.

A janela é ancorada em `max(data_venda)`, não em `CURRENT_DATE`. Num dataset
histórico, o relógio devolveria janela vazia. Foi o bug da primeira versão: zero
rupturas.

### Q02 — sugestão de compra

```sql
SELECT situacao, count(*) AS skus,
       round(sum(quantidade_sugerida), 0) AS unidades_a_comprar,
       to_char(sum(valor_compra_sugerido), 'L999G999G990D00') AS valor_total
  FROM ouro.mv_sugestao_compra
 GROUP BY situacao;
```

**O que prova.** A view materializada combina previsão, lead time do fornecedor,
estoque de segurança (z = 1,65) e lote mínimo. É a decisão de negócio, não a
estatística isolada.

### Q03 — curva ABC

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

**O que prova.** A window function acumula receita em uma varredura, sem
self-join. Num fato de 4,1M de linhas, a diferença é grande: 1,27 s medido contra
vários segundos da versão com self-join.

## Evidências de execução

### Testes de constraint (23 de 23)

`tests/test_constraints.py` prova que o banco rejeita dado inválido. Cada caso
afirma o SQLSTATE esperado. "Deu erro" não bastaria: o teste precisa provar qual
regra barrou o dado.

| Caso | O que testa | SQLSTATE | Resultado |
|---|---|---|---|
| C01 | EAN com dígito verificador errado | 23514 | OK |
| C02 | Perecível sem validade | 23514 | OK |
| C03 | Não perecível com validade | 23514 | OK |
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
| C18 | `horas_sem_estoque` acima de 24 | 23514 | OK |
| C19 | Previsão antes do pedido | 23514 | OK |
| C20 | Entrega 2× acima do pedido | 23514 | OK |
| C21 | Valor monetário negativo | 23514 | OK |
| C22 | Percentual acima de 100 | 23514 | OK |
| C23 | RLS: gerente não vê item de outra loja | — | OK (retorna 0) |

**C11 é o caso mais importante.** Ele revelou que a `UNIQUE` padrão trata `NULL`
como distinto. Dois cupons idênticos com `serie_cupom` NULL passavam, duplicando
receita em silêncio. A correção (`NULLS NOT DISTINCT`) está no DDL.

### Testes de integridade (25)

`tests/test_integridade.py` verifica o conteúdo carregado.

| Código | Verificação |
|---|---|
| I01 | toda venda tem ao menos um item |
| I02 | soma dos itens = total do cupom |
| I03 | equação de estoque fecha |
| I04 | nenhum estoque negativo |
| I05 | nenhum item sem produto |
| I06 | todo produto tem fornecedor |
| I07 | um fornecedor preferencial por SKU |
| I08 | uma faixa de preço aberta por SKU |
| I09 | faixas de preço não se sobrepõem |
| I10 | nenhum cupom duplicado, incluindo NULL |
| I11 | toda venda tem loja |
| I12 | data de venda existe no calendário |
| I13 | nenhum EAN inválido |
| I14 | item de pedido tem pedido |
| I15 | soma do pedido confere |
| I16 | cancelada não entra no fato |
| I17 | star schema íntegro |
| I18 | demanda reconstruída ≥ vendida |
| I19 | previsão existe para todo SKU ativo |
| I20 | sugestão só para SKU com previsão |
| I21 | quarentena sempre tem motivo |
| I22 | contabilidade do lote fecha |
| I23 | valores monetários ≥ 0 |
| I24 | quantidades de venda > 0 |
| I25 | volume carregado é plausível |

### Planos de execução

Cada consulta tem o plano exportado em `docs/evidencias/q*.plan.txt`.

- **Q01** lê `mv_rupturas` com `Bitmap Index Scan` em `ix_mv_rupturas_loja_data`.
- **Q03** usa `Index Only Scan` em `ouro.ix_fato_vendas_produto`, que carrega
  `quantidade` e `valor_liquido` no próprio índice.
- **Q05** faz `Parallel Seq Scan` no estoque (precisa de todas as linhas para
  achar a última data por SKU) e `Index Scan` na PK para buscar essas linhas. A
  versão anterior usava `row_number()` sobre 921 mil linhas e derramava para
  disco (`temp read=11298`). A troca por `max(data_ref)` cortou o tempo em cerca
  de 7×.
- Consultas com filtro de data mostram partition pruning. Só as partições
  necessárias aparecem no plano.

### Tempo de execução medido

<!-- TEMPOS_INICIO -->

| Consulta | Tempo | Estratégia |
|---|---|---|
| Q01 | 76 ms | lê view materializada |
| Q02 | 1.1 ms | lê view materializada |
| Q02b | 1.7 ms | lê view materializada |
| Q03 | 1.274 ms | varredura do fato inteiro |
| Q04 | 1.843 ms | agrega 24 meses |
| Q05 | 272 ms | índice + agregação por SKU |
| Q06 | 81 ms | compara contagens |
| Q07 | 760 ms | agrega por dia da semana |
| Q08 | 27 ms | fato de compras é pequeno |
| Q09 | 3.559 ms | duas agregações sobre o fato |
| Q10 | 53 ms | tabela de métricas |

**7 consultas abaixo de 500 ms; 4 acima** (Q03, Q04, Q07, Q09). O padrão tem explicação. As rápidas leem view materializada ou tabela pequena. As lentas varrem o fato de 4,1 milhões de linhas.

<!-- TEMPOS_FIM -->

As consultas que leem view materializada (Q01, Q02, Q02b) ficam em
milissegundos. As que varrem o fato inteiro (Q03, Q04, Q07, Q09) ficam na casa
dos segundos. Ler 4,1 milhões de linhas custa caro; ler 1.260 custa pouco. É a
razão de a camada ouro existir. A Q08 é rápida por outro motivo: o fato de
compras tem 37 mil linhas, não 4 milhões.

## Restore test

Prova de que o backup é real, não uma promessa.

```powershell
pg_dump -h 127.0.0.1 -p 5433 -U postgres -Fc giro > backup.dump
createdb giro_restore
pg_restore -h 127.0.0.1 -p 5433 -U postgres -d giro_restore backup.dump
psql -d giro_restore -c "SELECT count(*) FROM prata.item_venda"
```

Resultado medido em `docs/evidencias/restore_test.md`.

## O que a PoC não faz

Honestidade sobre o escopo.

- **A interface é um painel estático** (`docs/painel.html`), gerado do banco por
  `dashboard/gerar.py`. Abre por duplo clique, sem servidor. O edital não avalia
  app. O painel existe para provar que o modelo sustenta a decisão.
- **Não integra com PDV real.** A entrada é CSV, no formato que a maioria dos
  PDVs exporta. Integração via API seria trabalho de implantação, não de
  modelagem.
- **Não prevê com aprendizado de máquina.** A previsão é SQL: EWMA mais fator
  sazonal. A justificativa está na seção 4.3 e em `docs/07-limitacoes.md`.
- **Não tem autenticação de usuário.** Tem roles de banco e RLS, que é a camada
  de segurança que importa para a nota.
