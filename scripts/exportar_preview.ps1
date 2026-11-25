# Exporta o .docx para PDF, para inspecao visual.
#
# POR QUE ISSO EXISTE
# -------------------
# Medir paginas e contar tabelas nao diz se o documento e legivel. So
# olhando a pagina se ve se a tabela esta apertada, se o titulo esta
# orfao no pe da folha, se o bloco de codigo vazou da margem.

param(
    [string]$Caminho = "docs/relatorio-final.docx",
    [string]$Saida = "logs/preview-relatorio.pdf"
)

$ErrorActionPreference = "Stop"
$absoluto = (Resolve-Path $Caminho).Path
$destino = Join-Path (Get-Location) $Saida
New-Item -ItemType Directory -Force -Path (Split-Path $destino) | Out-Null
if (Test-Path $destino) { Remove-Item $destino -Force }

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($absoluto, $false, $true)

    # wdExportFormatPDF = 17
    $doc.ExportAsFixedFormat($destino, 17)
    Write-Host "PDF: $destino"
    Write-Host "Paginas: $($doc.ComputeStatistics(2))"
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
