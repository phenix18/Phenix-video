; Phenix-video — © 2026 Phenix - kcw. Installateur Windows (Inno Setup, construit par GitHub Actions).
; Installe sans droits administrateur dans %LOCALAPPDATA%\Programs\Phenix-video, crée les raccourcis.
#define AppVer GetEnv("PHENIX_VERSION")
[Setup]
AppName=Phenix-video
AppVersion={#AppVer}
AppPublisher=Phenix - kcw
DefaultDirName={localappdata}\Programs\Phenix-video
DefaultGroupName=Phenix-video
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Phenix-video-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\PhenixVideo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs
Source: "..\references\*"; DestDir: "{app}\references"; Flags: ignoreversion recursesubdirs
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Phenix-video"; Filename: "{app}\PhenixVideo.exe"; IconFilename: "{app}\assets\icon.ico"; WorkingDir: "{app}"
Name: "{autoprograms}\Phenix-video"; Filename: "{app}\PhenixVideo.exe"; IconFilename: "{app}\assets\icon.ico"; WorkingDir: "{app}"

[Run]
Filename: "{app}\PhenixVideo.exe"; Description: "Lancer Phenix-video (1re fois : installation des composants, quelques minutes)"; Flags: postinstall nowait skipifsilent
