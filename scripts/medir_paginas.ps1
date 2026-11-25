# Mede quantas paginas cada secao ocupa no .docx.
#
# POR QUE ISSO EXISTE
# -------------------
# "66 paginas" era o sintoma, nao a causa. Antes de cortar texto, e
# preciso saber ONDE as paginas estao: prosa, tabela de evidencia ou
# bloco de codigo. Sem essa medida, o corte vira chute e tira o que o
# edital cobra.

param(
    [string]$Caminho = "docs/relatorio-final.docx"
)

$ErrorActionPreference = "Stop"
$absoluto = (Resolve-Path $Caminho).Path

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($absoluto, $false, $true)   # ReadOnly

    $total = $doc.ComputeStatistics(2)
    Write-Host "TOTAL: $total paginas"
    Write-Host ""

    $anterior = 1
    $anteriorNome = "(capa)"
    $linhas = @()

    foreach ($p in $doc.Paragraphs) {
        if ($p.OutlineLevel -eq 1) {
            $pagina = $p.Range.Information(3)   # wdActiveEndPageNumber
            $nome = $p.Range.Text.Trim()
            if ($nome.Length -gt 46) { $nome = $nome.Substring(0, 46) }
            $linhas += [pscustomobject]@{
                Pagina = $pagina
                Paginas = $pagina - $anterior
                Secao = $anteriorNome
            }
            $anterior = $pagina
            $anteriorNome = $nome
        }
    }
    $linhas += [pscustomobject]@{
        Pagina = $total
        Paginas = $total - $anterior + 1
        Secao = $anteriorNome
    }

    $linhas | Format-Table -AutoSize
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
