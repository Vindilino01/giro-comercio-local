# Giro — sistema visual

Registro do painel (`docs/painel.html`), gerado por `dashboard/gerar.py` a partir do
PostgreSQL do projeto. Este arquivo descreve o que o código efetivamente faz, não uma
intenção anterior a ele.

## Por que esta tela não parece um dashboard genérico

O painel é a página de catálogo do distribuidor que o dono do mercadinho já lê toda
semana, reconstruída como tela de trabalho. Ele recusa o padrão da categoria — grade de
cartões de KPI sobre um gráfico sobre uma tabela — porque nesse padrão a decisão não
existe em lugar nenhum. Aqui, o primeiro viewport já contém a decisão: quanto comprar,
de quem, e o que a falta custou.

## Cor

Dois tintos de impressão sobre papel frio. A estratégia é **contida**: neutros tintados
do próprio mundo mais um acento profundo.

| Token | Valor | Papel |
|---|---|---|
| `--paper` | `#f1f0ea` | fundo, papel frio |
| `--paper-2` | `#e7e5dc` | faixa de data, hover de linha |
| `--paper-3` | `#dcd9ce` | trilho de barras |
| `--ink` | `#16211c` | texto, réguas fortes |
| `--ink-2` | `#4a554e` | texto secundário |
| `--ink-3` | `#5e6961` | rótulos, eixo |
| `--rule` | `#c9c7be` | régua fina, divisória de coluna |
| `--rule-2` | `#a9a79c` | régua interativa, trilho |
| `--green` | `#0b4f3c` | masthead, aba selecionada |
| `--green-deep` | `#073a2c` | números de dinheiro |
| `--red` | `#a8231b` | ruptura, perda |
| `--ochre` | `#8a5a00` | crítico, aviso |

A cor nunca carrega significado sozinha: todo estado aparece também em palavra
(`RUPTURA`, `CRÍTICO`, `REPOR`).

O verde do masthead deve ficar **literal** em `.masthead` (`#0b4f3c`, não `var(--green)`):
o verificador de contraste estático precisa resolver o fundo, e um `var()` o faz assumir
branco.

## Linguagem

A tela fala como o dono da loja, n�o como analista. A primeira vers�o usava
vocabul�rio de log�stica e de BI: SKU, lead time, ruptura, cobertura, ponto de
pedido, n�vel de servi�o, z � s � Vlead time. Nada disso existe no dia de quem
abre a loja �s 7h.

| Antes | Agora |
|---|---|
| SKU | produto |
| lead time | entrega (em dias) |
| ruptura | falta / acabou |
| cobertura | quantos dias dura |
| demanda/dia | vende por dia |
| ponto de pedido | precisa ter |
| n�vel de servi�o | margem de seguran�a |
| receita perdida | deixei de vender |
| departamento | se��o |
| selo de confian�a | d� para confiar? |

Os identificadores internos (colunas do banco, classes CSS, campos do JSON)
continuam iguais: a tradu��o acontece s� na camada de texto. Isso mant�m
dashboard/verificar.py e as consultas funcionando sem tocar em SQL.

## Dois modos de ver o pedido

A tabela de dez colunas explica a conta, mas n�o � como algu�m separa compra no
estoque. Por isso o painel abre em **lista de compras**: uma linha por produto,
caixa para marcar a dedo, quantidade e unidade. A tabela fica atr�s da aba
"Conferir a conta".

No papel (@media print) s� a lista sai: dez colunas n�o cabem em A4 sem virar
ileg�vel, e o que o dono leva para o telefone � a lista.

## Tipografia

| Voz | Fonte | Uso |
|---|---|---|
| Editorial | Piazzolla (serifa variável) | títulos, números de dinheiro, selos |
| Instrumento | Archivo (sans variável) | rótulos, tabelas, prosa curta |

Ambas são embutidas em base64 no HTML gerado (`dashboard/fonts/*.woff2`). Nenhuma
requisição de rede em tempo de execução — o arquivo abre offline, de um pendrive.

Escala fixa, não fluida: 12 / 13 / 14 / 16 / 18 / 22 / 28 / 40 px. O piso é 12 px
porque a tela é lida num projetor. Números usam `font-variant-numeric: tabular-nums
lining-nums` global.

## Estrutura

Sem cartões, sem sombras, sem cantos arredondados. A estrutura vem de réguas de 1 px e
de colunas de tabela. O documento tem cinco blocos, cada um respondendo a uma pergunta:

1. **Masthead** — marca, filtro de loja, data de referência, aviso de dado sintético.
2. **Lede** — uma frase com os dois números que definem o trade-off.
3. **O pedido da semana** - o total em escala de pôster, o controle de nível de serviço,
   a faixa de fornecedores e a lista de separação. No escopo "todas as lojas" a lista
   é agrupada por loja (cabeçalho `tr.grp` com `colspan` total, trazendo SKUs, unidades
   e valor daquele grupo): a mesma peça aparece uma vez por loja, e sem o cabeçalho a
   linha não dizia de qual loja era.
4. **A perda** — receita perdida, taxa de ruptura, demanda reconstruída, série mensal,
   ofensores.
