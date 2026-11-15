# Build the Windows distribution (dist\PDFMaster\PDFMaster.exe) and Setup Installer (dist\PDFMaster-Setup.exe).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1 [-SkipTests]
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

$cargo = if (Get-Command cargo -ErrorAction SilentlyContinue) { "cargo" } elseif (Test-Path "C:\Program Files\Rust stable GNU 1.100\bin\cargo.exe") { "C:\Program Files\Rust stable GNU 1.100\bin\cargo.exe" } else { $null }
if ($cargo -and (Test-Path "rust_accel\Cargo.toml")) {
    Write-Host "Building native Rust PDF accelerator (rust_accel)..."
    & $cargo build --release --manifest-path rust_accel\Cargo.toml
    if ($LASTEXITCODE -eq 0 -and (Test-Path "rust_accel\target\release\pdf_rust_accel.dll")) {
        Copy-Item "rust_accel\target\release\pdf_rust_accel.dll" "core\pdf_rust_accel.dll" -Force
        Write-Host "Copied native DLL to core\pdf_rust_accel.dll"
    }
}

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
Write-Host "Built setup installer: installer\PDFMaster-Setup.exe"
