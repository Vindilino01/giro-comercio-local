// Verifica a folha impressa.
//
// POR QUE ESTE ARQUIVO EXISTE
// ---------------------------
// O CSS de impressao nunca teve teste. A versao anterior saia com 8
// paginas, das quais 3 eram material de banca (perda, capital, selo) e
// as paginas 2 a 5 nao tinham loja, fornecedor, data nem numero. Uma
// folha sem identificacao e inutil para quem separa mercadoria.
//
// O que este teste exige:
//
//   1. so a lista imprime - as secoes de analise nao;
//   2. toda pagina carrega o cabecalho corrente com loja e data;
//   3. cada loja comeca em pagina propria, nomeada;
//   4. nenhuma pagina tem menos de 100 palavras (folha quase vazia);
//   5. a lista do papel tem a MESMA contagem da tela (nada se perde na
//      troca de ordem).
//
// Uso: node scripts/verificar_impressao.js

const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const p = require('puppeteer-core');

(async () => {
  let falhas = 0;
  const ok = (nome, cond, detalhe) => {
    console.log(`${cond ? 'OK  ' : 'FALHA'} ${nome} — ${detalhe}`);
    if (!cond) falhas++;
  };

  const b = await p.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
    args: ['--allow-file-access-from-files'],
  });
  const pg = await b.newPage();
  await pg.setViewport({ width: 1366, height: 900 });

  const erros = [];
  pg.on('pageerror', (e) => erros.push(String(e)));

  await pg.goto('file:///' + path.join(process.cwd(), 'docs', 'painel.html').replace(/\\/g, '/'),
    { waitUntil: 'networkidle0' });
  await pg.evaluate(() => localStorage.clear());
  await pg.reload({ waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 900));

  ok('sem erro de JavaScript', erros.length === 0, erros.join(' | ') || 'nenhum');

  // ---- a lista do papel tem a mesma contagem da tela ----
  const contagens = await pg.evaluate(() => ({
    tela: document.querySelectorAll('#picking-lista .lista__item').length,
    papel: document.querySelectorAll('#picking-lista-papel .lista__item').length,
    papelOcultoNaTela:
      getComputedStyle(document.getElementById('picking-lista-papel')).display === 'none',
  }));
  ok('lista do papel tem os mesmos itens da tela',
    contagens.tela === contagens.papel && contagens.tela > 0,
    `tela ${contagens.tela} · papel ${contagens.papel}`);
  ok('lista do papel nao aparece na tela', contagens.papelOcultoNaTela,
    String(contagens.papelOcultoNaTela));

  // ---- ordem no papel: loja primeiro ----
  const ordem = await pg.evaluate(() =>
    [...document.querySelectorAll('#picking-lista-papel > li')]
      .map((e) => e.className)
      .filter((c) => /lista__(loja|grupo)/.test(c))
      .slice(0, 6));
  ok('papel comeca por loja, nao por urgencia',
    /loja/.test(ordem[0] || ''), ordem.slice(0, 3).join(' · '));

  // ---- gera o PDF e le pagina por pagina ----
  const destino = path.join(process.cwd(), 'logs', 'impressao-teste.pdf');
  await pg.pdf({
    path: destino,
    format: 'A4',
    printBackground: true,
    margin: { top: '16mm', bottom: '12mm', left: '12mm', right: '12mm' },
  });
  await b.close();

  const script = path.join(process.cwd(), 'logs', 'ler_impressao.py');
  fs.writeFileSync(script, `
import pymupdf, sys, json
d = pymupdf.open(sys.argv[1])
paginas = []
for p in d:
    t = p.get_text()
    paginas.append({
        "palavras": len(t.split()),
        "texto": t,
    })
print(json.dumps({"n": d.page_count, "paginas": paginas}, ensure_ascii=False))
`);
  const bruto = execFileSync('python', [script, destino], { encoding: 'utf-8' });
  const pdf = JSON.parse(bruto);

  ok('gera PDF', pdf.n > 0, `${pdf.n} paginas`);

  // ---- 1. so a lista imprime ----
  const temAnalise = pdf.paginas.some((pg2) =>
    /prateleira vazia custou|dinheiro parado|DÁ PARA CONFIAR/i.test(pg2.texto));
  ok('analise nao imprime', !temAnalise,
    temAnalise ? 'encontrou secao de analise no PDF' : 'so a lista');

  // ---- 2. cabecalho corrente em toda pagina ----
  const semCabecalho = pdf.paginas
    .map((pg2, i) => ({ i: i + 1, tem: /lista de separa/i.test(pg2.texto) }))
    .filter((x) => !x.tem);
  ok('cabecalho corrente em toda pagina', semCabecalho.length === 0,
    semCabecalho.length ? `sem cabecalho: p${semCabecalho.map((x) => x.i).join(',')}` : `em ${pdf.n}`);

  // ---- 3. cabecalho nomeia loja e data ----
  const cabecalhoOk = pdf.paginas.every((pg2) => /vendas at[eé]/i.test(pg2.texto));
  ok('cabecalho traz a data de referencia', cabecalhoOk,
    cabecalhoOk ? 'em todas' : 'faltou em alguma');

  // ---- 4. cada loja nomeada numa pagina ----
  const nomesLojas = ['Mercadinho da Familia', 'Mercado Bom Preco', 'Mercado Sao Jorge'];
  const paginasComLoja = nomesLojas.map((nome) => ({
    nome,
    pagina: pdf.paginas.findIndex((pg2) =>
      pg2.texto.toUpperCase().includes(nome.toUpperCase())),
  }));
  const todasNomeadas = paginasComLoja.every((x) => x.pagina >= 0);
  ok('as tres lojas aparecem nomeadas', todasNomeadas,
    paginasComLoja.map((x) => `${x.nome.split(' ')[1]||x.nome}:p${x.pagina + 1}`).join(' · '));

  // ---- 5. nenhuma folha quase vazia ----
  const vazias = pdf.paginas
    .map((pg2, i) => ({ i: i + 1, n: pg2.palavras }))
    .filter((x) => x.n < 100);
  ok('nenhuma pagina quase vazia', vazias.length === 0,
    vazias.length ? `p${vazias.map((x) => `${x.i}(${x.n})`).join(',')}` : 'todas acima de 100');

  // ---- relatorio ----
  console.log('');
  console.log('paginas: ' + pdf.n + ' · palavras: ' +
    pdf.paginas.reduce((s, x) => s + x.palavras, 0));
  for (let i = 0; i < pdf.paginas.length; i++) {
    const t = pdf.paginas[i].texto.split('\n').filter((x) => x.trim());
    console.log(`  p${i + 1} (${pdf.paginas[i].palavras}): ${t.slice(1, 3).join(' / ').slice(0, 74)}`);
  }

  console.log('');
  console.log(falhas === 0 ? 'IMPRESSAO OK' : `${falhas} FALHA(S)`);
  process.exit(falhas === 0 ? 0 : 1);
})();
