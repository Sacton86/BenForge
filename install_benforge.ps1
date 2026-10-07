<#
==============================================================================
 BenForge - one-shot installer / updater (Windows, PowerShell)

 Run it to install BenForge fresh, or run it again later to update. It performs
 four clearly announced steps:
   STEP 1/4  Check prerequisites (git, python)           [installs via winget]
   STEP 2/4  Clone the repo (or update it if present)
   STEP 3/4  Create a Python virtual environment and install dependencies
   STEP 4/4  Download the matching Blender engine if one isn't available

 Everything printed is also saved to a timestamped log file. If anything fails,
 the script stops and prints exactly which step failed and where the log is, so
 you can send it for support.

 Quick start (run in PowerShell):
   irm https://raw.githubusercontent.com/Sacton86/BenForge/main/install_benforge.ps1 | iex

 Install location defaults to %USERPROFILE%\BenForge. Override with:
   $env:BENFORGE_DIR = "D:\Apps\BenForge"; <then run the installer>
==============================================================================
#>

$ErrorActionPreference = 'Stop'
$ScriptVersion = '1.1'
$RepoUrl    = 'https://github.com/Sacton86/BenForge.git'
$InstallDir = if ($env:BENFORGE_DIR) { $env:BENFORGE_DIR } else { Join-Path $env:USERPROFILE 'BenForge' }
$BlenderVer = '4.1.1'
$BlenderUrl = "https://download.blender.org/release/Blender4.1/blender-$BlenderVer-windows-x64.zip"

