[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Origem)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host '[FAIL] Prepare a nova pasta com INICIAR.ps1 -Objetos -InstallOnly antes de importar.'
    exit 1
}
& $Python 'tools\import_previous.py' '--source' $Origem
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python 'tools\reuse_model.py' '--source' $Origem
if ($LASTEXITCODE -ne 0) { Write-Host '[WARN] Dados importados; modelo nao reutilizado. Revise a mensagem acima.' }
exit 0
