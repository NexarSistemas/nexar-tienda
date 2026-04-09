# 🗺️ Nexar Tienda — Pasos Faltantes (Paso 24 → Paso 29)

> **Base:** versión `v1.13.0` con 23 pasos completados.
> **Referencia:** Nexar Almacén como guía estructural.
> **Stack:** Python 3.11 · Flask 3.0 · SQLite · Bootstrap 5.3 · Font Awesome 6.4
> **Paleta:** Navy blue `#1e3a5f` con acentos plateados.

---

## Estado actual (resumen hasta Paso 23)

| Paso | Módulo | Versión | Estado |
|------|--------|---------|--------|
| 3–14 | Login, ABM, Stock, POS, Clientes, Proveedores, Compras, Caja, Gastos, Estadísticas, Usuarios, Temporadas DB | v0.1.1–v1.4.0 | ✅ |
| 15 | Temporadas: rutas CRUD | v1.5.0 | ✅ |
| 16 | Respaldo: panel UI | v1.6.0 | ✅ |
| 17 | Configuración del sistema | v1.7.0 | ✅ |
| 18 | Historial de ventas | v1.8.0 | ✅ |
| 19 | Estadísticas avanzadas | v1.9.0 | ✅ |
| 20 | Exportación Excel / PDF | v1.10.0 | ✅ |
| 21 | Páginas informativas | v1.11.0 | ✅ |
| 22 | Apagado controlado | v1.12.0 | ✅ |
| 23 | Sidebar: refactorización y navegación | v1.13.0 | ✅ |

---

## Análisis comparativo: Tienda vs Almacén

Luego de revisar ambos proyectos se identificaron las siguientes brechas:

| Característica | Nexar Almacén | Nexar Tienda | Estado |
|---|---|---|---|
| Sistema de licencias propio (DEMO/BASICA/PRO) | ✅ con `machine_id` y tiers | ✅ parcial — sin pantalla de activación manual por código | ⚠️ Brecha menor |
| `SECRET_KEY` desde GitHub Secret | ✅ via `.env` generado en CI/CD | ✅ ya implementado en `app.py` | ✅ OK |
| Build Windows (.exe + instalador Inno Setup) | ✅ `.github/workflows/build.yml` | ❌ No existe | ❌ Faltante |
| Build Linux (.deb) | ✅ `build_deb.sh` + workflow | ❌ No existe | ❌ Faltante |
| Ventana nativa (pywebview) | ✅ `iniciar.py` con webview | ❌ Solo `iniciar.sh` / `iniciar.bat` | ❌ Faltante |
| Cierre desde login (botón + SweetAlert2) | ✅ | ⚠️ Solo en sidebar con `confirm()` nativo | ⚠️ Brecha |
| Cartel SweetAlert2 al cerrar sistema | ✅ SweetAlert2 | ⚠️ `confirm()` del navegador | ⚠️ Brecha |
| Banner licencia DEMO en topbar | ✅ | ⚠️ Sin banner visible | ⚠️ Brecha |
| `iniciar.py` como launcher universal | ✅ | ❌ No existe | ❌ Faltante |
| Spec PyInstaller | ✅ | ❌ No existe | ❌ Faltante |
| `.github/workflows/build.yml` | ✅ | ❌ No existe | ❌ Faltante |

---

---

## PASO 24 — Launcher `iniciar.py` + ventana nativa (pywebview) 🖥️

**Versión objetivo:** `v1.14.0`
**Prioridad:** 🔴 Alta — Nexar Almacén lo tiene. Es la base para el build ejecutable.

### Problema a resolver

Nexar Tienda arranca con `iniciar.sh` / `iniciar.bat`, que son scripts de shell
que ejecutan `python app.py` directamente. Esto obliga al usuario a tener Python
instalado y no genera una ventana de aplicación propia.

Nexar Almacén tiene `iniciar.py`, un **launcher Python** que:
1. Verifica e instala dependencias automáticamente.
2. Busca un puerto libre (no usa siempre el 5000).
3. Abre una ventana nativa con **pywebview** si está disponible.
4. Si pywebview no está, abre el navegador predeterminado.
5. Invalida sesiones al cerrar.
6. Es el punto de entrada del `.exe` generado por PyInstaller.

### Archivos a crear

- `iniciar.py` — launcher principal (nuevo)

### Archivos a modificar

- `iniciar.sh` — reemplazar por: `python3 iniciar.py`
- `iniciar.bat` — reemplazar por: `python iniciar.py`

### Código: `iniciar.py`

