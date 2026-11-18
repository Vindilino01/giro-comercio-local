/**
 * Verificacao de runtime do painel.
 *
 * POR QUE ISTO EXISTE
 * -------------------
 * `node --check` valida sintaxe, mas nao pega erro de execucao como
 * `esc is not defined` - que abortou `renderTabela` no meio e deixou o
 * grafico com zero barras, o total em "—" e metade da pagina vazia.
 * O unico jeito de saber e abrir a pagina e olhar o DOM.
 *
 * Uso: node scripts/verificar_painel.js
 */
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const RAIZ = path.resolve(__dirname, '..');
const PAINEL = 'file:///' + path.join(RAIZ, 'docs', 'painel.html').replace(/\\/g, '/');

(async () => {
  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    args: ['--allow-file-access-from-files', '--disable-gpu'],
  });

  let falhas = 0;
  const check = (nome, ok, detalhe) => {
    console.log(`${ok ? 'OK   ' : 'FALHA'} ${nome}${detalhe ? ' — ' + detalhe : ''}`);
    if (!ok) falhas += 1;
  };

  const page = await browser.newPage();
  const erros = [];
  page.on('pageerror', (e) => erros.push('pageerror: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') erros.push('console: ' + m.text());
  });

  await page.setViewport({ width: 1366, height: 768 });
  await page.goto(PAINEL, { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 900));

  const d = await page.evaluate(() => {
    const txt = (s) => document.querySelector(s)?.textContent?.trim() || '';
    const sl = document.querySelector('#nivel')?.getBoundingClientRect();
    return {
      barras: document.querySelectorAll('.bar-m').length,
      totalPedido: txt('#total-pedido'),
      linhas: document.querySelectorAll('#tabela-body tr').length,
      hbars: document.querySelectorAll('.hbar').length,
      offenders: document.querySelectorAll('#offenders-body tr').length,
      headH1: document.querySelectorAll('h1').length,
      unidade: document.querySelectorAll('.unidade').length,
      slider: sl ? { l: sl.left, w: sl.width } : null,
      // Centro de cada rótulo: é o que representa o valor. A borda
      // esquerda não serve - os extremos são alinhados por dentro.
      escala: Array.from(document.querySelectorAll('.service__scale span'))
        .map((s) => {
          const r = s.getBoundingClientRect();
          return { t: s.textContent, c: r.left + r.width / 2 };
        }),
      perdaReceita: txt('#perda-receita'),
      selos: document.querySelectorAll('.seal').length,
      overflowX: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    };
  });

  check('sem erro de JavaScript', erros.length === 0,
        erros.length ? erros.slice(0, 3).join(' | ') : 'ok');
  check('grafico renderizou 24 barras', d.barras === 24, `${d.barras}`);
  check('total do pedido calculado', d.totalPedido.startsWith('R$'), d.totalPedido);
  check('tabela tem linhas', d.linhas > 20, `${d.linhas}`);
  check('histograma de cobertura', d.hbars >= 5, `${d.hbars} barras`);
  check('ranking de ofensores', d.offenders >= 8, `${d.offenders}`);
  check('perda calculada', d.perdaReceita.startsWith('R$'), d.perdaReceita);
  check('selo por loja', d.selos === 3, `${d.selos}`);
  check('um unico h1', d.headH1 === 1, `${d.headH1}`);
  check('unidade visivel na tabela', d.unidade > 0, `${d.unidade}`);
  check('sem overflow horizontal', d.overflowX <= d.viewport + 1,
        `${d.overflowX} vs ${d.viewport}`);

  // Escala do slider: o CENTRO de cada rotulo deve cair na posicao real
  // do seu valor dentro do trilho. O valor 90% fica na borda esquerda,
  // 99% na direita; os intermediarios distribuem linearmente.
  let posOk = true;
  let pior = 0;
  if (d.slider && d.slider.w > 0) {
    for (const s of d.escala) {
      const v = parseFloat(s.t);
      const esperado = (v - 90) / 9;
      const real = (s.c - d.slider.l) / d.slider.w;
      // O primeiro e o ultimo sao alinhados por dentro; a tolerancia
      // cobre o deslocamento de meio rotulo (~13px).
      const tol = 0.075;
      const diff = Math.abs(real - esperado);
      pior = Math.max(pior, diff);
      if (diff > tol) posOk = false;
    }
  } else {
    posOk = false;
  }
  check('escala do slider alinhada', posOk, `pior desvio ${(pior * 100).toFixed(1)}%`);

  await page.close();

  // ---- impressao sem background ----
  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1200, height: 900 });
  await p2.emulateMediaType('print');
  await p2.goto(PAINEL, { waitUntil: 'networkidle0' });
  await p2.waitForSelector('.bar-m', { timeout: 5000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 500));

  const pint = await p2.evaluate(() => {
    const seg = document.querySelector('.band__seg');
    const after = seg ? getComputedStyle(seg, '::after') : null;
    const hb = document.querySelector('.hbar__fill');
    const bar = document.querySelector('.bar');
    return {
      bandBorder: after ? after.borderTopWidth : null,
      bandWidth: after ? parseFloat(after.width) : 0,
      bandAdjust: after ? after.printColorAdjust : null,
      hbarWidth: hb ? hb.getBoundingClientRect().width : 0,
      hbarAdjust: hb ? getComputedStyle(hb).printColorAdjust : null,
      barAdjust: bar ? getComputedStyle(bar).printColorAdjust : null,
      barW: bar ? bar.getBoundingClientRect().width : 0,
    };
  });

  check('faixa imprime com proporcao', pint.bandBorder === '3px' && pint.bandWidth > 10,
        `border ${pint.bandBorder}, largura ${pint.bandWidth.toFixed(0)}px`);
  check('histograma imprime com largura', pint.hbarWidth > 5,
        `${pint.hbarWidth.toFixed(0)}px`);
  check('barras de perda com exact', pint.barAdjust === 'exact',
        String(pint.barAdjust));

  await p2.close();
  await browser.close();

  console.log(`\n${falhas === 0 ? 'PAINEL OK' : falhas + ' FALHA(S)'}`);
  process.exit(falhas === 0 ? 0 : 1);
})();
