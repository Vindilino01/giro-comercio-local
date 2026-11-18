/** Lista elementos com font-size 11px e o texto que carregam. */
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const SITE = 'file:///' + path.resolve(__dirname, '..', 'dashboard', 'site', 'index.html')
  .replace(/\\/g, '/');

(async () => {
  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: EDGE, headless: 'new', args: ['--allow-file-access-from-files'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000 });
  await page.goto(SITE, { waitUntil: 'load' });
  const out = await page.evaluate(() => {
    const vistos = new Map();
    document.querySelectorAll('body *').forEach((el) => {
      const st = getComputedStyle(el);
      if (parseFloat(st.fontSize) !== 11) return;
      const texto = (el.textContent || '').trim().slice(0, 48);
      if (!texto) return;
      const chave = el.tagName.toLowerCase() + '.' + (el.className || '');
      const item = vistos.get(chave) || { chave, n: 0, amostra: texto, fonte: st.fontFamily.slice(0, 28) };
      item.n += 1;
      vistos.set(chave, item);
    });
    return Array.from(vistos.values()).sort((a, b) => b.n - a.n);
  });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();
