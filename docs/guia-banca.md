# Guia da banca — como mostrar o banco, o MER e os casos de uso

> **Por que este arquivo existe.** A professora pediu, durante a
> apresentação, para ver o banco de dados em si: as tabelas, a interface
> dele. O projeto tinha o dicionário, mas nenhum roteiro de como abrir o
> PostgreSQL na hora, e nenhum MER nem diagrama de casos de uso. Este
> guia fecha os três buracos.
>
> **Regra:** nada aqui é para decorar. Cada comando abre uma janela real
> sobre o banco. Se ela pedir para ver de novo, é rodar de novo.

---

## 1. Antes de começar: o banco precisa estar no ar

Abra o PowerShell na pasta do projeto e rode:

```powershell
.\scripts\pg.ps1 start
```

Resposta esperada:

```
pg_ctl: servidor está executando (PID: 6140)
```

Se já estiver rodando, ele avisa e não faz nada. O cluster fica em
`C:\Users\CPU\.giro-pg` — fora do repositório, de propósito: dado não
entra no Git.

---

## 2. Abrir o cliente de linha de comando

O `psql` vem com o PostgreSQL instalado, mas **não está no PATH**. Use o
caminho completo:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 5433 -U postgres -d giro
```

Senha: a que você definiu na instalação (provavelmente vazia — só Enter).

O prompt muda para `giro=#`. Você está dentro do banco.

> **Atalho.** Se for usar muito, adicione ao PATH uma vez:
> ```powershell
> $env:PATH += ';C:\Program Files\PostgreSQL\18\bin'
> ```
> Aí basta `psql -h 127.0.0.1 -p 5433 -U postgres -d giro`.

---

## 3. Os cinco comandos que respondem "mostre o banco"

### 3.1 Ver os schemas e o tamanho de cada camada

```sql
\dn+
```

Mostra `prata`, `ouro`, `gov`. São as três camadas:
**prata** é a fonte de verdade (3FN), **ouro** é o star schema
(derivado), **gov** é governança.

### 3.2 Listar as tabelas

```sql
\dt prata.*
\dt ouro.*
\dt gov.*
```

Resposta: **15 tabelas na prata, 8 no ouro, 5 no gov** — 28 lógicas.
As `venda_2025_01`, `item_venda_2025_01` etc. são **partições**: a mesma
tabela dividida por mês, 43 de cada. Não são tabelas novas.

> Se ela perguntar "por que 473 objetos?": são 43 partições × 11 objetos
> (2 tabelas + seus índices + as chaves). O `\dt` já esconde isso.

### 3.3 Ver a estrutura de uma tabela

```sql
\d+ prata.venda
\d+ ouro.fato_vendas
\d+ ouro.mv_sugestao_compra
```

Mostra colunas, tipos, chaves, índices e partições. É o que a banca quer
ver quando pede "a interface do banco".

### 3.4 Ver as views materializadas

```sql
\dm ouro.*
```

Cinco: `mv_demanda_diaria`, `mv_previsao_demanda`, `mv_sugestao_compra`,
`mv_rupturas`, `mv_qualidade_loja`. São a camada que faz o painel
responder em milissegundos.

### 3.5 Provar que os números do painel vêm do banco

Esta é a demonstração que fecha a arguição. Rode:

```sql
-- O total do pedido que o painel mostra no topo
select round(sum(valor_compra_sugerido)::numeric, 2) as total_do_pedido
  from ouro.mv_sugestao_compra;

-- A taxa de ruptura
select round(100.0 * count(*) filter (where houve_ruptura)
             / count(*), 2) as taxa_ruptura_pct
  from ouro.mv_demanda_diaria;
```

Resposta esperada na primeira: **259577.64**. É o mesmo número do
painel (R$ 259.577,64), só sem a formatação brasileira.

> **Por que não `to_char` com `'L999G999G990D00'`.** Testei: devolve
> `259,577.64` — formato americano, porque a formatação segue o locale do
> Windows, não o do banco. Na frente da banca, o número sem vírgula de
> milhar é mais seguro que um formato meio brasileiro, meio americano.

---

## 4. O MER — Modelo Entidade-Relacionamento

Três desenhos, todos **gerados do catálogo do banco** por
`src/gerar_mer.py`. Não foram desenhados à mão: se uma migration mudar, o
desenho muda junto.

| Arquivo | O que mostra |
|---|---|
| `docs/mer.svg` | as 28 tabelas nas três camadas, com os relacionamentos |
| `docs/mer-prata.svg` | a prata com **todas as colunas**, chaves e tipos |
| `docs/mer-ouro.svg` | o star schema: 3 fatos, 5 dimensões, 5 views |
| `docs/mer.png` | versão raster, para slide |

**Como abrir:** clique duas vezes no `.svg` (abre no navegador, dá zoom
sem perder nitidez). O `.png` é para colar em slide.

**Para regerar depois de qualquer mudança no banco:**

```powershell
python src\gerar_mer.py
```

O que procurar no desenho:

