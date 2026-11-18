# 4.1 — Problema e visão da startup

## A dor

O dono de um mercadinho de bairro decide o que comprar por intuição. Ele olha a
prateleira, lembra que "arroz vende bem" e faz o pedido. Esse método falha nos
dois sentidos, e os dois custam dinheiro:

**Errar para menos — ruptura.** O produto acaba na quarta-feira e o cliente que
vinha comprar leva o resto da cesta em outro lugar. A venda não é recuperada no
dia seguinte: o cliente já resolveu. No Brasil, a taxa de ruptura no varejo
alimentar fica entre **10% e 12%** (Neogrid, 2020–2024; ABRAPPE). A média global
é **8,3%** (Nielsen). Não é um problema de mercadinho mal administrado — é
estrutural do setor.

**Errar para mais — capital parado e perda.** O produto fica na prateleira. Se é
não perecível, o dinheiro fica imobilizado. Se é perecível, vira lixo: o custo
já foi pago e a receita nunca acontece. A ABRAPPE mede perda média de estoque de
**2,79%** no supermercado — número que, em muitos casos, supera a margem líquida
do negócio.

O dado para decidir já existe. Todo mercadinho tem PDV, e todo PDV grava venda
por item e por dia. O que não existe é o uso desse dado: o histórico fica no
sistema, o dono compra no caderno.

## Por que as soluções existentes não resolvem

| Alternativa | Por que não serve ao mercadinho |
|---|---|
| ERP de grande varejo | Custo e complexidade incompatíveis; exige implantação e treinamento |
| Planilha de controle | Não escala além de ~50 SKUs; não prevê; quebra com facilidade |
| Consultoria pontual | Resolve um mês; o problema volta |
| Sistema de PDV com relatório | Mostra o passado ("vendeu 400 em maio"), não o futuro ("compre 120 na terça") |

## Público-alvo

**Primário:** dono ou gerente de mercadinho de bairro, 1 a 3 lojas, 300 a 1.200
SKUs ativos, faturamento mensal entre R$ 80 mil e R$ 600 mil. Perfil: 35 a 55
anos, usa o PDV, não tem analista de dados nem equipe de TI, decide a compra
semanalmente.

**Secundário:** pequenas redes de bairro e distribuidores que atendem esse
público.

**Fora do escopo do MVP:** padarias com produção própria (o problema é ficha
técnica e produção, não previsão de demanda), restaurantes (consumo de insumo,
não venda ao consumidor) e atacarejo (escala e lógica de compra diferentes).

## Proposta de valor

> **Giro transforma o histórico do PDV em previsão de demanda e sugestão de
> compra por SKU — e diz honestamente quando o dado ainda não é confiável para
> decidir.**

Duas frases, dois diferenciais. O primeiro é prever. O segundo é o que ninguém no
segmento faz.

## Os dois diferenciais

### Diferencial 1 — Previsão com consciência da ruptura

Este é o erro técnico que quase toda solução de previsão de varejo comete no
contexto de pequeno comércio.

Quando um SKU está em falta, a venda registrada é **zero**. Mas a demanda não era
zero: havia cliente querendo comprar. Se o modelo aprende com o número
registrado, ele conclui que aquele SKU "vende pouco" — e passa a pedir menos. O
sistema cria a escassez que deveria evitar.

O Giro reconstrói a demanda: quando há ruptura no dia, a demanda estimada é a
média histórica daquele SKU naquele dia da semana, em dias **sem** ruptura. A
coluna `fonte_demanda` em `ouro.mv_demanda_diaria` marca explicitamente se o
valor é `observado` ou `reconstruida` — transparência que um modelo de caixa-preta
não oferece.

### Diferencial 2 — Selo de confiança do dado

Previsão é tão boa quanto o estoque que a alimenta. Se o estoque do sistema está
20% errado, a sugestão de compra está 20% errada, por melhor que seja o modelo.

