# ════════════════════════════════════════════════════════════
# build/nexar_tienda_linux.spec — Configuración de PyInstaller (Linux)
# ════════════════════════════════════════════════════════════

import os

PROJ = os.path.abspath(os.path.join(SPECPATH, '..'))

block_cipher = None

datas = [
    (os.path.join(PROJ, 'templates'), 'templates'),
    (os.path.join(PROJ, 'static'), 'static'),
    (os.path.join(PROJ, 'VERSION'), '.'),
    (os.path.join(PROJ, 'CHANGELOG.md'), '.'),
]

a = Analysis(
    [os.path.join(PROJ, 'iniciar.py')],
    pathex=[PROJ],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'flask', 'flask.helpers', 'flask.templating',
        'jinja2', 'jinja2.ext',
        'werkzeug', 'werkzeug.serving', 'werkzeug.routing', 'werkzeug.exceptions',
        'app', 'database',
        'openpyxl', 'reportlab', 'reportlab.lib.pagesizes',
        'reportlab.platypus', 'reportlab.lib.styles',
        'webview', 'webview.platforms', 'webview.platforms.gtk',
        'sqlite3', 'json', 'hashlib', 'uuid', 'socket',
        'threading', 'signal', 'webbrowser', 'importlib', 'importlib.util',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'pytest'],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJ, 'static', 'icons', 'nexar_tienda.ico'),
)