```python
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║   NEXAR TIENDA  —  v1.14.0                                           ║
║   Creado por Nexar Sistemas · Desarrollado con Claude.ai · 2026     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sys

# Fix encoding para consola Windows (cp1252 no soporta Unicode)
if sys.platform == 'win32':
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import os
import subprocess
import threading
import time
import webbrowser
import socket
import signal
import importlib.util

# Cuando corre como .exe de PyInstaller los archivos están en sys._MEIPASS
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

IS_WIN    = sys.platform == 'win32'
IS_FROZEN = getattr(sys, 'frozen', False)

PORT_FILE = os.path.join(BASE_DIR, '.port')

# En Windows, la DB va a AppData para evitar problemas de permisos
if os.name == 'nt' and not os.environ.get('TIENDA_DB_PATH'):
    _appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
    _data_dir = os.path.join(_appdata, 'nexartienda')
    os.makedirs(_data_dir, exist_ok=True)
    os.environ['TIENDA_DB_PATH'] = os.path.join(_data_dir, 'tienda.db')

# ─────────────────────────────────────────────
# Colores consola
# ─────────────────────────────────────────────
def verde(t):   return f'\033[92m{t}\033[0m'
def rojo(t):    return f'\033[91m{t}\033[0m'
def bold(t):    return f'\033[1m{t}\033[0m'
def amarillo(t):return f'\033[93m{t}\033[0m'
def cyan(t):    return f'\033[96m{t}\033[0m'


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


# ─────────────────────────────────────────────
# Instalar dependencias obligatorias
# ─────────────────────────────────────────────
def install_required():
    if IS_FROZEN:
        return

    needed = [
        p for p in ('flask', 'openpyxl', 'reportlab', 'python-dotenv')
        if not has_module(p.replace('-', '_'))
    ]
    if not needed:
        return

    print(amarillo(f'  Instalando dependencias: {", ".join(needed)} ...'))
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '-q',
             '--break-system-packages'] + needed
        )
        print(verde('  ✓ Dependencias instaladas'))
    except Exception:
        print(rojo('  No se pudieron instalar dependencias'))
        sys.exit(1)


# ─────────────────────────────────────────────
# Instalar pywebview en background (no bloquea)
# ─────────────────────────────────────────────
def try_install_webview_background():
    if IS_FROZEN or has_module('webview'):
        return

    def _install():
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install',
                 'pywebview', '-q', '--break-system-packages']
            )
        except Exception:
            pass

    threading.Thread(target=_install, daemon=True).start()


# ─────────────────────────────────────────────
# Puerto libre
# ─────────────────────────────────────────────
def get_free_port(start=5200, end=5999):
    import random
    ports = list(range(start, end))
    random.shuffle(ports)
    for p in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', p))
                return p
        except Exception:
            continue
    return 5000


def save_port(port):
    try:
        with open(PORT_FILE, 'w') as f:
            f.write(str(port))
    except Exception:
        pass


# ─────────────────────────────────────────────
# Invalidar sesiones activas
# ─────────────────────────────────────────────
def invalidate_sessions():
    try:
        import database as db
        from datetime import datetime
        db.set_config({'sessions_invalidated_at': datetime.now().isoformat()})
    except Exception:
        pass


# ─────────────────────────────────────────────
# Esperar que Flask levante
# ─────────────────────────────────────────────
def wait_for_server(host, port):
    for _ in range(40):
        time.sleep(0.25)
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except Exception:
            pass
    return False


# ─────────────────────────────────────────────
# Banner de inicio
# ─────────────────────────────────────────────
def _read_version():
    try:
        return open(os.path.join(BASE_DIR, 'VERSION')).read().strip()
    except Exception:
        return '1.14.0'


def print_banner(url):
    ver = _read_version()
    titulo = f'  🛍️  NEXAR TIENDA  v{ver}  '
    print()
    print(verde('╔' + '═' * 54 + '╗'))
    print(verde('║') + bold(titulo.ljust(54)) + '   ' + verde('║'))
    print(verde('╠' + '═' * 54 + '╣'))
    print(verde('║') + f'  URL:    {url}'.ljust(54) + verde('║'))
    print(verde('║') + '  Login:  admin  /  admin123'.ljust(54) + verde('║'))
    print(verde('║') + '  Ctrl+C para cerrar'.ljust(54) + verde('║'))
    print(verde('╚' + '═' * 54 + '╝'))
    print()


# ─────────────────────────────────────────────
# Señal de salida
# ─────────────────────────────────────────────
def on_exit(signum=None, frame=None):
    print('\n' + amarillo('  Cerrando sistema...'))
    invalidate_sessions()
    print(verde('  ✓ Sistema cerrado\n'))
    sys.exit(0)

signal.signal(signal.SIGTERM, on_exit)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print(bold('\n  Iniciando Nexar Tienda...\n'))

    print('  Verificando dependencias...', end=' ', flush=True)
    install_required()
    print(verde('OK'))

    try_install_webview_background()

    print('  Iniciando base de datos...', end=' ', flush=True)
    try:
        import database as db
        db.init_db()
        print(verde('OK'))
    except Exception as e:
        print(rojo(str(e)))
        sys.exit(1)

    print('  Buscando puerto libre...', end=' ', flush=True)
    PORT = get_free_port()
    HOST = '127.0.0.1'
    URL  = f'http://{HOST}:{PORT}'
    save_port(PORT)
    print(verde(f'OK (puerto {PORT})'))

    print('  Cargando aplicación...', end=' ', flush=True)
    try:
        from app import app as flask_app
        print(verde('OK'))
    except Exception as e:
        print(rojo(str(e)))
        sys.exit(1)

    print_banner(URL)

    # ─── Flask en hilo separado
    def start_flask():
        flask_app.run(
            host=HOST,
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True
        )

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    wait_for_server(HOST, PORT)

    # ─── UI: ventana nativa o navegador
    if has_module('webview'):
        import webview
        print(cyan('  > Ventana independiente abierta (modo app nativa)'))
        webview.create_window(
            'Nexar Tienda',
            URL,
            width=1280,
            height=800,
            min_size=(900, 600),
            resizable=True,
            confirm_close=True        # ← Cartel nativo al intentar cerrar
        )
        webview.start()
        invalidate_sessions()
        sys.exit(0)
    else:
        print(cyan(f'  → Abriendo en navegador: {URL}'))
        webbrowser.open(URL)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
```

### Modificar `iniciar.sh`

Reemplazar todo el contenido por:

```bash
#!/bin/bash
cd "$(dirname "$0")"
python3 iniciar.py
```

### Modificar `iniciar.bat`

Reemplazar todo el contenido por:

```bat
@echo off
cd /d "%~dp0"
python iniciar.py
pause
```

### Verificar que funciona

```bash
# Desde la raíz del proyecto
python3 iniciar.py
# Debe mostrar el banner, abrir ventana nativa o el navegador
# y responder en http://127.0.0.1:<puerto>
```

### Commit sugerido

```bash
git add iniciar.py iniciar.sh iniciar.bat
git commit -m "feat(launcher): iniciar.py con ventana nativa pywebview - Paso 24 v1.14.0"
git tag v1.14.0
git push origin main --tags
```

---

---

## PASO 25 — Cartel SweetAlert2 para cierre del sistema 🔔

**Versión objetivo:** `v1.15.0`
**Prioridad:** 🔴 Alta — El `confirm()` nativo del navegador es visualmente inconsistente y no combina con la paleta del sistema.

