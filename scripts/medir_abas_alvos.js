/**
 * Mede contraste das abas e alvos de toque pequenos.
 *
 * Contraste calculado com a formula WCAG 2.1 (luminancia relativa), sobre
 * a cor de fundo efetiva do elemento - nao sobre branco assumido.
 */
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const RAIZ = path.resolve(__dirname, '..');
const PAINEL = 'file:///' + path.join(RAIZ, 'docs', 'painel.html').replace(/\\/g, '/');

(async () => {
  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: EDGE, headless: 'new',
    args: ['--allow-file-access-from-files'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });
  await page.goto(PAINEL, { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 900));

  const dados = await page.evaluate(() => {
    const lum = (c) => {
      const [r, g, b] = c.map((v) => {
        const x = v / 255;
        return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const parse = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const bgDe = (el) => {
      let n = el;
      while (n && n !== document.documentElement) {
        const c = getComputedStyle(n).backgroundColor;
        if (c && !c.includes('rgba(0, 0, 0, 0)')) return parse(c);
        n = n.parentElement;
      }
      return [241, 240, 234];
    };
    const ratio = (el) => {
      const st = getComputedStyle(el);
      const fg = parse(st.color);
      const bg = bgDe(el);
      const L1 = lum(fg);
      const L2 = lum(bg);
      return {
        px: parseFloat(st.fontSize),
        bold: parseInt(st.fontWeight, 10) >= 700,
        r: Math.round(((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)) * 100) / 100,
        cor: st.color,
      };
    };

    const abas = [...document.querySelectorAll('.modos__btn')].map((el) => ({
      texto: el.textContent.trim(),
      selecionada: el.getAttribute('aria-selected'),
      ...ratio(el),
    }));

    // Checkbox dentro de <label> conta pela area do label: o alvo real
    // de toque e o rotulo, nao o quadradinho de 18px. Sem esta excecao o
    // medidor acusa 106 falsos positivos.
    const pequenos = [...document.querySelectorAll('button, select, input, summary, .band__seg')]
      .map((el) => {
        let alvo = el;
        if (el.type === 'checkbox') {
          const lab = el.labels && el.labels[0];
          if (lab) alvo = lab;
        }
        const r = alvo.getBoundingClientRect();
        return {
          el: el.tagName + (el.id ? '#' + el.id.slice(0, 14) : '') + (alvo !== el ? ' (via label)' : ''),
          w: Math.round(r.width),
          h: Math.round(r.height),
        };
      })
      .filter((x) => x.w > 0 && (x.w < 44 || x.h < 44));

    return { abas, pequenos, totalPequenos: pequenos.length };
  });

  await browser.close();

  console.log('ABAS');
  for (const a of dados.abas) {
    console.log(`  ${a.texto.padEnd(20)} ${a.px}px  contraste ${a.r}  ${a.selecionada}`);
  }
  console.log('\nALVOS MENORES QUE 44x44');
  for (const p of dados.pequenos.slice(0, 15)) {
    console.log(`  ${p.el.padEnd(24)} ${p.w}x${p.h}`);
  }
  console.log(`  total: ${dados.totalPequenos}`);
})();
