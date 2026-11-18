/**
 * Conta o jargao que sobrou no texto visivel do painel.
 *
 * O texto e lido do DOM renderizado, nao do HTML: assim pegamos o que o
 * motor de templates injeta (saida do JS), e nao o que esta no molde.
 */
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const RAIZ = path.resolve(__dirname, '..');
const PAINEL = 'file:///' + path.join(RAIZ, 'docs', 'painel.html').replace(/\\/g, '/');

const TERMOS = [
  'SKU', 'lead time', 'ruptura', 'cobertura', 'demanda', 'estoque de segur',
  'nivel de servico', 'nível de serviço', 'ponto de pedido', 'receita perdida',
  'benchmark', 'recall', 'precisao', 'precisão', 'acuracidade', 'dimensao',
  'dimensão', 'quarentena', 'dataset', 'sintetico', 'sintético', 'trade-off',
  'sortimento', 'gondola', 'gôndola', 'F1 ', 'p-valor', 'sigma', 'z 1,65',
];

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

  const texto = await page.evaluate(() => document.body.innerText);
  await browser.close();

  const baixo = texto.toLowerCase();
  let achados = 0;
  console.log('ocorrencias  termo');
  console.log('-'.repeat(40));
  for (const t of TERMOS) {
    const alvo = t.toLowerCase();
    let n = 0;
    let i = baixo.indexOf(alvo);
    while (i >= 0) { n += 1; i = baixo.indexOf(alvo, i + 1); }
    if (n) {
      console.log(String(n).padStart(9), '  ', t);
      achados += n;
    }
  }
  console.log('-'.repeat(40));
  console.log('total:', achados);
  console.log('palavras visiveis:', baixo.split(/\s+/).length);
})();
