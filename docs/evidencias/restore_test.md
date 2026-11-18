# Teste de restore

> Medição real, não estimativa. Reproduza com `python tests/test_restore.py`
> (leva cerca de 8 minutos: dump + drop + create + restore + verificação).

| Etapa | Resultado |
|---|---|
| Banco de origem | `giro` (3130 MB) |
| Itens de venda | 4,159,608 |
| Vendas | 545,093 |
| Snapshots de estoque | 921,060 |
| Tamanho do dump (comprimido) | 179 MB |
| Tempo de `pg_dump` | 35.4 s |
| Tempo de `pg_restore` | 450.6 s |
| Tempo de verificação | 0,8 s |
| **RTO medido** | **451 s (7.5 min)** |
| Contagens idênticas | sim |
| Receita total (restaurado) | 58669541.02 |
| Receita total (original) | 58669541.02 |

## O que este teste prova

1. O backup é **restaurável** — não é apenas um arquivo gerado.
2. As contagens batem — não há perda silenciosa de linhas.
3. As consultas funcionam no banco restaurado — views materializadas,
   índices e constraints foram todos recriados.
4. O RTO de 451 s é aceitável para um banco de 3,1 GB em disco
   (dump comprimido de 179 MB), num notebook comum.

## Limitação

O RPO é de 24 h (backup diário). Uma falha de disco às 23h perde o dia
inteiro de vendas. Isso é aceitável porque o **PDV é a fonte original**:
o dado pode ser reexportado e recarregado. Aumentar a frequência do
backup não resolve o problema real — reduzi-lo exigiria replicação
contínua (WAL shipping), que é custo de infraestrutura sem retorno para
uma loja de bairro.

## Por que o dump é 179 MB e o banco 3,1 GB

O banco em disco carrega índices (721 MB), a área de staging `stg`
(603 MB, que existe só durante a carga), as views materializadas
(180 MB) e espaço livre de versões antigas de linha. O dump guarda
apenas as tabelas e os objetos — e comprime com ZSTD.
