#ifndef AppVersion
  #define AppVersion "4.2.0"
#endif
#ifndef BuildRoot
  #define BuildRoot ".."
#endif
[Setup]
AppId={{F8CF01A7-8D9B-4426-AC13-DBB1B27C7A06}
AppName=CamCraft
AppVersion={#AppVersion}
AppVerName=CamCraft {#AppVersion}
AppPublisher=Davi Brand
AppPublisherURL=https://github.com/DragonBlack18/CamCraft
AppSupportURL=https://github.com/DragonBlack18/CamCraft/issues
AppUpdatesURL=https://github.com/DragonBlack18/CamCraft/releases
DefaultDirName={localappdata}\Programs\CamCraft
DefaultGroupName=CamCraft
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir={#BuildRoot}\release
OutputBaseFilename=CamCraft-Setup-{#AppVersion}-x64
SetupIconFile={#BuildRoot}\assets\camcraft.ico
UninstallDisplayIcon={app}\CamCraft.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile={#BuildRoot}\LICENSE
InfoBeforeFile={#BuildRoot}\packaging\INSTALL_NOTES.txt
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
[Files]
Source: "{#BuildRoot}\dist\CamCraft\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildRoot}\packaging\installed.marker"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\CamCraft"; Filename: "{app}\CamCraft.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\CamCraft"; Filename: "{app}\CamCraft.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\CamCraft.exe"; Description: "Abrir CamCraft"; Flags: nowait postinstall skipifsilent
; Deliberately no UninstallDelete for user data. Evidence lives outside {app}.
