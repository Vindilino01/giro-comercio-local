/**
 * Captura o painel canonico e roda checagens de acessibilidade.
 */
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PAINEL = 'file:///' + path.resolve(__dirname, '..', 'docs', 'painel.html')
  .replace(/\\/g, '/');
const SHOTS = path.resolve(__dirname, '..', 'logs', 'shots');

(async () => {
  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    args: ['--allow-file-access-from-files', '--disable-gpu'],
  });

  const larguras = [
    { nome: 'painel_desktop', w: 1440, h: 950 },
    { nome: 'painel_notebook', w: 1366, h: 768 },
    { nome: 'painel_mobile', w: 390, h: 844 },
  ];

  for (const cfg of larguras) {
    const page = await browser.newPage();
    await page.setViewport({ width: cfg.w, height: cfg.h });
    await page.goto(PAINEL, { waitUntil: 'load' });
    await new Promise((r) => setTimeout(r, 500));
    await page.screenshot({ path: path.join(SHOTS, `${cfg.nome}.png`) });
    await page.close();
  }

  // Pagina inteira para leitura de composicao
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 950 });
  await page.goto(PAINEL, { waitUntil: 'load' });
  await new Promise((r) => setTimeout(r, 500));
  await page.screenshot({ path: path.join(SHOTS, 'painel_inteiro.png'), fullPage: true });

  // ---- checagens ----
  const checks = await page.evaluate(() => {
    const out = [];
    const add = (nome, ok, detalhe) => out.push({ nome, ok, detalhe });

    // unidades visiveis
    const unidades = document.querySelectorAll('.unidade');
    add('unidade exibida na tabela', unidades.length > 0, `${unidades.length} ocorrencias`);

    // headings
    const h1 = document.querySelectorAll('h1');
    add('um unico h1', h1.length === 1, `${h1.length}`);

    // tabela
    const ths = Array.from(document.querySelectorAll('thead th'));
    add('th com scope', ths.every((t) => t.getAttribute('scope')), `${ths.length} colunas`);

    // contraste de amostra
    const lum = (c) => {
      const [r, g, b] = c.match(/\d+/g).map(Number).slice(0, 3).map((v) => {
        v /= 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const ratio = (fg, bg) => {
      const a = lum(fg) + 0.05, b = lum(bg) + 0.05;
      return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100;
    };
    const bg = getComputedStyle(document.body).backgroundColor;
    const amostras = ['.poster__valor', '.picking td', '.lede', '.c-num']
      .map((sel) => {
        const e = document.querySelector(sel);
        if (!e) return null;
        const st = getComputedStyle(e);
        return { sel, fs: st.fontSize, ratio: ratio(st.color, bg) };
      }).filter(Boolean);
    add('contraste >= 4.5 no corpo', amostras.every((a) => a.ratio >= 4.5),
        JSON.stringify(amostras));

    // overflow
    add('sem overflow horizontal',
        document.documentElement.scrollWidth <= window.innerWidth + 1,
        `${document.documentElement.scrollWidth} vs ${window.innerWidth}`);

    // controles nomeados
    // controles nomeados: texto, aria-label, aria-labelledby ou title
    const ctrls = Array.from(document.querySelectorAll('button, select, input, a[href]'));
    const semNome = ctrls.filter((e) => !(
      e.textContent.trim()
      || e.getAttribute('aria-label')
      || e.getAttribute('aria-labelledby')
      || e.getAttribute('title')
    ));
    add('todos os controles nomeados', semNome.length === 0, `${semNome.length} sem nome`);

    // fontes reais
    const fam = getComputedStyle(document.body).fontFamily;
    add('fonte propria carregada', /Piazzolla|Archivo/.test(document.documentElement.outerHTML),
        fam.slice(0, 60));

    return out;
  });

  console.log('\n=== CHECAGENS ===');
  for (const c of checks) {
    console.log(`${c.ok ? 'OK   ' : 'FALHA'} ${c.nome} — ${c.detalhe}`);
  }

  await browser.close();
  console.log('\ncapturas em logs/shots/painel_*.png');
})();
