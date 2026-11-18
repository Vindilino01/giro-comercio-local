# 4.2 — Diagnóstico dos dados

## Fontes de dados

| Fonte | Formato | Frequência | Tipo de dado | Uso no Giro |
|---|---|---|---|---|
| PDV (cupom fiscal) | CSV ou XML NFC-e | Diária (D-1) | Estruturado | Vendas por item, base de tudo |
| Sistema de estoque | CSV / planilha | Diária | Estruturado | Snapshot de estoque, ruptura |
| Cadastro de produto | CSV | Sob demanda | Estruturado | SKU, EAN, categoria, preço |
| Pedido de compra | CSV | Por evento | Estruturado | Lead time, OTIF |
| NF-e do fornecedor | **XML** | Por entrega | **Semiestruturado** | Conferência de custo e quantidade |
| Calendário de feriados | API / CSV | Anual | Estruturado | Sazonalidade |
| Contagem de inventário | Planilha / app | Mensal (cíclico) | Estruturado | Acurácia do estoque |

## Tipo dos dados

**Predominantemente estruturado.** O núcleo do negócio — venda, estoque, produto
— tem esquema fixo e bem definido: é exatamente o caso de banco relacional.

**Um componente semiestruturado real:** o XML da NF-e. Ele tem estrutura
conhecida, mas aninhada e com campos opcionais que variam por fornecedor e por
versão do layout. Forçá-lo direto em colunas rígidas exigiria migração a cada
mudança de layout. A solução é manter o XML bruto na camada bronze e extrair
apenas os campos usados para a prata.

**Nenhum dado não estruturado no escopo.** Não há imagem, áudio, vídeo ou texto
livre que precise de processamento. Dizer isso explicitamente importa: é o que
justifica **não** usar um banco de documentos ou um vector database.

## Os 5 Vs do Big Data

### Volume — calculado, não estimado

Premissas explícitas, calibradas com a realidade de um mercadinho de bairro:

```
3 lojas × 210 cupons/dia/loja × 8,4 itens/cupom ≈ 5.300 linhas de item/dia
```

Com 24 meses de histórico:

| Entidade | Linhas | Cálculo |
|---|---|---|
| `item_venda` | 4.159.608 | 731 dias × 3 lojas × 210 cupons × 9,03 itens |
| `venda` | 545.093 | 731 dias × 3 lojas × 248 cupons |
| `estoque_snapshot` | 921.060 | 731 × 3 × 420 SKUs |
| `movimentacao_estoque` | 654.910 | eventos de venda, compra e perda |
| `pedido_compra` + `item_pedido` | 74.612 | 37.306 em cada |
| `promocao_produto` | 5.385 | 72 promoções × ~75 SKUs |
| Cadastros e calendário | 1.652 | 420 produtos, 731 dias, 72 promoções, 3 lojas, 6 fornecedores, 420 preços |
| **Total** | **6.362.320** | **3.116 MB em disco** |

**De onde vêm os 3.116 MB** (medido por schema, `pg_total_relation_size`):

| Schema | Tabelas (heap) | Índices | Total |
|---|---|---|---|
| `prata` | 625 MB | 613 MB | **1.241 MB** |
| `ouro` | 648 MB | 606 MB | **1.255 MB** |
| `stg` (staging da carga) | 603 MB | 13 MB | **616 MB** |
| `gov` | 1,9 MB | 2,2 MB | **4 MB** |

Os índices ocupam quase metade do banco — é o custo de ter 38 definições de
índice, entre elas um covering de 247 MB que carrega `quantidade` e
`valor_total` para a Q03 sair do próprio índice. O `stg` com 603 MB é
temporário: existe durante a carga e pode ser truncado depois.

**Ritmo de crescimento: ~265 mil linhas/mês** (3 lojas), dos quais ~174 mil são
itens de venda.

**Projeção 100×** (300 lojas): **636 milhões** de linhas em 24 meses, ~150 GB. Para 300× (900 lojas) seriam ~1,9 bilhão e ~450 GB.

**Conclusão honesta: hoje não é Big Data.** 6,3 milhões de linhas cabem
confortavelmente num notebook, e um PostgreSQL processa isso em segundos. Usar
Hadoop ou Spark aqui seria erro de engenharia, não demonstração de competência.
O que justifica a arquitetura **hoje** não é o volume — são veracidade e
variedade. O volume entra na seção 4.7, como gatilho de mudança.

### Velocidade — moderada, e isso determina a decisão de ingestão

| Operação | Taxa | Contexto |
|---|---|---|
| Escrita (PDV) | ~0,06 cupons/s por loja (pico ~0,3/s) | 210 cupons em 12h |
| Escrita (itens) | ~0,5 linhas/s por loja | diluído no dia |
| Leitura (dashboard) | 1 carga a cada abertura | varre 12–24 meses |
| Leitura (sugestão de compra) | 1× por dia por loja | recalcula 420 SKUs |

