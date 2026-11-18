# Giro — previsão de estoque e vendas para pequenos mercados

> **A3 — Análise de Dados e Big Data**
> Startup de dados que transforma o histórico do PDV de mercadinhos de bairro
> em previsão de demanda e sugestão de compra, e diz honestamente quando o dado
> ainda não é confiável para decidir.

---

## O problema em uma frase

O dono do mercadinho compra por intuição. Compra a menos e perde venda por
ruptura; compra a mais e imobiliza capital em produto que vence na prateleira.
O dado para decidir já existe no PDV — só não é usado.

## Os dois diferenciais

**Previsão com consciência da ruptura.** Quando o produto está em falta, a venda
registrada é 0, mas a demanda não era 0. A maioria dos sistemas aprende com esse
número truncado e passa a pedir menos justamente do que mais falta. O Giro
reconstrói a demanda perdida a partir do estoque do dia e marca, em cada linha,
se o valor é `observado` ou `reconstruida`.

**Selo de confiança do dado.** Cada loja recebe um score calculado sobre a **pior**
dimensão de qualidade — não sobre a média. Previsão construída sobre estoque 86%
acurado está 14% errada, por melhor que seja a completude. A sugestão só aparece
como confiável quando o elo mais fraco passa do limiar.

---

## Como rodar

Pré-requisito: PostgreSQL 18 em `C:\Program Files\PostgreSQL\18`.

```powershell
# 1. sobe o cluster isolado do projeto (porta 5433)
.\scripts\pg.ps1 start

# 2. instala dependências Python
python -m pip install -r requirements.txt

# 3. cria banco, gera dados, carrega, valida e produz o painel
python run_all.py --reset
```

O comando acima executa **sete etapas**, nesta ordem:

| # | Etapa | O que faz |
|---|---|---|
| 1 | `db` | aplica as 12 migrations: prata (3FN), ouro (star schema), governança, RBAC e auditoria |
| 2 | `dados` | gera 6,36M de linhas calibradas, injeta defeitos, carrega o dataset limpo |
| 3 | `sujo` | carrega o dataset com defeitos em banco isolado e mede recall por regra |
| 4 | `marts` | materializa star schema e as 5 views materializadas |
| 5 | `consultas` | executa as 11 consultas e exporta as evidências |
| 6 | `painel` | gera `docs/painel.html` e **verifica cada número contra o banco** |
| 7 | `testes` | 22 testes de constraint + 25 testes de integridade |

Tempo total: **~25 minutos** em um notebook comum.

### Comandos úteis

| Comando | O que faz |
|---|---|
| `python run_all.py --reset` | tudo, do zero |
| `python run_all.py --etapa painel` | só regenera o painel e verifica |
| `python run_all.py --etapa testes` | só as suites de validação |
| `python dashboard/gerar.py` | gera `docs/painel.html` |
| `python dashboard/verificar.py` | confere cada número do painel contra o banco |
| `node scripts/verificar_painel.js` | abre o painel num browser e valida runtime, acessibilidade e impressão |
| `python tests/test_constraints.py` | prova que o banco rejeita dado ruim |
| `python tests/test_integridade.py` | prova que o dado carregado é coerente |
| `python tests/test_restore.py` | mede o RTO real do backup |
| `python src/benchmark_duckdb.py` | benchmark colunar para o cenário 100× |
| `.\scripts\pg.ps1 psql` | abre sessão psql no banco `giro` |

---

## O painel

`docs/painel.html` — **arquivo único, 780 KB, abre por duplo clique**.

Não é um app servidor: o pitch roda num notebook emprestado, sem rede, com
projetor. Um servidor a mais seria um ponto de falha a mais. As fontes (Piazzolla
e Archivo) vão embutidas em base64, os dados em JSON, e não há nenhuma requisição
de rede em tempo de execução. Funciona de um pendrive.

Ele é gerado por `dashboard/gerar.py` a partir do PostgreSQL, e cada número na
tela é conferido por `dashboard/verificar.py` contra uma consulta independente.

**Por que não Streamlit:** Streamlit tem vocabulário visual próprio — cartões
arredondados, métricas em caixa, tipografia de framework. Isso é o oposto de
"ferramenta de gestão em que o dono confia". O painel estático permite controle
tipográfico total, carrega instantaneamente e não depende de infraestrutura.

---

## Arquitetura de dados

Persistência poliglota **quando justificada**, com o PostgreSQL como núcleo:

| Camada | Tecnologia | Papel |
|---|---|---|
| Bronze | CSV/XML imutável em `data/bronze/` | dado bruto com hash SHA-256, linhagem e reprocessamento |
| Prata | **PostgreSQL 18** (3ª Forma Normal) | fonte de verdade transacional, ACID, 200+ constraints |
| Ouro | **PostgreSQL** (star schema + views materializadas) | agregações e previsão para o painel |

