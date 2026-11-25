# Publicação no GitHub Pages

Este diretório é a raiz publicada do projeto. Três arquivos existem só
para o Pages funcionar e não fazem parte do relatório.

## `index.html`

O Pages serve `index.html` quando alguém abre a raiz do site. O painel se
chama `painel.html`, então o `index.html` é uma página de entrada que
redireciona e oferece o link, para quem chegar pelo endereço curto não
ver um 404.

## `.nojekyll`

O Pages roda o Jekyll por padrão, que ignora arquivos e pastas começando
com `_` ou `.`. O painel é um HTML único com tudo embutido, mas o
`.nojekyll` garante que nenhum arquivo seja filtrado e evita a etapa de
build. Sem ele, o Pages também demora mais para publicar.

## `painel.html`

Gerado por `dashboard/gerar.py` a partir de `dashboard/molde.html` e dos
dados do banco. **Nunca editar à mão**: a próxima geração sobrescreve.

## Como publicar

```powershell
git push origin master
```

No GitHub: **Settings → Pages → Source: Deploy from a branch →
Branch: `master` → Folder: `/docs`**.

O site fica em `https://<usuario>.github.io/giro-comercio-local/`.

## O painel não depende da rede

O `painel.html` tem 1 MB com CSS, JavaScript e três fontes embutidos em
base64. Zero requisições externas, o que foi verificado por teste. Isso é
o que torna o Pages viável: não há API para fora, e a página funciona
igual aberta por duplo clique.
