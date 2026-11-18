-- =====================================================================
-- 099 - Testes de constraint (evidencia E01)
--
-- Objetivo: provar que o banco REJEITA dado invalido, em vez de
-- aceitar silenciosamente. Cada caso abaixo DEVE falhar. Se algum
-- passar, a constraint esta furada.
--
-- Executado por tests/test_constraints.sql. Todo INSERT vai dentro de
-- um savepoint que e revertido, entao o banco fica limpo.
-- =====================================================================

\set ON_ERROR_STOP off

\echo ''
\echo '=========================================='
\echo 'E01 - Testes de constraint do modelo OLTP'
\echo '=========================================='

-- Semente minima para os testes de FK
BEGIN;

INSERT INTO prata.loja (codigo, nome, cidade, uf, data_abertura)
VALUES ('TST', 'Loja Teste', 'Santos', 'SP', '2020-01-01');

INSERT INTO prata.categoria (codigo, nome, nivel)
VALUES ('TST1', 'Teste', 1);

INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida, e_perecivel, dias_validade)
VALUES ('7891000053508', 'SKU-TST', 'Produto Teste',
        (SELECT categoria_id FROM prata.categoria WHERE codigo = 'TST1'), 'UN', TRUE, 30);

\echo ''
\echo '--- C01: EAN com digito verificador errado (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida)
VALUES ('7891000053500', 'SKU-BAD1', 'EAN invalido',
        (SELECT categoria_id FROM prata.categoria WHERE codigo = 'TST1'), 'UN');
ROLLBACK TO s;

\echo ''
\echo '--- C02: perecivel sem dias_validade (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida, e_perecivel)
VALUES ('7891000100103', 'SKU-BAD2', 'Perecivel sem validade',
        (SELECT categoria_id FROM prata.categoria WHERE codigo = 'TST1'), 'UN', TRUE);
ROLLBACK TO s;

\echo ''
\echo '--- C03: nao-perecivel COM dias_validade (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida, e_perecivel, dias_validade)
VALUES ('7891000100103', 'SKU-BAD3', 'Nao perecivel com validade',
        (SELECT categoria_id FROM prata.categoria WHERE codigo = 'TST1'), 'UN', FALSE, 10);
ROLLBACK TO s;

\echo ''
\echo '--- C04: EAN duplicado (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida)
VALUES ('7891000053508', 'SKU-BAD4', 'EAN duplicado',
        (SELECT categoria_id FROM prata.categoria WHERE codigo = 'TST1'), 'UN');
ROLLBACK TO s;

\echo ''
\echo '--- C05: unidade de medida invalida (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto (ean, sku_interno, nome, categoria_id, unidade_medida)
VALUES ('7891000100103', 'SKU-BAD5', 'Unidade invalida',
        (SELECT categoria_id FROM prata.categoria WHERE codigo = 'TST1'), 'XYZ');
ROLLBACK TO s;

\echo ''
\echo '--- C06: UF invalida na loja (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.loja (codigo, nome, cidade, uf, data_abertura)
VALUES ('TST2', 'Loja UF ruim', 'Santos', 'XX', '2020-01-01');
ROLLBACK TO s;

\echo ''
\echo '--- C07: CNPJ com mascara (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.fornecedor (cnpj, razao_social)
VALUES ('12.345.678/0001-90', 'Fornecedor com mascara');
ROLLBACK TO s;

\echo ''
\echo '--- C08: quantidade negativa no estoque (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.estoque_snapshot (loja_id, produto_id, data_ref, qtd_inicio, qtd_fim)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        (SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2025-01-01', -5, 0);
ROLLBACK TO s;

\echo ''
\echo '--- C09: equacao de estoque que nao fecha (deve FALHAR) ---'
-- inicio 10 + entradas 0 + saidas 0 + ajustes 0 deve ser 10, mas informamos 7
SAVEPOINT s;
INSERT INTO prata.estoque_snapshot (loja_id, produto_id, data_ref, qtd_inicio, qtd_entradas, qtd_saidas, qtd_ajustes, qtd_fim)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        (SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2025-01-02', 10, 0, 0, 0, 7);
ROLLBACK TO s;

\echo ''
\echo '--- C10: cupom com total incoerente (deve FALHAR) ---'
-- 100 - 5 deveria ser 95, informamos 90
SAVEPOINT s;
INSERT INTO prata.venda (loja_id, data_venda, hora_venda, numero_cupom, valor_bruto, valor_desconto, valor_liquido, qtd_itens)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        '2025-01-01', '10:00', '000001', 100.00, 5.00, 90.00, 2);
ROLLBACK TO s;