### Problema a resolver

Nexar Tienda ya tiene los botones de "Cerrar sistema" en `base.html` y "Apagar
sistema" en `login.html`, pero usa el `confirm()` estándar del navegador.
Nexar Almacén usa **SweetAlert2** para ambos carteles, logrando una experiencia
visual consistente con la paleta navy blue del sistema.

Además, el botón de apagado **no existe** en `login.html` de Nexar Tienda. Hay
que crearlo.

### Archivos a modificar

- `templates/base.html` — reemplazar `onsubmit="return confirm(...)"` por función SweetAlert2
- `templates/login.html` — agregar botón de apagado con SweetAlert2

### Cambios en `templates/base.html`

**1. Agregar SweetAlert2 al final del `<head>` o antes de `{% block scripts %}`:**

```html
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
```

**2. Reemplazar el botón de cerrar sistema (buscar el `<form>` con `apagar_sistema`):**

```html
<!-- ANTES (borrar esto): -->
<form method="POST" action="{{ url_for('apagar_sistema') }}"
      onsubmit="return confirm('¿Cerrar el sistema? Se cerrarán todas las sesiones activas.')" class="px-3">
    <button type="submit" class="btn btn-sm btn-outline-danger w-100">
        <i class="fas fa-power-off me-1"></i>Cerrar sistema
    </button>
</form>

<!-- DESPUÉS (poner esto): -->
<form id="form-apagar" method="POST" action="{{ url_for('apagar_sistema') }}" class="px-3">
    <button type="button" onclick="confirmarApagado()"
            class="btn btn-sm btn-outline-danger w-100">
        <i class="fas fa-power-off me-1"></i>Cerrar sistema
    </button>
</form>
```

**3. Agregar función JavaScript antes de `{% block scripts %}`:**

```html
<script>
function confirmarApagado() {
    Swal.fire({
        title: '¿Cerrar el sistema?',
        text: 'Se cerrará la conexión con el servidor y todas las sesiones activas.',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#c62828',
        cancelButtonColor: '#3a5a8f',
        confirmButtonText: 'Sí, cerrar ahora',
        cancelButtonText: 'Cancelar',
        background: '#1a2a3f',
        color: '#ffffff'
    }).then((result) => {
        if (result.isConfirmed) {
            document.getElementById('form-apagar').submit();
        }
    });
}
</script>
```

### Cambios en `templates/login.html`

**1. Agregar botón de apagado en el pie del formulario de login:**

Buscar el bloque `{% block content %}` y agregar al pie de la tarjeta de login:

```html
<!-- Al pie del card de login, antes del cierre </div> de login-card -->
<div class="text-center mt-4" style="border-top:1px solid #dee2e6; padding-top:12px;">
    <form id="form-apagar-login" method="POST" action="{{ url_for('apagar_rapido') }}"
          style="margin-bottom:8px;">
        <button type="button" onclick="confirmarApagadoLogin()"
                style="background:none;border:1px solid #ccc;border-radius:6px;
                       padding:4px 14px;font-size:.78rem;color:#999;cursor:pointer;
                       transition:all .2s"
                onmouseover="this.style.background='#fff0f0';this.style.color='#c62828';this.style.borderColor='#c62828'"
                onmouseout="this.style.background='none';this.style.color='#999';this.style.borderColor='#ccc'">
            <i class="fas fa-power-off me-1"></i>Apagar sistema
        </button>
    </form>
    <small class="text-muted">Nexar Tienda · v{{ app_version }}</small>
</div>
```

**2. Agregar SweetAlert2 y función JS al final de `login.html`:**

```html
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
<script>
function confirmarApagadoLogin() {
    Swal.fire({
        title: '¿Apagar el sistema?',
        text: 'El servidor dejará de responder inmediatamente.',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#c62828',
        cancelButtonColor: '#6c757d',
        confirmButtonText: 'Sí, apagar ahora',
        cancelButtonText: 'Cancelar',
        background: '#ffffff',
        color: '#333333'
    }).then((result) => {
        if (result.isConfirmed) {
            document.getElementById('form-apagar-login').submit();
        }
    });
}
</script>
```

### Verificación

1. Abrir el sistema e intentar cerrar desde el sidebar → debe aparecer el cartel SweetAlert2 con paleta oscura.
2. Cerrar sesión y desde la pantalla de login, hacer click en "Apagar sistema" → debe aparecer el cartel SweetAlert2 con fondo blanco.
3. Verificar que "Cancelar" en ambos casos NO envía el formulario.

### Commit sugerido

```bash
git add templates/base.html templates/login.html
git commit -m "ux(apagado): reemplazar confirm() por SweetAlert2 en sidebar y login - Paso 25 v1.15.0"
git tag v1.15.0
git push origin main --tags
```

---

---

## PASO 26 — Banner de licencia DEMO y mejoras de usabilidad 🎨

**Versión objetivo:** `v1.16.0`
**Prioridad:** 🟠 Media-Alta — Sin el banner de DEMO el usuario no sabe en qué modo está. Además hay mejoras de UX menores pendientes.

### Problema a resolver

Nexar Almacén muestra un banner visible en el topbar cuando la licencia está en
modo DEMO o próxima a vencer. Nexar Tienda no tiene este aviso, y el usuario
puede usar el sistema indefinidamente en DEMO sin saberlo ni ver ningún recordatorio.

Adicionalmente, se identificaron mejoras de usabilidad:
- El sidebar no tiene un estado activo visual claro para la página actual.
- Los mensajes flash desaparecen solos (no tienen auto-dismiss).
- La topbar no muestra el nombre del negocio configurado.

### Archivos a modificar

- `templates/base.html` — banner DEMO + mejoras de topbar + auto-dismiss flash + nav activo

### Cambios en `templates/base.html`

**1. Banner de licencia DEMO (agregar después del `<div id="main">`):**

