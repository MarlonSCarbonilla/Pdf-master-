PDF Master v1.0.0 – Offline Windows Setup & Installer
======================================================

Files in this folder:
1. PDFMaster-Setup.exe  — Full Windows GUI Setup Wizard (installs PDF Master, creates Desktop & Start Menu shortcuts, and registers the uninstaller).
2. Uninstall.exe        — Uninstaller utility (automatically copied into the installation folder during setup).
3. installer.iss        — Inno Setup configuration script.

How to install:
- Double-click `PDFMaster-Setup.exe` and click "Install Now".
- Default installation path: `%LOCALAPPDATA%\Programs\PDFMaster`

Silent installation (command line):
- `PDFMaster-Setup.exe /S`
- `PDFMaster-Setup.exe /S /DIR="C:\Custom\Folder"`