5. **O capital** e **a confiança** — cobertura, vencimento, departamentos, selo, regras.

## O movimento assinatura: largura é valor

A faixa de fornecedores é o único gráfico de barras do topo da página e também a
navegação. A largura de cada segmento é **exatamente** a participação daquele fornecedor
no valor total do pedido. Clicar no segmento troca a lista de separação abaixo.

Implementação: `grid-template-columns` em `fr` proporcionais (`minmax(0, Nfr)`), nunca
`%` nem `flex-grow`. Com `%` o conteúdo mínimo estoura a faixa e o último fornecedor sai
cortado; com `flex` o item não encolhe abaixo do conteúdo.

Em colunas estreitas, `@container` reduz o tipo e esconde o lead time. O tamanho do valor
não varia por coluna enquanto couber: a faixa é uma comparação, e tipos desiguais
atrapalham a leitura.

## O segundo movimento: o controle remapeia o painel

O controle de nível de serviço (90–99%) recalcula o pedido inteiro ao vivo:

```
ponto_pedido = demanda_dia × lead_time + z × σ × √lead_time
quantidade   = ceil(max(0, ponto_pedido − estoque) / múltiplo) × múltiplo
```

`z` vem de uma tabela de inversa da normal. **95% usa 1,65**, o mesmo valor da migration
011 — a tela tem que bater com o banco até o centavo. Os insumos (`demanda`, `sigma`,
`lead`, `estoque`, `multiplo`, `custo`) vêm crus do banco no JSON; o front não guarda
números pré-calculados de quantidade.

O delta é sempre exibido contra 95%, para o dono ver o preço da proteção.

## Estados

| Componente | Estados |
|---|---|
| Segmento de fornecedor | default, hover, selecionado, foco visível, teclado (setas) |
| Coluna ordenável | default, hover, ordenada (`aria-sort`), foco |
| Botão | default, hover, cópia concluída (texto vira "Copiado" por 1,8 s), foco |
| Tabela | vazia (mensagem no lugar das linhas), rolagem própria no celular |
| `details` | fechado, aberto |

Movimento: apenas transições de estado, 90 ms, com `steps(2, end)`. Nada entra
voando, nada anima no carregamento. `prefers-reduced-motion` zera tudo.

## Impressão

A folha impressa é uma lista de pedido assinável. O CSS de `@media print`:

- remove controles, filtro e o controle de nível;
- converte a faixa de fornecedores em lista, preservando a proporção como barra
  (a largura continua sendo dado no papel);
- mantém os cabeçalhos de loja (`tr.grp`): com três entregas, a folha precisa ser
  separável na chegada;
- reduz a tabela de separação às colunas que se usa para separar mercadoria
  (situação, SKU, departamento, comprar, valor);
- força fundo branco e réguas mais escuras.

Resultado: 8 páginas A4, contra 12 antes do ajuste.

## Acessibilidade

- Contraste medido no navegador: piso de **5,01:1** em todo texto; o mínimo projetado
  para 12 px é 4,5:1.
- 21 controles focáveis, todos com nome acessível (rótulo, `aria-label` ou texto).
- Foco visível de 2 px em verde, `outline-offset: 2px`, em botão, `select`, `input`,
  `summary` e cabeçalho ordenável.
- Faixa de fornecedores é `role="toolbar"` (não `tablist`): os seis valores ficam
  visíveis ao mesmo tempo, então são botões de alternância — cada um carrega
  `aria-pressed` e `aria-controls="painel-fornecedor"`, e a lista abaixo é a região
  que eles mudam. Setas, `Home` e `End` movem a seleção; o foco acompanha a escolha
  (`render()` recria os botões e devolve o foco ao selecionado).
- O total recalculado é anunciado: `#total-delta` é `role="status"` com
  `aria-live="polite"`, e o slider declara `aria-valuetext` ("95% — nível de serviço").
- Um único `h1`, a pergunta que organiza a página ("O pedido da semana"); a marca no
  masthead é um `div`, não um título.
- Toda tabela tem `<th scope="col">`; a tabela de separação tem `<caption>` invisível
  que resume o conteúdo.
- No escopo "todas as lojas" a lista de separação é agrupada por loja: um cabeçalho
  `tr.grp` com `colspan` total abre cada grupo, com SKUs, unidades e valor daquela
  loja. Sem ele a mesma peça aparecia três vezes sem dizer de qual loja era.
- Abaixo de 900 px a faixa deixa de ter largura proporcional, e a legenda troca de
  texto junto com o layout ("ordenados por valor") em vez de continuar afirmando que
  a largura é o valor.
- `aria-live="polite"` no tooltip do gráfico.
- Estado nunca só por cor.

## O que este sistema recusa

- Cartões como estrutura de página; cartões aninhados.
- Números grandes com rótulo pequeno e estatísticas de apoio (o template de KPI).
- *Eyebrow* ou kicker acima de título.
- Texto em gradiente, vidro, sombra dura deslocada.
- Barra colorida de 4 px na lateral de cartão/alerta.
- Ícone/emoji no lugar de ícone desenhado.
- Monoespaçada como fantasia de "técnico": aqui só números tabulares.
- Família de sistema como voz de display: a serifa é auto-hospedada.