```html
<!-- Banner de estado de licencia -->
{% set lic = get_licencia_status() %}
{% if lic and lic.es_demo %}
    {% if lic.vencido %}
    <div style="background:#c62828;color:#fff;padding:8px 16px;text-align:center;font-size:.85rem;">
        <i class="fas fa-lock me-2"></i>
        <strong>DEMO VENCIDA.</strong>
        Tu período de prueba de 30 días ha finalizado.
        <a href="{{ url_for('licencia') }}" style="color:#ffd;font-weight:700;margin-left:8px;">
            Activar licencia →
        </a>
    </div>
    {% elif lic.aviso_proximo %}
    <div style="background:#e65100;color:#fff;padding:8px 16px;text-align:center;font-size:.85rem;">
        <i class="fas fa-clock me-2"></i>
        <strong>Demo — {{ lic.dias_restantes }} días restantes.</strong>
        Activá tu licencia para uso sin límites.
        <a href="{{ url_for('licencia') }}" style="color:#ffd;font-weight:700;margin-left:8px;">
            Ver opciones →
        </a>
    </div>
    {% endif %}
{% endif %}
```

**2. Función `get_licencia_status()` en `app.py` (context_processor):**

```python
@app.context_processor
def inject_licencia():
    """Inyecta el estado de licencia en todos los templates."""
    def get_licencia_status():
        try:
            info = db.get_license_info()
            tier = info.get('tier', 'DEMO')
            es_demo = (tier == 'DEMO')
            dias = 0
            vencido = False
            aviso_proximo = False
            if es_demo and info.get('activated_at'):
                from datetime import datetime
                activado = datetime.fromisoformat(info['activated_at'])
                dias_usados = (datetime.now() - activado).days
                dias = max(0, 30 - dias_usados)
                vencido = (dias == 0)
                aviso_proximo = (0 < dias <= 7)
            return {
                'es_demo': es_demo,
                'dias_restantes': dias,
                'vencido': vencido,
                'aviso_proximo': aviso_proximo,
                'tier': tier
            }
        except Exception:
            return {'es_demo': False}
    return {'get_licencia_status': get_licencia_status}
```

**3. Nombre del negocio en la topbar:**

Buscar el `<div class="tb-actions">` o topbar y agregar:

```html
<span class="text-muted" style="font-size:.82rem;">
    <i class="fas fa-store me-1"></i>
    {{ get_config_valor('negocio_nombre', 'Nexar Tienda') }}
</span>
```

Agregar al `context_processor` la función `get_config_valor`:

```python
# Dentro del mismo @app.context_processor inject_licencia (o en uno nuevo)
def get_config_valor(clave, default=''):
    try:
        return db.get_config().get(clave, default)
    except Exception:
        return default
```

**4. Auto-dismiss de mensajes flash (agregar en el bloque JS de base.html):**

```javascript
// Auto-ocultar mensajes flash después de 4 segundos
document.addEventListener('DOMContentLoaded', function () {
    const flashes = document.querySelectorAll('[class^="flash-"]');
    flashes.forEach(function (el) {
        setTimeout(function () {
            el.style.transition = 'opacity 0.5s';
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 500);
        }, 4000);
    });
});
```

**5. Clase activa en el sidebar:**

En cada `<a class="nav-link"` del sidebar, agregar la condición de clase activa:

```html
<!-- Patrón a aplicar en cada enlace del sidebar -->
<a class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}"
   href="{{ url_for('dashboard') }}">
    <i class="fas fa-tachometer-alt me-2"></i>Dashboard
</a>
```

> **Nota:** repetir para cada enlace, usando el nombre de la función de la ruta
> correspondiente como valor del `request.endpoint`.

### Commit sugerido

```bash
git add templates/base.html app.py
git commit -m "ux(licencia): banner DEMO, nombre negocio en topbar, auto-dismiss flash, nav activo - Paso 26 v1.16.0"
git tag v1.16.0
git push origin main --tags
```

---

---

## PASO 27 — Infraestructura de build: `spec`, `.iss` y `build_deb.sh` 🔧

**Versión objetivo:** `v1.17.0`
**Prioridad:** 🔴 Alta — Sin esta infraestructura no hay builds automáticos ni distribución.

### Problema a resolver

Nexar Tienda no tiene ningún archivo de build. Para poder generar el ejecutable
de Windows y el paquete `.deb` de Linux (como Nexar Almacén) se necesitan
tres archivos que no existen todavía.

### Archivos a crear

- `build/nexar_tienda.spec` — configuración de PyInstaller
- `build/nexar_tienda.iss` — script de Inno Setup 6 para Windows
- `build_deb.sh` — generador del paquete `.deb` para Linux

---

### Código: `build/nexar_tienda.spec`

```python
# ════════════════════════════════════════════════════════════
# build/nexar_tienda.spec — Configuración de PyInstaller
#
# Genera un único .exe que incluye todo lo necesario para
# ejecutar Nexar Tienda sin instalar Python.
#
# Para compilar manualmente desde la raíz del proyecto:
#   pyinstaller build/nexar_tienda.spec --distpath dist --noconfirm
# ════════════════════════════════════════════════════════════

import os

PROJ = os.path.abspath(os.path.join(SPECPATH, '..'))

block_cipher = None

datas = [
    (os.path.join(PROJ, 'templates'),    'templates'),
    (os.path.join(PROJ, 'static'),       'static'),
    (os.path.join(PROJ, 'services'),     'services'),
    (os.path.join(PROJ, 'VERSION'),      '.'),
    (os.path.join(PROJ, 'CHANGELOG.md'), '.'),
]

a = Analysis(
    scripts=[os.path.join(PROJ, 'iniciar.py')],
    pathex=[PROJ],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Flask y dependencias
        'flask', 'flask.helpers', 'flask.templating',
        'jinja2', 'jinja2.ext',
        'werkzeug', 'werkzeug.serving', 'werkzeug.routing', 'werkzeug.exceptions',
        'click',
        # Módulos del proyecto
        'app', 'database', 'services',
        # Exportaciones
        'openpyxl', 'reportlab', 'reportlab.lib.pagesizes',
        'reportlab.platypus', 'reportlab.lib.styles',
        # pywebview — ventana nativa
        'webview', 'webview.util', 'webview.window', 'webview.event',
        'webview.screen', 'webview.guilib',
        'webview.platforms', 'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr', 'clr._extra_clr_loader',
        # Estándar Python
        'sqlite3', 'json', 'hashlib', 'uuid', 'socket',
        'threading', 'signal', 'webbrowser', 'importlib', 'importlib.util',
        'calendar', 'zipfile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        'PIL', 'scipy', 'cryptography', 'pytest',
        'docutils', 'pydoc',
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
    console=False,        # Sin ventana de consola negra
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJ, 'static', 'icons', 'nexar_tienda_ico.ico'),
)
```

