# Roteiro do pitch — 10 minutos

> **Regra:** 10 minutos ÷ 7 pessoas ≈ 85 segundos por pessoa. O roteiro
> abaixo é cronometrado e cada fala tem o tempo marcado ao lado.
>
> **Plano B:** grave um vídeo de 90 s da demo na véspera e leve no celular.
> Se o notebook falhar, o `run_all.py` recria o banco; o vídeo cobre a falha
> de máquina.

---

## Estrutura de tempo

| Início | Bloco | Pessoa | Tempo |
|---|---|---|---|
| 0:00 | Abertura: dor e persona | P1 | 40 s |
| 0:40 | Os 5 Vs e a volumetria | P2 | 75 s |
| 1:55 | **Escolha do banco** | P3 | 85 s |
| 3:20 | **Modelagem** | P4 | 80 s |
| 4:40 | Qualidade e governança | P5 | 75 s |
| 5:55 | **Demo ao vivo** | P6 | 105 s |
| 7:40 | Limitações e 100× | P7 | 70 s |
| 8:50 | Fechamento + Q&A | P1 | 70 s |

**Deixa de ouro:** 20 segundos. Use se algo der errado no meio.

---

## P1 — Abertura (0:00 – 0:40)

**Fala:**

> O dono de um mercadinho de bairro compra por intuição. Ele olha a prateleira e
> decide. Esse método erra nos dois sentidos: compra de menos e perde venda, ou
> compra demais e o produto vence.
>
> O mercado brasileiro perde entre **10 e 12% das vendas por ruptura** — dado da
> Neogrid. E **2,79% em perda de estoque** — dado da ABRAPPE. Não é um dono ruim;
> é estrutural.
>
> **Giro** é a startup que resolve isso: transforma o histórico do PDV, que já
> existe, em previsão de demanda e sugestão de compra.

**Dica:** não leia. Olhe para a plateia. A dor precisa soar real.

---

## P2 — Os 5 Vs e a volumetria (0:40 – 1:55)

**Fala:**

> Antes de escolher banco, precisamos saber o que estamos guardando.
>
> **Volume:** 3 lojas, 24 meses, 6,36 milhões de linhas. A 100× (300 lojas), 636 milhões — ainda abaixo do limiar de Big Data.
> Esse número é o que define se precisamos de Big Data — e hoje não precisamos.
>
> **Velocidade:** 0,3 cupons por segundo no pico. A escrita é trivial. O gargalo
> é a leitura analítica.
>
> **Variedade:** CSV do PDV, XML da NF-e, JSON de calendário. É por isso que
> temos camada bronze.
>
> **Veracidade:** o V mais importante. Ruptura, EAN inválido, estoque divergente.
> É aqui que o projeto ganha ou perde.
>
> **Valor:** cada R$ de capital parado e cada venda perdida que conseguimos
> quantificar.
>
> E o dado mais importante da análise: **o padrão de acesso é assimétrico**. A
> escrita é pequena e contínua; a leitura é grande e esporádica. É isso que
> justifica a escolha que vem a seguir.

**Dica:** aponte para o slide do padrão de acesso. É o gráfico que conecta esta
fala com a próxima.

---

## P3 — Escolha do banco (1:55 – 3:20)

**Fala:**

> Avaliamos **oito opções** com uma matriz ponderada. Consistência vale 25%,
> adequação à consulta 20%, manutenção e custo 15% cada.
>
> **PostgreSQL ganhou com 4,65 de 5,00.** Não porque é o melhor em algo, mas
> porque é o melhor no conjunto — e vence nos critérios de maior peso.
>
> Por que não MongoDB? Porque o problema é relacional. Venda, item, produto,
> estoque — são entidades com cardinalidade clara. E estoque exige invariante
> transacional que o Mongo não expressa.
>
> Por que não Cassandra? Porque consistência eventual em estoque significa vender
> produto que já saiu.
>
> Por que não TimescaleDB? Foi a mais difícil. O Giro tem série temporal. Mas a
> consulta dominante não é agregação de janela por sensor — é média por dia da
> semana por SKU. Isso é `GROUP BY` sobre partição, e o Postgres faz nativo.
>
> E há um ponto que quase todo trabalho erra: **CAP não se aplica a um nó
> único**. Não somos um sistema distribuído. Dizer "escolhemos CP" seria erro
> conceitual. A análise correta é condicional: **se** houver réplica, o caminho de
> estoque continua CP e o dashboard aceita AP. É uma decisão por caminho, não do
> sistema.

**Dica:** esta é a fala que vale nota. Não corra. A parte do CAP é o que separa
a resposta de uma decoreba.

---

## P4 — Modelagem (3:20 – 4:40)

**Fala:**

