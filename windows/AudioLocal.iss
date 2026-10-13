#define AppVersion "1.0.0-beta.1"
[Setup]
AppId={{21C5C5A8-7598-4E21-BE03-B8CE6AADE143}
AppName=AudioLocal
AppVersion={#AppVersion}
AppPublisher=GuiaEstudio
AppPublisherURL=https://guiaestudio.cl/audiolocal/
DefaultDirName={localappdata}\Programs\AudioLocal
DefaultGroupName=AudioLocal
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=release
OutputBaseFilename=AudioLocal-1.0.0-beta.1-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AudioLocal.exe
CloseApplications=yes
SetupLogging=yes
[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked
[Files]
Source: "dist\AudioLocal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\AudioLocal"; Filename: "{app}\AudioLocal.exe"
Name: "{autodesktop}\AudioLocal"; Filename: "{app}\AudioLocal.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\AudioLocal.exe"; Description: "Abrir AudioLocal"; Flags: nowait postinstall skipifsilent
