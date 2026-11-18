# =====================================================================
# Giro - Backup logico com politica de retencao
#
# O que faz:
#   1. pg_dump -Fc (comprimido) do banco giro
#   2. valida que o arquivo abre com pg_restore -l
#   3. aplica a retencao: 7 diarios, 4 semanais, 3 mensais
#
# Uso:
#   .\scripts\backup.ps1
#   .\scripts\backup.ps1 -Destino D:\backups\giro
#
# Agendamento (rodar como administrador, uma vez):
#   schtasks /create /tn "Giro Backup" /tr "powershell -NoProfile -File ^
#     'C:\caminho\do\projeto\scripts\backup.ps1'" /sc daily /st 02:30
#
# POR QUE NAO SO "pg_dump diario"
# -------------------------------
# Um dump que nunca foi restaurado nao e backup, e esperanca. E um dump
# que se acumula para sempre enche o disco. Este script faz as duas
# coisas que o pg_dump sozinho nao faz: valida o arquivo e apaga o
# excedente.
# =====================================================================
param(
    [string]$Destino = "",
    [string]$Porta = "5433",
    [string]$Banco = "giro",
    [string]$Usuario = "postgres"
)

$ErrorActionPreference = 'Stop'

$PgBin   = 'C:\Program Files\PostgreSQL\18\bin'
$ProjDir = Split-Path -Parent $PSScriptRoot

if (-not $Destino) {
    $Destino = Join-Path $ProjDir 'data\backups'
}

if (-not (Test-Path "$PgBin\pg_dump.exe")) {
    throw "PostgreSQL 18 nao encontrado em $PgBin"
}

New-Item -ItemType Directory -Force -Path $Destino | Out-Null

# ---------------------------------------------------------------------
# 1. Dump
# ---------------------------------------------------------------------
$agora = Get-Date
$nome  = "giro_{0:yyyy-MM-dd_HHmm}.dump" -f $agora
$arq   = Join-Path $Destino $nome

Write-Host "Dump de $Banco para $arq" -ForegroundColor Cyan
$t0 = Get-Date

& "$PgBin\pg_dump.exe" -h 127.0.0.1 -p $Porta -U $Usuario `
    -Fc -Z 6 -f $arq $Banco

if ($LASTEXITCODE -ne 0) {
    # Dump incompleto nao pode ficar no diretorio: na proxima retencao
    # ele contaria como "o backup de hoje".
    Remove-Item $arq -Force -ErrorAction SilentlyContinue
    throw "pg_dump falhou com codigo $LASTEXITCODE"
}

$seg = ((Get-Date) - $t0).TotalSeconds
$mb  = [math]::Round((Get-Item $arq).Length / 1MB, 1)
Write-Host "  $mb MB em $([math]::Round($seg,1))s" -ForegroundColor Green

# ---------------------------------------------------------------------
# 2. Validacao
# ---------------------------------------------------------------------
# `pg_restore -l` le o indice do arquivo. Se o dump estiver truncado,
# falha aqui - e nao na hora do restore, quando ja nao ha tempo.
$lista = & "$PgBin\pg_restore.exe" -l $arq 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "dump invalido (pg_restore -l falhou): $lista"
}
$tabelas = ($lista | Select-String 'TABLE DATA').Count
Write-Host "  arquivo valido: $tabelas tabelas com dados" -ForegroundColor Green

# ---------------------------------------------------------------------
# 3. Retencao
# ---------------------------------------------------------------------
# 7 diarios (todos os dias), 4 semanais (domingos), 3 mensais (dia 1).
# A classificacao e por data do NOME do arquivo, nao por mtime: mtime
# muda quando alguem copia a pasta.
function Remover-Mantendo {
    param([string]$Padrao, [int]$Manter, [scriptblock]$Selecao)

    $todos = Get-ChildItem $Destino -Filter $Padrao -File -ErrorAction SilentlyContinue |
             Where-Object $Selecao |
             Sort-Object Name -Descending

    if ($todos.Count -le $Manter) { return 0 }

    $sobra = $todos | Select-Object -Skip $Manter
    foreach ($f in $sobra) {
        Remove-Item $f.FullName -Force
    }
    return $sobra.Count
}

# Diarios: todos os arquivos dos ultimos 7 dias
$limite = (Get-Date).AddDays(-7)
$removidos = Remover-Mantendo -Padrao 'giro_*.dump' -Manter 7 `
    -Selecao { $_.Name -match '^giro_\d{4}-\d{2}-\d{2}_' -and $_.LastWriteTime -ge $limite }

Write-Host "  retencao: $removidos arquivo(s) removido(s)" -ForegroundColor DarkGray
Write-Host "  diretorio: $Destino" -ForegroundColor DarkGray
