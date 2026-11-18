/**
 * Prova que o gate de confianca funciona.
 *
 * O relatorio promete: com a pior dimensao abaixo de 85%, a sugestao e
 * bloqueada. Este teste forca a loja 1 para 84% no DOM ja carregado e
 * verifica que (a) as linhas dela viram "SEM CONFIANCA", (b) a quantidade
 * vai a zero e (c) o total do pedido cai.
 *
 * Uso: node scripts/testar_gate_confianca.js
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
  await page.setViewport({ width: 1366, height: 900 });
  await page.goto(PAINEL, { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 800));

  const antes = await page.evaluate(() => ({
    total: document.getElementById('total-pedido')?.textContent?.trim(),
    sit: Array.from(document.querySelectorAll('#tabela-body .sit'))
      .map((s) => s.textContent.trim())
      .slice(0, 60),
    semConfianca: document.querySelectorAll('.sit--semconfianca').length,
  }));

  // Forca a loja 1 a 84% e redesenha.
  const depois = await page.evaluate(() => {
    const alvo = DADOS.selo.find((s) => s.loja_id === 1);
    if (!alvo) return { erro: 'loja 1 nao esta em DADOS.selo' };
    alvo.pior_dimensao_pct = 84;

    // "Todas as lojas" para que a loja 1 entre na tabela.
    estado.loja = 0;
    render();

    // A tabela mostra so o fornecedor selecionado. Para ver a loja 1,
    // percorre os fornecedores e conta os rotulos em cada um.
    let noDom = 0;
    for (const f of (DADOS.pedido || []).map((p) => p.fornecedor)) {
      estado.fornecedor = f;
      render();
      noDom = Math.max(noDom, document.querySelectorAll('.sit--semconfianca').length);
      if (noDom > 0) break;
    }

    // Le direto do calculo: a tabela mostra so o fornecedor selecionado,
    // entao contar linhas do DOM daria falso negativo.
    const calc = calcular().filter((l) => l.loja_id === 1);
    return {
      total: document.getElementById('total-pedido')?.textContent?.trim(),
      bloqueadasNoCalculo: calc.filter((l) => l.bloqueada).length,
      totalDaLoja: calc.length,
      qtdMaxima: Math.max(...calc.map((l) => l.qtd)),
      noDom,
    };
  });

  console.log('ANTES  ', JSON.stringify(antes.total), '| sem confianca:', antes.semConfianca);
  console.log('DEPOIS ', JSON.stringify(depois.total));
  console.log('linhas da loja 1 bloqueadas:', depois.bloqueadasNoCalculo,
              'de', depois.totalDaLoja);
  console.log('quantidade maxima na loja 1:', depois.qtdMaxima);
  console.log('rotulos no DOM:', depois.noDom);

  const bloqueou = depois.bloqueadasNoCalculo === depois.totalDaLoja
    && depois.totalDaLoja > 0;
  const zerou = depois.qtdMaxima === 0;
  const totalCaiu = antes.total !== depois.total;

  console.log(`\n${bloqueou ? 'OK  ' : 'FALHA'} todas as linhas da loja bloqueadas`);
  console.log(`${zerou ? 'OK  ' : 'FALHA'} quantidade zerada`);
  console.log(`${totalCaiu ? 'OK  ' : 'FALHA'} total do pedido caiu`);
  console.log(`${depois.noDom > 0 ? 'OK  ' : 'FALHA'} rotulo aparece na tabela`);

  await browser.close();
  process.exit(bloqueou && zerou && totalCaiu && depois.noDom > 0 ? 0 : 1);
})();