A escrita é **trivial**. O desafio está na leitura: cada carregamento do dashboard
varre milhões de linhas. Essa assimetria — escrita pequena e frequente, leitura
grande e esporádica — é o argumento central da escolha de banco (seção 4.3).

**Consequência direta:** streaming (Kafka, Kinesis) está descartado. A decisão de
compra é semanal; a cadência natural do dado é diária. Processar em tempo real
seria complexidade sem benefício.

### Variedade — o V que realmente importa aqui

Quatro formatos convivem:

1. **CSV** — exportação do PDV e das planilhas de estoque.
2. **XML** — NF-e dos fornecedores, com aninhamento e campos opcionais.
3. **JSON** — APIs de feriados e, futuramente, integração com sistemas de PDV.
4. **Texto livre** — campo `documento_ref` da movimentação, onde pode aparecer
   CPF (ver LGPD na seção 4.5).

Essa variedade é o que justifica uma camada bronze que preserva o formato
original. Se todos os dados chegassem em CSV limpo, a camada bronze seria
burocracia.

### Veracidade — o V mais crítico do projeto

É aqui que o Giro ganha ou perde. Os problemas reais de dado em mercadinho:

| Problema | Frequência observada | Consequência se não tratado |
|---|---|---|
| EAN ausente ou inválido | ~3% do catálogo ao longo do ano | SKU fantasma, previsão separada para o mesmo produto |
| Produto duplicado | ~1,5% do catálogo | Demanda dividida entre dois registros |
| Cupom duplicado na reimportação | 0,02% por lote | Receita inflada |
| Estoque divergente do físico | 15% das contagens com desvio >5% | Sugestão de compra errada |
| Dia sem carga | ~1 dia/mês | Série temporal com buraco, previsão distorcida |
| Cancelamento não marcado | 0,5% dos cupons | Receita inflada |
| Venda truncada por ruptura | 8,3% dos SKU-dia | **Demanda subestimada — o erro central** |

O último item é o que dá origem ao diferencial do produto. Os outros são tratados
pelo pipeline de qualidade (seção 4.5).

**Zero real versus dado ausente** merece destaque. Um dia sem venda pode ser:
- loja fechada (feriado) → zero legítimo;
- produto em ruptura → zero legítimo, mas demanda existia;
- falha de carga → **dado ausente**, não zero.

Tratar os três como o mesmo número corrompe qualquer previsão. O Giro usa o
calendário para distinguir os dois primeiros e a regra DQ018 para detectar o
terceiro.

### Valor — o que os dados permitem decidir

| Decisão | Dado necessário | Valor estimado |
|---|---|---|
| Quanto comprar de cada SKU | histórico + lead time + ruptura | reduz capital parado e perda |
| Quando disparar o pedido | demanda no lead time + variabilidade | evita ruptura |
| Qual fornecedor priorizar | OTIF e lead time real | evita falta por atraso |
| Qual promoção repetir | lift de receita **e** de margem | evita promoção que só dá desconto |
| Onde focar a gestão | curva ABC | concentra esforço nos 20% que importam |

## Padrão de acesso

Esta é a análise que sustenta a escolha de banco. Ela é **assimétrica**:

| Característica | Escrita (PDV) | Leitura (análise) |
|---|---|---|
| Frequência | contínua, ao longo do dia | 1–3 vezes/dia |
| Granularidade | 1 linha por vez | varredura de milhares de linhas |
| Padrão | `INSERT` pontual | `JOIN` + `GROUP BY` + janela |
| Latência tolerada | segundos | segundos (não é tempo real) |
| Consistência exigida | **ACID obrigatório** | consistência de leitura (snapshot) |
| Pico | fim de semana, 10h–13h | abertura do dashboard, de manhã |

Três conclusões:

1. **A escrita exige transação.** Estoque não pode ficar negativo; cupom
   duplicado não pode entrar; a soma dos itens tem que fechar com o total. Isso
   é ACID, e restringe fortemente a escolha.
2. **A leitura é analítica.** Varredura de colunas em milhões de linhas é o
   padrão que mais se beneficia de armazenamento colunar ou de agregação
   pré-computada.
3. **Nenhum dos dois exige baixa latência** (sub-100 ms). Isso libera margem para
   usar views materializadas em vez de um banco especializado.

## Consequência para a arquitetura

O padrão de acesso é assimétrico; a solução não precisa ser um único banco.
A seção 4.3 avalia se vale separar as duas cargas ou manter um banco só, e
justifica a decisão com números.
