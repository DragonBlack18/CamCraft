[CmdletBinding()]
param(
    [switch]$Test,
    [switch]$InstallOnly,
    [switch]$Repair,
    [switch]$Diagnostico,
    [switch]$Objetos,
    [switch]$CameraOnly,
    [switch]$Offline,
    [switch]$NoInstallPython,
    [string]$PythonPath = ""
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$Data = Join-Path $PSScriptRoot 'data'
$Reports = Join-Path $Data 'reports'
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
$Log = Join-Path $Reports 'launcher.log'
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$Probe = "import sys,struct,sysconfig,tkinter; ok=(3,11)<=sys.version_info[:2]<=(3,14) and struct.calcsize('P')==8 and not sysconfig.get_config_var('Py_GIL_DISABLED'); print(sys.executable if ok else ''); sys.exit(0 if ok else 1)"

function Invoke-Python {
    param([string]$Exe,[string[]]$Arguments)
    $Previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | Tee-Object -FilePath $Log -Append | ForEach-Object { Write-Host $_ }
        $Code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $Previous }
    if ($Code -ne 0) { throw "Python terminou com codigo $Code. Consulte data\reports\launcher.log." }
}

function Find-Python {
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'O caminho informado em -PythonPath nao existe.' }
        $Found = & $PythonPath -c $Probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $Found) { return [string]($Found | Select-Object -Last 1) }
        throw 'Python informado incompativel: use CPython x64 3.11 a 3.14, com GIL.'
    }
    $PrivatePython = Join-Path $PSScriptRoot '.runtime\python\python.exe'
    if (Test-Path -LiteralPath $PrivatePython) {
        $Found = & $PrivatePython -c $Probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $Found) { return [string]($Found | Select-Object -Last 1) }
    }
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        foreach ($Version in @('-3.14','-3.13','-3.12','-3.11')) {
            try {
                $Found = & $Launcher.Source $Version -c $Probe 2>$null
                if ($LASTEXITCODE -eq 0 -and $Found) { return [string]($Found | Select-Object -Last 1) }
            } catch { }
        }
    }
    $Command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($Command -and $Command.Source -notmatch 'WindowsApps') {
        try {
            $Found = & $Command.Source -c $Probe 2>$null
            if ($LASTEXITCODE -eq 0 -and $Found) { return [string]($Found | Select-Object -Last 1) }
        } catch { }
    }
    return ''
}

