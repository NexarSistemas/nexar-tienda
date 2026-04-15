# ════════════════════════════════════════════════════════════
# build/nexar_tienda_linux.spec — PyInstaller (Linux)
#
# Genera un único binario ejecutable para Linux.
# Modo OneFile: todo incluido en un solo archivo.
#
# Para compilar manualmente desde la raíz del proyecto:
#   pyinstaller build/nexar_tienda_linux.spec \
#     --distpath dist --workpath build/work --noconfirm
# ════════════════════════════════════════════════════════════

import os

# SPECPATH = directorio del .spec (build/)
# PROJ     = raíz del proyecto (un nivel arriba)
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
        # pywebview — en Linux usa GTK/webkit
        'webview',
        'webview.platforms',
        'webview.platforms.gtk',
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'pytest',
        # Módulos exclusivos de Windows — no incluir en Linux
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr',
        'pythonnet',
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
    a.binaries,     # OneFile: binarios embebidos en el ejecutable
    a.datas,
    [],
    name='NexarTienda',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,     # Reduce el tamaño del binario en Linux
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Sin ventana de terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # En Linux no se usa .ico — se omite icon= para evitar errores
)
