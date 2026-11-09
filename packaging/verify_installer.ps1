[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SetupPath, [Parameter(Mandatory=$true)][string]$ReportDirectory)
$ErrorActionPreference = 'Stop'
$SetupPath = (Resolve-Path $SetupPath).Path
$ReportDirectory = (Resolve-Path $ReportDirectory).Path
$install = Join-Path ([IO.Path]::GetTempPath()) ('CamCraft installed test ' + [Guid]::NewGuid().ToString('N'))
$log = Join-Path $ReportDirectory 'setup.log'
$uninstallLog = Join-Path $ReportDirectory 'uninstall.log'
$sentinel = Join-Path $env:LOCALAPPDATA ('CamCraft\data\ci-preserve-'+[Guid]::NewGuid().ToString('N')+'.txt')
$sentinelParentExisted = Test-Path (Split-Path -Parent $sentinel)
$result = @{ installed=$false; installed_exe_passed=$false; uninstalled=$false; user_data_preserved=$false }
try {
    $p = Start-Process -FilePath $SetupPath -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',"/DIR=`"$install`"","/LOG=`"$log`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Setup falhou: $($p.ExitCode)" }
    if (!(Test-Path (Join-Path $install 'CamCraft.exe')) -or !(Test-Path (Join-Path $install 'installed.marker'))) { throw 'Instalacao incompleta.' }
    $result.installed = $true
    & (Join-Path $PSScriptRoot 'verify_frozen.ps1') -Executable (Join-Path $install 'CamCraft.exe') -Report (Join-Path $ReportDirectory 'installed-smoke.json')
    $frozen = Get-Content (Join-Path $ReportDirectory 'installed-smoke.json') -Raw | ConvertFrom-Json
    $expectedData = Join-Path $env:LOCALAPPDATA 'CamCraft\data'
    if ($frozen.runtime.default_data -ne $expectedData) { throw 'Pasta de dados do app instalado esta incorreta.' }
    $result.installed_exe_passed = $true
    New-Item -ItemType Directory -Force (Split-Path -Parent $sentinel) | Out-Null
    [IO.File]::WriteAllText($sentinel, 'Evidence preservation sentinel')
    $uninstaller = Join-Path $install 'unins000.exe'
    $p = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/LOG=`"$uninstallLog`"") -Wait -PassThru
    if ($p.ExitCode -ne 0 -or (Test-Path (Join-Path $install 'CamCraft.exe'))) { throw 'Desinstalacao falhou.' }
    $result.uninstalled = $true
    if (!(Test-Path $sentinel)) { throw 'Desinstalador removeu dados do usuario.' }
    $result.user_data_preserved = $true
    Write-Output '[PASS] Instalar, executar, desinstalar e preservar dados.'
} finally {
    $result | ConvertTo-Json | Set-Content (Join-Path $ReportDirectory 'installer-smoke.json') -Encoding utf8
    Remove-Item $sentinel -Force -ErrorAction SilentlyContinue
    if (!$sentinelParentExisted) {
        $parent = Split-Path -Parent $sentinel
        if ((Test-Path $parent) -and @(Get-ChildItem $parent -Force).Count -eq 0) { Remove-Item $parent -Force }
    }
}
