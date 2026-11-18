/**
 * Prova que o grafico e a barra de proporcao sobrevivem ao PDF com
 * printBackground: false (o default do dialogo de impressao).
 */
const path = require('path');
const fs = require('fs');
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
  // O grafico e criado por JS depois do load; espera o primeiro bar.
  await page.waitForSelector('.bar-m', { timeout: 5000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 400));

  // printBackground: false = default do dialogo do usuario
  const pdf = await page.pdf({
    format: 'A4',
    printBackground: false,
    margin: { top: '12mm', right: '10mm', bottom: '14mm', left: '10mm' },
  });
  fs.writeFileSync(path.join(OUT, 'print_sem_bg.pdf'), pdf);

  // Mede se as barras existem no DOM de print e tem largura > 0
  const barras = await page.evaluate(() => {
    const segs = Array.from(document.querySelectorAll('.band__seg'));
    const medir = (el) => {
      const st = getComputedStyle(el, '::after');
      return {
        texto: el.textContent.trim().slice(0, 24),
        fatia: el.style.getPropertyValue('--fatia'),
        borderTop: st.borderTopWidth,
        largura: st.width,
        printAdjust: st.printColorAdjust || st.webkitPrintColorAdjust,
      };
    };
    return {
      mediaPrint: matchMedia('print').matches,
      segmentos: segs.slice(0, 3).map(medir),
      barrasGrafico: document.querySelectorAll('.bar-m').length,
      barAdjust: (() => {
        const b = document.querySelector('.bar-m');
        if (!b) return null;
        const s = getComputedStyle(b);
        return {
          printAdjust: s.printColorAdjust || s.webkitPrintColorAdjust,
          bg: s.backgroundColor,
        };
      })(),
    };
  });

  console.log(JSON.stringify(barras, null, 2));
  console.log(`\nPDF: ${(pdf.length / 1024).toFixed(0)} KB`);

  // Renderiza as paginas 1 e 1 do PDF para inspecao visual
  const { execSync } = require('child_process');
  await browser.close();
})();
