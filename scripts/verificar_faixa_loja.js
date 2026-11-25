// A faixa funciona com UMA loja selecionada?
//
// POR QUE ESTE TESTE EXISTE
// -------------------------
// scripts/verificar_faixa.js mede so o escopo padrao ("todas as lojas").
// O Assessment A apontou que, com uma loja so, os seis fornecedores
// continuam existindo mas o valor total cai para ~R$ 50 mil - as fatias
// encolhem, e o menor segmento pode ficar estreito demais para o valor.
//
// Medido por ele em 1366px: ultimo segmento de 55,8px e "R$ 4.194,65"
// transbordando 30,5px para fora do segmento.
//
// Este teste cobre o caso que faltava: cada loja, e o escopo da rede.
//
// Uso: node scripts/verificar_faixa_loja.js

const path = require('path');
const p = require('puppeteer-core');

const LARGURAS = [901, 1024, 1100, 1280, 1366, 1600];

(async () => {
  const b = await p.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
    args: ['--allow-file-access-from-files'],
  });

  let falhas = 0;

  for (const w of LARGURAS) {
    const pg = await b.newPage();
    await pg.setViewport({ width: w, height: 900 });
    await pg.goto('file:///' + path.join(process.cwd(), 'docs', 'painel.html').replace(/\\/g, '/'),
      { waitUntil: 'networkidle0' });
    await pg.evaluate(() => localStorage.clear());
    await pg.reload({ waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 600));

    // lojas disponiveis
    const lojas = await pg.evaluate(() =>
      [...document.querySelectorAll('#loja option')].map((o) => o.value).filter((v) => v !== '0'));

    const escopos = ['0', ...lojas];
    const linhas = [];

    for (const loja of escopos) {
      await pg.evaluate((v) => {
        const sel = document.getElementById('loja');
        sel.value = v;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }, loja);
      await new Promise((r) => setTimeout(r, 450));

      const d = await pg.evaluate(() => {
        /* A sonda e criada uma vez e reutilizada: criar e remover um span
           por palavra, em 6 segmentos x 4 escopos x 6 larguras, custava
           segundos de teste. */
        const sonda = document.createElement("span");
        sonda.style.cssText = "position:absolute;visibility:hidden;"
          + "white-space:nowrap;left:-9999px;top:0;pointer-events:none";
        document.body.appendChild(sonda);

        function larguraDe(texto, est) {
          sonda.textContent = texto;
          sonda.style.fontFamily = est.fontFamily;
          sonda.style.fontSize = est.fontSize;
          sonda.style.fontWeight = est.fontWeight;
          sonda.style.letterSpacing = est.letterSpacing;
          sonda.style.fontVariantNumeric = est.fontVariantNumeric;
          return sonda.getBoundingClientRect().width;
        }

        const segs = [...document.querySelectorAll(".band__seg")];
        const out = [];
        for (const seg of segs) {
          const val = seg.querySelector(".band__value");
          if (!val) continue;
          const cs = getComputedStyle(seg);
          const vs = getComputedStyle(val);
          const interno = seg.clientWidth
            - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);

          /* O valor na tela pode estar ABREVIADO de proposito ("4 mil").
             O teste tem que julgar o que esta renderizado, nao o valor
             completo - senao acusa corte onde houve abreviacao
             deliberada. O que nao pode acontecer e o texto que esta na
             tela nao caber. */
          const naTela = (val.textContent || "").trim();
          const precisa = larguraDe(naTela, vs);
          const estoura = precisa > interno + 1;

          out.push({
            valor: naTela,
            interno: Math.round(interno),
            precisa: Math.round(precisa * 10) / 10,
            estoura,
          });
        }

        sonda.remove();
        return { n: segs.length, segs: out };
      });

      const ruins = d.segs.filter((x) => x.estoura);
      if (ruins.length) falhas++;
      linhas.push({
        loja,
        n: d.n,
        ruins,
        pior: d.segs.length
          ? d.segs.reduce((a, x) => (x.interno < a.interno ? x : a), d.segs[0])
          : null,
      });
    }

    const problemas = linhas.filter((l) => l.ruins.length);
    const ok = problemas.length === 0;
    console.log(`${w}px: ${ok ? 'OK  ' : 'FALHA'} ` +
      (ok
        ? `${linhas.length} escopos, menor segmento ${Math.min(...linhas.map((l) => l.pior ? l.pior.interno : 999))}px`
        : problemas.map((l) =>
            `loja ${l.loja}: ${l.ruins.length} cortados ` +
            `(${l.ruins.map((r) => `"${r.valor}" precisa ${r.precisa}px, tem ${r.interno}px`).join('; ')})`).join(' | ')));

    await pg.close();
  }

  await b.close();
  console.log('');
  console.log(falhas === 0 ? 'FAIXA (POR LOJA) OK' : `${falhas} LARGURA(S) COM CORTE`);
  process.exit(falhas === 0 ? 0 : 1);
})();
