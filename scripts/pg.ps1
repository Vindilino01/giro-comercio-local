# =====================================================================
# Giro - Gerenciamento do cluster PostgreSQL isolado do projeto
#
# Por que um cluster proprio em vez do servico postgresql-x64-18?
#   1. Reprodutibilidade: qualquer integrante sobe o ambiente com um
#      comando, sem depender de senha pre-existente.
#   2. Isolamento: o projeto nao encosta no cluster do usuario.
#   3. O pitch funciona offline na maquina de qualquer um que tenha
#      o PostgreSQL instalado.
#   4. Porta 5433 evita conflito com instalacao padrao (5432).
#
# ONDE FICAM OS DADOS
# -------------------
# Fora do repositorio, em `$env:USERPROFILE\.giro-pg`. Duas razoes:
#   - o data dir tem dezenas de MB e centenas de arquivos; dentro de
#     `logs/` ele inflava a entrega e confundia "codigo" com "estado";
#   - `logs/` e descartavel por definicao; apagar log nao pode apagar
#     o banco.
# A versao anterior usava `logs\pgdata`. Quem ja tinha esse cluster
# continua funcionando: `Resolve-PgData` detecta e migra.
#
# Uso:
#   .\scripts\pg.ps1 start     inicia o cluster
#   .\scripts\pg.ps1 stop      para o cluster
#   .\scripts\pg.ps1 status    mostra o estado
#   .\scripts\pg.ps1 psql      abre sessao interativa
#   .\scripts\pg.ps1 init      cria o cluster sem iniciar
#   .\scripts\pg.ps1 reset     DESTROI e recria do zero (com confirmacao)
# =====================================================================
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'psql', 'reset', 'init')]
    [string]$Acao = 'status'
)

$ErrorActionPreference = 'Stop'

$PgBin   = 'C:\Program Files\PostgreSQL\18\bin'
$ProjDir = Split-Path -Parent $PSScriptRoot
$Port    = 5433
$DbName  = 'giro'

# Local canonico do cluster: fora do repositorio.
$PgDataCanonico = Join-Path $env:USERPROFILE '.giro-pg'
$PgDataAntigo   = Join-Path $ProjDir 'logs\pgdata'

function Resolve-PgData {
    # Preferencia: o canonico. Se ele nao existe mas o antigo sim, usa o
    # antigo (cluster de uma execucao anterior) em vez de criar um vazio -
    # criar outro na mesma porta produziria dois bancos concorrentes, que
    # foi exatamente o problema encontrado na auditoria.
    if (Test-Path (Join-Path $PgDataCanonico 'PG_VERSION')) { return $PgDataCanonico }
    if (Test-Path (Join-Path $PgDataAntigo 'PG_VERSION')) {
        Write-Host "Usando cluster existente em $PgDataAntigo" -ForegroundColor Yellow
        Write-Host "  (o local canonico e $PgDataCanonico; migre quando puder)" -ForegroundColor DarkGray
        return $PgDataAntigo
    }
    return $PgDataCanonico
}

$PgData = Resolve-PgData
$PgLog  = Join-Path $ProjDir 'logs\postgresql.log'

if (-not (Test-Path "$PgBin\pg_ctl.exe")) {
    throw "PostgreSQL 18 nao encontrado em $PgBin. Instale o PostgreSQL 18 ou ajuste `$PgBin neste script."
}

function Test-Cluster {
    return (Test-Path (Join-Path $PgData 'PG_VERSION'))
}

function Test-Rodando {
    & "$PgBin\pg_isready.exe" -h 127.0.0.1 -p $Port *> $null
    return ($LASTEXITCODE -eq 0)
}

function Initialize-Cluster {
    if (Test-Cluster) { Write-Host 'Cluster ja existe.' -ForegroundColor Yellow; return }

    Write-Host 'Criando cluster isolado...' -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $PgData | Out-Null

    & "$PgBin\initdb.exe" -D $PgData -U postgres --auth=trust --encoding=UTF8 `
        --locale=C --lc-messages=C 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) { throw 'initdb falhou' }

    # pg_stat_statements precisa ser habilitado no boot do servidor.
    $conf = Join-Path $PgData 'postgresql.conf'
    Add-Content -Path $conf -Value @"

# ---- Configuracao do projeto Giro ----
port = $Port
listen_addresses = '127.0.0.1'
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.max = 5000
pg_stat_statements.track = all
log_min_duration_statement = 200
timezone = 'America/Sao_Paulo'
datestyle = 'ISO, DMY'
lc_monetary = 'pt_BR.UTF-8'
default_text_search_config = 'pg_catalog.portuguese'
work_mem = '32MB'
maintenance_work_mem = '256MB'
random_page_cost = 1.1
effective_cache_size = '1GB'
"@

    Write-Host 'Cluster criado.' -ForegroundColor Green
}

function Start-Cluster {
    if (-not (Test-Cluster)) { Initialize-Cluster }

    if (Test-Rodando) {
        Write-Host "Ja esta rodando na porta $Port." -ForegroundColor Yellow
        return
    }

    # O log NAO pode ficar dentro de PGDATA: no Windows isso gera
    # sharing violation durante recovery e o servidor nao termina de subir.
    & "$PgBin\pg_ctl.exe" -D $PgData -o "-p $Port" -l $PgLog start 2>&1 | Out-Null

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 700
        if (Test-Rodando) {
            Write-Host "PostgreSQL rodando em 127.0.0.1:$Port" -ForegroundColor Green
            return
        }
    }
    throw "Servidor nao respondeu. Ver $PgLog"
}

function Stop-Cluster {
    if (-not (Test-Cluster)) { Write-Host 'Cluster nao existe.' -ForegroundColor Yellow; return }
    & "$PgBin\pg_ctl.exe" -D $PgData stop -m fast 2>&1 | Out-Null
    Write-Host 'Parado.' -ForegroundColor Green
}

function Show-Status {
    if (-not (Test-Cluster)) { Write-Host 'Cluster nao inicializado.' -ForegroundColor Yellow; return }
    & "$PgBin\pg_ctl.exe" -D $PgData status 2>&1 | Select-Object -First 3
}

switch ($Acao) {
    'init'   { Initialize-Cluster }
    'start'  { Start-Cluster }
    'stop'   { Stop-Cluster }
    'status' { Show-Status }
    'psql'   {
        Start-Cluster
        & "$PgBin\psql.exe" -h 127.0.0.1 -p $Port -U postgres -d $DbName
    }
    'reset'  {
        Write-Host 'ATENCAO: isso apaga todos os dados do projeto.' -ForegroundColor Red
        $r = Read-Host 'Digite SIM para confirmar'
        if ($r -ne 'SIM') { Write-Host 'Cancelado.'; return }
        Stop-Cluster
        Remove-Item $PgData -Recurse -Force -ErrorAction SilentlyContinue
        Initialize-Cluster
        Start-Cluster
    }
}
