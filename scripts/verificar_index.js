// Verifica a pagina de entrada do GitHub Pages.
//
// POR QUE ESTE TESTE EXISTE
// -------------------------
// O index.html e a porta de entrada do site publicado. Um link quebrado
// ou um numero errado aqui e o primeiro (e talvez unico) contato de quem
// avalia o projeto. Tres coisas precisam valer:
//
//   1. os quatro links levam a arquivos que existem;
//   2. os quatro numeros batem com o painel;
//   3. a pagina nao rola na horizontal em 360px de largura.
//
// Uso: node scripts/verificar_index.js

const path = require('path');
const fs = require('fs');
const p = require('puppeteer-core');

const RAIZ = process.cwd();
const DOCS = path.join(RAIZ, 'docs');

function ok(nome, cond, detalhe) {
  console.log(`${cond ? 'OK  ' : 'FALHA'} ${nome} — ${detalhe}`);
  return cond;
}

(async () => {
  let falhas = 0;

  // ---- 1. arquivos alvo dos links ----
  const html = fs.readFileSync(path.join(DOCS, 'index.html'), 'utf8');
  const alvos = [...html.matchAll(/href="([^"#:]+)"/g)].map((m) => m[1]);
  for (const alvo of new Set(alvos)) {
    const existe = fs.existsSync(path.join(DOCS, alvo));
    if (!ok(`link ${alvo}`, existe, existe ? 'existe' : 'ARQUIVO AUSENTE')) falhas++;
  }

  const b = await p.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
    args: ['--allow-file-access-from-files'],
  });

  // ---- 2. renderizacao e numeros ----
  const pg = await b.newPage();
  const erros = [];
  pg.on('pageerror', (e) => erros.push(String(e)));
  pg.on('requestfailed', (r) => erros.push('request failed: ' + r.url()));
  const externos = [];
  pg.on('request', (r) => {
    if (!r.url().startsWith('file://')) externos.push(r.url());
  });

  await pg.setViewport({ width: 1366, height: 768 });
  await pg.goto('file:///' + path.join(DOCS, 'index.html').replace(/\\/g, '/'),
    { waitUntil: 'networkidle0' });

  if (!ok('sem erro de JavaScript', erros.length === 0, erros.join(' | ') || 'nenhum')) falhas++;
  if (!ok('zero requisicao externa', externos.length === 0,
    externos.join(' | ') || 'nenhuma')) falhas++;

  const d = await pg.evaluate(() => {
    const txt = (s) => document.querySelector(s)?.textContent?.trim() || '';
    const link = (s) => document.querySelector(s)?.getAttribute('href') || '';
    return {
      marca: txt('.marca'),
      titulo: txt('h1'),
      numeros: [...document.querySelectorAll('.numero__valor')].map((e) => e.textContent.trim()),
      rotulos: [...document.querySelectorAll('.numero__rotulo')].map((e) => e.textContent.trim()),
      botao: link('a.botao'),
      h1: document.querySelectorAll('h1').length,
      alturaBotao: Math.round(document.querySelector('a.botao').getBoundingClientRect().height),
    };
  });

  if (!ok('marca e Giro', d.marca === 'Giro', d.marca)) falhas++;
  if (!ok('um unico h1', d.h1 === 1, String(d.h1))) falhas++;
  if (!ok('h1 descreve a proposta', /comprar hoje/i.test(d.titulo), d.titulo.slice(0, 46))) falhas++;
  if (!ok('botao aponta para o painel', d.botao === 'painel.html', d.botao)) falhas++;
  if (!ok('botao com alvo de 44px', d.alturaBotao >= 44, d.alturaBotao + 'px')) falhas++;
  if (!ok('quatro numeros', d.numeros.length === 4, d.numeros.join(' · '))) falhas++;
  if (!ok('cada numero tem rotulo', d.rotulos.length === 4, d.rotulos.length + ' rotulos')) falhas++;

  // ---- 3. sem rolagem horizontal em telas estreitas ----
  for (const largura of [360, 414, 768]) {
    await pg.setViewport({ width: largura, height: 700 });
    await new Promise((r) => setTimeout(r, 120));
    const medida = await pg.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      view: window.innerWidth,
    }));
    const cabe = medida.scroll <= medida.view;
    if (!ok(`sem rolagem horizontal em ${largura}px`, cabe,
      `${medida.scroll} vs ${medida.view}`)) falhas++;
  }

  await b.close();

  console.log('');
  console.log(falhas === 0 ? 'INDEX OK' : `${falhas} FALHA(S)`);
  process.exit(falhas === 0 ? 0 : 1);
})();
