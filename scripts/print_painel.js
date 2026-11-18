/** Testa a impressao A4 do painel: proporcao, cores e quebra de pagina. */
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PAINEL = 'file:///' + path.resolve(__dirname, '..', 'docs', 'painel.html')
  .replace(/\\/g, '/');
const OUT = path.resolve(__dirname, '..', 'logs', 'shots');

(async () => {
  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: EDGE, headless: 'new', args: ['--allow-file-access-from-files'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 900 });
  await page.emulateMediaType('print');
  await page.goto(PAINEL, { waitUntil: 'load' });
  await new Promise((r) => setTimeout(r, 400));

  // Paginas do PDF
  const pdf = await page.pdf({
    format: 'A4',
    printBackground: true,
    margin: { top: '12mm', right: '10mm', bottom: '14mm', left: '10mm' },
  });
  const fs = require('fs');
  fs.writeFileSync(path.join(OUT, 'painel_print.pdf'), pdf);
  console.log(`PDF gerado: ${(pdf.length / 1024).toFixed(0)} KB`);

  // Diagnostico de impressao
  const diag = await page.evaluate(() => {
    const out = {};
    // A faixa de fornecedores preserva proporcao?
    const faixa = document.querySelector('.faixa, .band, [class*="faixa"]');
    if (faixa) {
      const filhos = Array.from(faixa.children).map((c) => ({
        w: Math.round(c.getBoundingClientRect().width),
        txt: c.textContent.trim().slice(0, 26),
      }));
      const total = filhos.reduce((s, f) => s + f.w, 0);
      out.faixa = filhos.map((f) => ({
        ...f, pct: Math.round((f.w / total) * 100),
      }));
    }
    // Elementos que ficariam cortados
    out.overflowX = document.documentElement.scrollWidth;
    out.viewport = window.innerWidth;
    // Tabelas muito largas no papel
    out.tabelas = Array.from(document.querySelectorAll('table')).map((t) => ({
      colunas: t.querySelectorAll('thead th').length,
      largura: Math.round(t.getBoundingClientRect().width),
    }));
    return out;
  });
  console.log(JSON.stringify(diag, null, 2));

  await page.screenshot({ path: path.join(OUT, 'painel_print.png'), fullPage: true });
  await browser.close();
})();
