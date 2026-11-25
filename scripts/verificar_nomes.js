// Nome acessivel dos checkboxes da lista de separacao.
//
// POR QUE ESTE TESTE EXISTE
// -------------------------
// O label envolve so o nome do produto. Antes, o leitor de tela
// anunciava "Frango Inteiro, caixa de selecao, nao marcada" - sem
// quantidade, sem unidade, sem loja. E como "Frango Inteiro" aparece uma
// vez por loja, as tres linhas soavam identicas.
//
// O usuario de leitor de tela precisa saber O QUE comprar e QUANTO, nao
// so o nome. Este teste exige as tres informacoes.
//
// Uso: node scripts/verificar_nomes.js

const path = require('path');
const p = require('puppeteer-core');

(async () => {
  const b = await p.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
    args: ['--allow-file-access-from-files'],
  });
  const pg = await b.newPage();
  await pg.setViewport({ width: 1366, height: 900 });
  await pg.goto('file:///' + path.join(process.cwd(), 'docs', 'painel.html').replace(/\\/g, '/'),
    { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 800));

  const nomes = await pg.evaluate(() =>
    [...document.querySelectorAll('.lista__check')].map((b) => ({
      id: b.id,
      aria: b.getAttribute('aria-label') || '',
    })));

  let falhas = 0;

  // 1. todo checkbox tem aria-label
  const semNome = nomes.filter((n) => !n.aria);
  console.log(`${semNome.length === 0 ? 'OK  ' : 'FALHA'} todos os ${nomes.length} checkboxes tem nome — ${semNome.length} sem`);
  if (semNome.length) falhas++;

  // 2. o nome traz quantidade (numero)
  const semQtd = nomes.filter((n) => !/\d/.test(n.aria));
  console.log(`${semQtd.length === 0 ? 'OK  ' : 'FALHA'} nome traz a quantidade — ${semQtd.length} sem numero`);
  if (semQtd.length) falhas++;

  // 3. o nome traz unidade de medida
  const semUn = nomes.filter((n) => !/\b(UN|KG|CX|PCT|DZ|L|ML)\b/.test(n.aria));
  console.log(`${semUn.length === 0 ? 'OK  ' : 'FALHA'} nome traz a unidade — ${semUn.length} sem unidade`);
  if (semUn.length) falhas++;

  // 4. o nome traz a loja (escopo "todas as lojas")
  const semLoja = nomes.filter((n) => !/—/.test(n.aria) || n.aria.split('—').length < 3);
  console.log(`${semLoja.length === 0 ? 'OK  ' : 'FALHA'} nome traz a loja — ${semLoja.length} sem loja`);
  if (semLoja.length) falhas++;

  // 5. o mesmo produto em lojas diferentes tem nomes distintos
  const porProduto = new Map();
  for (const n of nomes) {
    const produto = n.aria.split('—')[0].trim();
    if (!porProduto.has(produto)) porProduto.set(produto, []);
    porProduto.get(produto).push(n.aria);
  }
  const ambiguos = [...porProduto.entries()]
    .filter(([, lista]) => lista.length > 1 && new Set(lista).size === 1);
  console.log(`${ambiguos.length === 0 ? 'OK  ' : 'FALHA'} produto repetido tem nome distinto — ${ambiguos.length} ambiguos`);
  if (ambiguos.length) {
    falhas++;
    for (const [produto, lista] of ambiguos.slice(0, 3)) {
      console.log(`    "${produto}" x${lista.length}, todos iguais`);
    }
  }

  // amostra para o relatorio
  console.log('');
  console.log('amostra:');
  for (const n of nomes.slice(0, 3)) console.log(`  ${n.aria}`);

  await b.close();
  console.log('');
  console.log(falhas === 0 ? 'NOMES OK' : `${falhas} FALHA(S)`);
  process.exit(falhas === 0 ? 0 : 1);
})();
