# Auditoria de UX — método e achados

> Este arquivo registra **como** a auditoria foi feita, para que o
> resultado não pareça opinião. Cada achado tem uma medição.

## O método

Rodei o protocolo da skill `/impeccable` para o painel: duas avaliações
**independentes e isoladas**, que não viram a conclusão uma da outra.

| | O que faz |
|---|---|
| **Assessment A** | Revisão de design: especificidade, hierarquia, carga cognitiva, jornada emocional, 10 heurísticas de Nielsen |
| **Assessment B** | Evidência determinística: detector de padrões, contraste medido no navegador, alvos de toque, foco, ARIA, overflow, requisições externas |

A separação importa. Se a mesma cabeça faz as duas, a segunda vira
confirmação da primeira. Aqui, B achou **quatro problemas que A não
viu** — e um deles era grave.

## O que a medição encontrou

### P1 — Dinheiro cortado de 901 a 1280 px

O valor em R$ de cada fornecedor era recortado: 36 px de texto fora, em
901 px. Em 1280 px, uma coluna ainda cortava.

**Causa raiz.** O `@container (max-width: 126px)` que deveria encolher o
valor estava declarado **antes** de `.band__value`. Container query não
soma especificidade: mesma especificidade, vence a última regra. O 14 px
posterior sempre vencia.

O comentário do próprio código dizia "dinheiro cortado é pior que
dinheiro pequeno". A intenção estava escrita, e o CSS a desfazia.

### P1 — Trabalho de separação morria ao recarregar

`estado.separados` vivia só na memória. Medido: marquei 5 itens,
recarreguei, 0 continuavam.

Nelson é interrompido o tempo todo — chega cliente, chega entrega. Cinco
minutos é o intervalo inteiro da tarefa. Se ele separa metade da
mercadoria e é chamado, o trabalho sumia. A resposta racional dele era
voltar para a planilha de 2009, que não perde nada porque é arquivo.

### P1 — Overflow abaixo de 375 px

Três botões numa linha flex sem `flex-wrap`. Em 360 px, `#imprimir` saía
9 px fora da tela. A faixa medida: 320 → +49, 344 → +25, 360 → +9.

### P1 — Botões de 40 px no aparelho do persona

A media query de altura reduzia `.btn` para 40 px para ganhar espaço
vertical. Resultado: três botões abaixo do piso de 44 px no notebook
1366×657 nomeado no PRODUCT.md.

### P1 — Duas contagens com o mesmo rótulo

O título dizia "70 produtos" (SKUs distintos) e o rodapé dizia "137
produtos" (pares loja × SKU), na mesma tela. As duas estavam certas pela
sua definição e juntas faziam o dono desconfiar do número.

### P2 — Filtro só por cor

Clicar num fornecedor filtrava a lista, mas a única pista era o verde do
segmento. Contra a promessa do DESIGN.md: "estado nunca só por cor".

A correção tinha dois lugares: a legenda da faixa e a etiqueta no título.
A legenda some abaixo de 860 px de altura — **o aparelho do persona**.
Só a etiqueta chega nele.

### P2 — Abas sem navegação por seta

`role="tablist"` com dois tabs, ambos `tabindex=0`, sem handler de seta.
O leitor de tela anunciava "tab 1 de 2" e a seta não fazia nada. A faixa
de fornecedores já tinha o padrão correto.

### P3 — Fonte itálica embutida e nunca usada

43 KB em base64. Medido: os únicos três elementos em itálico são `<i>`
vazios de legenda, e herdam Archivo. O painel caiu de 1.022 para 988 KB.

## Hipóteses que a medição derrubou

Registrar o que **não** era problema importa mais que listar acertos: é
o que mostra que o método foi seguido.

| Hipótese | Resultado |
|---|---|
| "Falta cabeçalho de tabela fixo" | Já existe (`position: sticky`, molde:903) |
| "O texto copiado é ambíguo" | Já agrupa por fornecedor e por loja |
| "Falta o padrão do Afresh: pedido pronto, revisão curta" | Já existe: 23 rupturas visíveis, 31 recolhidas |
| "O contraste está abaixo do prometido" | 724 elementos, 0 abaixo do mínimo |

## O que o teste também errou

Três versões do teste de corte passaram sem medir nada:

1. `getBoundingClientRect` do elemento lê a caixa, não o texto
2. `scrollWidth` com `overflow: hidden` devolve a largura **já recortada**
3. `Range` com `white-space: normal` devolve a caixa da linha

A medição que funciona cria uma sonda invisível em `nowrap` e compara a
largura do texto com o espaço interno. Só essa versão reproduziu o que
a screenshot mostrava.

Isso fica registrado porque um teste verde que não mede é pior que teste
nenhum: ele autoriza a publicar.

## Verificação atual

| Teste | Resultado |
|---|---|
| Painel × banco | 18/18 |
| Runtime e acessibilidade do painel | 25/25 |
| Larguras da faixa (901 a 1600) | 8/8 |
| Contraste medido | 724 elementos, 0 abaixo |
| Alvos de toque | 0 abaixo de 44 px |
| Anéis de foco | 0 ausentes |
| Overflow | 320 a 1920 px, nenhum |
| Lint de texto | 0 violações |

## O que continua em aberto

- **Teste com o Nelson real.** Não houve. Toda a persona vem do
  PRODUCT.md, não de observação.
- **Leitor de tela real.** Os nomes acessíveis foram lidos da árvore de
  acessibilidade do Chromium, não do NVDA ou VoiceOver. A ordem de
  anúncio não foi verificada.
- **Zoom de 200% e alto contraste do Windows.** O harness headless não
  reproduz fielmente.
- **Impressão em papel.** Verifiquei por emulação de mídia, não em folha.
- **Caminho da linha para o histórico do produto.** O critique de 16/11
  apontou; continua valendo.
