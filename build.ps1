# Build script for Alias Media Renamer (PyInstaller + Inno Setup)
# Uses Alias.spec for PyInstaller configuration.
$ErrorActionPreference = "Stop"

Write-Host "=== Step 1: Building Alias executable with PyInstaller (Alias.spec) ===" -ForegroundColor Cyan

# Clean previous build artifacts if unlocked
if (Test-Path "build") {
    Remove-Item -Path "build" -Recurse -Force -ErrorAction SilentlyContinue
}

$pythonExe = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
& $pythonExe -m PyInstaller --noconfirm --clean Alias.spec

Write-Host "`n=== Step 2: Building Windows Installer with Inno Setup ===" -ForegroundColor Cyan

$isccPaths = @(
    "ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$iscc = $null
foreach ($candidate in $isccPaths) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $iscc = $candidate
        break
    }
    if (Test-Path $candidate) {
        $iscc = $candidate
        break
    }
}

if ($iscc) {
    Write-Host "Found Inno Setup Compiler at: $iscc" -ForegroundColor Green
    & $iscc installer.iss
    Write-Host "`nInstaller generated successfully in: installer_output\" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup Compiler (ISCC.exe) not found in PATH or standard installation directories."
    Write-Warning "To compile the setup installer, install Inno Setup 6 (https://jrsoftware.org/isdl.php) and run: ISCC.exe installer.iss"
}
