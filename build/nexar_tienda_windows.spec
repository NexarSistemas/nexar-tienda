# ════════════════════════════════════════════════════════════
# build/nexar_tienda_windows.spec — PyInstaller (Windows)
#
# Cambios respecto a la versión anterior:
#   - console=False en producción, pero con sistema de logs
#   - Se agrega runtime hook para capturar errores al inicio
#   - Se incluye carpeta logs/ en los datos empaquetados
# ════════════════════════════════════════════════════════════

import os

PROJ = os.path.abspath(os.path.join(SPECPATH, '..'))

block_cipher = None

datas = [
    (os.path.join(PROJ, 'templates'),    'templates'),
    (os.path.join(PROJ, 'static'),       'static'),
    (os.path.join(PROJ, 'VERSION'),      '.'),
    (os.path.join(PROJ, 'CHANGELOG.md'), '.'),
]

# Incluir clave pública RSA sólo si existe la carpeta keys/
# En CI se escribe desde el secret PUBLIC_KEY antes de correr pyinstaller.
# Si no existe, la app busca la clave vía variable de entorno PUBLIC_KEY.
_keys_dir = os.path.join(PROJ, 'keys')
if os.path.isdir(_keys_dir):
    datas.append((_keys_dir, 'keys'))

a = Analysis(
    [os.path.join(PROJ, 'iniciar.py')],
    pathex=[PROJ],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Flask y dependencias web
        'flask',
        'flask.helpers',
        'flask.templating',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'werkzeug.exceptions',
        # Módulos del proyecto
        'app',
        'database',
        # Exportaciones
        'openpyxl',
        'reportlab',
        'reportlab.lib.pagesizes',
        'reportlab.platypus',
        'reportlab.lib.styles',
        # pywebview — en Windows usa WinForms + WebView2 (Edge Chromium)
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        # pythonnet — necesario para WinForms y acceso a .NET
        'clr',
        # stdlib
        'sqlite3',
        'json',
        'hashlib',
        'uuid',
        'socket',
        'threading',
        'signal',
        'webbrowser',
        'importlib',
        'importlib.util',
        'ctypes',
        'ctypes.wintypes',
        # logging — necesario para el sistema de logs de error
        'logging',
        'logging.handlers',
        'traceback',
    ],
    hookspath=[os.path.join(PROJ, 'build', 'hooks')],  # hooks personalizados
    hooksconfig={},
    runtime_hooks=[
        os.path.join(PROJ, 'build', 'hooks', 'rthook_error_logger.py')
    ],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'pytest',
        'webview.platforms.gtk',
        'gi',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NexarTienda',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # Sin consola negra en producción
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJ, 'static', 'icons', 'nexar_tienda.ico'),
)
