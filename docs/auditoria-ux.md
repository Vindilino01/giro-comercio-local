# Auditoria própria — o que eu encontrei medindo o painel

> Registro de trabalho da sessão de 25/11/2026, para não se perder quando
> o critique for sintetizado. Cada item foi **medido**, não deduzido.

## Confirmado por medição

### 1. O progresso de separação morre ao recarregar — P1

`estado.separados` é um `Set` em memória (molde.html:2102). Nada grava em
`localStorage` nem em `sessionStorage`.

**Medido:** marquei 5 itens na lista, recarreguei a página, 0 continuavam
marcados. Perda de 5 de 5.

**Por que é P1, e não P2.** O PRODUCT.md diz que Nelson trabalha na sala
dos fundos, entre o fechamento do caixa e a saída do último funcionário.
A tela tem 5 minutos. Cinco minutos é exatamente o intervalo em que alguém
é interrompido numa loja.

Se ele separa metade da mercadoria, é chamado no balcão e volta, o
trabalho sumiu. A resposta dele é voltar para a planilha de 2009. A
planilha não perde nada, porque é um arquivo.

**Correção:** persistir `separados`, `loja`, `fornecedor`, `nivel` e `modo`
em `localStorage` com chave versionada. Oferecer "limpar seleção" com
confirmação. Precisa sobreviver a fechar a aba, não só a recarregar.

### 2. Não há indicação textual de filtro ativo — P2

Cliquei num fornecedor: a tabela filtra, o segmento fica selecionado por
cor, mas nenhum texto diz "mostrando só Distribuidora Central". A única
pista é a cor do segmento.

**Por que importa:** o DESIGN.md promete "estado nunca só por cor". Aqui o
filtro é estado, e está só por cor. Um daltônico não sabe que está vendo
um sexto do pedido. Pode mandar esse pedido achando que é o total.

**Correção:** uma linha acima da lista, em texto corrente: "Mostrando os
23 produtos de Logística Vale Verde · R$ 68.315,59 · ver todos os 6
fornecedores". O "ver todos" é o botão de limpar.

### 3. Cabeçalho de tabela já é sticky — hipótese descartada

Eu suspeitava que faltasse. É a recomendação do NN/g para tabela grande.
Medi: `table.picking thead th` tem `position: sticky; top: 0; z-index: 2`
(molde.html:903). **Já estava correto.** Registro aqui para não "corrigir"
o que não está quebrado.

### 4. "Copiar pedido" já está bem resolvido — hipótese descartada

Suspeitava que o texto copiado fosse ambíguo. O critique de 16/11 tinha
esse P0. Verifiquei o código: `textoDoPedido()` agrupa por fornecedor e
por loja, com cabeçalho por bloco. Soma unidades por unidade de medida,
porque KG + PCT + DZ não somam. O P0 antigo foi corrigido.

Sobra uma melhoria menor: o texto não diz o que fazer se o fornecedor
pedir o pedido em outro formato. Não é problema de UI.

### 5. Zero `<h1>` era problema, e foi corrigido

O critique antigo registrou "Zero `<h1>`". Hoje o painel tem um `h1`: a
pergunta que organiza a página. Confirmado pelo teste de runtime (19/19,
incluindo "um unico h1").

## O que a pesquisa de referência acrescentou

Comparado com o **Afresh** (o concorrente mais próximo, ver
`referencias-ux.md`), eu esperava encontrar uma lacuna de enquadramento.
O Afresh escreve o pedido pronto. O Giro parecia abrir numa tabela de 140
linhas para o dono montar.

**Medi antes de afirmar, e a hipótese estava errada.** O painel já faz o
agrupamento certo:

| Grupo | Linhas | Estado inicial |
|---|---|---|
| Acabou — compre primeiro | 23 | visível |
| Quase acabando | 83 | visível |
| O resto da lista | 31 | recolhido atrás de botão |

São 106 linhas visíveis de 137, ordenadas por urgência, com o resto
recolhido. É o mesmo padrão do Afresh, obtido por agrupamento em vez de
frase de marketing.

Fica uma diferença de vocabulário, não de arquitetura de informação. O
Giro nunca diz "o pedido está pronto"; o dono deduz. Uma frase acima da
lista resolveria. É P2, não a reestruturação que eu supunha.

## O que continua em aberto

- Teste com o Nelson real: não houve. Toda a persona vem do PRODUCT.md.
- ERPs brasileiros (Linx, Bling, Omie): os sites bloqueiam acesso
  automatizado (403). A referência ficou pelo conhecimento de setor, sem
  captura.
- O painel não tem caminho da linha para o histórico daquele produto. O
  critique antigo já apontou. Continua valendo.
