# Benchmark PostgreSQL × DuckDB

> Medição real executada em `src/benchmark_duckdb.py`. Evidência para a seção 4.7 do relatório (cenário 100×).

**Gerado em:** 2026-11-18 10:57:04  
**PostgreSQL:** PostgreSQL 18.3 on x86_64-windows, compiled by msvc-19.44.35225, 64-bit  
**DuckDB:** 2.0.0  
**Linhas em `fato_vendas`:** 4,134,291  
**Tamanho no PostgreSQL:** 896 MB

## Tamanho em disco

| Tabela | Parquet (ZSTD) |
|---|---|
| `fato_vendas` | 34.8 MB |
| `dim_tempo` | 0.01 MB |
| `dim_produto` | 0.01 MB |

## Resultados

| Consulta | PostgreSQL (mediana) | DuckDB (mediana) | Razão | Vencedor |
|---|---|---|---|---|
| **A_varredura_ampla** — Receita por mes em 24 meses | 667.7 ms | 63.4 ms | 10.53× | DUCKDB |
| **B_agregacao_por_sku** — Curva ABC completa (420 SKUs) | 435.7 ms | 21.2 ms | 20.53× | DUCKDB |
| **C_filtro_seletivo** — Vendas de um SKU em um mes | 0.8 ms | 9.7 ms | 0.09× | POSTGRES |

### Detalhe por consulta

#### A_varredura_ampla — Receita por mes em 24 meses

Varredura de toda a tabela de fatos, agregando por mes. Cenario classico de dashboard anual.

- **PostgreSQL:** [674.39, 667.68, 651.08] ms (24 linhas)
- **DuckDB:** [103.88, 63.41, 60.85] ms (24 linhas)

#### B_agregacao_por_sku — Curva ABC completa (420 SKUs)

Agregacao por SKU com window function para acumulado. Cenario de analise de sortimento.

- **PostgreSQL:** [435.67, 450.32, 427.53] ms (420 linhas)
- **DuckDB:** [35.56, 21.22, 20.82] ms (420 linhas)

#### C_filtro_seletivo — Vendas de um SKU em um mes

Filtro altamente seletivo (~1/4200 da tabela). Cenario onde o indice do row store deveria vencer.

- **PostgreSQL:** [2.92, 0.85, 0.83] ms (30 linhas)
- **DuckDB:** [12.94, 9.74, 9.35] ms (30 linhas)
