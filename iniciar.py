#!/usr/bin/env python3
import logging
import os
import sys
import subprocess
import threading
import time
import socket
import webbrowser
import threading as _threading
import platform

from services.file_open_service import open_external_target

# ==============================
# 🔹 Safe print (evita errores Unicode)
# ==============================
def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "ignore").decode())


VENV_DIR = "venv"
APP_TITLE = "Nexar Comercio"
APP_HOST = "127.0.0.1"
logger = logging.getLogger(__name__)


# ==============================
# 🔹 Detectar entorno
# ==============================
def en_virtualenv():
    return sys.prefix != sys.base_prefix


def es_ejecutable():
    return getattr(sys, 'frozen', False)


def es_desktop_empaquetado():
    return es_ejecutable() and not os.environ.get("FLASK_ENV", "").strip().lower() == "development"


def omitir_venv():
    return os.environ.get("NEXAR_SKIP_VENV", "").lower() in {"1", "true", "yes"}


def preparar_entorno_linux_frozen():
    if not (sys.platform.startswith("linux") and es_ejecutable()):
        return

    os.environ.pop("GSETTINGS_SCHEMA_DIR", None)
    xdg_dirs = os.environ.get("XDG_DATA_DIRS", "")
    base_dirs = ["/usr/local/share", "/usr/share"]
    current_dirs = [d for d in xdg_dirs.split(":") if d]

    merged = []
    for directory in base_dirs + current_dirs:
        if directory not in merged:
            merged.append(directory)

    os.environ["XDG_DATA_DIRS"] = ":".join(merged)


