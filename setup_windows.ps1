[CmdletBinding()]
param(
    [switch]$InstallTools,
    [switch]$InstallWSL,
    [switch]$InstallPythonDependencies,
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"

function Write-Section([string]$Message) {
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage([string]$Id, [string]$Label) {
    if (-not (Test-Command "winget")) {
        Write-Warning "winget is unavailable; install '$Label' manually from its official website."
        return
    }
    Write-Host "Installing $Label ($Id)..."
    & winget install --id $Id --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget returned exit code $LASTEXITCODE for $Label. You may need to install it manually."
    }
}

Write-Section "AndroidBuilder Windows 10 setup"
Write-Host "This script checks prerequisites and can install selected developer tools."
Write-Host "It does not flash, root, unlock, or modify a connected phone."
Write-Host "ROM builds should run in WSL2 Ubuntu, not directly in native Windows."

if ($InstallTools) {
    Write-Section "Installing Windows tools"
    Install-WingetPackage "Git.Git" "Git"
    Install-WingetPackage "Python.Python.3.12" "Python 3.12"
    Install-WingetPackage "Google.PlatformTools" "Android SDK Platform-Tools (ADB)"
}

if ($InstallWSL) {
    Write-Section "Installing WSL2 Ubuntu"
    if (-not (Test-Command "wsl")) {
        Write-Warning "The wsl command is unavailable. Update Windows 10 and install WSL from Microsoft's instructions."
    } else {
        Write-Host "Requesting WSL2 with Ubuntu 22.04. Windows may require administrator approval or a restart."
        Write-Host "This step is only run because -InstallWSL was explicitly supplied."
        & wsl --install -d Ubuntu-22.04
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "WSL installation did not complete automatically. Follow https://learn.microsoft.com/windows/wsl/install"
        }
    }
}

Write-Section "Checking prerequisites"
$checks = @(
    @{ Name = "git"; Label = "Git"; Hint = "Install Git for Windows: https://git-scm.com/download/win" },
    @{ Name = "python"; Label = "Python"; Hint = "Install Python 3.10+ and enable the PATH option in its installer." },
    @{ Name = "adb"; Label = "Android Debug Bridge"; Hint = "Install Platform-Tools: https://developer.android.com/tools/releases/platform-tools" },
    @{ Name = "wsl"; Label = "Windows Subsystem for Linux"; Hint = "Install WSL2 Ubuntu for ROM builds: https://learn.microsoft.com/windows/wsl/install" }
)
$missing = @()
foreach ($check in $checks) {
    $found = Test-Command $check.Name
    if ($found) {
        Write-Host ("[OK]   {0} found" -f $check.Label) -ForegroundColor Green
    } else {
        Write-Host ("[MISS] {0} not found. {1}" -f $check.Label, $check.Hint) -ForegroundColor Yellow
        $missing += $check.Name
    }
}

if (Test-Command "python") {
    & python --version
    if ($LASTEXITCODE -ne 0) { Write-Warning "Python was found but failed to report its version." }
}
if (Test-Command "git") {
    & git --version
}
if (Test-Command "adb") {
    & adb version
    if (-not $SkipChecks) {
        Write-Section "Connected Android devices"
        & adb devices -l
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "ADB could not list devices. Check Platform-Tools installation."
        } else {
            Write-Host "If your phone appears as 'unauthorized', unlock it and accept the USB debugging prompt."
        }
    }
}

if ($InstallPythonDependencies) {
    if (-not (Test-Command "python")) {
        Write-Warning "Python is required before installing optional Python dependencies."
    } else {
        Write-Section "Installing optional Python dependencies"
        & python -m pip install --user --upgrade pip
        if ($LASTEXITCODE -ne 0) { Write-Warning "pip upgrade failed; continuing to requirements installation." }
        if (Test-Path (Join-Path $PSScriptRoot "requirements.txt")) {
            & python -m pip install --user -r (Join-Path $PSScriptRoot "requirements.txt")
            if ($LASTEXITCODE -ne 0) { Write-Warning "Some optional Python dependencies could not be installed." }
        } else {
            Write-Warning "requirements.txt was not found beside this script."
        }
    }
}

Write-Section "Project self-check"
if ((Test-Command "python") -and (Test-Path (Join-Path $PSScriptRoot "romforge.py"))) {
    Push-Location $PSScriptRoot
    try {
        & python romforge.py ut-check --help
        if ($LASTEXITCODE -ne 0) { Write-Warning "The readiness CLI self-check failed." }
        if (Test-Path "tests") {
            Write-Host "Running project unit tests..."
            & python -m unittest discover -s tests -v
            if ($LASTEXITCODE -ne 0) { Write-Warning "One or more tests failed. Review the output above." }
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Run this script from the AndroidBuilder project folder to enable the project self-check."
}

Write-Section "Setup summary"
if ($missing.Count -eq 0) {
    Write-Host "All checked commands are available." -ForegroundColor Green
} else {
    Write-Host ("Still missing: " + ($missing -join ", ")) -ForegroundColor Yellow
}
Write-Host "Native Windows is suitable for project scripts and ADB checks."
Write-Host "Use WSL2 Ubuntu for Android ROM source sync/build dependencies; large builds need substantial free disk space and RAM."
Write-Host "No reboot was initiated by this script."
