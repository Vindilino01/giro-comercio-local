# 4.1 — Problema e visão

## A dor

O dono de um comércio de bairro decide a compra por intuição. Ele olha a
prateleira, lembra que "arroz vende bem" e faz o pedido. O método falha nos dois
sentidos. Os dois custam dinheiro.

**Comprar de menos.** O produto acaba na quarta-feira. O cliente leva o resto da
cesta para outro lugar, e a venda não volta no dia seguinte. No varejo alimentar
brasileiro a falta fica entre 10% e 12% (Neogrid, 2020–2024). A média global é
8,3% (Nielsen). O problema é estrutural do setor.

**Comprar de mais.** O produto fica parado. No não perecível, o dinheiro não
gira. No perecível, vira lixo: o custo já foi pago e a receita nunca acontece. A
ABRAPPE mede 2,79% de perda média no supermercado. Em muitos casos isso supera a
margem líquida do negócio.

O dado para decidir já existe. Todo comércio tem PDV, e todo PDV grava venda por
item e por dia. Falta o uso: o histórico fica no sistema, o dono compra no
caderno.

## Por que as soluções atuais não resolvem

| Alternativa | Por que não serve |
|---|---|
| ERP de grande varejo | Custo e complexidade incompatíveis com uma loja |
| Planilha de controle | Não escala acima de ~50 itens; não prevê |
| Consultoria pontual | Resolve um mês; o problema volta |
| Relatório do PDV | Mostra o passado ("vendeu 400 em maio"), não o futuro |

## Público-alvo

**Primário:** dono ou gerente de comércio de bairro. Uma a três lojas, 300 a 1.200
itens ativos, faturamento mensal entre R$ 80 mil e R$ 600 mil. Tem entre 35 e 55
anos, usa o PDV e não tem analista nem equipe de TI.

**Secundário:** pequenas redes de bairro e distribuidores que atendem esse
público.

**Fora do MVP:** padarias com produção própria (o problema é ficha técnica),
restaurantes (consumo de insumo, não venda) e atacarejo (outra escala).

O motor serve a qualquer comércio com PDV. O dataset de demonstração é de um
mercado, porque é o segmento com mais dados públicos de calibração.

## Proposta de valor

> **O Giro transforma o histórico do PDV em previsão de demanda e sugestão de
> compra. Ele também avisa quando o dado não permite decidir.**

A primeira parte prevê. A segunda quase ninguém no segmento faz.

## Diferencial 1 — previsão que sabe da falta

Quase toda solução de previsão erra neste ponto.

Quando um item está em falta, a venda registrada é zero. A demanda não era zero:
havia cliente querendo comprar. Se o modelo aprende com zero, conclui que o item
vende pouco. Aí pede menos. O sistema cria a escassez que devia evitar.

O Giro reconstrói a demanda. Em dia de falta, a estimativa é a média histórica
daquele item naquele dia da semana. A média usa só dias sem falta. A coluna
`fonte_demanda` de `ouro.mv_demanda_diaria` marca se o valor é `observado` ou
`reconstruida`.

Medido no dataset: 91,38% das linhas são observadas e 7,90% são reconstruídas.

## Diferencial 2 — selo de confiança do dado

A previsão vale o que vale o estoque. Se o sistema diz 10 e a prateleira tem 6, a
sugestão está errada. O modelo pode estar correto: a base é que não.

O Giro mede a qualidade do dado de cada loja e exibe o selo junto da recomendação.

| Nota | Selo | O que acontece |
|---|---|---|
| ≥ 95% | CONFIAVEL | sugestão exibida |
| 85–95% | ATENCAO | sugestão com ressalva |
| < 85% | NAO_CONFIAVEL | sugestão bloqueada |

O selo usa a **pior** dimensão, não a média. Uma loja com completude 100% e
contagem de estoque em 84% tem um problema real. A média de 97% esconderia o elo
que faz a sugestão errar.

O bloqueio tem teste: `node scripts/testar_gate_confianca.js` força uma loja para
84%. As 420 linhas dela saem do pedido.

## Perguntas de negócio

| # | Pergunta | Consulta | Por que importa |
|---|---|---|---|
| P1 | Quanto deixei de vender por falta? | Q01 | Mede a dor em R$ |
| P2 | O que comprar, quanto e de quem? | Q02, Q02b | A decisão do produto |
| P3 | Onde meu dinheiro está parado? | Q04 | O outro lado |
| P4 | O que vai vencer? | Q05 | Perda em perecível |
| P5 | Posso confiar nos números? | Q06, Q10 | Sustenta o selo |
| P6 | Qual fornecedor falha? | Q08 | A entrega não é constante |

Também implementadas: concentração da receita (Q03), sazonalidade (Q07) e retorno
de promoção (Q09).

## KPIs do cliente

| KPI | Definição | Baseline medido | Meta |
|---|---|---|---|
| Frequência de falta | % de item-dia com estoque zero | 8,62% (24 meses) | reduzir 30% |
| Receita perdida | demanda não atendida × preço | Q01 | reduzir 40% |
| Cobertura | dias que o estoque aguenta | Q04 | manter 7–15 dias |
| Risco de vencimento | estoque acima da demanda até a validade | Q05 | reduzir 50% |
| Acurácia de contagem | 1 − \|contado − sistema\| / sistema | Q06 | ≥ 95% |
| OTIF | % de entregas no prazo e completas | Q08 | monitorar |

O baseline de 8,62% não é arbitrário. A Nielsen mede 8,3% no varejo alimentar
brasileiro, e o dataset foi calibrado para esse patamar. É conservador: a Neogrid
reporta 10–12%, e o dataset está abaixo.

Três números parecidos, com significados diferentes:

| Número | O que é | Janela |
|---|---|---|
| 8,3% | benchmark de mercado (Nielsen) | referência externa |
| 8,62% | falta medida no dataset | 24 meses |
| 8,77% | falta medida no dataset | 12 meses (janela da Q01) |

## KPIs do produto

| KPI | Definição | Onde é medido |
|---|---|---|
| Cobertura de itens | % do catálogo com previsão calculável | `mv_previsao_demanda` |
| Qualidade de detecção | recall e precisão por regra | `metricas_qualidade.json` |
| Frescor do dado | idade da última carga | `gov.lote_carga` |

## Modelo de negócio

Assinatura mensal por loja, com faixa por volume de itens. O custo marginal é
quase zero, porque o dado já existe. A aquisição vem pelo contador ou pelo
fornecedor de PDV, que já tem o relacionamento.

O edital não avalia plano de negócios. Esta seção mostra apenas que a escolha
técnica tem lastro comercial.