> **Nota:** crear el ícono `static/icons/nexar_tienda_ico.ico` antes de compilar.
> Puede generarse desde una imagen PNG con herramientas online o con Pillow.

---

### Código: `build/nexar_tienda.iss`

```ini
; ════════════════════════════════════════════════════════════
; build/nexar_tienda.iss — Script de Inno Setup 6
; Para compilar: ISCC.exe /DAppVersion=1.17.0 build\nexar_tienda.iss
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

DefaultDirName={userappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

OutputDir=..\dist\installer
OutputBaseFilename=NexarTienda_{#AppVersion}_Setup

SetupIconFile=..\static\icons\nexar_tienda_ico.ico
LicenseFile=..\LICENSE

Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Opciones adicionales:"

[Files]
Source: "..\dist\NexarTienda.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Sistema de gestión para tiendas de regalos"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
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
```

---

### Código: `build_deb.sh`

```bash
#!/bin/bash
# ============================================================
# build_deb.sh — Genera el paquete .deb para Nexar Tienda
# Uso: bash build_deb.sh
# Requiere: dpkg-deb, python3
# ============================================================

set -e

VERSION="$(cat VERSION)"
PACKAGE="nexar-tienda"
ARCH="all"
MAINTAINER="Nexar Sistemas <nexarsistemas@outlook.com.ar>"
DESCRIPTION="Nexar Tienda — v${VERSION}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build_deb"
PKG_DIR="${BUILD_DIR}/${PACKAGE}_${VERSION}"
INSTALL_DIR="${PKG_DIR}/opt/nexar-tienda"
DEBIAN_DIR="${PKG_DIR}/DEBIAN"

echo "=================================================="
echo "  Nexar Tienda — Builder .deb v${VERSION}"
echo "=================================================="

rm -rf "${BUILD_DIR}"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${DEBIAN_DIR}"
mkdir -p "${PKG_DIR}/usr/local/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/pixmaps"

echo "→ Copiando archivos del sistema..."

cp "${SCRIPT_DIR}/iniciar.py"   "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/app.py"       "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/database.py"  "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/VERSION"      "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/CHANGELOG.md" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/README.md"    "${INSTALL_DIR}/"

cp -r "${SCRIPT_DIR}/templates" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/static"    "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/services"  "${INSTALL_DIR}/"

# Icono
if [ -f "${SCRIPT_DIR}/static/icons/nexar_tienda_ico.png" ]; then
    cp "${SCRIPT_DIR}/static/icons/nexar_tienda_ico.png" \
       "${PKG_DIR}/usr/share/pixmaps/nexar-tienda.png"
fi

# Limpieza
find "${INSTALL_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "${INSTALL_DIR}" -name "*.pyc" -delete 2>/dev/null || true
find "${INSTALL_DIR}" -name "*.db"  -delete 2>/dev/null || true

echo "→ Creando lanzador..."

cat > "${PKG_DIR}/usr/local/bin/tienda" << 'EOF'
#!/bin/bash
export TIENDA_DB_PATH="${HOME}/.local/share/nexartienda/tienda.db"
mkdir -p "${HOME}/.local/share/nexartienda"
cd /opt/nexar-tienda
python3 iniciar.py
EOF
chmod +x "${PKG_DIR}/usr/local/bin/tienda"

echo "→ Creando entrada de menú de escritorio..."

cat > "${PKG_DIR}/usr/share/applications/nexar-tienda.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Nexar Tienda
Comment=Sistema de gestión para tiendas de regalos
Exec=/usr/local/bin/tienda
Icon=nexar-tienda
Terminal=false
Categories=Office;Finance;
EOF

echo "→ Creando metadatos del paquete..."

cat > "${DEBIAN_DIR}/control" << EOF
Package: ${PACKAGE}
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: ${MAINTAINER}
Depends: python3 (>= 3.11)
Section: misc
Priority: optional
Homepage: https://wa.me/5492645858874
Description: ${DESCRIPTION}
 Sistema completo de gestión para tiendas de regalos y accesorios.
EOF

cat > "${DEBIAN_DIR}/postinst" << 'EOF'
#!/bin/bash
set -e
echo "Instalando dependencias de Nexar Tienda..."
python3 -m pip install --quiet --break-system-packages --ignore-installed \
    flask openpyxl reportlab pywebview python-dotenv || \
echo "Nota: algunas dependencias pueden instalarse al primer inicio."
chmod +x /usr/local/bin/tienda
chmod -R a+rX /opt/nexar-tienda
echo ""
echo "============================================"
echo " Nexar Tienda instalado correctamente"
echo "============================================"
echo " Ejecutar: tienda"
echo "============================================"
exit 0
EOF
chmod +x "${DEBIAN_DIR}/postinst"

cat > "${DEBIAN_DIR}/prerm" << 'EOF'
#!/bin/bash
set -e
echo "Desinstalando Nexar Tienda..."
exit 0
EOF
chmod +x "${DEBIAN_DIR}/prerm"

cat > "${DEBIAN_DIR}/postrm" << 'EOF'
#!/bin/bash
set -e
update-desktop-database /usr/share/applications 2>/dev/null || true
exit 0
EOF
chmod +x "${DEBIAN_DIR}/postrm"

echo "→ Construyendo .deb..."

DEB_FILE="${BUILD_DIR}/${PACKAGE}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${DEB_FILE}"

echo ""
echo "✅ Paquete generado:"
echo "${DEB_FILE}"
```