> Três camadas, três propósitos.
>
> **Bronze:** CSV imutável com hash SHA-256. Garante linhagem e reprocessamento.
>
> **Prata:** 3ª forma normal. Aqui está a fonte de verdade. Por que normalizar?
> Porque mudar o nome de uma categoria em 4 milhões de linhas desnormalizadas é
> um risco. Normalizado, é uma linha.
>
> **Ouro:** star schema. Aqui desnormalizamos de propósito — porque a leitura é
> analítica e o analista não deveria conhecer 14 tabelas.
>
> Da modelagem, duas decisões valem destaque.
>
> **Primeira:** chave surrogate mais chave natural única. Sem a natural, reimportar
> um arquivo duplica receita. E encontramos um bug real com isso: a `UNIQUE`
> padrão do Postgres trata `NULL` como distinto, então dois cupons idênticos com
> série NULL passavam. Corrigimos com `NULLS NOT DISTINCT`. Está documentado no
> DDL e no caso de teste C11.
>
> **Segunda:** particionamento mensal por data. A consulta de 30 dias lê 1
> partição em vez de 24 meses. E a PK inclui a coluna de partição — é o preço do
> particionamento nativo, e vale.

**Dica:** mostre o DER por 5 segundos. Não leia as tabelas. O que importa são as
decisões.

---

## P5 — Qualidade e governança (4:40 – 5:55)

**Fala:**

> O princípio é: **dado ruim não é descartado em silêncio**. Ele vai para
> quarentena com código de motivo.
>
> Temos **21 regras** nas seis dimensões: completude, unicidade, consistência,
> validade, acuracidade, atualidade. E uma sétima de conformidade para LGPD.
>
> Mas descrever regras vale pouco. Então **medimos**.
>
> Geramos dois datasets da mesma semente: um limpo e um com **17 tipos de defeito
> em quantidade conhecida**. Carregamos o sujo num banco separado e cruzam os
> resultados com o gabarito.
>
> **Resultado: recall global de 96.61%** — 97.27% nos defeitos de linha. A precisão varia por regra, e as três que ficam fora da curva estão explicadas no relatório.
>
> E três números que não são 100% são o melhor argumento do projeto. O DQ006 tem
> recall de 50% porque o defeito afeta dois registros e a dedupe mantém um —
> **rejeitar os dois seria errado**. O DQ020 tem precisão baixa porque
> cancelamento é evento legítimo do PDV, não corrupção. Saber interpretar o
> próprio número é o que separa medir de fingir que mediu.
>
> Sobre LGPD: a decisão foi **não coletar dado pessoal**. Análise é por SKU e por
> loja. Minimização na modelagem, não em política escrita. E há uma regra que
> detecta CPF em campo livre, porque o operador pode digitar.

**Dica:** esta fala é a que impressiona. O "rejeitar os dois seria errado" mostra
entendimento de negócio, não só de SQL.

---

## P6 — Demo ao vivo (5:55 – 7:40)

**Antes de começar:** o banco já deve estar rodando. Teste 5 minutos antes.

**Fala durante a demo:**

> Vou mostrar três consultas.

**(1) Ruptura — 30 s**

> Esta é a pergunta que ninguém faz: quanto eu deixei de vender por falta de
> produto? A view `mv_rupturas` reconstrói a demanda usando a média histórica do
> mesmo dia da semana em dias **sem** ruptura. Sem isso, "vendeu 0" seria tratado
> como "demanda 0" — e o sistema pediria menos justamente do que mais falta.

**(2) Sugestão de compra — 40 s**

> Aqui a decisão. A `mv_sugestao_compra` junta previsão, lead time do fornecedor,
> estoque de segurança de 95% e múltiplo de compra. Note a coluna `situacao`:
> RUPTURA, CRÍTICO, REPOR, OK. E a coluna `score_qualidade_loja` — a sugestão vem
> com o selo de confiança do dado.

**(3) Curva ABC — 20 s**

> Esta é a prova técnica: window function acumulando receita sem self-join. Em
> 4,1 milhões de linhas, é a diferença entre 70 milissegundos e vários segundos.

**Fecho da demo — 15 s**

> As consultas que leem view materializada rodam em milissegundos; as que
> varrem o fato inteiro ficam na casa dos segundos. O `EXPLAIN ANALYZE` de
> cada uma está em `docs/evidencias/`.

**Dica:** narre o que está fazendo enquanto digita. Silêncio na demo é morte.

---

## P7 — Limitações e 100× (7:40 – 8:50)

**Fala:**

