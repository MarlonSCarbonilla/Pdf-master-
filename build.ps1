# Build the Windows distribution (dist\PDFMaster\PDFMaster.exe) and Setup Installer (dist\PDFMaster-Setup.exe).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1 [-SkipTests]
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

& $py tools\generate_app_icon.py
if (-not $args.Contains("-SkipTests")) {
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed - build aborted." }
}
& $py -m PyInstaller PDFMaster.spec --noconfirm --clean --distpath dist --workpath build\pyi
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
Write-Host "Built standalone app: dist\PDFMaster\PDFMaster.exe"

& $py tools\build_installer.py
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
Write-Host "Built setup installer: dist\PDFMaster-Setup.exe"
