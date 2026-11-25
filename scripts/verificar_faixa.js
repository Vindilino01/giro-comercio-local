// O valor em R$ de cada fornecedor cabe dentro do segmento?
//
// POR QUE ESTE TESTE EXISTE
// -------------------------
// "Dinheiro cortado e pior que dinheiro pequeno" (comentario do molde).
// Era exatamente o que acontecia de 901px a 1280px: o @container que
// deveria encolher o valor estava declarado ANTES de `.band__value`, e
// como container query nao soma especificidade, o 14px posterior vencia.
// Resultado medido: 36px de texto cortado em 901px.
//
// A verificacao e por Range: mede a largura do texto renderizado e
// compara com a largura interna do segmento. getBoundingClientRect do
// elemento nao serve, porque com overflow:hidden ele devolve a caixa
// recortada, nao o texto.
//
// Uso: node scripts/verificar_faixa.js

const path = require('path');
const p = require('puppeteer-core');

const LARGURAS = [901, 960, 1024, 1100, 1200, 1280, 1366, 1600];

(async () => {
  const b = await p.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
    args: ['--allow-file-access-from-files'],
  });

  let falhas = 0;

  for (const w of LARGURAS) {
    const pg = await b.newPage();
    await pg.setViewport({ width: w, height: 800 });
    await pg.goto('file:///' + path.join(process.cwd(), 'docs', 'painel.html').replace(/\\/g, '/'),
      { waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 500));

    const d = await pg.evaluate(() => {
      /* Maior palavra de um texto cabe na largura dada? Usado para
         validar a quebra em duas linhas: se "R$" e "22.446,34" cabem
         separados, a quebra e legivel. Se qualquer pedaco nao cabe, o
         numero foi partido ou cortado. */
      function maiorPalavraCabe(texto, largura, estiloOrigem) {
        const palavras = String(texto).trim().split(/\s+/);
        for (const palavra of palavras) {
          const s = document.createElement('span');
          s.textContent = palavra;
          s.style.cssText = [
            'position:absolute', 'visibility:hidden', 'white-space:nowrap',
            'left:-9999px', 'top:0',
            `font-family:${estiloOrigem.fontFamily}`,
            `font-size:${estiloOrigem.fontSize}`,
            `font-weight:${estiloOrigem.fontWeight}`,
            `letter-spacing:${estiloOrigem.letterSpacing}`,
          ].join(';');
          document.body.appendChild(s);
          const w = s.getBoundingClientRect().width;
          s.remove();
          if (w > largura + 1) return false;
        }
        return true;
      }

      const out = [];
      for (const seg of document.querySelectorAll('.band__seg')) {
        const val = seg.querySelector('.band__value');
        if (!val) continue;
        const cs = getComputedStyle(seg);

        /* Medicao a prova de recorte.

           TrES tentativas anteriores falharam por motivos diferentes:
             1. getBoundingClientRect(val) devolve a caixa, nao o texto;
             2. scrollWidth com overflow:hidden devolve a largura ja
                recortada, entao nunca acusa;
             3. Range sobre conteudo com white-space:normal devolve a
                caixa da LINHA, que e a largura disponivel - tambem
                nunca acusa.

           O caminho que funciona: medir o texto numa unica linha, numa
           copia invisivel fora do fluxo, e comparar com o espaco interno
           do segmento. E a unica medida que nao depende de como o
           navegador esta recortando o original. */
        const interno = seg.clientWidth
          - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);

        const sonda = document.createElement('span');
        sonda.textContent = val.textContent;
        const vs = getComputedStyle(val);
        sonda.style.cssText = [
          'position:absolute', 'visibility:hidden', 'white-space:nowrap',
          'left:-9999px', 'top:0',
          `font-family:${vs.fontFamily}`, `font-size:${vs.fontSize}`,
          `font-weight:${vs.fontWeight}`, `letter-spacing:${vs.letterSpacing}`,
          `font-variant-numeric:${vs.fontVariantNumeric}`,
        ].join(';');
        document.body.appendChild(sonda);
        const larguraUmaLinha = sonda.getBoundingClientRect().width;
        sonda.remove();

        // Quantas linhas o valor ocupa hoje (para saber se quebrou).
        const alturaVal = val.getBoundingClientRect().height;
        const alturaLinha = parseFloat(vs.lineHeight) || parseFloat(vs.fontSize) * 1.2;
        const linhas = Math.max(1, Math.round(alturaVal / alturaLinha));

        out.push({
          valor: (val.textContent || '').trim(),
          interno: Math.round(interno),
          larguraUmaLinha: Math.round(larguraUmaLinha),
          linhas,
          /* Aprovado quando:
             - cabe numa linha (o caso normal), OU
             - quebra em 2+ linhas E a maior palavra isolada cabe. Se a
               quebra so acontece no espaco depois de "R$", cada linha e
               legivel; se parte um numero, nao e. */
          estoura: larguraUmaLinha > interno + 1
            ? !maiorPalavraCabe(val.textContent, interno, vs)
            : false,
          fonte: vs.fontSize,
        });
      }
      return out;
    });

    const cortados = d.filter((x) => x.estoura);
    const ok = cortados.length === 0;
    if (!ok) falhas++;

    console.log(`${w}px: ${ok ? 'OK  ' : 'FALHA'} ${cortados.length} nao cabem` +
      (cortados.length
        ? '\n        ' + cortados.map((x) =>
            `"${x.valor}" precisa ${x.larguraUmaLinha}px, tem ${x.interno}px (${x.fonte}, ${x.linhas} linha${x.linhas > 1 ? 's' : ''})`).join('\n        ')
        : ` | fontes ${[...new Set(d.map((x) => x.fonte))].join(' ')}`));

    await pg.close();
  }

  await b.close();
  console.log('');
  console.log(falhas === 0 ? 'FAIXA OK' : `${falhas} LARGURA(S) COM CORTE`);
  process.exit(falhas === 0 ? 0 : 1);
})();
