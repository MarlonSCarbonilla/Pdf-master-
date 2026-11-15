; Inno Setup script - install from https://jrsoftware.org/isinfo.php, run build.ps1 first,
; then compile this file (ISCC installer.iss). Output: build\installer\PDFMaster-Setup.exe
#define AppName "PDF Master"
#define AppVersion "1.0.0"

[Setup]
AppId={{6C1E5E0A-4C8B-4B6E-9A52-PDFMASTER0001}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\PDFMaster
DefaultGroupName={#AppName}
OutputDir=build\installer
OutputBaseFilename=PDFMaster-Setup
SetupIconFile=resources\icons\app.ico
UninstallDisplayIcon={app}\PDFMaster.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Files]
Source: "dist\PDFMaster\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\PDFMaster.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PDFMaster.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\PDFMaster.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