A decisão, as **oito alternativas descartadas** com justificativa e a aplicação
do Teorema CAP estão em
[`docs/03-escolha-banco.md`](docs/03-escolha-banco.md).

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [`PRODUCT.md`](PRODUCT.md) | persona, restrições do produto, modos de uso |
| [`DESIGN.md`](DESIGN.md) | sistema visual do painel: cor, tipografia, estrutura |
| [`docs/01-problema.md`](docs/01-problema.md) | dor, público, proposta de valor, 6 KPIs |
| [`docs/02-diagnostico.md`](docs/02-diagnostico.md) | fontes, tipos, os 5 Vs, volumetria, padrão de acesso |
| [`docs/03-escolha-banco.md`](docs/03-escolha-banco.md) | tipo escolhido, 8 alternativas, CAP, matriz ponderada |
| [`docs/04-modelagem.md`](docs/04-modelagem.md) | conceitual, lógico, físico, chaves, índices, partições |
| [`docs/05-qualidade.md`](docs/05-qualidade.md) | 21 regras DQ, fluxo ETL, medição de recall, LGPD, riscos |
| [`docs/06-prova-conceito.md`](docs/06-prova-conceito.md) | banco real, 11 consultas com resultado, testes |
| [`docs/07-limitacoes.md`](docs/07-limitacoes.md) | limites, cenário 100×, benchmark, aprendizados |
| [`docs/08-declaracao-ia.md`](docs/08-declaracao-ia.md) | uso de IA declarado, o que foi revisado |
| [`docs/dicionario-de-dados.md`](docs/dicionario-de-dados.md) | todos os campos, gerado do catálogo do banco |
| [`docs/pitch-roteiro.md`](docs/pitch-roteiro.md) | roteiro de 10 minutos com 7 falantes |
| [`docs/relatorio-final.pdf`](docs/relatorio-final.pdf) | relatório consolidado |
| [`docs/pitch.pdf`](docs/pitch.pdf) | slides |

---

## Estrutura do repositório

```
db/migrations/     migrations em ordem numérica (001..011)
db/queries/        as 11 consultas de negócio (Q01..Q10, Q02b)
db/build.sql       aplica todas as migrations
src/               pipeline: gerador, injetor de defeitos, ingestão, marts,
                   métricas de qualidade, dicionário, benchmarks, PDF
dashboard/         gerar.py, molde.html, verificar.py, fontes
tests/             constraints, integridade, gerador, restore, pipeline rápido
data/bronze/       CSV bruto (limpo e sujo) — não versionado
docs/              relatório, diagramas, evidências, painel.html
scripts/           pg.ps1 (cluster), regenerar.py, diagnósticos
```

---

## Números do projeto

| Métrica | Valor |
|---|---|
| Linhas carregadas | 6.362.320 aceitas em `gov.lote_carga` |
| Tabelas lógicas | 28 (15 prata + 8 ouro + 5 gov) |
| Índices (definições no DDL) | 38 — materializados em 43 partições cada |
| Partições | 43 por tabela particionada (86 no total, contando as duas) |
| Consultas de negócio | 11 |
| Regras de qualidade | 21 (7 dimensões no laboratório sujo) |
| Testes automatizados | 23 constraints + 25 integridade + 14 invariantes do gerador |
| Recall de detecção de defeitos | ver `docs/evidencias/metricas_qualidade.json` |
| Tempo de carga | ~12 min por carga (limpa e suja), ~30 min o pipeline |

---

## Ambiente

- PostgreSQL 18.3 (cluster isolado na porta 5433)
- Python 3.12+ (testado em 3.14.6)
- Windows 10/11 com PowerShell 7 — o projeto também roda em Linux/macOS trocando
  `scripts/pg.ps1` por `initdb`/`pg_ctl` equivalentes
- Microsoft Edge ou Chromium (só para **regerar** os PDFs de relatório e pitch)
- Nenhuma dependência de rede em tempo de execução

### Onde ficam os dados do cluster

`%USERPROFILE%\.giro-pg` — **fora do repositório**, de propósito: o data dir
tem dezenas de MB e centenas de arquivos, e misturar "código" com "estado"
dificulta a entrega. `logs/` é descartável; apagar log não pode apagar o banco.

```powershell
.\scripts\pg.ps1 start    # sobe o cluster (cria na primeira vez)
.\scripts\pg.ps1 status   # mostra onde ele está e se está no ar
.\scripts\pg.ps1 stop     # para
```

Se existir um cluster antigo em `logs\pgdata`, o script o detecta e o usa em
vez de criar um segundo na mesma porta. A versão anterior tinha esse defeito:
o serviço do Windows apontava para um data dir e o `pg.ps1` para outro,
produzindo dois bancos concorrentes na porta 5433.

O cluster criado por `pg.ps1` usa autenticação `trust` em `127.0.0.1` e define
`lc_monetary = 'pt_BR.UTF-8'`. Um cluster criado de outra forma, com
`lc_monetary = 'C'`, formata dinheiro no padrão americano — foi a causa de um
total publicado como R$ 264,50 quando o valor real era R$ 266.318,86. As
consultas hoje devolvem `numeric` e formatam em Python, então o problema não
depende mais da configuração do cluster.

## Uso de IA

Declarado em [`docs/08-declaracao-ia.md`](docs/08-declaracao-ia.md), conforme
exige a seção 2 do edital.

---

## Antes de entregar

Dois passos que o código **não** pode fazer sozinho:

1. **Preencher `docs/integrantes.md`** com nome e RA dos sete integrantes.
   O `relatorio_pdf.py` lê essa tabela e imprime na capa. Sem ela, a capa sai
   com "integrantes não informados".

   ```powershell
   python src/relatorio_pdf.py
   ```

2. **Anexar a autorização da professora** para o grupo de 7. Salve como
   `docs/autorizacao-grupo.pdf` (ou `.png`). Se o arquivo existir, ele entra
   como última página do relatório.

Confira antes de enviar:

```powershell
python -m pytest -q                      # 5 suites
python dashboard/verificar.py            # 18 conferencias painel x banco
node scripts/verificar_painel.js         # 15 verificacoes de runtime
```

---

## Referências

O relatório fecha com uma seção de referências (`docs/referencias.md`): Nielsen,
Neogrid, ABRAS, Sebrae, LGPD, documentação do PostgreSQL 18, Kimball, Kleppmann,
DAMA-DMBOK, Hyndman e a literatura de gestão de estoque. Os números do próprio
projeto não estão lá — eles vêm do banco e ficam em `docs/evidencias/`, cada um
com o comando que o reproduz.
