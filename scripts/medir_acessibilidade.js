// Contraste e teclado medidos no navegador, nao lidos do CSS.
//
// POR QUE ESTE ARQUIVO EXISTE
// ---------------------------
// O DESIGN.md afirma "contraste minimo 5,01:1 em 2.020 elementos". Uma
// afirmacao dessas so vale se for reexecutavel. Este script refaz a
// medicao: percorre todo elemento com texto, resolve o fundo efetivo
// subindo a arvore (porque a maioria dos fundos e transparente), e
// calcula o racio WCAG.
//
// Tambem percorre o documento por Tab e verifica se cada parada tem anel
// de foco visivel - um controle focavel sem anel e um controle que o
// usuario de teclado nao consegue localizar.
//
// Uso: node scripts/medir_acessibilidade.js

const path = require('path');
const p = require('puppeteer-core');

const LARGURAS = [1366, 768, 390];

function contraste(l1, l2) {
  const a = (l1 + 0.05) / (l2 + 0.05);
  return a < 1 ? 1 / a : a;
}

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
  await new Promise((r) => setTimeout(r, 900));

  // ---- 1. contraste ----
  const cores = await pg.evaluate(() => {
    function rgb(s) {
      const m = s.match(/[\d.]+/g);
      if (!m) return null;
      return [Number(m[0]), Number(m[1]), Number(m[2]), m[3] === undefined ? 1 : Number(m[3])];
    }
    function lum([r, g, b]) {
      const f = (v) => {
        const x = v / 255;
        return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    }

    const out = [];
    for (const el of document.querySelectorAll('body *')) {
      const txt = (el.childNodes.length
        ? [...el.childNodes].filter((n) => n.nodeType === 3)
            .map((n) => n.textContent.trim()).join('')
        : '');
      if (!txt) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      if (el.offsetParent === null && cs.position !== 'fixed') continue;

      const fg = rgb(cs.color);
      if (!fg) continue;

      // sobe a arvore ate achar fundo opaco
      let node = el;
      let bg = null;
      while (node && node !== document.documentElement) {
        const c = rgb(getComputedStyle(node).backgroundColor);
        if (c && c[3] > 0.99) { bg = c; break; }
        node = node.parentElement;
      }
      if (!bg) bg = [241, 240, 234, 1];

      const size = parseFloat(cs.fontSize);
      const bold = Number(cs.fontWeight) >= 700;
      out.push({
        txt: txt.slice(0, 34),
        fg: lum(fg),
        bg: lum(bg),
        size,
        bold,
        cls: (el.className || '').toString().slice(0, 30),
        tag: el.tagName,
      });
    }
    return out;
  });

  let abaixo = 0;
  let pior = { r: 99, txt: '' };
  for (const c of cores) {
    const r = contraste(c.fg, c.bg);
    const minimo = (c.size >= 24 || (c.size >= 18.66 && c.bold)) ? 3 : 4.5;
    if (r < minimo) {
      abaixo++;
      if (r < pior.r) pior = { r, txt: `${c.tag}.${c.cls} "${c.txt}"` };
      if (abaixo <= 8) {
        console.log(`  BAIXO ${r.toFixed(2)}:1 ${c.tag}.${c.cls} "${c.txt}" (${c.size}px)`);
      }
    }
  }
  console.log(`contraste: ${cores.length} elementos com texto, ${abaixo} abaixo do minimo`);
  if (abaixo) console.log(`  pior: ${pior.r.toFixed(2)}:1 em ${pior.txt}`);

  // ---- 2. teclado ----
  const paradas = [];
  await pg.evaluate(() => document.body.focus());
  for (let i = 0; i < 45; i++) {
    await pg.keyboard.press('Tab');
    const info = await pg.evaluate(() => {
      const a = document.activeElement;
      if (!a || a === document.body) return { fim: true };
      const cs = getComputedStyle(a);

      /* O alvo de toque real nao e sempre a caixa do elemento.
         Um checkbox de 18x18 dentro de um <label> de 533x43 tem alvo de
         533x43: clicar em qualquer ponto do texto marca. Medir a caixa do
         input acusava 32 falsos positivos de "alvo pequeno" na lista de
         separacao, quando o alvo real e a linha inteira. */
      let alvo = a.getBoundingClientRect();
      if (a.tagName === "INPUT" && a.labels && a.labels.length) {
        const l = a.labels[0].getBoundingClientRect();
        if (l.width * l.height > alvo.width * alvo.height) alvo = l;
      }

      // Nome acessivel: aria-label, <label>, ou texto. `a.value` de um
      // checkbox e "on" e nao nomeia nada - era o que aparecia no relatorio.
      let nome = a.getAttribute("aria-label");
      if (!nome && a.labels && a.labels.length) nome = a.labels[0].textContent;
      if (!nome && a.tagName !== "INPUT") nome = a.textContent;
      if (!nome) nome = a.getAttribute("title") || a.id;

      return {
        tag: a.tagName,
        nome: String(nome || "").trim().slice(0, 34),
        anel: parseFloat(cs.outlineWidth) > 0 && cs.outlineStyle !== "none",
        largura: Math.round(alvo.width),
        altura: Math.round(alvo.height),
      };
    });
    if (info.fim) break;
    paradas.push(info);
  }

  const semAnel = paradas.filter((x) => !x.anel);
  const pequenos = paradas.filter((x) => x.altura < 44 || x.largura < 44);
  console.log(`teclado: ${paradas.length} paradas de Tab`);
  console.log(`  sem anel de foco: ${semAnel.length}`);
  for (const s of semAnel.slice(0, 6)) console.log(`    ${s.tag} "${s.nome}"`);
  console.log(`  alvo menor que 44x44: ${pequenos.length}`);
  for (const s of pequenos.slice(0, 8)) {
    console.log(`    ${s.tag} "${s.nome}" ${s.largura}x${s.altura}`);
  }

  // ---- 3. overflow horizontal em varias larguras ----
  console.log('overflow horizontal:');
  for (const w of LARGURAS) {
    await pg.setViewport({ width: w, height: 800 });
    await new Promise((r) => setTimeout(r, 150));
    const m = await pg.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      view: window.innerWidth,
    }));
    console.log(`  ${w}px: ${m.scroll} vs ${m.view} ${m.scroll <= m.view ? 'OK' : 'ESTOURA'}`);
  }

  await b.close();
})();
