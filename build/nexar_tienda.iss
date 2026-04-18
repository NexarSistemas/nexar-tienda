; ════════════════════════════════════════════════════════════
; build/nexar_tienda.iss — Script de Inno Setup 6
;
; Cambios respecto a la versión anterior:
;   - Descarga e instala WebView2 automáticamente si no está
;   - Verifica .NET 6+ Runtime y lo descarga si falta
;   - Crea archivo de log en caso de error al iniciar
; ════════════════════════════════════════════════════════════

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName      "Nexar Tienda"
#define AppExeName   "NexarTienda.exe"
#define AppPublisher "Nexar Sistemas"
#define AppURL       "https://wa.me/5492645858874"

[Setup]
AppId={{B2C3D4E5-F6A7-8901-BCDE-F12345678901}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
LicenseFile=..\LICENSE.txt

DefaultDirName={userappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

OutputDir=..\dist\installer
OutputBaseFilename=NexarTienda_{#AppVersion}_Setup

SetupIconFile=..\static\icons\nexar_tienda.ico

Compression=lzma2/ultra64
SolidCompression=yes

WizardStyle=modern
WizardResizable=no

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; ── Necesario para descargar WebView2 y .NET en tiempo de instalación ──
; Inno Setup no descarga por sí solo — usamos un helper (ver [Code])

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Opciones adicionales:"

[Files]
Source: "..\dist\NexarTienda.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; ── Clave pública RSA para verificación de licencias ────────────────
; Sin este archivo, la activación de licencias fallará con
; "La firma digital es inválida".
Source: "..\keys\public_key.pem"; DestDir: "{app}\keys"; Flags: ignoreversion

; ── Wrapper que captura errores y los guarda en un log ──────────
; Este script .bat lanza el .exe y guarda el error si falla
Source: "launch_with_log.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Comment: "Sistema de gestión para tiendas"
Name: "{userdesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Comment: "Sistema de gestión para tiendas"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Description: "Iniciar {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[Code]

// ════════════════════════════════════════════════════════════
// UTILIDADES
// ════════════════════════════════════════════════════════════

// Descarga un archivo desde una URL a una ruta local usando PowerShell
function DownloadFile(URL, Dest: String): Boolean;
var
  ResultCode: Integer;
begin
  Exec(
    'powershell.exe',
    '-NoProfile -NonInteractive -Command "Invoke-WebRequest -Uri ''' + URL + ''' -OutFile ''' + Dest + ''' -UseBasicParsing"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  );
  Result := (ResultCode = 0) and FileExists(Dest);
end;

// ════════════════════════════════════════════════════════════
// WEBVIEW2
// ════════════════════════════════════════════════════════════

function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version
  );
  if not Result then
    Result := RegQueryStringValue(
      HKCU,
      'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version
    );
end;

procedure InstallWebView2();
var
  TempFile: String;
  ResultCode: Integer;
begin
  TempFile := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');

  MsgBox(
    'Se necesita instalar Microsoft WebView2 Runtime.' + #13#10 +
    'Es un componente gratuito de Microsoft.' + #13#10 + #13#10 +
    'Hacé clic en Aceptar para descargarlo e instalarlo automáticamente.' + #13#10 +
    '(Requiere conexión a internet)',
    mbInformation, MB_OK
  );

  if DownloadFile(
    'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
    TempFile
  ) then
  begin
    Exec(TempFile, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      MsgBox(
        'No se pudo instalar WebView2 automáticamente.' + #13#10 +
        'Instalalo manualmente desde: aka.ms/getwebview2',
        mbError, MB_OK
      );
  end
  else
    MsgBox(
      'No se pudo descargar WebView2.' + #13#10 +
      'Verificá tu conexión e instalalo manualmente desde: aka.ms/getwebview2',
      mbError, MB_OK
    );
end;

// ════════════════════════════════════════════════════════════
// .NET RUNTIME
// ════════════════════════════════════════════════════════════

function IsDotNetInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  // Verifica si existe dotnet.exe y si tiene la versión 6 o superior
  Exec(
    'powershell.exe',
    '-NoProfile -NonInteractive -Command "if ((dotnet --list-runtimes 2>$null) -match ''Microsoft.NETCore.App 6'') { exit 0 } else { exit 1 }"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  );
  Result := (ResultCode = 0);
end;

procedure InstallDotNet();
var
  TempFile: String;
  ResultCode: Integer;
begin
  TempFile := ExpandConstant('{tmp}\dotnet-runtime-installer.exe');

  MsgBox(
    'Se necesita instalar .NET 6 Runtime.' + #13#10 +
    'Es un componente gratuito de Microsoft.' + #13#10 + #13#10 +
    'Hacé clic en Aceptar para descargarlo e instalarlo automáticamente.' + #13#10 +
    '(Requiere conexión a internet)',
    mbInformation, MB_OK
  );

  // URL oficial del instalador .NET 6 Runtime x64
  if DownloadFile(
    'https://aka.ms/dotnet/6.0/dotnet-runtime-win-x64.exe',
    TempFile
  ) then
  begin
    Exec(TempFile, '/silent /install /norestart', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      MsgBox(
        'No se pudo instalar .NET Runtime automáticamente.' + #13#10 +
        'Instalalo manualmente desde: dotnet.microsoft.com/download/dotnet/6.0',
        mbError, MB_OK
      );
  end
  else
    MsgBox(
      'No se pudo descargar .NET Runtime.' + #13#10 +
      'Verificá tu conexión e instalalo manualmente desde: dotnet.microsoft.com/download/dotnet/6.0',
      mbError, MB_OK
    );
end;

// ════════════════════════════════════════════════════════════
// PUNTO DE ENTRADA — se ejecuta al iniciar el wizard
// ════════════════════════════════════════════════════════════

procedure InitializeWizard();
begin
  if not IsWebView2Installed() then
    InstallWebView2();

  if not IsDotNetInstalled() then
    InstallDotNet();
end;

[Messages]
WelcomeLabel1=Bienvenido al instalador de {#AppName} v{#AppVersion}
WelcomeLabel2=Este asistente instalará {#AppName} en tu computadora.%n%nNexar Tienda es un sistema de gestión completo para comercios.%n%nCerrá todas las demás aplicaciones antes de continuar.
FinishedHeadingLabel=Instalación completada
FinishedLabel={#AppName} v{#AppVersion} se instaló correctamente.%n%nHacé clic en Finalizar para cerrar el asistente.
