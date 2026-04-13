; ════════════════════════════════════════════════════════════
; build/nexar_tienda.iss — Script de Inno Setup 6
;
; Genera un instalador profesional para Windows que:
;   - Instala en la carpeta del usuario (sin requerir admin)
;   - Crea acceso directo en el Escritorio (opcional)
;   - Crea entrada en el Menú Inicio
;   - Verifica WebView2 Runtime antes de instalar
;   - Incluye desinstalador automático
;
; Para compilar manualmente:
;   ISCC.exe /DAppVersion=1.17.0 build\nexar_tienda.iss
;
; GitHub Actions pasa la versión automáticamente.
; ════════════════════════════════════════════════════════════

; ── VERSIÓN DINÁMICA ─────────────────────────────────────────
; Si no se pasa /DAppVersion desde la línea de comando,
; usa "1.0.0" como valor por defecto
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

; Instala en la carpeta del usuario (no requiere permisos de admin)
DefaultDirName={userappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Salida del instalador
OutputDir=..\dist\installer
OutputBaseFilename=NexarTienda_{#AppVersion}_Setup

; Ícono del instalador
SetupIconFile=..\static\icons\nexar_tienda.ico

Compression=lzma2/ultra64
SolidCompression=yes

WizardStyle=modern
WizardResizable=no

; Sin requerir admin — el usuario instala en su perfil
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesInstallIn64BitMode=x64compatible

; Requiere Windows 10 mínimo (para WebView2)
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Opciones adicionales:"

[Files]
; Copia el ejecutable único generado por PyInstaller (OneFile mode)
Source: "..\dist\NexarTienda.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Sistema de gestión para tiendas"
Name: "{userprograms}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Sistema de gestión para tiendas"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel1=Bienvenido al instalador de {#AppName} v{#AppVersion}
WelcomeLabel2=Este asistente instalará {#AppName} en tu computadora.%n%nNexar Tienda es un sistema de gestión completo para comercios.%n%nCerrá todas las demás aplicaciones antes de continuar.
FinishedHeadingLabel=Instalación completada
FinishedLabel={#AppName} v{#AppVersion} se instaló correctamente.%n%nHacé clic en Finalizar para cerrar el asistente.

[Code]
// ── Verificar si WebView2 Runtime está instalado ──────────────
// WebView2 es el motor que usa pywebview para la ventana nativa.
// En Windows 10/11 actualizado ya viene con Edge (la mayoría de equipos).
// Este código avisa al usuario si falta, pero NO bloquea la instalación.
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  // Verificar en HKLM (instalación del sistema)
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv',
    Version
  );
  // Si no está en HKLM, verificar en HKCU (instalación del usuario)
  if not Result then
    Result := RegQueryStringValue(
      HKCU,
      'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv',
      Version
    );
end;

procedure InitializeWizard();
begin
  if not IsWebView2Installed() then
    MsgBox(
      'Atención: Microsoft WebView2 Runtime no está instalado.' + #13#10 + #13#10 +
      'Nexar Tienda puede funcionar sin él, pero la aplicación se abrirá ' +
      'en el navegador predeterminado en lugar de una ventana propia.' + #13#10 + #13#10 +
      'Para instalar WebView2 visitá: aka.ms/getwebview2' + #13#10 +
      '(suele estar incluido en Windows 10/11 actualizado)',
      mbInformation, MB_OK
    );
end;