> O que quebra se crescermos 100 vezes? Medimos, não chutamos.
>
> O benchmark PostgreSQL × DuckDB é a evidência que sustenta o cenário 100×.
> Em **varredura ampla**, o colunar leva vantagem: lê só as colunas usadas.
> Em **filtro seletivo**, o Postgres leva, porque usa índice. O resultado
> medido está em `docs/evidencias/benchmark_duckdb.md`.
>
> Isso é o argumento: **não existe vencedor absoluto**. Existe adequação ao
> padrão de acesso. Por isso o Postgres continua sendo o núcleo e o colunar entra
> como camada analítica — não no lugar dele.
>
> A ordem em que as coisas quebram: primeiro o dashboard, em ~30 lojas. Depois
> backup, depois o `REFRESH`. A escrita **não** quebra nem a 100× — 30 inserções
> por segundo é carga leve.
>
> E o mais importante: **o modelo de dados sobrevive intacto**. 3FN continua
> correta, star schema continua correto, as constraints continuam necessárias.
> O que muda é infraestrutura, não modelagem.
>
> Sobre os dados: são **sintéticos**. Calibrados com benchmarks públicos, mas
> sintéticos. O próximo passo é rodar o mesmo pipeline sobre o dataset público
> Favorita. Declaramos isso no relatório em vez de esconder.

**Dica:** admitir a limitação dos dados sintéticos ganha mais pontos que esconder.
O professor vai perguntar.

---

## P1 — Fechamento (8:50 – 10:00)

**Fala:**

> Recapitulando o que o Giro entrega:
>
> **Um banco que recusa dado ruim.** 22 testes provam que ele rejeita. Não é
> declaração — é evidência executável.
>
> **Um pipeline que mede a própria eficácia.** 96.61% de recall em 17 tipos de
> defeito injetado, com gabarito.
>
> **Uma decisão de banco defensável.** Oito alternativas avaliadas, matriz
> ponderada, CAP aplicado com precisão.
>
> **E uma resposta de negócio.** Quanto estou perdendo, o que comprar, e posso
> confiar nesse número.
>
> O repositório tem o `run_all.py` que recria tudo em cerca de 30 minutos. Qualquer
> afirmação deste pitch tem um teste ou uma consulta por trás.
>
> Obrigado. Perguntas?

---

## Perguntas prováveis e respostas

### "Por que não usaram machine learning?"

> Três razões. A rubrica avalia escolha de banco e modelagem — ML não vale ponto.
> O catálogo tem 420 SKUs com 2 anos de história; um LightGBM ganharia pouco
> sobre uma EWMA com fator sazonal. E o diferencial do produto não está no
> modelo, está no tratamento da ruptura — que é o que realmente distorce a
> previsão. Preferimos investir o tempo nos dois eixos que valem 6 pontos.

### "Os dados são reais?"

> Não, são sintéticos e declaramos isso. Calibramos com benchmarks públicos:
> ruptura de 8,3% (Nielsen), curva ABC 20/80, ticket médio de mercadinho. O
> gerador está no repositório e é determinístico. A limitação está na seção 4.7,
> e o próximo passo é rodar sobre o dataset público Favorita.

### "Como garantem que o recall de 95% é real?"

> Temos gabarito. O injetor corrompe registros específicos e grava quais. Depois
> cruzamos o que foi injetado com o que entrou na quarentena. Sem gabarito,
> recall é opinião.

### "Por que não MongoDB?"

> O modelo é relacional: venda → item → produto → estoque. E estoque exige
> invariante transacional — não posso vender o que não tenho. O Mongo não
> expressa isso nativamente; eu teria que reimplementar as constraints na
> aplicação. Além disso, `JSONB` no Postgres já cobre atributo flexível de
> produto.

### "Por que não Kafka?"

> Porque a decisão de compra é semanal. Processar em tempo real resolveria um
> problema que ninguém tem, e adicionaria um componente a operar. O padrão de
> acesso medido mostra 0,3 cupons por segundo — isso é carga de brinquedo.

### "O que acontece se o estoque estiver errado?"

> Essa é a razão do selo de confiança. Se a acuracidade está abaixo de 85%, a
> sugestão é ocultada e o sistema pede correção de inventário. Previsão sobre
> estoque errado é pior que não ter previsão.

### "Por que 7 integrantes se o edital permite 5?"

> A professora autorizou por escrito antes do início. O documento está no
> repositório. E todos os 7 falam neste pitch.

### "Quanto tempo leva para rodar tudo?"

> Cerca de 30 minutos em um notebook (as duas cargas de 6,3M linhas dominam). A carga de 6,36 milhões de linhas leva cerca de
> dois minutos — medimos linhas por segundo no log.

### "E se o banco cair durante a apresentação?"

> Temos vídeo de 90 segundos da demo. E o `run_all.py` recria tudo do zero em
> 30 minutos se precisar.

---

## Checklist de ensaio

- [ ] Cronometrar uma vez sem interrupção
- [ ] Cada pessoa ensaia a própria fala 3× em voz alta
- [ ] Ensaiar as **passagens** (o fim de uma fala e o início da próxima)
- [ ] Testar o banco 5 min antes de apresentar
- [ ] Ter o vídeo de backup aberto em outra aba
- [ ] Ter o repositório aberto na pasta certa
- [ ] Conferir que ninguém lê slide de costas para a plateia
- [ ] Ensaiar a resposta para "os dados são reais?"
