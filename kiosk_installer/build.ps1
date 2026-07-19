# Builds the ZK9500 kiosk installer end to end:
#   1. PyInstaller -> dist\kiosk_agent.exe (console) + dist\kiosk_agent_service.exe (windowed)
#   2. Inno Setup (ISCC.exe) -> output\ZK9500KioskSetup.exe
#
# Run from anywhere; paths are resolved relative to this script's own folder.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $ScriptDir

$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"

Write-Host "==> Building kiosk_agent.exe / kiosk_agent_service.exe with PyInstaller..." -ForegroundColor Cyan
& $PyInstaller "kiosk_agent.spec" --distpath "dist" --workpath "build" --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (exit $LASTEXITCODE)." }

$Iscc = Get-ChildItem -Path "$env:ProgramFiles*", "$env:LOCALAPPDATA\Programs" -Filter "ISCC.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if (-not $Iscc) { throw "ISCC.exe (Inno Setup) nao encontrado. Instale com: winget install JRSoftware.InnoSetup" }

Write-Host "==> Compiling installer with Inno Setup ($Iscc)..." -ForegroundColor Cyan
& $Iscc "installer.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou (exit $LASTEXITCODE)." }

$SetupExe = Get-ChildItem -Path "$ScriptDir\output" -Filter "ZK9500KioskSetup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
Write-Host "==> Done: $SetupExe" -ForegroundColor Green