### Commit sugerido

```bash
mkdir build
git add build/nexar_tienda.spec build/nexar_tienda.iss build_deb.sh
git commit -m "build: spec PyInstaller, Inno Setup y build_deb.sh - Paso 27 v1.17.0"
git tag v1.17.0
git push origin main --tags
```

---

---

## PASO 28 — GitHub Actions: build automático Windows y Linux 🚀

**Versión objetivo:** `v1.18.0`
**Prioridad:** 🔴 Alta — Sin el workflow de CI/CD no hay releases automáticos.

### Problema a resolver

Nexar Almacén genera automáticamente un instalador `.exe` para Windows y un
paquete `.deb` para Linux cada vez que se hace push a `main` con una versión
nueva en el archivo `VERSION`. Nexar Tienda no tiene nada equivalente.

### Requisitos previos

Antes de activar el workflow hay que configurar estos **GitHub Secrets** en el
repositorio (Settings → Secrets and variables → Actions):

| Secret | Descripción |
|--------|-------------|
| `SECRET_KEY` | Clave Flask (generada con `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `GPG_PRIVATE_KEY` | Clave GPG privada en formato ASCII armor (para firmar los builds) |
| `GPG_PASSPHRASE` | Passphrase de la clave GPG |

> **Para crear la clave GPG:**
> ```bash
> gpg --full-generate-key
> # Seleccionar: RSA, 4096 bits, no expira, nombre: "Nexar Sistemas"
> gpg --armor --export-secret-keys "Nexar Sistemas" > private.asc
> # El contenido de private.asc va en el Secret GPG_PRIVATE_KEY
> ```

### Archivo a crear: `.github/workflows/build.yml`

```yaml
name: Build & Release Nexar Tienda

on:
  push:
    branches: [main, master]

permissions:
  contents: write

concurrency:
  group: build-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ════════════════════════════════════════
  # 🔍 VERIFICAR VERSIÓN Y RELEASE
  # ════════════════════════════════════════
  check:
    runs-on: ubuntu-latest
    outputs:
      version:        ${{ steps.ver.outputs.VERSION }}
      tag_exists:     ${{ steps.tag.outputs.exists }}
      release_exists: ${{ steps.rel.outputs.exists }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Leer versión
        id: ver
        run: echo "VERSION=$(cat VERSION)" >> $GITHUB_OUTPUT

      - name: Verificar tag
        id: tag
        run: |
          if git rev-parse "v${{ steps.ver.outputs.VERSION }}" >/dev/null 2>&1; then
            echo "exists=true" >> $GITHUB_OUTPUT
          else
            echo "exists=false" >> $GITHUB_OUTPUT
          fi

      - name: Verificar release
        id: rel
        run: |
          if gh release view "v${{ steps.ver.outputs.VERSION }}" >/dev/null 2>&1; then
            echo "exists=true" >> $GITHUB_OUTPUT
          else
            echo "exists=false" >> $GITHUB_OUTPUT
          fi
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # ════════════════════════════════════════
  # 🪟 BUILD WINDOWS
  # ════════════════════════════════════════
  build-windows:
    needs: check
    runs-on: windows-latest
    env:
      SECRET_KEY: ${{ secrets.SECRET_KEY }}

    steps:
      - uses: actions/checkout@v4

      - name: Usar versión
        id: ver
        run: echo "VERSION=${{ needs.check.outputs.version }}" >> $env:GITHUB_OUTPUT

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Instalar dependencias
        run: |
          python -m pip install --upgrade pip
          pip install flask openpyxl reportlab pywebview pythonnet pyinstaller python-dotenv

      - name: Preparar LICENSE para Inno Setup
        shell: pwsh
        run: |
          if (Test-Path "LICENSE") {
            Copy-Item "LICENSE" "build\LICENSE.txt"
          } else {
            "Nexar Tienda License" | Out-File "build\LICENSE.txt"
          }

      - name: Generar archivo .env para compilación
        shell: pwsh
        run: |
          if (-not $env:SECRET_KEY) {
            throw "SECRET_KEY no está definido en los Secrets de GitHub."
          }
          "SECRET_KEY=$env:SECRET_KEY" | Out-File -FilePath ".env" -Encoding UTF8

      - name: Build EXE
        run: |
          pyinstaller build/nexar_tienda.spec --distpath dist --workpath build/work --noconfirm

      - name: Copiar .env a dist
        shell: pwsh
        run: |
          Copy-Item ".env" "dist\" -Force

      - name: Instalador Inno Setup
        shell: pwsh
        run: |
          $ver="${{ steps.ver.outputs.VERSION }}"
          & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DAppVersion=$ver" "build\nexar_tienda.iss"

      - name: SHA256 Windows
        shell: pwsh
        run: |
          $out="dist\SHA256SUMS_Windows.txt"
          Get-ChildItem dist -File | Where-Object {$_.Name -notlike "*SHA256*"} | ForEach-Object {
            $h=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
            "$h  $($_.Name)" | Add-Content $out
          }

      - uses: actions/upload-artifact@v4
        with:
          name: win-${{ steps.ver.outputs.VERSION }}
          path: dist/

  # ════════════════════════════════════════
  # 🐧 BUILD LINUX
  # ════════════════════════════════════════
  build-linux:
    needs: check
    runs-on: ubuntu-latest
    env:
      SECRET_KEY: ${{ secrets.SECRET_KEY }}

    steps:
      - uses: actions/checkout@v4

      - name: Usar versión
        id: ver
        run: echo "VERSION=${{ needs.check.outputs.version }}" >> $GITHUB_OUTPUT

      - name: Validar SECRET_KEY
        run: |
          if [ -z "$SECRET_KEY" ]; then echo "Error: SECRET_KEY no definida"; exit 1; fi

      - name: Crear .env para Linux
        run: echo "SECRET_KEY=$SECRET_KEY" > .env

      - name: Build Linux (.deb)
        run: |
          mkdir -p dist
          chmod +x build_deb.sh
          bash build_deb.sh
          cp build_deb/*.deb dist/ || true

      - name: SHA256 Linux
        run: |
          cd dist
          sha256sum * > SHA256SUMS_Linux.txt

      - uses: actions/upload-artifact@v4
        with:
          name: linux-${{ steps.ver.outputs.VERSION }}
          path: dist/

  # ════════════════════════════════════════
  # 🔐 FIRMA GPG
  # ════════════════════════════════════════
  sign:
    needs: [build-windows, build-linux]
    runs-on: ubuntu-latest

    steps:
      - uses: actions/download-artifact@v4
        with:
          path: dist/

      - name: Configurar GPG
        run: |
          mkdir -p ~/.gnupg
          echo "pinentry-mode loopback"    >> ~/.gnupg/gpg.conf
          echo "allow-loopback-pinentry"   >> ~/.gnupg/gpg-agent.conf
          gpgconf --kill gpg-agent

      - name: Importar clave
        run: echo "${{ secrets.GPG_PRIVATE_KEY }}" | gpg --batch --import

      - name: Firmar archivos
        run: |
          find dist -type f ! -name "*.sig" -exec \
          gpg --batch --yes \
              --pinentry-mode loopback \
              --passphrase "${{ secrets.GPG_PASSPHRASE }}" \
              --detach-sign {} \;

      - uses: actions/upload-artifact@v4
        with:
          name: signed
          path: dist/

  # ════════════════════════════════════════
  # 🚀 RELEASE AUTOMÁTICO
  # ════════════════════════════════════════
  release:
    needs: [check, sign]
    if: |
      needs.check.outputs.tag_exists == 'false' ||
      needs.check.outputs.release_exists == 'false'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Leer versión
        id: ver
        run: echo "VERSION=${{ needs.check.outputs.version }}" >> $GITHUB_OUTPUT

      - uses: actions/download-artifact@v4
        with:
          name: signed
          path: dist/

      - name: Generar notas de release desde CHANGELOG
        run: |
          VER="${{ steps.ver.outputs.VERSION }}"
          awk "/## \[$VER\]/,/## \[/" CHANGELOG.md | sed '$d' > release.md

      - name: Crear tag si no existe
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git tag v${{ steps.ver.outputs.VERSION }} || true
          git push origin v${{ steps.ver.outputs.VERSION }} || true

      - name: Crear Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: v${{ steps.ver.outputs.VERSION }}
          name: Nexar Tienda v${{ steps.ver.outputs.VERSION }}
          body_path: release.md
          prerelease: false
          files: dist/**/*
```

### Cómo usar el workflow

```bash
# 1. Crear la carpeta .github/workflows si no existe
mkdir -p .github/workflows

# 2. Guardar el archivo
# (ya hecho al crear el archivo)

# 3. Subir al repositorio
git add .github/workflows/build.yml
git commit -m "ci: workflow de build automático Windows y Linux - Paso 28 v1.18.0"

# 4. Actualizar VERSION con la nueva versión
echo "1.18.0" > VERSION
git add VERSION
git commit -m "chore: bump version a 1.18.0"

# 5. Push — esto dispara el workflow automáticamente
git push origin main

git tag v1.18.0
git push origin v1.18.0
```

### Verificación en GitHub

1. Ir a **Actions** → verificar que los 4 jobs (check, build-windows, build-linux, sign) pasen en verde.
2. Ir a **Releases** → debe aparecer `v1.18.0` con los archivos adjuntos.
3. El instalador Windows debe llamarse `NexarTienda_1.18.0_Setup.exe`.
4. El paquete Linux debe llamarse `nexar-tienda_1.18.0_all.deb`.

---

### Commit sugerido

```bash
git add .github/workflows/build.yml
git commit -m "ci: GitHub Actions build Windows + Linux con firma GPG - Paso 28 v1.18.0"
git tag v1.18.0
git push origin main --tags
```

---

---

## PASO 29 — Mejoras de usabilidad generales (UX polish) ✨

**Versión objetivo:** `v1.19.0`
**Prioridad:** 🟠 Media — Mejoras que no agregan módulos nuevos pero hacen la
experiencia diaria considerablemente mejor, especialmente en el POS y en la
navegación general.

### Problema a resolver

Al comparar la experiencia de usuario de Nexar Almacén con Nexar Tienda se
identificaron las siguientes mejoras de usabilidad que están en Almacén pero
faltan en Tienda, o que aplican específicamente al negocio de tienda de regalos:

1. **Focus automático** en el campo de búsqueda del POS al cargar la página.
2. **Tecla Enter** en el buscador del POS para agregar el primer resultado.
3. **Confirmación antes de vaciar el carrito** en el POS.
4. **Ticket de venta con nombre del negocio** desde la config (actualmente hardcodeado).
5. **Paginación** en la lista de productos (si hay más de 50, la tabla se vuelve lenta).
6. **Indicador de stock bajo** visible en la lista de productos con ícono de alerta.
7. **Atajos de teclado** documentados en `ayuda.html`.

---

### Cambio 1 — Focus automático en el POS

En `templates/punto_venta.html`, agregar al final del bloque `{% block scripts %}`:

```javascript
// Focus automático en el campo de búsqueda del POS
document.addEventListener('DOMContentLoaded', function () {
    const buscador = document.getElementById('buscar-producto');
    if (buscador) buscador.focus();
});
```

---

### Cambio 2 — Enter en el buscador del POS agrega el primer resultado

En `static/js/pos.js` (o inline en `punto_venta.html`), agregar:

```javascript
document.getElementById('buscar-producto').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        // Agregar el primer resultado de la búsqueda al carrito
        const primerBoton = document.querySelector('.btn-agregar-producto');
        if (primerBoton) primerBoton.click();
    }
});
```

---

### Cambio 3 — Confirmación antes de vaciar el carrito

En `templates/punto_venta.html`, buscar el botón "Vaciar carrito" y agregar:

```html
<!-- ANTES: -->
<button onclick="vaciarCarrito()" class="btn btn-outline-danger btn-sm">
    <i class="fas fa-trash"></i> Vaciar
