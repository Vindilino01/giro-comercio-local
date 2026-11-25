# Referências de UX/UI — o que o Giro copia e o que recusa

> **Por que este arquivo existe.** O `docs/referencias.md` cita fonte de
> *dado* (Nielsen, Neogrid, Kimball). Não citava fonte de *interface*.
> Numa banca de Análise de Dados isso passa; num projeto que se apresenta
> como produto, não. Este arquivo registra o que foi estudado, o que foi
> adotado e o que foi deliberadamente recusado — com o motivo.

## 1. Afresh — o concorrente mais próximo, e o que ele ensina

**O que é.** Plataforma de IA para varejo alimentar (EUA). O módulo
*Store Ordering* faz exatamente o que o Giro faz: escreve o pedido de
reposição item a item a partir da demanda prevista.

**O que o site deles afirma como benefício** (números deles, não nossos):

| Alegação | Valor |
|---|---|
| Aumento de vendas | 3% |
| Redução de perda | 25% |
| Ordenação mais rápida | 40–50% |

**A lição de interface, e é grande.** O texto principal é:

> "Afresh writes an order for every item in your store. **No need to build
> orders from scratch** or scramble when your most experienced order writer
> is out."

E, sobre inventário:

> "Afresh estimates on-hand inventory for every item and gives you a
> **short, targeted list to verify**. Every count sharpens the next
> prediction, so you **count less and trust more**."

Três padrões que o Giro **não** tinha e que passam a valer:

1. **O sistema escreve, o humano revisa.** O estado inicial não é uma
   tabela de 140 linhas para o dono montar. É um pedido pronto, com um
   caminho de revisão. A pergunta "o que eu compro?" já vem respondida.
2. **Lista curta de verificação, não inventário completo.** Pedir ao dono
   que confira 420 produtos é pedir que ele não confira nenhum. A lista de
   conferência tem que ser curta e escolhida pelo risco.
3. **"Count less and trust more" é a métrica real.** O sucesso não é
   mostrar mais dado; é o dono precisar conferir menos.

**O que o Giro faz melhor que o Afresh, e deve manter.** O Afresh vende
confiança ("our agents automate routine work"). O Giro prova confiança. O
recall medido é 96,61% contra gabarito. São 21 regras com código de motivo.
O selo por loja usa a pior dimensão. Numa banca, prova vence promessa.

**O que o Giro faz pior, e deve corrigir.** O Afresh nunca mostra uma
tabela crua como resposta principal. O Giro abre na lista de separação.

## 2. NN/g — *Data Tables: Four Major User Tasks* (Laubheimer, 2022)

Fonte: https://www.nngroup.com/articles/data-tables/

As quatro tarefas que uma tabela precisa suportar: **encontrar** registros
por critério, **comparar** dados, **ver/editar** uma linha, **agir** sobre
registros.

O que se aplica ao Giro, ponto a ponto:

| Regra do NN/g | Estado no Giro |
|---|---|
| Primeira coluna é identificador legível, não ID | ✅ nome do produto |
| Ordem das colunas reflete importância | ⚠️ "Comprar" fica no meio; deveria ser a primeira depois do nome |
| Filtros descobríveis e com estado visível | ⚠️ o filtro de fornecedor é a faixa, mas não há indicação textual de "filtrado" |
| Cabeçalho congelado em tabela maior que a tela | ❌ **não implementado** |
| Zebra/hover para não perder a linha | ✅ hover existe; zebra não |
| Comparação entre colunas distantes é cara | ⚠️ valor unitário ausente obriga cálculo mental |
| Ações em lote com seleção | ✅ checkboxes + copiar |

**Duas correções concretas saem daqui:** cabeçalho de tabela congelado, e
indicação textual de filtro ativo.

## 3. NN/g — *Mobile Tables* (Schade, 2017)

Fonte: https://www.nngroup.com/articles/mobile-tables/

Regras que valem para o celular da banca:

- Colunas legíveis sem zoom (2 colunas em tela estreita, se o texto for longo)
- Cabeçalho de coluna fixo
- Indicar que há mais dado além da dobra horizontal
- Primeira coluna fixa quando há rolagem lateral
- **Acordeões para agrupar** — dá visão geral e acesso direto
- Deixar o usuário escolher o subconjunto que quer ver

