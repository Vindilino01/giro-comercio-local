# Atualiza o sumario do relatorio .docx e informa a contagem de paginas.
#
# POR QUE POWERSHELL E NAO PYTHON
# -------------------------------
# python-docx nao calcula campo. O sumario (TOC) e o numero de paginas
# sao resultados que so o Word sabe produzir, porque dependem da
# paginacao real. win32com nao esta instalado nesta maquina, mas o
# PowerShell fala COM nativamente.
#
# O que este script faz:
#   1. abre o .docx no Word (invisivel);
#   2. atualiza todos os campos, inclusive o sumario;
#   3. salva;
#   4. le o total de paginas e imprime.
#
# Uso:
#   pwsh scripts/atualizar_sumario.ps1
#   pwsh scripts/atualizar_sumario.ps1 -Caminho docs/relatorio-final.docx

param(
    [string]$Caminho = "docs/relatorio-final.docx"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Caminho)) {
    Write-Error "Arquivo nao encontrado: $Caminho"
    exit 1
}

$absoluto = (Resolve-Path $Caminho).Path
Write-Host "Abrindo no Word: $absoluto"

$word = $null
$doc = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0   # wdAlertsNone

    # ReadWrite e sem senha. Abrir como somente leitura impediria salvar
    # o resultado da atualizacao dos campos.
    $doc = $word.Documents.Open($absoluto, $false, $false)

    # wdUpdateFields = 1, wdUpdateTOC = 2 -> atualiza os dois.
    $doc.Fields.Update() | Out-Null
    foreach ($toc in $doc.TablesOfContents) {
        $toc.Update()
    }

    # Repagina antes de ler o total: sem isto, o numero reflete a
    # paginacao anterior a atualizacao do sumario.
    $doc.Repaginate()
    $paginas = $doc.ComputeStatistics(2)   # wdStatisticPages

    $doc.Save()
    Write-Host "Sumario atualizado. Paginas: $paginas"

    # Contagem de palavras tambem e util para conferir contra o lint.
    $palavras = $doc.ComputeStatistics(0)  # wdStatisticWords
    Write-Host "Palavras: $palavras"
}
finally {
    if ($doc) {
        $doc.Close($false)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
    }
    if ($word) {
        $word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
