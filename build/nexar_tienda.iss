; ════════════════════════════════════════════════════════════
; build/nexar_tienda.iss — Script de Inno Setup 6
; ════════════════════════════════════════════════════════════

#define AppName      "Nexar Tienda"
#define AppVersion   "1.17.0"
#define AppExeName   "NexarTienda.exe"
#define AppPublisher "Nexar Sistemas"

[Setup]
AppId={{B2C3D4E5-F6A7-8901-BCDE-F12345678901}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={userappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=..\dist\installer
OutputBaseFilename=NexarTienda_{#AppVersion}_Setup
SetupIconFile=..\static\icons\nexar_tienda.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Opciones adicionales:"

[Files]
Source: "..\dist\NexarTienda.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
end;

procedure InitializeWizard();
begin
  if not IsWebView2Installed() then
    MsgBox('Atención: Microsoft WebView2 Runtime no detectado.' + #13#10 + 
           'Se recomienda instalarlo para una mejor experiencia visual.', mbInformation, MB_OK);
end;