\echo ''
\echo '--- C11: cupom duplicado na mesma loja/data/serie (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.venda (loja_id, data_venda, hora_venda, numero_cupom, valor_bruto, valor_desconto, valor_liquido, qtd_itens)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        '2025-01-01', '10:00', 'CP-DUP', 100.00, 0, 100.00, 2);
SAVEPOINT s2;
INSERT INTO prata.venda (loja_id, data_venda, hora_venda, numero_cupom, valor_bruto, valor_desconto, valor_liquido, qtd_itens)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        '2025-01-01', '11:00', 'CP-DUP', 50.00, 0, 50.00, 1);
ROLLBACK TO s2;
ROLLBACK TO s;

\echo ''
\echo '--- C12: status CANCELADA sem data de cancelamento (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.venda (loja_id, data_venda, hora_venda, numero_cupom, valor_bruto, valor_desconto, valor_liquido, qtd_itens, status)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        '2025-01-02', '10:00', 'CP-CANC', 100.00, 0, 100.00, 2, 'CANCELADA');
ROLLBACK TO s;

\echo ''
\echo '--- C13: item de venda com quantidade zero (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.venda (loja_id, data_venda, hora_venda, numero_cupom, valor_bruto, valor_desconto, valor_liquido, qtd_itens)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        '2025-01-03', '10:00', 'CP-QTD0', 10.00, 0, 10.00, 1);
INSERT INTO prata.item_venda (venda_id, data_venda, item_seq, produto_id, quantidade, preco_unitario, valor_total)
VALUES ((SELECT venda_id FROM prata.venda WHERE numero_cupom = 'CP-QTD0'),
        '2025-01-03', 1,
        (SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        0, 10.00, 0);
ROLLBACK TO s;

\echo ''
\echo '--- C14: duas faixas de preco abertas para o mesmo produto (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto_preco_historico (produto_id, data_inicio, preco_custo, preco_venda)
VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2024-01-01', 5.00, 10.00);
SAVEPOINT s2;
INSERT INTO prata.produto_preco_historico (produto_id, data_inicio, preco_custo, preco_venda)
VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2024-06-01', 6.00, 12.00);
ROLLBACK TO s2;
ROLLBACK TO s;

\echo ''
\echo '--- C15: faixas de preco sobrepostas (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.produto_preco_historico (produto_id, data_inicio, data_fim, preco_custo, preco_venda)
VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2024-01-01', '2024-06-01', 5.00, 10.00);
SAVEPOINT s2;
INSERT INTO prata.produto_preco_historico (produto_id, data_inicio, data_fim, preco_custo, preco_venda)
VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2024-03-01', '2024-09-01', 6.00, 12.00);
ROLLBACK TO s2;
ROLLBACK TO s;

\echo ''
\echo '--- C16: movimentacao de VENDA com quantidade positiva (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.movimentacao_estoque (loja_id, produto_id, data_movimento, tipo, quantidade)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        (SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2025-01-01', 'VENDA', 5);
ROLLBACK TO s;

\echo ''
\echo '--- C17: dois fornecedores preferenciais para o mesmo produto (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.fornecedor (cnpj, razao_social) VALUES ('11111111111111', 'Forn A');
INSERT INTO prata.fornecedor (cnpj, razao_social) VALUES ('22222222222222', 'Forn B');
INSERT INTO prata.produto_fornecedor (produto_id, fornecedor_id, custo_unitario, lead_time_dias, preferencial)
VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        (SELECT fornecedor_id FROM prata.fornecedor WHERE cnpj = '11111111111111'), 5.00, 7, TRUE);
SAVEPOINT s2;
INSERT INTO prata.produto_fornecedor (produto_id, fornecedor_id, custo_unitario, lead_time_dias, preferencial)
VALUES ((SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        (SELECT fornecedor_id FROM prata.fornecedor WHERE cnpj = '22222222222222'), 5.50, 5, TRUE);
ROLLBACK TO s2;
ROLLBACK TO s;

\echo ''
\echo '--- C18: horas_sem_estoque acima de 24 (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.estoque_snapshot (loja_id, produto_id, data_ref, qtd_inicio, qtd_fim, houve_ruptura, horas_sem_estoque)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        (SELECT produto_id FROM prata.produto WHERE sku_interno = 'SKU-TST'),
        '2025-01-04', 0, 0, TRUE, 30);
ROLLBACK TO s;

\echo ''
\echo '--- C19: pedido com entrega antes do pedido (deve FALHAR) ---'
SAVEPOINT s;
INSERT INTO prata.pedido_compra (loja_id, fornecedor_id, numero_pedido, data_pedido, data_previsao, status)
VALUES ((SELECT loja_id FROM prata.loja WHERE codigo = 'TST'),
        (SELECT fornecedor_id FROM prata.fornecedor LIMIT 1),
        'PED-ERR', '2025-01-10', '2025-01-05', 'ENVIADO');
ROLLBACK TO s;

\echo ''
\echo '--- C20: produto fica; base de teste e revertida ---'
ROLLBACK;

\echo ''
\echo '=========================================='
\echo 'Fim. Cada caso acima deveria ter mostrado ERROR.'
\echo 'Nenhum ERROR = constraint furada.'
\echo '=========================================='