- **Chaves marcadas com 🔑** — as PKs e as colunas das chaves naturais
- **A cor de cada camada:** verde é prata (fonte de verdade), âmbar é
  ouro (derivado), cinza é gov
- **O número ao lado do nome** é a contagem real de linhas
- **As setas** são as 249 chaves estrangeiras reais, com o nome da coluna

---

## 5. O diagrama de casos de uso

`docs/casos-de-uso.svg` (e `.png`).

**Três colunas:** ator → caso de uso → **o controle que o executa no
painel**. A terceira coluna é o que impede o diagrama de virar ficção:
todo caso aponta o elemento real de interface.

| Ator | O que faz |
|---|---|
| **Nelson** (dono) | 12 casos: decidir, separar, entregar, entender |
| **Fornecedor** | recebe o pedido (não usa o sistema) |
| **Banca** | confere rastreabilidade e modelo de dados |

Para regerar: `python src\gerar_casos_uso.py`

---

## 6. Se ela quiser ver uma interface gráfica

O projeto **não depende** de pgAdmin ou DBeaver, mas se ela preferir
uma janela em vez de linha de comando:

```powershell
winget install --id dbeaver.dbeaver --exact
```

Depois, no DBeaver: **Nova conexão → PostgreSQL**, com

| Campo | Valor |
|---|---|
| Host | `127.0.0.1` |
| Porta | `5433` |
| Banco | `giro` |
| Usuário | `postgres` |

Ao conectar, aparece a árvore com os três schemas. É a mesma informação
do `psql`, com clique em vez de comando.

> **Alternativa sem instalar nada:** o dicionário de dados em
> `docs/dicionario-de-dados.md` é gerado do catálogo e descreve as 28
> tabelas, coluna por coluna, com tipos e constraints. Se a banca
> perguntar "o que tem na tabela X" e a rede estiver ruim, é ali.

---

## 7. Roteiro de 3 minutos

Se ela disser "me mostra o banco", esta é a ordem que funciona:

| # | Ação | O que prova |
|---|---|---|
| 1 | `\dt prata.*` | existem 15 tabelas normalizadas |
| 2 | `\d+ prata.venda` | tem tipo, chave, índice, partição |
| 3 | `\dm ouro.*` | existem 5 views materializadas |
| 4 | `select count(*) from prata.item_venda;` | 4.159.608 linhas reais |
| 5 | `select sum(valor_compra_sugerido) from ouro.mv_sugestao_compra;` | o número do painel |
| 6 | abrir `docs/mer-prata.svg` | o desenho é o banco, não uma versão ideal |
| 7 | abrir `docs/casos-de-uso.svg` | cada caso tem controle na tela |

O passo 5 é o mais forte. Ele liga a tela ao banco na frente dela.

---

## 8. Números para ter na ponta da língua

Medidos agora, não estimados:

| O que | Valor |
|---|---|
| PostgreSQL | 18.3 |
| Tabelas lógicas | 28 (15 prata + 8 ouro + 5 gov) |
| Views materializadas | 5 |
| Colunas | 1.476 |
| Chaves estrangeiras | 249 |
| Constraints | 1.900 |
| Índices | 464 |
| Partições | 43 por tabela particionada |
| Linhas em `prata.item_venda` | 4.159.608 |
| Linhas em `prata.venda` | 545.093 |
| Linhas em `ouro.fato_vendas` | 4.134.291 |
| Tamanho em disco | 3,8 GB (giro + giro_qualidade) |

> **Cuidado com o número de partições.** Se ela perguntar por que o
> `\dt` mostra menos tabelas do que o `pg_class` conta, a resposta é:
> 43 partições × 11 objetos (2 tabelas, seus índices e as chaves) = 473
> objetos físicos para 2 tabelas lógicas. É o preço do *partition
> pruning*, e está justificado na seção 4.4.

---

## 9. Se algo falhar

| Sintoma | Causa | Correção |
|---|---|---|
| `psql: command not found` | não está no PATH | use o caminho completo da seção 2 |
| `connection refused` | cluster parado | `.\scripts\pg.ps1 start` |
| `database "giro" does not exist` | carga não rodou | `python run_all.py --reset` (~30 min) |
| MER desatualizado | banco mudou | `python src\gerar_mer.py` |
| Gráfico do MER ilegível | arquivo antigo | abra o `.svg`, não o `.png` |

---

## 10. O que não existe, e é honesto dizer

- **Não há interface de usuário para o banco** além do painel e do
  relatório. O banco é operado por SQL e por scripts. pgAdmin/DBeaver
  seriam conveniência, não requisito.
- **O diagrama de casos de uso não existia** antes desta sessão. Foi
  gerado agora, a partir dos controles reais do painel.
- **O MER anterior era conceitual**, em ASCII, no `04-modelagem.md`. Os
  três arquivos `mer*.svg` são o modelo **físico**, derivado do catálogo.
- **O dataset é sintético.** Está escrito no painel e no rodapé de todo
  material. Não esconder isso na banca é parte do argumento.
