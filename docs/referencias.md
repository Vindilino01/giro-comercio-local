# Referências

As fontes abaixo sustentam as afirmações factuais do relatório. Os números
do próprio projeto não estão aqui — eles vêm do banco e estão em
`docs/evidencias/`, com o comando que os reproduz.

## Mercado e problema

**NIELSEN.** *O que o consumidor brasileiro quer?* Relatório de
tendências de consumo no varejo alimentar. São Paulo, 2023.
Usado para calibrar a taxa de ruptura de 8,3% mencionada na seção 4.1.

**NEOGRID.** *Índice de ruptura no varejo brasileiro.* Belo Horizonte, 2024. Disponível em: <https://www.neogrid.com>. Acesso em: nov. 2025.
Faixa de 10% a 12% usada como referência de mercado para o baseline.

**ABRAS.** *Ranking ABRAS/SuperHiper de supermercados.* Associação
Brasileira de Supermercados, 2024. Contexto do setor: número de lojas,
faturamento médio e concentração regional.

**SEBRAE.** *Sobrevivência das empresas no Brasil.* Serviço Brasileiro
de Apoio às Micro e Pequenas Empresas, 2023.
Base para a discussão de mortalidade de pequenos varejos.

**ABRAPPE.** *Associação Brasileira de Prevenção de Perdas.* Estudos
sobre quebras e perdas no varejo, 2023.
Usado no diagnóstico de perdas por vencimento.

## Legislação

**BRASIL.** *Lei nº 13.709, de 14 de agosto de 2018.* Lei Geral de
Proteção de Dados Pessoais (LGPD). Diário Oficial da União, Brasília, DF,
15 ago. 2018.
Fundamenta a decisão de não coletar dado pessoal (seção 5.4) e o
princípio da minimização.

**BRASIL.** *Lei nº 12.965, de 23 de abril de 2014.* Marco Civil da
Internet. Diário Oficial da União, Brasília, DF, 24 abr. 2014.

## Banco de dados

**POSTGRESQL GLOBAL DEVELOPMENT GROUP.** *PostgreSQL 18 Documentation.*
2025. Disponível em: <https://www.postgresql.org/docs/18/>.
Referência para particionamento declarativo (`PARTITION BY RANGE`),
`EXCLUDE USING gist`, `UNIQUE NULLS NOT DISTINCT`, `REFRESH
MATERIALIZED VIEW CONCURRENTLY`, políticas de Row-Level Security e
`ALTER DEFAULT PRIVILEGES`.

**POSTGRESQL GLOBAL DEVELOPMENT GROUP.** *PostgreSQL: Up and Running*
(3rd ed.). O'Reilly, 2017. Base conceitual de MVCC e do modelo de
isolamento.

**KLEPPMANN, M.** *Designing Data-Intensive Applications.* O'Reilly, 2017. Capítulos 5 (replicação), 6 (particionamento) e 9 (consistência e
consenso) sustentam a análise de CAP da seção 4.3.

**BREWER, E.** *CAP Twelve Years Later: How the "Rules" Have Changed.*
Computer, v. 45, n. 2, p. 23-29, 2012.
Base para a leitura de que CAP se aplica a sistemas distribuídos — e,
portanto, não a um nó único.

**GILBERT, S.; LYNCH, N.** *Brewer's Conjecture and the Feasibility of
Consistent, Available, Partition-Tolerant Web Services.* ACM SIGACT
News, v. 33, n. 2, p. 51-59, 2002.

**RAASVELDT, M.; MÜHLEISEN, H.** *DuckDB: an Embeddable Analytical
Database.* Proceedings of the 2019 International Conference on Management
of Data (SIGMOD), p. 1981-1984, 2019.
Justifica o uso de DuckDB no benchmark da seção 4.7 e no apêndice.

**ABADI, D.; BONCZ, P.; HARIZOPOULOS, S.; IDREOS, S.; MADDEN, S.**
*The Design and Implementation of Modern Column-Oriented Database
Systems.* Foundations and Trends in Databases, v. 5, n. 3, p. 197-280, 2013. Sustenta a comparação row store × column store.

## Modelagem e qualidade de dados

**KIMBALL, R.; ROSS, M.** *The Data Warehouse Toolkit: The Definitive
Guide to Dimensional Modeling* (3rd ed.). Wiley, 2013.
Base do star schema da camada ouro e da distinção entre fato e dimensão.

**INMON, W. H.** *Building the Data Warehouse* (4th ed.). Wiley, 2005.
Contraponto a Kimball, usado para justificar a camada prata em 3FN.

**CODD, E. F.** *A Relational Model of Data for Large Shared Data Banks.*
Communications of the ACM, v. 13, n. 6, p. 377-387, 1970.

**DAMA INTERNATIONAL.** *DAMA-DMBOK: Data Management Body of Knowledge*
(2nd ed.). Technics Publications, 2017.
Define as seis dimensões de qualidade citadas no edital (completude,
consistência, unicidade, validade, atualidade e acurácia) e a
classificação usada na seção 5.

**ISO/IEC.** *ISO 8000-61:2016 — Data quality — Part 61: Data quality
management process reference model.* Genebra, 2016.

**REDMAN, T. C.** *Data Quality for the Information Age.* Artech House, 1996. Base conceitual para dimensão de acurácia.

## Estatística e previsão

**HYNDMAN, R. J.; ATHANASOPOULOS, G.** *Forecasting: Principles and
Practice* (3rd ed.). OTexts, 2021. Disponível em:
<https://otexts.com/fpp3/>.
Suavização exponencial (EWMA) e decomposição sazonal.

**BROWN, R. G.** *Smoothing, Forecasting and Prediction of Discrete Time
Series.* Prentice-Hall, 1963. Origem do EWMA.

**SILVER, E. A.; PYKE, D. F.; THOMAS, D. J.** *Inventory and Production
Management in Supply Chains* (4th ed.). Routledge, 2016.
Ponto de pedido, estoque de segurança e o fator `z` do nível de serviço.

**CHOPRA, S.; MEINDL, P.** *Supply Chain Management* (7th ed.). Pearson, 2019. Métricas de OTIF e lead time.

## Ferramentas

**PYTHON SOFTWARE FOUNDATION.** *Python 3.14 Documentation.* 2025.
Disponível em: <https://docs.python.org/3.14/>.

**PSYCOPG DEVELOPMENT TEAM.** *Psycopg 3 Documentation.* 2025.
Disponível em: <https://www.psycopg.org/psycopg3/docs/>.

**FOLGER, A.; PONTARELLI, R.; et al.** *PyMuPDF Documentation.* 2025.
Usado na validação automática dos PDFs gerados.

**MICROSOFT.** *Microsoft Edge — command-line options.* 2025.
Base da geração de PDF via `--headless --print-to-pdf`.