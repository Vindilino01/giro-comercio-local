# Mede o espaco vertical que cada tipo de elemento ocupa no .docx.
#
# POR QUE ISSO EXISTE
# -------------------
# Contar paginas nao diz o que cortar. Este script separa o documento em
# quatro consumidores de altura - prosa, tabela, bloco de codigo e
# citacao - e mede a fracao de pagina de cada um. Foi assim que ficou
# claro que o sumario de 3 paginas e as 482 linhas de tabela eram o
# problema, e nao a prosa.

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
    $doc = $word.Documents.Open($absoluto, $false, $true)

    $total = $doc.ComputeStatistics(2)
    # Altura util da pagina em pontos: A4 (842) menos margens (2+1.8 cm).
    $alturaPagina = 842 - (56.7 + 51.0)

    # --- tabelas ---
    $tabelas = $doc.Tables.Count
    $linhasTab = 0
    $alturaTab = 0
    foreach ($t in $doc.Tables) {
        $linhasTab += ($t.Rows.Count - 1)
        $alturaTab += $t.Rows.Count * 14   # ~14pt por linha de 7.5pt
    }

    # --- paragrafos de prosa (fora de tabela) ---
    $prosa = 0
    $codigo = 0
    foreach ($p in $doc.Paragraphs) {
        if ($p.Range.Information(12)) { continue }   # wdWithInTable
        $txt = $p.Range.Text.Trim()
        if ($txt.Length -eq 0) { continue }
        $fonte = $p.Range.Font.Name
        if ($fonte -eq "Consolas") {
            $codigo += 1
        } else {
            $prosa += 1
        }
    }

    Write-Host "paginas          : $total"
    Write-Host "altura util      : $([math]::Round($alturaPagina)) pt por pagina"
    Write-Host ""
    Write-Host "tabelas          : $tabelas"
    Write-Host "  linhas de dados: $linhasTab"
    Write-Host "  altura estimada: $([math]::Round($alturaTab / $alturaPagina, 1)) paginas"
    Write-Host ""
    Write-Host "paragrafos fora de tabela: $prosa"
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