</button>

<!-- DESPUÉS: -->
<button onclick="confirmarVaciarCarrito()" class="btn btn-outline-danger btn-sm">
    <i class="fas fa-trash"></i> Vaciar
</button>
```

Agregar la función en el bloque JS:

```javascript
function confirmarVaciarCarrito() {
    if (carrito.length === 0) return;
    Swal.fire({
        title: '¿Vaciar carrito?',
        text: 'Se eliminarán todos los productos del carrito actual.',
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#c62828',
        cancelButtonColor: '#3a5a8f',
        confirmButtonText: 'Sí, vaciar',
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed) vaciarCarrito();
    });
}
```

---

### Cambio 4 — Ticket con nombre del negocio desde config

En `templates/ticket.html`, reemplazar el nombre hardcodeado por:

```html
<!-- ANTES: -->
<h2>Nexar Tienda</h2>

<!-- DESPUÉS: -->
<h2>{{ cfg.get('negocio_nombre', 'Nexar Tienda') }}</h2>
<p>{{ cfg.get('negocio_direccion', '') }}</p>
<p>{{ cfg.get('negocio_telefono', '') }}</p>
```

Verificar que la ruta del ticket pase `cfg = db.get_config()` al template.
Si no lo hace, agregarlo en `app.py`:

```python
# En la ruta que genera el ticket (por ejemplo, venta_ticket o similar)
cfg = db.get_config()
return render_template('ticket.html', venta=venta, detalle=detalle, cfg=cfg)
```

---

### Cambio 5 — Paginación en lista de productos

En `app.py`, en la ruta `/productos`, agregar paginación simple:

```python
@app.route('/productos')
@login_required
def productos():
    search = request.args.get('q', '')
    pagina = int(request.args.get('p', 1))
    por_pagina = 50
    offset = (pagina - 1) * por_pagina

    lista, total = db.get_productos_paginados(search, por_pagina, offset)
    total_paginas = (total + por_pagina - 1) // por_pagina

    return render_template('productos.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        productos=lista,
        search=search,
        pagina=pagina,
        total_paginas=total_paginas
    )