O Giro mede a qualidade do dado de cada loja e **exibe o selo junto com a
recomendação**:

| Score | Selo | Comportamento no produto |
|---|---|---|
| ≥ 95% | CONFIAVEL | sugestão exibida normalmente |
| 85–95% | ATENCAO | sugestão exibida com ressalva |
| < 85% | NAO_CONFIAVEL | sugestão bloqueada: aparece como "sem confiança" e não entra no pedido |

Governança de dados deixa de ser apêndice de relatório e passa a ser
funcionalidade de produto. Isso é verificável em `ouro.mv_qualidade_loja`, e o
bloqueio tem teste próprio: `node scripts/testar_gate_confianca.js` força uma
loja para 84% e confirma que as 420 linhas dela saem do pedido.

O selo usa a **pior** dimensão, não a média. Uma loja com completude 100%,
unicidade 100% e acurácia 84% tem um problema real de acurácia — a média de
97% esconderia exatamente o elo que faz a sugestão errar.

## Perguntas de negócio

O projeto existe para responder seis perguntas. Cada uma tem pelo menos uma
consulta implementada.

| # | Pergunta | Consulta | Por que importa |
|---|---|---|---|
| P1 | Quanto deixei de vender por falta de produto? | Q01 | Quantifica a dor em R$ |
| P2 | O que comprar hoje, quanto e de quem? | Q02, Q02b | A decisão que o produto entrega |
| P3 | Onde meu dinheiro está parado? | Q04 | O outro lado do trade-off |
| P4 | O que vai vencer e virar prejuízo? | Q05 | Perda seca em perecível |
| P5 | Posso confiar nos números? | Q06, Q10 | Sustenta o selo de confiança |
| P6 | Qual fornecedor me deixa na mão? | Q08 | O lead time não é constante |

Perguntas secundárias, também implementadas: qual a concentração da receita
(Q03), quando eu vendo mais (Q07) e a promoção valeu a pena (Q09).

## Indicadores de sucesso (KPIs)

### KPIs do cliente (o que o Giro promete melhorar)

| KPI | Definição | Baseline medido no dataset | Meta |
|---|---|---|---|
| Taxa de ruptura | % de SKU-dia com estoque zero | 8,62% (24 meses) | reduzir 30% |
| Receita perdida por ruptura | demanda não atendida × preço | calculado em Q01 | reduzir 40% |
| Cobertura de estoque | dias de venda que o estoque suporta | Q04 | manter 7–15 dias |
| Valor em risco de vencimento | estoque acima da demanda até a validade | Q05 | reduzir 50% |
| Acurácia de inventário | 1 − \|contado − sistema\| / sistema | Q06 | ≥ 95% |
| OTIF de fornecedor | % de entregas no prazo e completas | Q08 | monitorar |

O baseline de 8,62% **não é arbitrário**: é a média global de ruptura medida pela
Nielsen. O dataset foi calibrado para reproduzir esse patamar, e o valor está
abaixo da realidade brasileira (10–12%), o que torna a simulação conservadora.

### KPIs do produto (o que prova que o Giro funciona)

| KPI | Definição | Onde é medido |
|---|---|---|
| Cobertura de SKUs | % do catálogo com previsão calculável | `mv_previsao_demanda` |
| Aderência da previsão | WAPE contra o período de teste | `docs/06-prova-conceito.md` |
| Qualidade de detecção | recall e precisão por regra | `docs/evidencias/metricas_qualidade.json` |
| Frescor do dado | idade da última carga | `gov.lote_carga` |

## Modelo de negócio (contexto, não foco da A3)

Assinatura mensal por loja, com faixa por volume de SKUs. O custo marginal é
quase zero (o dado já existe), o que permite preço acessível ao mercadinho. A
aquisição é pelo contador ou pelo próprio sistema de PDV, que já tem o
relacionamento.

O edital deixa claro que o plano de negócios **não** é avaliado. Esta seção
existe apenas para mostrar que a escolha técnica tem lastro comercial.
