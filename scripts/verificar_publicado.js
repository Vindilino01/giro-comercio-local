// Verifica o painel na URL publicada do GitHub Pages.
//
// POR QUE ESTE TESTE EXISTE
// -------------------------
// Os testes locais abrem o arquivo por file://. No Pages ele vem por
// HTTPS, com outro MIME e outra origem. Tres coisas podem quebrar so ali:
//
//   1. o painel depende de algo que so funciona em file://;
//   2. o Pages injeta algo que dispara requisicao externa (o teste local
//      de "zero requisicao externa" nao cobriria);
//   3. o certificado ou o redirecionamento atrasam o carregamento.
//
// Uso: node scripts/verificar_publicado.js [url]

const p = require('puppeteer-core');

const URL_BASE = process.argv[2] || 'https://vindilino01.github.io/giro-comercio-local/';

function ok(nome, cond, detalhe) {
  console.log(`${cond ? 'OK  ' : 'FALHA'} ${nome} — ${detalhe}`);
  return cond;
}

(async () => {
  let falhas = 0;

  const b = await p.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
  });

  const pg = await b.newPage();
  await pg.setViewport({ width: 1366, height: 768 });

  const erros = [];
  const externos = [];
  const falhasRede = [];
  pg.on('pageerror', (e) => erros.push(String(e)));
  pg.on('requestfailed', (r) => falhasRede.push(r.url() + ' :: ' + (r.failure() || {}).errorText));
  pg.on('request', (r) => {
    const u = r.url();
    if (!u.startsWith(URL_BASE) && !u.startsWith('data:')) externos.push(u);
  });

  // ---- 1. raiz: redireciona para o painel? ----
  const resp = await pg.goto(URL_BASE, { waitUntil: 'networkidle0', timeout: 60000 });
  if (!ok('raiz responde 200', resp.status() === 200, String(resp.status()))) falhas++;

  const raiz = await pg.evaluate(() => ({
    titulo: document.title,
    temBotao: !!document.querySelector('a.botao'),
    hrefBotao: document.querySelector('a.botao')?.getAttribute('href') || '',
    marca: document.querySelector('.marca')?.textContent?.trim() || '',
  }));
  if (!ok('raiz e a pagina de entrada', raiz.marca === 'Giro', raiz.marca || 'sem marca')) falhas++;
  if (!ok('botao leva ao painel', raiz.hrefBotao === 'painel.html', raiz.hrefBotao)) falhas++;

  // ---- 2. clicar no botao chega no painel de verdade ----
  await Promise.all([
    pg.waitForNavigation({ waitUntil: 'networkidle0', timeout: 60000 }),
    pg.click('a.botao'),
  ]);

  const painel = await pg.evaluate(() => ({
    url: location.pathname,
    h1: document.querySelectorAll('h1').length,
    total: document.querySelector('#total-pedido')?.textContent?.trim() || '',
    linhas: document.querySelectorAll('#tabela-body tr').length,
    barras: document.querySelectorAll('.bar-m').length,
    perda: document.querySelector('#perda-receita')?.textContent?.trim() || '',
    titulo: document.title,
  }));

  if (!ok('chegou em painel.html', painel.url.endsWith('/painel.html'), painel.url)) falhas++;
  if (!ok('painel renderizou o total', /R\$/.test(painel.total), painel.total)) falhas++;
  if (!ok('tabela populada', painel.linhas > 100, painel.linhas + ' linhas')) falhas++;
  if (!ok('grafico renderizou', painel.barras === 24, painel.barras + ' barras')) falhas++;
  if (!ok('perda calculada', /R\$/.test(painel.perda), painel.perda)) falhas++;
  if (!ok('um unico h1', painel.h1 === 1, String(painel.h1))) falhas++;

  // ---- 3. rede ----
  if (!ok('sem erro de JavaScript', erros.length === 0, erros.join(' | ') || 'nenhum')) falhas++;
  if (!ok('sem requisicao externa', externos.length === 0,
    externos.join(' | ') || 'nenhuma')) falhas++;
  if (!ok('sem falha de rede', falhasRede.length === 0,
    falhasRede.join(' | ') || 'nenhuma')) falhas++;

  // ---- 4. o Word publicado abre? ----
  const docx = await pg.evaluate(async (base) => {
    const r = await fetch(base + 'relatorio-final.docx', { method: 'HEAD' });
    return { status: r.status, tipo: r.headers.get('content-type') || '', tamanho: r.headers.get('content-length') };
  }, URL_BASE);
  if (!ok('Word responde 200', docx.status === 200, String(docx.status))) falhas++;
  if (!ok('Word com MIME de docx', /wordprocessingml/.test(docx.tipo), docx.tipo)) falhas++;
  if (!ok('Word com tamanho plausivel', Number(docx.tamanho) > 100000,
    docx.tamanho ? Math.round(Number(docx.tamanho) / 1024) + ' KB' : 'sem tamanho')) falhas++;

  await pg.screenshot({ path: 'logs/shots/publicado_painel.png', fullPage: false });

  await b.close();

  console.log('');
  console.log(falhas === 0 ? 'PUBLICADO OK' : `${falhas} FALHA(S)`);
  process.exit(falhas === 0 ? 0 : 1);
})();
