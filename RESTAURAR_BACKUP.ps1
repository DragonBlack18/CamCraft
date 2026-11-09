[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Arquivo,
    [Parameter(Mandatory=$true)][string]$Destino
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host '[FAIL] Prepare o ambiente com INICIAR.ps1 -Objetos -InstallOnly.'
    exit 1
}
& $Python 'tools\restore_backup.py' '--archive' $Arquivo '--destination' $Destino
exit $LASTEXITCODE
