# 4.2 — Diagnóstico dos dados

## Fontes

| Fonte | Formato | Frequência | Tipo | Uso |
|---|---|---|---|---|
| PDV (cupom fiscal) | CSV ou XML NFC-e | diária (D-1) | estruturado | vendas por item |
| Estoque | CSV / planilha | diária | estruturado | posição e falta |
| Cadastro de produto | CSV | sob demanda | estruturado | item, EAN, categoria |
| Pedido de compra | CSV | por evento | estruturado | prazo e OTIF |
| NF-e do fornecedor | XML | por entrega | semiestruturado | custo e quantidade |
| Calendário | API / CSV | anual | estruturado | sazonalidade |
| Inventário | planilha / app | mensal | estruturado | acurácia |

## Tipo dos dados

O núcleo é estruturado. Venda, estoque e produto têm esquema fixo. É caso de
banco relacional.

Há um componente semiestruturado real: o XML da NF-e. A estrutura é conhecida,
mas aninhada. Campos opcionais variam por fornecedor e por versão do layout.
Forçar em colunas rígidas exigiria migração a cada mudança. A solução é guardar o
XML bruto na camada bronze e extrair só os campos usados.

Não há dado não estruturado no escopo. Sem imagem, áudio ou texto livre. Isso
justifica não usar banco de documentos nem vector database.

## Os 5 Vs

### Volume — calculado

```
3 lojas × 210 cupons/dia × 8,4 itens/cupom ≈ 5.300 linhas/dia
```

Com 24 meses:

| Entidade | Linhas | Cálculo |
|---|---|---|
| `item_venda` | 4.159.608 | 731 × 3 × 210 × 9,03 |
| `venda` | 545.093 | 731 × 3 × 248 |
| `estoque_snapshot` | 921.060 | 731 × 3 × 420 |
| `movimentacao_estoque` | 654.910 | venda, compra e perda |
| `pedido_compra` + `item_pedido` | 74.612 | 37.306 em cada |
| `promocao_produto` | 5.385 | 72 × ~75 |
| Cadastros e calendário | 1.652 | 420 itens, 731 dias, 72 promoções |
| **Total** | **6.362.320** | **3.116 MB** |

De onde vêm os 3.116 MB:

| Schema | Tabelas | Índices | Total |
|---|---|---|---|
| `prata` | 625 MB | 613 MB | 1.241 MB |
| `ouro` | 648 MB | 606 MB | 1.255 MB |
| `stg` | 603 MB | 13 MB | 616 MB |
| `gov` | 1,9 MB | 2,2 MB | 4 MB |

Os índices ocupam quase metade. São 38 definições. Entre elas está um covering de
247 MB, que carrega `quantidade` e `valor_total` para a Q03 sair do índice. O
`stg` é temporário: existe durante a carga e pode ser truncado.

Crescimento: ~265 mil linhas por mês, das quais ~174 mil são itens de venda.

Projeção 100× (300 lojas): 636 milhões de linhas, ~150 GB. A 300× (900 lojas):
1,9 bilhão, ~450 GB.

**Hoje não é Big Data.** 6,3 milhões de linhas cabem num notebook, e o PostgreSQL
processa isso em segundos. Hadoop ou Spark aqui seria erro de engenharia. O que
justifica a arquitetura hoje é veracidade, não volume. O volume entra na seção
4.7 como gatilho de mudança.

### Velocidade — moderada

| Operação | Taxa | Contexto |
|---|---|---|
| Escrita (PDV) | ~0,06 cupons/s por loja (pico 0,3/s) | 210 cupons em 12h |
| Escrita (itens) | ~0,5 linhas/s por loja | diluído no dia |
| Leitura (dashboard) | 1 carga por abertura | varre 12–24 meses |
| Leitura (sugestão) | 1× por dia | recalcula 420 itens |

A escrita é trivial. O desafio está na leitura: cada abertura do dashboard varre
milhões de linhas. Essa assimetria é o argumento central da seção 4.3.

Consequência direta: streaming (Kafka, Kinesis) está descartado. A decisão de
compra é semanal e o dado chega uma vez por dia. Tempo real seria complexidade
sem benefício.

### Variedade — o V que importa aqui

Convive com quatro formatos:

1. **CSV** — exportação do PDV e das planilhas.
2. **XML** — NF-e, aninhada e com campos opcionais.
3. **JSON** — APIs de feriados e futura integração com PDV.
4. **Texto livre** — `documento_ref` da movimentação, onde pode aparecer CPF.

Essa variedade justifica a camada bronze, que preserva o formato original. Se
tudo chegasse em CSV limpo, a bronze seria burocracia.

### Veracidade — o V crítico

| Problema | Frequência observada | Consequência |
|---|---|---|
| EAN ausente ou inválido | ~3% do catálogo/ano | item fantasma, previsão partida |
| Produto duplicado | ~1,5% do catálogo | demanda dividida |
| Cupom duplicado | 0,02% por lote | receita inflada |
| Estoque divergente do físico | 15% das contagens com desvio >5% | sugestão errada |
| Dia sem carga | ~1 por mês | série com buraco |
| Cancelamento não marcado | 0,5% dos cupons | receita inflada |
| Venda truncada por falta | 8,3% dos item-dia | **demanda subestimada** |

O último item dá origem ao diferencial do produto. Os outros são tratados pelo
pipeline da seção 4.5.

Zero real e dado ausente são coisas diferentes. Um dia sem venda pode ser:

- loja fechada (feriado) → zero legítimo;
- item em falta → zero legítimo, mas havia demanda;
- falha de carga → **dado ausente**.

Tratar os três como o mesmo número corrompe a previsão. O calendário separa os
dois primeiros. A regra DQ018 detecta o terceiro.

### Valor — o que os dados permitem decidir

| Decisão | Dado necessário | Efeito |
|---|---|---|
| Quanto comprar de cada item | histórico, prazo e falta | reduz capital e perda |
| Quando disparar o pedido | demanda no prazo e variabilidade | evita falta |
| Qual fornecedor priorizar | OTIF e prazo real | evita falta por atraso |
| Qual promoção repetir | retorno de receita e margem | evita desconto sem lucro |
| Onde focar a gestão | curva ABC | concentra esforço nos 20% |

## Padrão de acesso

A análise que sustenta a escolha do banco. Ela é assimétrica:

| Característica | Escrita (PDV) | Leitura (análise) |
|---|---|---|
| Frequência | contínua | 1–3 vezes por dia |
| Granularidade | 1 linha por vez | milhares de linhas |
| Padrão | `INSERT` pontual | `JOIN`, `GROUP BY`, janela |
| Latência tolerada | segundos | segundos |
| Consistência | **ACID obrigatório** | leitura consistente |
| Pico | fim de semana, 10h–13h | abertura do painel |

Três conclusões.

Primeiro, a escrita exige transação. Estoque não pode ficar negativo, cupom
duplicado não pode entrar, a soma dos itens tem que fechar. Isso é ACID e
restringe a escolha.

Segundo, a leitura é analítica. Varredura de colunas em milhões de linhas se
beneficia de armazenamento colunar ou de agregação pré-computada.

Terceiro, nenhum dos dois exige baixa latência. Isso libera espaço para views
materializadas em vez de um banco especializado.

## Consequência para a arquitetura

O padrão é assimétrico, e a solução não precisa ser um banco só. A seção 4.3
compara separar as duas cargas contra manter um banco.
