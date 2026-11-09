[CmdletBinding()]
param([string]$PythonPath = '', [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Este build requer Windows x64.' }
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (!$PythonPath) {
    $PythonPath = Join-Path $Root '.build-venv\Scripts\python.exe'
    if (!(Test-Path $PythonPath)) {
        python -m venv (Join-Path $Root '.build-venv')
        if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.12 x64 somente no computador de build.' }
    }
    & $PythonPath -m pip install --disable-pip-version-check --only-binary=:all: -r (Join-Path $Root 'packaging\requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Falha preparando dependencias de build.' }
}
$PythonPath = (Resolve-Path $PythonPath).Path
function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $PythonPath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python falhou: $($Arguments -join ' ')" }
}
New-Item -ItemType Directory -Force release, 'build\reports' | Out-Null
Invoke-Python -m pip check
Invoke-Python -c "import importlib.metadata as m; names=[d.metadata['Name'].lower() for d in m.distributions()]; assert names.count('opencv-python-headless')==1 and not any(n in names for n in ['opencv-python','opencv-contrib-python','opencv-contrib-python-headless']), 'Only one OpenCV distribution allowed'"
Invoke-Python tools/prepare_model.py
if (!$SkipTests) { Invoke-Python -m pytest -q --junitxml=build/reports/pytest-windows.xml }
Invoke-Python packaging/collect_licenses.py
$Version = (& $PythonPath -c 'from vision_app.runtime import VERSION; print(VERSION)').Trim()
$env:CAMCRAFT_BUNDLE_MODE = 'onedir'
Invoke-Python -m PyInstaller --noconfirm --clean --workpath build/onedir --distpath dist packaging/camcraft.spec
Invoke-Python packaging/audit_native.py --directory dist/CamCraft --output build/reports/native-audit.json
& (Join-Path $PSScriptRoot 'verify_frozen.ps1') -Executable (Join-Path $Root 'dist\CamCraft\CamCraft.exe') -Report (Join-Path $Root 'build\reports\onedir-smoke.json')
$env:CAMCRAFT_BUNDLE_MODE = 'onefile'
Invoke-Python -m PyInstaller --noconfirm --clean --workpath build/onefile --distpath release packaging/camcraft.spec
$Portable = Join-Path $Root "release\CamCraft-Portable-$Version-x64.exe"
& (Join-Path $PSScriptRoot 'verify_frozen.ps1') -Executable $Portable -Report (Join-Path $Root 'build\reports\portable-smoke.json')
$Compiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (!(Test-Path $Compiler)) {
    $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (!$found) { throw 'Inno Setup 6.3+ nao encontrado. Instale apenas na maquina de build.' }
    $Compiler = $found.Source
}
Write-Output "[INFO] Inno Setup: $((Get-Item $Compiler).VersionInfo.FileVersion)"
& $Compiler "/DAppVersion=$Version" "/DBuildRoot=$Root" (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Falha compilando instalador.' }
& (Join-Path $PSScriptRoot 'verify_installer.ps1') -SetupPath (Join-Path $Root "release\CamCraft-Setup-$Version-x64.exe") -ReportDirectory (Join-Path $Root 'build\reports')
Copy-Item '.build_assets\runtime-manifest.json' 'build\reports\runtime-manifest.json' -Force
$files = Get-ChildItem release -Filter '*.exe' | Sort-Object Name
if ($files.Count -ne 2) { throw 'A distribuicao precisa conter exatamente dois executaveis.' }
$lines = foreach ($file in $files) { "$((Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $($file.Name)" }
[IO.File]::WriteAllLines((Join-Path $Root 'release\SHA256SUMS.txt'), $lines, [Text.UTF8Encoding]::new($false))
Compress-Archive -Path 'build\reports\*' -DestinationPath "release\CamCraft-$Version-validation.zip" -Force
Write-Output '[PASS] Portatil e Setup gerados; testes dos dois executaveis e instalacao/desinstalacao aprovados.'
