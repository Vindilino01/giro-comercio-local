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
      // Contagens com rotulo. O titulo e o rodape usavam a MESMA palavra
      // "produtos" para numeros diferentes (SKUs distintos no titulo,
      // pares loja x SKU no rodape): 70 contra 137 na mesma tela. O dono
      // lia dois numeros e desconfiava de ambos.
      tituloContagem: document.querySelector('#picking-title span')?.textContent || '',
      totalContagem: document.querySelector('#picking-total small')?.textContent || '',
      slider: sl ? { l: sl.left, w: sl.width } : null,
      // O slider de 10 posicoes virou escolha de 3 opcoes. O que se testa
      // agora: existem 3 radios, o de 95 vem marcado, todos com 44px.
      radios: Array.from(document.querySelectorAll('input[name=nivel]')).map((r) => {
        const lab = r.closest('.disp__opt');
        const box = lab.getBoundingClientRect();
        return { v: r.value, marcado: r.checked, h: Math.round(box.height) };
      }),
      ajudaDisp: txt('#disp-help'),
      ajustesFechado: document.getElementById('ajustes')?.open === false,
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

  // A mesma palavra nao pode nomear dois numeros diferentes na mesma
  // tela. Quando o escopo e a rede, o titulo conta SKUs distintos ("70
  // produtos em 3 lojas") e o rodape conta linhas ("137 linhas"). Se os
  // dois voltarem a dizer "produtos", o dono ve 70 e 137 e nao sabe qual
  // e o pedido.
  const tituloFalaProdutos = /produtos em \d+ lojas/.test(d.tituloContagem);
  const rodapeFalaLinhas = /linhas/.test(d.totalContagem);
  check('titulo conta produtos distintos', tituloFalaProdutos,
    d.tituloContagem.trim().slice(0, 48));
  check('rodape conta linhas, nao produtos', rodapeFalaLinhas,
    d.totalContagem.trim().slice(0, 48));
  check('as duas contagens nao usam a mesma palavra',
    !(/produtos/.test(d.totalContagem) && /produtos/.test(d.tituloContagem)),
    `titulo="${d.tituloContagem.trim().slice(0, 26)}" rodape="${d.totalContagem.trim().slice(0, 26)}"`);
  check('unidade visivel na tabela', d.unidade > 0, `${d.unidade}`);
  check('sem overflow horizontal', d.overflowX <= d.viewport + 1,
        `${d.overflowX} vs ${d.viewport}`);

  // Disponibilidade: tres opcoes, a de 95 marcada, todas com 44px de alvo.
  // O slider de 10 posicoes nao existe mais: 95% contra 96% nao era uma
  // diferenca que o dono conseguisse avaliar.
  const temTres = d.radios.length === 3;
  const marcado95 = d.radios.some((r) => r.v === '95' && r.marcado);
  const alvosOk = d.radios.every((r) => r.h >= 44);
  check('disponibilidade tem 3 opcoes', temTres, `${d.radios.length}`);
  check('95 vem marcado', marcado95, d.radios.map((r) => r.v + (r.marcado ? '*' : '')).join(' '));
  check('opcoes com alvo de 44px', alvosOk, d.radios.map((r) => r.h + 'px').join(' '));
  check('ajuda fala em semanas', /95 de 100 semanas/.test(d.ajudaDisp), d.ajudaDisp.slice(0, 46));
  check('ajustes comeca fechado', d.ajustesFechado, String(d.ajustesFechado));

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
