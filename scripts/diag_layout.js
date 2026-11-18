/**
 * Diagnóstico e captura do site em larguras reais.
 *
 * O --screenshot do Edge headless com --window-size não aplica o
 * media query de forma confiável (a viewport do layout difere da
 * janela). Puppeteer define a viewport do layout explicitamente, que
 * é o que o CSS realmente consulta.
 */

const path = require('path');
const fs = require('fs');

const RAIZ = path.resolve(__dirname, '..');
const SITE = path.join(RAIZ, 'dashboard', 'site', 'index.html');
const SHOTS = path.join(RAIZ, 'logs', 'shots');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

const URL_SITE = 'file:///' + SITE.replace(/\\/g, '/');

async function main() {
  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    args: ['--allow-file-access-from-files', '--disable-gpu'],
  });

  const larguras = [
    { nome: 'desktop', w: 1440, h: 1000 },
    { nome: 'notebook', w: 1366, h: 768 },
    { nome: 'tablet', w: 900, h: 900 },
    { nome: 'mobile', w: 390, h: 844 },
  ];

  const relatorio = [];

  for (const cfg of larguras) {
    const page = await browser.newPage();
    await page.setViewport({ width: cfg.w, height: cfg.h, deviceScaleFactor: 1 });
    await page.goto(URL_SITE, { waitUntil: 'load' });
    await new Promise((r) => setTimeout(r, 350));

    const diag = await page.evaluate(() => {
      const doc = document.documentElement;
      const marcar = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          left: Math.round(r.left),
          right: Math.round(r.right),
          largura: Math.round(r.width),
        };
      };
      // Um elemento dentro de um contêiner com overflow-x rolável é
      // legítimo: a tabela é mais larga que a tela e rola dentro do
      // próprio bloco. O que caracteriza overflow real é o documento
      // ganhar rolagem horizontal (scrollWidth > innerWidth) ou um
      // elemento vazar de um ancestral que NÃO tem overflow.
      const dentroDeScroll = (el) => {
        let p = el.parentElement;
        while (p && p !== document.body) {
          const st = getComputedStyle(p);
          if (st.overflowX === 'auto' || st.overflowX === 'scroll') return true;
          p = p.parentElement;
        }
        return false;
      };

      const estourados = Array.from(document.querySelectorAll('body *'))
        .map((el) => ({ el, r: el.getBoundingClientRect() }))
        .filter((o) => o.r.right > window.innerWidth + 1 && !dentroDeScroll(o.el))
        .slice(0, 8)
        .map((o) => ({
          tag: o.el.tagName.toLowerCase(),
          classe: String(o.el.className || ''),
          right: Math.round(o.r.right),
          largura: Math.round(o.r.width),
        }));

      return {
        viewport: window.innerWidth,
        matchMobile: window.matchMedia('(max-width: 820px)').matches,
        shellDisplay: getComputedStyle(document.querySelector('.shell')).display,
        rail: marcar(document.querySelector('.rail')),
        main: marcar(document.querySelector('.main')),
        tabela: marcar(document.querySelector('table')),
        overflowX: doc.scrollWidth,
        estourados,
      };
    });

    relatorio.push({ tela: cfg.nome, ...diag });

    await page.screenshot({
      path: path.join(SHOTS, `real_${cfg.nome}.png`),
      fullPage: false,
    });

    await page.close();
  }

  await page_full(browser);

  await browser.close();

  const saida = path.join(RAIZ, 'logs', 'diag_layout.json');
  fs.writeFileSync(saida, JSON.stringify(relatorio, null, 2), 'utf-8');

  for (const r of relatorio) {
    const ok = r.estourados.length === 0 && r.overflowX <= r.viewport + 1;
    console.log(
      `${ok ? 'OK  ' : 'FALHA'} ${r.tela.padEnd(9)} viewport=${r.viewport} ` +
      `scrollWidth=${r.overflowX} mobile=${r.matchMobile} ` +
      `shell=${r.shellDisplay}`
    );
    if (r.estourados.length) {
      for (const e of r.estourados) {
        console.log(`       vaza: ${e.tag}.${e.classe} right=${e.right}`);
      }
    }
  }
  console.log(`\nRelatório: ${saida}`);
}

async function page_full(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  await page.goto(URL_SITE, { waitUntil: 'load' });
  await new Promise((r) => setTimeout(r, 400));
  await page.screenshot({
    path: path.join(SHOTS, 'real_pagina_inteira.png'),
    fullPage: true,
  });
  await page.close();
}

main().catch((e) => {
  console.error('ERRO:', e.message);
  process.exit(1);
});
