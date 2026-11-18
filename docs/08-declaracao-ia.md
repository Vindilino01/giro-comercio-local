# 08 — Declaração de uso de inteligência artificial

> Exigência da seção 2 do edital: *"Se usar ferramentas de IA, declare em quais
> partes e o que foi revisado pelo grupo."*

## Resumo

Usamos IA (assistente de código) como **ferramenta de desenvolvimento**, do mesmo
modo que se usa um IDE com autocomplete ou um linter. A IA não tomou decisões de
arquitetura isoladamente, não inventou dados de negócio e não foi usada para
fabricar resultados.

**O que é de responsabilidade do grupo:** toda decisão de modelagem, a escolha do
banco, a definição dos KPIs, a validação de cada resultado e a defesa no pitch.

## Onde a IA foi usada

| Etapa | Uso | Nível de revisão do grupo |
|---|---|---|
| Redação das seções do relatório | Estrutura e texto inicial | **Revisão integral** — cada afirmação técnica foi conferida contra o código |
| DDL (migrations SQL) | Geração inicial do schema | **Revisão linha a linha** + 23 testes de constraint executados |
| Gerador de dados sintéticos | Estrutura do código | **Validado por testes de invariante** (`tests/test_gerador.py`) |
| Pipeline de ingestão | SQL de validação | **Cada regra testada contra o gabarito** de defeitos |
| Consultas de negócio | SQL inicial | **Resultado conferido manualmente** contra o CSV de origem |
| Comentários no código | Explicação de decisões | Revisados; decisões contestadas foram reescritas |
| Documentação de evidências | Formatação | Números conferidos contra a execução real |

## Onde a IA **não** foi usada

- **Dados de negócio.** Todos os dados são sintéticos, gerados por código que
  está no repositório (`src/gerador.py`). Nenhum número do relatório foi inventado.
- **Resultados das consultas.** Toda tabela de resultado em `docs/evidencias/` é
  saída direta do banco, exportada por `src/consultas.py`.
- **Benchmarks.** Os tempos em `docs/evidencias/benchmark_duckdb.md` são medições
  reais de `time.perf_counter()`, não estimativas.
- **Métricas de qualidade.** O recall e a precisão vêm do cruzamento entre o
  gabarito de defeitos injetados e a quarentena real do banco.

## Como verificar as afirmações

O edital valoriza justificativa técnica. Justificativa sem verificação é opinião.
Por isso cada afirmação do relatório tem um caminho de verificação:

| Afirmação no relatório | Como verificar |
|---|---|
| "O banco rejeita 23 tipos de dado inválido" | `python tests/test_constraints.py` |
| "Os dados carregados são íntegros" | `python tests/test_integridade.py` |
| "Recall de 96,61% na detecção de defeitos" | `python run_all.py --etapa sujo` gera `metricas_qualidade.json` |
| "As consultas de view materializada rodam em milissegundos" | `docs/evidencias/q*.plan.txt` |
| "O modelo é 3FN na prata" | `docs/dicionario-de-dados.md`, gerado do catálogo |
| "PostgreSQL vence a matriz de decisão (4,65)" | `docs/03-escolha-banco.md`, critérios com pesos |
| "DuckDB é 10,5× mais rápido em varredura ampla" | `python src/benchmark_duckdb.py` |
| "A taxa de ruptura é 8,77% em 12 meses (8,62% em 24)" | `docs/evidencias/q01_ruptura_demanda_perdida.md` |
| "O painel bate com o banco" | `python dashboard/verificar.py` (18 conferências) |
| "O painel funciona no browser" | `node scripts/verificar_painel.js` |
| "O backup é restaurável" | `python tests/test_restore.py` (RTO medido) |
| "O RLS isola por loja" | `python scripts/test_rls.py` |
| "O preço da dim_produto é o praticado" | `python scripts/verificar_preco.py` |

## Princípios que o grupo adotou

1. **Nenhum número sem origem.** Se está no relatório, tem consulta ou teste que
   o produz.
2. **Nenhuma afirmação sem verificação executável.** "Funciona" significa
   "o teste passa", não "parece certo".
3. **Erros encontrados ficam documentados.** Os bugs C11 (NULL em UNIQUE), o
   arredondamento de dinheiro e a subquery O(n²) estão registrados no código e
   neste relatório. Esconder o erro seria pior que cometê-lo.
4. **Decisão técnica é do grupo.** Quando a sugestão da IA conflitou com a
   rubrica (por exemplo, incluir ML), o grupo decidiu com base no edital.

## Ferramentas utilizadas

| Ferramenta | Uso |
|---|---|
| Assistente de código com IA | Sugestões de código e estrutura de texto |
| PostgreSQL 18.3 | Banco de dados |
| Python 3.14 | Geração de dados, ingestão, automação |
| DuckDB | Benchmark comparativo (seção 4.7) |
| PowerShell 7 | Scripts de ambiente |

---

**Declaração final:** o grupo compreende integralmente o conteúdo do projeto,
sabe explicar cada decisão de modelagem e de escolha de banco, e assume
responsabilidade por todo o código e por todas as afirmações técnicas deste
relatório. As ferramentas de IA aceleraram a produção; não substituíram o
entendimento.
