# Publica o repositorio no GitHub e ativa o GitHub Pages.
#
# POR QUE ESTE SCRIPT EXISTE
# --------------------------
# Publicar envolve cinco passos que dependem um do outro, e tres deles
# falham em silencio se a ordem estiver errada: o Pages precisa do
# repositorio, o push precisa do remote, a URL depende do Pages compilar.
# Fazer isso a mao uma vez e aceitavel; fazer duas vezes e convite a
# publicar na branch errada.
#
# PRE-REQUISITO
# -------------
# Estar autenticado no gh:
#
#     gh auth login
#
# Escolha: GitHub.com -> HTTPS -> Login with a web browser.
#
# Uso:
#     pwsh scripts/publicar.ps1
#     pwsh scripts/publicar.ps1 -Nome outro-nome
#
# O script e idempotente: se o repositorio ja existir e ja estiver
# publicado, ele nao recria nada - so confere o estado e termina.

param(
    [string]$Nome = "giro-comercio-local",
    [string]$Dono = "",
    [switch]$Publico
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# ---------------------------------------------------------------------
# 1. Pre-condicoes
# ---------------------------------------------------------------------
$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('PATH', 'User')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "gh nao encontrado. Instale com: winget install --id GitHub.cli --exact"
    exit 1
}

gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nao autenticado. Rode primeiro:" -ForegroundColor Yellow
    Write-Host "    gh auth login" -ForegroundColor Cyan
    Write-Host "  GitHub.com -> HTTPS -> Login with a web browser" -ForegroundColor Gray
    exit 1
}

$usuario = (gh api user --jq .login)
if (-not $Dono) { $Dono = $usuario }
Write-Host "Conta: $usuario" -ForegroundColor Gray
Write-Host "Repositorio: $Dono/$Nome" -ForegroundColor Gray

# ---------------------------------------------------------------------
# 2. Checagens locais que evitam publicar algo quebrado
# ---------------------------------------------------------------------
if (-not (Test-Path "docs/index.html")) {
    Write-Error "docs/index.html ausente: o Pages serviria 404 na raiz."
    exit 1
}
if (-not (Test-Path "docs/.nojekyll")) {
    Write-Error "docs/.nojekyll ausente."
    exit 1
}
if (-not (Test-Path "docs/painel.html")) {
    Write-Error "docs/painel.html ausente: nada para publicar."
    exit 1
}

$sujo = git status --porcelain
if ($sujo) {
    Write-Host "Ha alteracoes nao commitadas:" -ForegroundColor Yellow
    $sujo | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    Write-Host "  Commit antes de publicar (o Pages publica o que esta no git)." -ForegroundColor Yellow
    exit 1
}

$branch = (git branch --show-current)
Write-Host "Branch: $branch" -ForegroundColor Gray

# ---------------------------------------------------------------------
# 3. Repositorio remoto
# ---------------------------------------------------------------------
$existe = gh repo view "$Dono/$Nome" --json name 2>$null
if ($LASTEXITCODE -eq 0 -and $existe) {
    Write-Host "Repositorio ja existe no GitHub." -ForegroundColor Gray
    $visibilidade = (gh repo view "$Dono/$Nome" --json visibility --jq .visibility)
    if ($visibilidade -ne "PUBLIC") {
        Write-Host "  Visibilidade atual: $visibilidade" -ForegroundColor Yellow
        Write-Host "  GitHub Pages em conta gratuita exige repositorio publico." -ForegroundColor Yellow
    }
} else {
    Write-Host "Criando repositorio publico..." -ForegroundColor Cyan
    # --source . e --remote origin: sem eles o push seguinte nao tem para
    # onde ir e o usuario precisa rodar git remote add a mao.
    gh repo create "$Dono/$Nome" --public --source . --remote origin `
        --description "Giro: previsao de estoque e sugestao de compra para comercio de bairro" `
        --disable-wiki
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Falha ao criar o repositorio."
        exit 1
    }
}

$remoto = (git remote get-url origin 2>$null)
if (-not $remoto) {
    git remote add origin "https://github.com/$Dono/$Nome.git"
}
Write-Host "Remote origin: $(git remote get-url origin)" -ForegroundColor Gray

# ---------------------------------------------------------------------
# 4. Push
# ---------------------------------------------------------------------
Write-Host "Enviando commits..." -ForegroundColor Cyan
git push -u origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Error "Push falhou. Verifique a autenticacao com: gh auth status"
    exit 1
}

# ---------------------------------------------------------------------
# 5. GitHub Pages
# ---------------------------------------------------------------------
Write-Host "Ativando GitHub Pages (branch $branch, pasta /docs)..." -ForegroundColor Cyan

# A API do Pages aceita a configuracao direto; se ja estiver ativa com a
# mesma origem, devolve 409 e isso nao e erro.
$corpo = @{
    source = @{
        branch = $branch
        path   = "/docs"
    }
} | ConvertTo-Json -Depth 4

$corpo | gh api -X POST "repos/$Dono/$Nome/pages" --input - 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    # Ja configurado: atualiza em vez de criar.
    $corpo | gh api -X PUT "repos/$Dono/$Nome/pages" --input - 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Nao foi possivel configurar o Pages pela API." -ForegroundColor Yellow
        Write-Host "  Faca a mao: Settings -> Pages -> Source: Deploy from a branch" -ForegroundColor Yellow
        Write-Host "             Branch: $branch   Folder: /docs" -ForegroundColor Yellow
    } else {
        Write-Host "  Configuracao do Pages atualizada." -ForegroundColor Gray
    }
} else {
    Write-Host "  Pages configurado." -ForegroundColor Gray
}

# ---------------------------------------------------------------------
# 6. Espera o primeiro build
# ---------------------------------------------------------------------
Write-Host "Aguardando o primeiro build..." -ForegroundColor Gray
$url = "https://$($Dono.ToLower()).github.io/$Nome/"
$pronto = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 10
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
        if ($r.StatusCode -eq 200 -and $r.Content -match 'Giro') {
            $pronto = $true
            break
        }
    } catch {
        Write-Host "  tentativa $i : ainda compilando" -ForegroundColor DarkGray
    }
}

Write-Host ""
if ($pronto) {
    Write-Host "Publicado: $url" -ForegroundColor Green
    Write-Host "Painel:    ${url}painel.html" -ForegroundColor Green
    Write-Host "Word:      ${url}relatorio-final.docx" -ForegroundColor Green
} else {
    Write-Host "Push concluido. O Pages ainda esta compilando." -ForegroundColor Yellow
    Write-Host "  Acompanhe em: https://github.com/$Dono/$Nome/actions" -ForegroundColor Gray
    Write-Host "  O endereco sera: $url" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Repositorio: https://github.com/$Dono/$Nome" -ForegroundColor Gray
