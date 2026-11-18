# PRODUCT.md — Giro

## O que é

Giro é uma ferramenta de decisão de compra para donos de mercadinho de bairro.
Transforma o histórico do PDV em previsão de demanda e sugestão de compra por SKU,
e diz honestamente quando o dado ainda não é confiável para decidir.

## Quem usa

**Persona primária — Nelson, 48 anos.**
Dono de dois mercados de bairro em Santos. Trabalha 11 horas por dia, seis dias
por semana. Não tem analista nem gerente de TI. Usa o PDV para emitir cupom e
sabe ler o relatório de vendas que o sistema dele já imprime. Faz o pedido do
fornecedor numa planilha que ele mesmo montou em 2009.

**O que ele precisa do produto:** abrir, ver o que comprar, fechar. Cinco minutos.
Não vai aprender um sistema novo. Não vai ler manual.

**Onde ele usa:** na sala dos fundos da loja, num notebook de 15" com resolução
1366×768, ao lado de caixas de estoque, entre o fechamento do caixa e a saída
do último funcionário. Luz fria de lâmpada fluorescente.

**Modo:** Operate. Ele está executando uma tarefa, não sendo convencido de nada.
O sucesso é: ele entende o que comprar e confia no número.

## O que a tela precisa responder

Em ordem de prioridade — nesta ordem, não em outra:

1. **O que eu compro hoje?** A pergunta que traz Nelson de volta toda semana.
2. **Quanto eu estou perdendo?** Justifica o esforço; sem isso ele não muda de hábito.
3. **Posso confiar nesse número?** Sustenta as duas primeiras. Se o dado é ruim,
   a recomendação é perigosa.
4. **Onde meu dinheiro está parado?** A outra face do trade-off.
5. **A promoção valeu a pena?** Pergunta secundária, mas de alto valor.

## Restrições e verdades do produto

- **Os números têm que vir do banco.** Cada valor visível precisa ser rastreável
  até uma consulta. Isso é a tese do projeto, não um detalhe de engenharia.
- **O dado é histórico, não ao vivo.** A última carga é do dia anterior. A tela
  não deve fingir tempo real.
- **Nelson não lê SQL.** Mas o avaliador da banca lê. A tela serve aos dois:
  o número em primeiro plano, a consulta a um clique.
- **A base é sintética.** O produto não pode afirmar mais do que o dado sustenta.
- **Três lojas hoje, mas a interface não pode assumir uma.** O filtro de loja
  é parte do produto, não um extra.

## O que este produto não é

- Não é um ERP. Não emite cupom, não controla caixa, não faz financeiro.
- Não é um dashboard de "métricas". Não existe vanity metric aqui.
- Não é tempo real. A decisão é semanal; a cadência do dado é diária.
- Não é um app bonito. O edital é explícito: o foco é banco e modelagem.

## Entregável desta superfície

Um site estático gerado a partir do banco (`dashboard/site/`), aberto no navegador
sem servidor. Existe para provar, na banca, que o modelo de dados sustenta a
decisão de negócio — e para ser demonstrável sem depender de infraestrutura.