```

Agregar en `database.py`:

```python
def get_productos_paginados(self, search='', limit=50, offset=0):
    """Retorna productos paginados y el total de resultados."""
    condicion = ''
    params = []
    if search:
        condicion = "WHERE descripcion LIKE ? OR codigo LIKE ? OR categoria LIKE ?"
        params = [f'%{search}%', f'%{search}%', f'%{search}%']

    total_row = self.q(
        f"SELECT COUNT(*) FROM productos {condicion}",
        params, fetchone=True
    )
    total = total_row[0] if total_row else 0

    lista = self.q(
        f"SELECT * FROM productos {condicion} ORDER BY descripcion LIMIT ? OFFSET ?",
        params + [limit, offset]
    )
    return lista, total
```

En `templates/productos.html`, agregar al pie de la tabla:

```html
<!-- Paginación -->
{% if total_paginas > 1 %}
<nav class="mt-3">
  <ul class="pagination pagination-sm justify-content-center">
    {% for i in range(1, total_paginas + 1) %}
    <li class="page-item {% if i == pagina %}active{% endif %}">
      <a class="page-link" href="?q={{ search }}&p={{ i }}">{{ i }}</a>
    </li>
    {% endfor %}
  </ul>
</nav>
{% endif %}
```

---

### Cambio 6 — Indicador de stock bajo en lista de productos

En `templates/productos.html`, en la columna de stock de cada fila:

```html
<!-- Agregar ícono de alerta si el stock está por debajo del mínimo -->
<td>
    {{ p.stock_actual }}
    {% if p.stock_actual <= p.stock_minimo %}
    <i class="fas fa-exclamation-triangle text-warning ms-1"
       title="Stock bajo (mínimo: {{ p.stock_minimo }})"></i>
    {% endif %}
</td>
```

---

### Commit sugerido

```bash
git add templates/punto_venta.html templates/productos.html templates/ticket.html \
        templates/ayuda.html static/js/pos.js app.py database.py
git commit -m "ux(polish): focus POS, vaciar carrito, ticket con config, paginación, stock bajo - Paso 29 v1.19.0"
git tag v1.19.0
git push origin main --tags
```

---

---

## 📋 Resumen del roadmap actualizado

| Paso | Módulo | Versión | Prioridad | Archivos principales |
|------|--------|---------|-----------|----------------------|
| **24** | Launcher `iniciar.py` + ventana nativa | v1.14.0 | 🔴 Alta | `iniciar.py`, `iniciar.sh`, `iniciar.bat` |
| **25** | SweetAlert2 en cierre de sistema | v1.15.0 | 🔴 Alta | `base.html`, `login.html` |
| **26** | Banner DEMO + mejoras UX topbar | v1.16.0 | 🟠 Media-Alta | `base.html`, `app.py` |
| **27** | Build: spec, .iss y build_deb.sh | v1.17.0 | 🔴 Alta | `build/`, `build_deb.sh` |
| **28** | GitHub Actions: CI/CD Windows + Linux | v1.18.0 | 🔴 Alta | `.github/workflows/build.yml` |
| **29** | UX polish: POS, ticket, paginación | v1.19.0 | 🟠 Media | múltiples |

### Orden de ejecución recomendado

```
24 → 25 → 26 → 27 → 28 → 29
```

Los pasos 24, 25 y 28 son los que más valor aportan para llegar a un producto
distribuible. El Paso 24 es prerequisito del Paso 28 (el launcher es el punto
de entrada del `.exe`).

---

*Documento generado el 09/04/2026 — Nexar Tienda v1.13.0*
*Referencia: Nexar Almacén como base estructural*
*Continuación de PASOS_FALTANTES.md (Pasos 15–23)*