$Log = Join-Path $env:TEMP ("benforge-install-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
try { Start-Transcript -Path $Log -Append | Out-Null } catch {}

$script:StepCurrent = 'startup'
function Step($s) { $script:StepCurrent = $s; Write-Host "`n========================================================" -ForegroundColor Cyan; Write-Host " STEP $s" -ForegroundColor Cyan; Write-Host "========================================================" -ForegroundColor Cyan }
function Info($s) { Write-Host "   -> $s" -ForegroundColor Cyan }
function Ok($s)   { Write-Host "   [OK] $s" -ForegroundColor Green }
function Warn($s) { Write-Host "   !  $s" -ForegroundColor Yellow }

function Fail-Report($err) {
    Write-Host "`n########################################################" -ForegroundColor Red
    Write-Host "  INSTALL FAILED" -ForegroundColor Red
    Write-Host "  Step   : $script:StepCurrent" -ForegroundColor Red
    Write-Host "  Error  : $($err.Exception.Message)" -ForegroundColor Red
    if ($err.InvocationInfo) { Write-Host "  Where  : line $($err.InvocationInfo.ScriptLineNumber): $($err.InvocationInfo.Line.Trim())" -ForegroundColor Red }
    Write-Host "########################################################" -ForegroundColor Red
    Write-Host "`nA full log was saved to:`n   $Log" -ForegroundColor Yellow
    Write-Host "Please send that file (or copy everything printed above) to report the problem.`n" -ForegroundColor Yellow
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}

function Need($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

try {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " BenForge Installer / Updater  (script v$ScriptVersion)"      -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "   Date        : $(Get-Date)"
    Write-Host "   User        : $env:USERNAME"
    Write-Host "   Machine      : $env:COMPUTERNAME  ($([System.Environment]::OSVersion.VersionString))"
    Write-Host "   PowerShell  : $($PSVersionTable.PSVersion)"
    Write-Host "   Install dir : $InstallDir"
    Write-Host "   Log file    : $Log"

    # ========================================================= STEP 1/4
    Step '1/4  Prerequisites (git, python)'
    if (-not (Need git)) {
        if (Need winget) { Info 'Installing Git via winget...'; winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements }
        else { throw "Git is not installed and winget is unavailable. Install Git from https://git-scm.com/download/win and re-run." }
    }
    Ok "git: $((git --version))"
    if (-not (Need python)) {
        if (Need winget) { Info 'Installing Python via winget...'; winget install --id Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements; $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User') }
        else { throw "Python is not installed and winget is unavailable. Install Python 3 from https://www.python.org/downloads/ (tick 'Add to PATH') and re-run." }
    }
    Ok "python: $((python --version 2>&1))"

    # ========================================================= STEP 2/4
    Step '2/4  Download / update BenForge source'
    if (Test-Path (Join-Path $InstallDir '.git')) {
        Info "Existing install found in $InstallDir - fetching latest..."
        git -C $InstallDir fetch --tags origin
        git -C $InstallDir pull --ff-only
        Ok 'Updated to the latest version.'
    } else {
        Info "Cloning $RepoUrl into $InstallDir ..."
        git clone $RepoUrl $InstallDir
        Ok 'Repository cloned.'
    }
    Set-Location $InstallDir
    Info "Now at commit: $((git rev-parse --short HEAD))  ($((git log -1 --format=%s)))"

    # ========================================================= STEP 3/4
    Step '3/4  Python environment & dependencies'
    if (-not (Test-Path '.venv')) { Info 'Creating virtual environment in .venv ...'; python -m venv .venv; Ok 'Virtual environment created.' }
    else { Info 'Reusing existing .venv' }
    $py = Join-Path $InstallDir '.venv\Scripts\python.exe'
    Info 'Upgrading pip...'
    & $py -m pip install --upgrade pip | Out-Null
    Info 'Installing runtime dependency: customtkinter'
    & $py -m pip install --upgrade customtkinter
    & $py -c "import customtkinter, tkinter"
    Ok 'Python dependencies ready (customtkinter + tkinter import cleanly).'

    # ========================================================= STEP 4/4
    Step '4/4  Blender unfolding engine'
    $engineExe = Join-Path $InstallDir 'engine\blender_portable\blender.exe'
    if (Test-Path $engineExe) {
        Ok 'Bundled Blender engine already present (engine\blender_portable).'
    } elseif (Need blender) {
        Ok "Using system Blender on PATH: $((Get-Command blender).Source)"
    } else {
        Info "No Blender found. Downloading Blender $BlenderVer (~400 MB, one time)..."
        New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir 'engine') | Out-Null
        $tmpZip = Join-Path $env:TEMP "blender-$BlenderVer.zip"
        $tmpDir = Join-Path $env:TEMP "blender-$BlenderVer-extract"
        Info "Downloading from $BlenderUrl"
        Invoke-WebRequest -Uri $BlenderUrl -OutFile $tmpZip
        Ok "Download complete ($([math]::Round((Get-Item $tmpZip).Length/1MB)) MB)."
        Info 'Extracting engine (this takes a moment)...'
        if (Test-Path $tmpDir) { Remove-Item -Recurse -Force $tmpDir }
        Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force
        $src = Join-Path $tmpDir "blender-$BlenderVer-windows-x64"
        $dst = Join-Path $InstallDir 'engine\blender_portable'
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Move-Item $src $dst
        Remove-Item -Force $tmpZip
        if (-not (Test-Path (Join-Path $dst 'blender.exe'))) { throw 'Blender engine was not set up correctly.' }
        Ok 'Blender engine installed into engine\blender_portable.'
    }

    # ========================================================= DONE
    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host " BenForge is installed and ready."                             -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "   Version  : $((git rev-parse --short HEAD))"
    Write-Host "   Location : $InstallDir"
    Write-Host "   Log file : $Log"
    Write-Host "`n   Launch it with:"
    Write-Host "      & `"$InstallDir\.venv\Scripts\python.exe`" `"$InstallDir\app.py`"" -ForegroundColor Cyan
    Write-Host "`n   Re-run this installer any time to update to the latest version.`n"
    try { Stop-Transcript | Out-Null } catch {}
}
catch {
    Fail-Report $_
}
