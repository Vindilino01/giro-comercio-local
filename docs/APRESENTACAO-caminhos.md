# Mostrar para a professora — caminhos e o que fazer

> Tudo verificado no disco em 28/11/2026. O banco está no ar (PID 6140,
> porta 5433). Os comandos abaixo foram executados e devolveram o que
> este documento promete.

## Pasta do projeto

```
C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data
```

Atalho: no PowerShell, cole

```powershell
cd "C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data"
```

---

## 1. O painel (a interface do produto)

**Caminho:**
```
C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data\docs\painel.html
```

**O que fazer:** duplo clique. Abre no navegador, sem servidor, sem
internet.

**Ou pelo site publicado:**
https://vindilino01.github.io/giro-comercio-local/

**O que mostrar em 30 segundos:**

1. O número grande: **R$ 259.577,64** — o pedido da semana
2. Clique num **fornecedor** na faixa verde — a lista filtra
3. Abra **"Ajustes do cenário"** e clique em **99 de 100** — o total sobe
   para R$ 296.631,09 e a consequência aparece ali mesmo
4. Role até **"Quanto a prateleira vazia custou"** — R$ 2.298.078,12

---

## 2. O banco de dados ao vivo (o que ela pediu)

**Abra o PowerShell e cole:**

```powershell
cd "C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data"
.\scripts\pg.ps1 start
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 5433 -U postgres -d giro
```

Senha: **Enter** (vazia).

O prompt vira `giro=#`. Você está dentro do banco.

**Os quatro comandos, na ordem:**

```sql
\dt prata.*
```
→ 15 tabelas da camada transacional

```sql
\dt ouro.*
```
→ 8 tabelas do star schema

```sql
\dm ouro.*
```
→ 5 views materializadas

```sql
\d+ prata.venda
```
→ estrutura completa: colunas, tipos, chaves, índices, partições

**A prova que fecha a arguição:**

```sql
select round(sum(valor_compra_sugerido)::numeric, 2) as total_do_pedido
  from ouro.mv_sugestao_compra;
```

Resposta: **259577.64** — o mesmo R$ 259.577,64 da tela. Diga: *"esse
número é o mesmo que está no painel; ele sai daqui"*.

**Para sair:** `\q`

---

## 3. O MER (Modelo Entidade-Relacionamento)

**Pasta:** `C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data\docs\`

| Arquivo | Caminho completo | Para quê |
|---|---|---|
| **mer-prata.svg** | `...\docs\mer-prata.svg` | **a que ela quer ver** — 15 tabelas com todas as colunas |
| mer-ouro.svg | `...\docs\mer-ouro.svg` | o star schema |
| mer.svg | `...\docs\mer.svg` | as três camadas lado a lado |

**O que fazer:** duplo clique no **`mer-prata.svg`**. Abre no navegador.
**Use Ctrl + scroll para dar zoom** — o SVG não perde nitidez.

Se ela quiser colar num slide, use os `.png` na mesma pasta.

**O que dizer:** *"O MER é gerado do catálogo do banco por
`src/gerar_mer.py`, não desenhado à mão. Se uma migration mudar, o
desenho muda junto."*

---

## 4. O diagrama de casos de uso

**Caminho:**
```
C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data\docs\casos-de-uso.svg
```

**O que fazer:** duplo clique.

Três colunas: **ator → caso de uso → o controle que executa no painel**.
Os 14 casos são exatamente os controles que existem na tela.

---

## 5. O relatório (Word e PDF)

**Word (editável):**
```
...\docs\relatorio-final.docx
```

**PDF (para ler ou projetar):**
```
...\docs\relatorio-final.pdf
```

O PDF tem **50 páginas**, incluindo o **Apêndice B** com os diagramas em
páginas deitadas (páginas 44 a 47).

**Se ela quiser a versão para imprimir:** o PDF.

**Se ela quiser comentar:** o `.docx`.

---

## 6. O pitch

```
...\docs\pitch.pdf
```

12 slides, 16:9.

---

## 7. O dicionário de dados (se ela perguntar de uma coluna)

```
...\docs\dicionario-de-dados.md
```

28 tabelas, 1.476 colunas, com tipo e constraint de cada uma. Gerado do
catálogo. Abre em qualquer editor de texto.

---

## 8. O guia completo (para você, antes da banca)

```
...\docs\guia-banca.md
```

Tem o roteiro de 3 minutos, os números reais, e o que fazer se algo
falhar.

---

## Roteiro de 3 minutos

| # | Ação | O que prova |
|---|---|---|
| 1 | Abrir `painel.html` | a interface existe e funciona |
| 2 | `\dt prata.*` | 15 tabelas normalizadas |
| 3 | `\d+ prata.venda` | o banco tem tipo, chave, índice, partição |
| 4 | A consulta do total | o número da tela sai do banco |
| 5 | Abrir `mer-prata.svg` | o desenho é o banco, não uma versão ideal |
| 6 | Abrir `casos-de-uso.svg` | cada caso tem controle na tela |

O passo 4 é o mais forte. Ele liga a tela ao banco na frente dela.

---

## Números para ter na ponta da língua

| O que | Valor |
|---|---|
| PostgreSQL | 18.3 |
| Tabelas lógicas | **28** (15 prata + 8 ouro + 5 gov) |
| Views materializadas | 5 |
| Colunas | 1.476 |
| Chaves estrangeiras | 249 |
| Constraints | 1.900 |
| Índices | 464 |
| Linhas em `prata.item_venda` | 4.159.608 |
| Linhas em `prata.venda` | 545.093 |
| Tamanho em disco | 3,8 GB |

**Se ela perguntar por que o `\dt` mostra menos tabelas que o banco
tem:** são 43 partições por tabela particionada. 2 tabelas lógicas
(`venda`, `item_venda`) viram 473 objetos físicos, incluindo índices.
É o preço do *partition pruning*.

---

## Se algo der errado

| Sintoma | Correção |
|---|---|
| `psql` não reconhecido | use o caminho completo: `& 'C:\Program Files\PostgreSQL\18\bin\psql.exe'` |
| `connection refused` | `.\scripts\pg.ps1 start` |
| `database "giro" does not exist` | `python run_all.py --reset` (~30 min) |
| MER desatualizado | `python src\gerar_mer.py` |

---

## Para colar na área de transferência (tudo de uma vez)

```powershell
cd "C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data"
start docs\painel.html
start docs\mer-prata.svg
start docs\casos-de-uso.svg
start docs\relatorio-final.pdf
.\scripts\pg.ps1 start
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 5433 -U postgres -d giro
```

Isso abre o painel, os dois diagramas, o relatório e entra no banco, na
ordem em que você vai mostrar.