# ==============================
# 🔹 Reiniciar dentro del venv
# ==============================
def reiniciar_en_venv():
    safe_print("🔁 Reiniciando dentro del entorno virtual...")

    if os.name == "nt":
        python_venv = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        python_venv = os.path.join(VENV_DIR, "bin", "python")

    # ✅ Crear venv
    if not os.path.exists(python_venv):
        safe_print("📦 Creando entorno virtual...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "venv",
            "--system-site-packages",
            VENV_DIR
        ])

    safe_print("📦 Instalando dependencias...")

    try:
        subprocess.check_call(
            [python_venv, "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if os.path.exists("requirements.txt"):
            subprocess.check_call(
                [python_venv, "-m", "pip", "install", "-r", "requirements.txt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        # ==============================
        # 🔥 INSTALAR SDK NEXAR LICENCIAS
        # ==============================
        ruta_sdk = os.path.abspath("../nexar_licencias")

        if os.path.exists(ruta_sdk):
            safe_print("📦 Instalando SDK Nexar Licencias...")
            safe_print(f"📁 Ruta SDK: {ruta_sdk}")

            subprocess.check_call(
                [python_venv, "-m", "pip", "install", "-e", ruta_sdk],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            safe_print("⚠️ No se encontró nexar_licencias (SDK no instalado)")
            safe_print(f"👉 Esperado en: {ruta_sdk}")

    except subprocess.CalledProcessError:
        safe_print("⚠️ Error instalando dependencias o SDK")

    # 🔁 Relanzar dentro del venv
    subprocess.check_call([python_venv, __file__])
    sys.exit()


# ==============================
# 🔹 Obtener puerto libre
# ==============================
def obtener_puerto_libre():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def configurar_logs_servidor_local():
    if not es_desktop_empaquetado():
        return

    try:
        from flask import cli as flask_cli

        flask_cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:
        pass

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.ERROR)
    werkzeug_logger.propagate = False


# ==============================
# 🔹 Iniciar Flask
# ==============================
def iniciar_flask(port):
    from app import app

    configurar_logs_servidor_local()
    logger.info("Servidor local iniciado en http://%s:%s", APP_HOST, port)
    app.run(
        host=APP_HOST,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


# ==============================
# 🔹 Esperar servidor
# ==============================
def esperar_servidor(url, timeout=10):
    import urllib.request

    start = time.time()

    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url)
            return True
        except:
            time.sleep(0.3)

    return False


# ==============================
# 🚀 MAIN
# ==============================
if __name__ == "__main__":
    safe_print("🚀 Iniciando Nexar Comercio...")

    if not es_ejecutable() and not omitir_venv():
        if not en_virtualenv():
            reiniciar_en_venv()

    port = obtener_puerto_libre()
    url = f"http://{APP_HOST}:{port}"

    safe_print(f"🌐 Servidor en: {url}")

    flask_thread = threading.Thread(
        target=iniciar_flask,
        args=(port,),
        daemon=True
    )
    flask_thread.start()

    if not esperar_servidor(url):
        safe_print("❌ No se pudo iniciar el servidor")
        sys.exit(1)

    safe_print("✅ Servidor listo")

    try:
        import webview

        def install_linux_native_print(window):
            if platform.system().lower() != "linux":
                return

            def _attach_print_hook():
                try:
                    native_window = getattr(window, "native", None)
                    browser = getattr(native_window, "webview", None)
                    page = browser.page() if browser else None
                    renderer_name = getattr(webview, "renderer", "desconocido")

                    if getattr(window, "_linux_native_print_hook_installed", False):
                        safe_print(f"[ticket] Hook de impresion ya instalado renderer={renderer_name}")
                        return

                    if native_window is None or browser is None or page is None:
                        safe_print(f"[ticket] No se pudo instalar hook de impresion renderer={renderer_name} motivo=ventana_nativa_no_lista")
                        return

                    from PySide6.QtPrintSupport import QPrintDialog, QPrinter

                    def _handle_print_request(*args):
                        safe_print(
                            f"[ticket] printRequested recibido plataforma=linux renderer={renderer_name} "
                            f"backend={getattr(webview.windows[0], 'gui', 'desconocido') if getattr(webview, 'windows', None) else 'desconocido'} "
                            f"args={len(args)}"
                        )
                        try:
                            native_window.raise_()
                            native_window.activateWindow()
                            browser.setFocus()

                            printer = QPrinter()
                            dialog = QPrintDialog(printer, native_window)
                            dialog.setWindowTitle("Imprimir ticket")

                            if dialog.exec():
                                def _print_finished(success):
                                    safe_print(f"[ticket] Impresion Qt finalizada ok={bool(success)} renderer={renderer_name}")

                                browser.print(printer, _print_finished)
                            else:
                                safe_print(f"[ticket] Impresion Qt cancelada por usuario renderer={renderer_name}")
                        except Exception as exc:
                            safe_print(f"[ticket] Error en impresion Qt renderer={renderer_name} detalle={exc}")

                    page.printRequested.connect(_handle_print_request)
                    if hasattr(page, "printRequestedByFrame"):
                        page.printRequestedByFrame.connect(lambda *_: _handle_print_request(*_))

                    window._linux_native_print_hook_installed = True
                    safe_print(f"[ticket] Hook de impresion nativa instalado plataforma=linux renderer={renderer_name}")
                except Exception as exc:
                    safe_print(f"[ticket] No se pudo instalar impresion nativa Linux: {exc}")

            window.events.shown += _attach_print_hook

        class DesktopController:
            def __init__(self):
                self.allow_close = False

            def handle_closing(self):
                try:
                    from routes.main import DESKTOP_STATE, _caja_abierta

                    if not self.allow_close and DESKTOP_STATE.get("user_logged_in"):
                        DESKTOP_STATE["close_warning_requested"] = True
                        return False
                except Exception:
                    pass
                self.allow_close = True
                return True

        class NexarBridge:
            def restartApp(self, delay_ms=5000):
                def _restart():
                    try:
                        safe_print(f"[update] Reinicio solicitado. Esperando {max(int(delay_ms or 5000), 1000)} ms antes de relanzar.")
                        time.sleep(max(int(delay_ms or 5000), 1000) / 1000)
                        if es_ejecutable():
                            subprocess.Popen([sys.executable], cwd=os.path.dirname(sys.executable) or None)
                        else:
                            subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=os.path.dirname(os.path.abspath(__file__)))
                    finally:
                        os._exit(0)

                _threading.Thread(target=_restart, daemon=True).start()
                return True

            def closeWindow(self):
                def _close():
                    try:
                        safe_print("[update] Cierre de ventana solicitado desde la app.")
                        if getattr(webview, "windows", None):
                            webview.windows[0].destroy()
                    finally:
                        os._exit(0)
                _threading.Timer(0.1, _close).start()
                return True

            def openExternalUrl(self, url):
                target = str(url or "").strip()
                safe_print(f"[ticket] Apertura externa solicitada plataforma={platform.system().lower()} target={target or 'vacio'}")
                result = open_external_target(target)
                if result.get("ok"):
                    safe_print(
                        f"[ticket] Apertura externa OK metodo={result.get('method', 'desconocido')} target={result.get('target', target)}"
                    )
                else:
                    safe_print(
                        f"[ticket] Apertura externa fallo plataforma={result.get('platform', platform.system().lower())} "
                        f"error={result.get('error', result.get('message', 'sin detalle'))}"
                    )
                return result

        controller = DesktopController()
        window = webview.create_window(
            APP_TITLE,
            url,
            width=1200,
            height=800,
            maximized=True,
            js_api=NexarBridge(),
        )
        install_linux_native_print(window)
        window.events.closing += controller.handle_closing

        localization = {
            'global.quitConfirmation': '¿Está seguro de que desea cerrar el sistema?'
        }
        start_kwargs = {"localization": localization}
        if platform.system().lower() == "linux":
            start_kwargs["gui"] = "qt"
        webview.start(**start_kwargs)

    except Exception as e:
        safe_print("⚠️ No se pudo abrir ventana nativa")
        safe_print(str(e))
        safe_print("🌐 Abriendo en navegador...")

        webbrowser.open(url)

        while True:
            time.sleep(1)
