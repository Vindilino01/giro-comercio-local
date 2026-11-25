# Visita guiada — o que olhar, em que ordem

Este arquivo é para quem nunca viu o projeto. A ordem vai do mais visual
para o mais técnico. Cada passo diz o que você deve **ver** e o que aquilo
prova.

Tempo total: ~25 minutos. Nada aqui exige instalar nada.

---

## 1. O painel (5 min) — comece por aqui

Abra **`docs/painel.html`** com duplo clique. Não precisa de servidor nem de
internet: o arquivo tem 990 KB e carrega tudo embutido.

**O que você vê primeiro:**

- Uma frase grande: *"O Giro recomenda comprar R$ 259.577,64 em 6 fornecedores
  nas 3 lojas."*
- Ao lado: *"Nos últimos 12 meses, a falta de produto custou R$ 2.298.078,12 em
  receita que a prateleira vazia não registrou."*

Esse segundo número é o diferencial do projeto. Todo sistema de varejo mostra
quanto **vendeu**. Este mostra quanto **deixou de vender por falta de produto**
— que é a venda que não aconteceu e por isso não está em lugar nenhum.

**O que experimentar:**

| Ação | O que observar |
|---|---|
| Arraste o **Nível de serviço** de 95% para 99% | O total do pedido sobe. Você está pedindo mais proteção contra falta, e isso imobiliza mais capital. É o trade-off real do varejo. |
| Troque a **Loja** para "Mercadinho da Família" | Os números mudam por loja. O seletor "Todas as lojas" agrupa por loja na tabela. |
| Clique no cabeçalho **Valor** | A tabela reordena. O foco do teclado fica no cabeçalho (acessibilidade). |
| Clique num **fornecedor** na faixa verde | A tabela filtra. A largura de cada bloco é proporcional ao valor do pedido daquele fornecedor. |
| Role até **"Onde a perda se concentra"** | Gráfico de 24 meses. A barra vermelha é o pior mês. |
| Role até o **selo de confiança** | Três lojas, cada uma com a **pior** dimensão de qualidade. Clique em "Ver as 7 dimensões". |
| Clique em **IMPRIMIR** | Gera um PDF de 8 páginas com o pedido completo, agrupado por loja. |

**O que isso prova:** o modelo de dados sustenta uma decisão de negócio.
Não é um diagrama — é uma tela que responde "o que comprar hoje".

---

## 2. O relatório (10 min) — a leitura

Abra **`docs/relatorio-final.docx`** (45 páginas) ou o PDF ao lado dele.

Não leia tudo. Leia nesta ordem:

| Página | O que procurar |
|---|---|
| **1** | Capa. Se estiver escrito "integrantes não informados", é porque o grupo ainda não preencheu `docs/integrantes.md`. |
| **2** | Sumário. As seções 4.1 a 4.7 são exatamente o que o edital pede. |
| **4** | **Os dois diferenciais.** É a tese do trabalho em uma página. |
| **12** | **Matriz de decisão.** 8 bancos comparados, 7 critérios com peso, nota final 4,65. Confira a aritmética: é isto que o professor vai fazer. |
| **20-25** | **Modelagem.** Diagrama conceitual, o `EXCLUDE USING gist` que impede faixas de preço sobrepostas, e a explicação honesta de que o histórico de preço tem só uma faixa por SKU. |
| **36-37** | **Tabela de recall.** 17 regras, quantos defeitos cada uma pegou, e a explicação dos casos fora da curva. |
| **42-45** | **As 11 consultas** com resultado real e tempo de execução. |
| **50** | **Seção 4.7.** Aqui o trabalho admite onde falha. Leia com atenção — é a parte que separa projeto honesto de propaganda. |
| **65** | **Referências.** |

---

## 3. O pitch (5 min) — a apresentação

Abra **`docs/pitch.pdf`** (12 slides, 16:9).

É o que vocês vão projetar. O roteiro de fala está em
**`docs/pitch-roteiro.md`**, com marcação de tempo por fala (10 minutos ÷
7 pessoas ≈ 85 segundos cada).

Os slides que importam:

- **3**: os 5 Vs do diagnóstico (com o volume real: 6,36M de linhas)
- **6**: a arquitetura em três camadas (bronze → prata → ouro)
- **7**: os três números que **não** são 100% — e por que isso é bom
- **10**: o cenário 100× com o benchmark medido

---

## 4. O banco de dados (5 min) — o que está por baixo

O PostgreSQL está rodando na porta 5433. Para abrir uma sessão:

```powershell
cd "C:\Users\CPU\Desktop\Projeto A3 - Analise de Dados e Big Data"
.\scripts\pg.ps1 psql
```

Dentro do psql, cole uma por vez:

```sql
-- Quantas linhas existem?
SELECT 'vendas' AS tabela, count(*) FROM prata.venda
UNION ALL SELECT 'itens', count(*) FROM prata.item_venda
UNION ALL SELECT 'snapshots', count(*) FROM prata.estoque_snapshot;

-- A pergunta de negócio: o que comprar hoje?
SELECT produto, fornecedor, estoque_atual, quantidade_sugerida,
       valor_compra_sugerido, situacao
  FROM ouro.mv_sugestao_compra
 WHERE situacao = 'RUPTURA'
 ORDER BY valor_compra_sugerido DESC
 LIMIT 10;

-- O selo de confiança: a pior dimensão de cada loja
SELECT loja, dimensoes_medidas, pior_dimensao_pct, dimensao_critica, selo
  FROM ouro.mv_qualidade_loja;
```

Para sair: `\q`

**O que isso prova:** o painel não é um HTML com números escritos à mão. Ele lê
essas views. Se você mudar um preço no banco e regerar o painel, o número muda.

---

## 5. As verificações (5 min) — a prova de que funciona

Cada comando abaixo imprime OK ou o erro. Rode na pasta do projeto:

```powershell
python scripts\checklist.py        # o resumo de tudo
python -m pytest -q                # 5 suites de teste
python dashboard\verificar.py      # 18 números do painel conferidos contra o banco
node scripts\verificar_painel.js   # 15 verificações no browser
```

O mais interessante é o **gate de confiança**:

```powershell
node scripts\testar_gate_confianca.js
```

Ele força uma loja para 84% de qualidade e mostra o painel **retirando o pedido
daquela loja** do total. É a funcionalidade que o relatório promete na seção
"segundo diferencial": com dado ruim, o sistema não finge precisão.

---

## 6. Se algo der errado

| Problema | O que fazer |
|---|---|
| O painel abre em branco | Use Edge ou Chrome. Firefox antigo não suporta os recursos de CSS usados. |
| `pg_isready` diz que não está no ar | `.\scripts\pg.ps1 start` |
| Quer regerar o painel | `python dashboard/gerar.py` |
| Quer regerar o Word | Preencha `docs/integrantes.md` antes, e rode `python src\relatorio_docx.py` |
| Quer tudo do zero | `python run_all.py --reset` (cerca de 30 minutos) |

---

## O que ainda falta vocês fazerem

1. **`docs/integrantes.md`** — 7 nomes e RAs. Sem isso a capa sai sem
   identificação.
2. **`docs/autorizacao-grupo.pdf`** — o documento da professora autorizando o
   grupo de 7. Se o arquivo existir, ele entra como última página do relatório.

Depois disso:

```powershell
python src\relatorio_docx.py
pwsh scripts\atualizar_sumario.ps1
python scripts\checklist.py
```
