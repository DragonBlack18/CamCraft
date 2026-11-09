[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Executable, [Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference = 'Stop'
$Executable = (Resolve-Path $Executable).Path
$Report = [IO.Path]::GetFullPath($Report)
New-Item -ItemType Directory -Force (Split-Path -Parent $Report) | Out-Null
if (Test-Path $Report) { Remove-Item $Report -Force }
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('CamCraft no Python ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $scratch | Out-Null
$saved = @{}
foreach ($name in @('PATH','PYTHONPATH','PYTHONHOME','CAMCRAFT_DATA_DIR','CAMCRAFT_TEST_MINIMAL_PATH')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:PYTHONPATH, Env:PYTHONHOME, Env:CAMCRAFT_DATA_DIR -ErrorAction SilentlyContinue
    $env:CAMCRAFT_TEST_MINIMAL_PATH = '1'
    $RunExecutable = $Executable
    if ([IO.Path]::GetFileName($Executable).StartsWith('CamCraft-Portable-')) {
        $RunExecutable = Join-Path $scratch 'CamCraft Portable.exe'
        Copy-Item $Executable $RunExecutable
    }
    $process = Start-Process -FilePath $RunExecutable -ArgumentList @('--self-test', '--report', "`"$Report`"", '--seconds', '15') -WorkingDirectory $scratch -PassThru
    if (!$process.WaitForExit(180000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw 'O executavel excedeu o tempo limite do self-test.'
    }
    $process.Refresh()
    if (!(Test-Path $Report)) { throw "Self-test nao criou relatorio. ExitCode=$($process.ExitCode)" }
    $result = Get-Content $Report -Raw | ConvertFrom-Json
    if ($process.ExitCode -ne 0 -or !$result.passed) {
        Get-Content $Report -Raw | Write-Output
        throw "Self-test do executavel falhou: $Executable"
    }
    if (!$result.runtime.frozen -or !$result.no_external_python_on_path) { throw 'O teste nao executou a distribuicao isolada.' }
    Write-Output "[PASS] Executavel testado sem Python no PATH: $Executable"
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    Remove-Item $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