**O que o Giro faz:** a 390 px a tabela ganha rolagem própria, mas sem
cabeçalho fixo e sem primeira coluna fixa. O agrupamento por loja existe
(`tr.grp`) e cumpre o papel do acordeão.

## 4. NN/g — *8 Design Guidelines for Complex Applications* (Kaplan, 2020)

Fonte: https://www.nngroup.com/articles/complex-application-design/

As oito, e o que o Giro faz:

| # | Diretriz | Giro |
|---|---|---|
| 1 | Aprender fazendo | ✅ muda o nível e vê o total mudar ao vivo |
| 2 | Ajudar a adotar método mais eficiente | ❌ não há atalho de teclado para a lista, nem dica de caminho rápido |
| 3 | Caminhos flexíveis e fluidos | ⚠️ duas abas (lista / conta), sem caminho da linha para o histórico do SKU |
| 4 | Ajudar a rastrear ações e raciocínio | ❌ **nada**: o dono não consegue marcar "já pedi este" e voltar depois |
| 5 | Coordenar transição entre ferramentas | ⚠️ copiar existe; exportar CSV não |
| 6 | Reduzir poluição sem reduzir capacidade | ✅ `details` para ajustes e regras |
| 7 | Facilitar transição entre primário e secundário | ✅ tooltip do gráfico; ❌ nada na tabela |
| 8 | Tornar o importante visualmente saliente | ✅ dinheiro em escala de pôster |

**A lacuna mais séria é a #4.** Complex apps servem a trabalho interrompido.
O Nelson é interrompido no meio do pedido — chega cliente, chega entrega.
Hoje ele perde o que marcou. Isso é P1.

## 5. NN/g — *Progressive Disclosure* (Nielsen, 2006)

Fonte: https://www.nngroup.com/articles/progressive-disclosure/

Os dois erros que ele nomeia, e onde o Giro cai:

1. **Divisão errada entre inicial e secundário.** O que é frequente tem que
   estar na primeira tela. O Giro põe a lista em primeiro, o que é correto.
   Mas também põe 140 linhas de uma vez. Frequente não é sinônimo de
   completo.
2. **Progressão precisa ser óbvia.** O Giro usa `details` fechado, que é
   correto, mas o rótulo "Ajustes do cenário" não diz o que há dentro.

Regra que o Giro adota a partir daqui: **no máximo dois níveis de
divulgação.** Já são dois (lista → ajustes). Não criar um terceiro.

## 6. O que o projeto recusa, com motivo

| Padrão de mercado | Por que o Giro não usa |
|---|---|
| Grade de cartões de KPI | A decisão não existe em lugar nenhum nessa grade. É a recusa central do DESIGN.md. |
| Gráfico de linha de "receita ao longo do tempo" no topo | Responde "como foi", não "o que faço". O Giro abre na ação. |
| Semáforo verde/amarelo/vermelho sem palavra | Cor sozinha não carrega significado. Todo estado tem rótulo. |
| Onboarding em modal | O dono não vai ler tutorial. A tela tem que se explicar. |
| "Powered by AI" | O Giro é SQL determinístico. Alegar IA seria mentira verificável. |
| Dashboard em tempo real | O dado é D-1 por natureza. Fingir tempo real é a mentira mais fácil de contar. |

## 7. O que ainda falta estudar

Registrado para não parecer que a pesquisa acabou:

- **Linx, Bling, Omie** (ERPs brasileiros de varejo): os concorrentes reais
  do Nelson. Os sites bloqueiam acesso automatizado (403), então a
  referência ficou pelo que se conhece do setor, sem captura. Um estudo
  presencial com o PDV que ele já usa seria mais valioso que qualquer
  benchmark gringo.
- **Instacart / Shipt** (lista de compra para leigo): padrão de lista
  marcável que pode informar a folha impressa.
- **Teste com o Nelson real.** Não houve. Toda a persona é derivada de
  PRODUCT.md, não de observação. Isso é limitação declarada.