function Install-PrivatePython {
    if ($NoInstallPython -or $Offline) { throw 'Python x64 nao encontrado. Instale CPython 3.11-3.14 ou forneca -PythonPath. Nenhuma configuracao foi apagada.' }
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Esta entrega requer Windows x64.' }
    $Version = '3.14.10'
    $ExpectedHash = '92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965'
    $DownloadDir = Join-Path $PSScriptRoot '.runtime\downloads'
    $Target = Join-Path $PSScriptRoot '.runtime\python'
    New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    $Installer = Join-Path $DownloadDir "python-$Version-amd64.exe"
    Write-Host '[INFO] Preparando CPython oficial por usuario. O PATH global nao sera alterado.'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    if (-not (Test-Path -LiteralPath $Installer)) {
        $Partial = "$Installer.download"
        Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$Version/python-$Version-amd64.exe" -OutFile $Partial
        Move-Item -LiteralPath $Partial -Destination $Installer -Force
    }
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
        throw 'SHA-256 do instalador Python divergente. Nao foi executado. Remova somente .runtime\downloads\python-3.14.10-amd64.exe e tente novamente.'
    }
    $Signature = Get-AuthenticodeSignature -LiteralPath $Installer
    if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw 'Assinatura do instalador Python nao foi validada. Nao foi executado.'
    }
    $Arguments = @('/quiet','InstallAllUsers=0','PrependPath=0','Include_launcher=0','InstallLauncherAllUsers=0',
        'Include_test=0','Include_doc=0','Include_tcltk=1','Include_pip=1','Shortcuts=0','AssociateFiles=0',
        "TargetDir=`"$Target`"")
    $Process = Start-Process -FilePath $Installer -ArgumentList $Arguments -Wait -PassThru
    if ($Process.ExitCode -notin @(0,3010)) { throw "Instalador Python falhou: $($Process.ExitCode)." }
    $Executable = Join-Path $Target 'python.exe'
    if (-not (Test-Path -LiteralPath $Executable)) { throw 'O instalador terminou, mas o Python privado nao foi encontrado. Use -PythonPath com uma instalacao x64 existente.' }
    return $Executable
}

try {
    Write-Host '=== VISION LOCAL / 4.1 FLUIDEZ ==='
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $BasePython = Find-Python
        if (-not $BasePython) { $BasePython = Install-PrivatePython }
        Write-Host '[INFO] Criando ambiente isolado .venv; sem alterar outros projetos.'
        Invoke-Python -Exe $BasePython -Arguments @('-m','venv',(Join-Path $PSScriptRoot '.venv'))
    }
    Invoke-Python -Exe $VenvPython -Arguments @('-c',$Probe)
    $Requirements = Join-Path $PSScriptRoot 'requirements.txt'
    $HashFile = Join-Path $PSScriptRoot '.venv\vision-requirements.sha256'
    $Hash = (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash
    $NeedInstall = $Repair -or -not (Test-Path -LiteralPath $HashFile)
    if (-not $NeedInstall) { $NeedInstall = (Get-Content -LiteralPath $HashFile -Raw).Trim() -ne $Hash }
    if ($NeedInstall) {
        if ($Offline) { throw 'Ambiente nao preparado. Execute sem -Offline uma vez com internet.' }
        Write-Host '[INFO] Instalando dependencias fixadas. A primeira preparacao precisa de internet.'
        $InstallArgs = @('-m','pip','install','--disable-pip-version-check','--only-binary=:all:','-r',$Requirements)
        if ($Repair) { $InstallArgs += '--force-reinstall' }
        Invoke-Python -Exe $VenvPython -Arguments $InstallArgs
        Invoke-Python -Exe $VenvPython -Arguments @('-m','pip','check')
        Invoke-Python -Exe $VenvPython -Arguments @('tools\doctor.py')
        Set-Content -LiteralPath $HashFile -Value $Hash -Encoding ASCII
        Write-Host '[PASS] Ambiente instalado e dependencias verificadas.'
    } else {
        Invoke-Python -Exe $VenvPython -Arguments @('tools\doctor.py')
        Write-Host '[PASS] Ambiente existente preservado; sem reinstalacao.'
    }
    if ($Test) {
        if (-not $Offline) {
            Invoke-Python -Exe $VenvPython -Arguments @('-m','pip','install','--disable-pip-version-check','--only-binary=:all:','-r','requirements-test.txt')
        }
        Invoke-Python -Exe $VenvPython -Arguments @('-m','pytest','-q',"--junitxml=$Reports\tests-windows.xml")
        Write-Host '[PASS] Testes locais concluidos. Veja se houve SKIP do modelo no relatorio.'
        exit 0
    }
    if (-not $Diagnostico -and -not $Objetos -and -not $CameraOnly) {
        $ModelArgs = @('tools\prepare_model.py')
        if ($Offline) { $ModelArgs += '--offline' }
        Invoke-Python -Exe $VenvPython -Arguments $ModelArgs
    }
    if ($InstallOnly) { exit 0 }
    $RunArgs = @('run.py')
    if ($Diagnostico) { $RunArgs += @('--demo','--hog') }
    elseif ($Objetos) { $RunArgs += @('--regions') }
    if ($CameraOnly) { $RunArgs += '--camera-only' }
    Invoke-Python -Exe $VenvPython -Arguments $RunArgs
    exit 0
} catch {
    $Message = "[FAIL] $($_.Exception.Message)"
    Write-Host $Message -ForegroundColor Red
    Add-Content -LiteralPath $Log -Value $Message
    Write-Host 'Se houver bloqueio corporativo, nao desative o antivirus/firewall. Use -PythonPath ou consulte a TI.'
    exit 1
}
