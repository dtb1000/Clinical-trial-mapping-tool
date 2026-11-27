; Inno Setup script for the SDTM Helper Windows installer.
; Built by .github/workflows/build-windows.yml after PyInstaller has produced dist\SDTM Helper\.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1B0F7E-4C55-4E0B-9B57-6F0C2D1A9E31}
AppName=SDTM Helper
AppVersion={#AppVersion}
AppPublisher=SDTM Helper contributors
AppPublisherURL=https://github.com/dtb1000/Clinical-trial-mapping-tool
DefaultDirName={autopf}\SDTM Helper
DefaultGroupName=SDTM Helper
OutputDir=..\dist
OutputBaseFilename=SDTM-Helper-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
UninstallDisplayIcon={app}\SDTM Helper.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\SDTM Helper\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\SDTM Helper"; Filename: "{app}\SDTM Helper.exe"
Name: "{autodesktop}\SDTM Helper"; Filename: "{app}\SDTM Helper.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SDTM Helper.exe"; Description: "Start SDTM Helper"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedLabel=SDTM Helper is installed.%n%nIt needs Java (for example Eclipse Temurin from adoptium.net) to connect to SAS. Open Settings in the app to choose your connection.
