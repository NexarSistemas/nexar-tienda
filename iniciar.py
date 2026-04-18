#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import time
import socket
import webbrowser
import threading as _threading

# ==============================
# 🔹 Safe print (evita errores Unicode)
# ==============================
def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "ignore").decode())


VENV_DIR = "venv"
APP_TITLE = "Nexar Tienda"
APP_HOST = "127.0.0.1"


# ==============================
# 🔹 Detectar entorno
# ==============================
def en_virtualenv():
    return sys.prefix != sys.base_prefix


def es_ejecutable():
    return getattr(sys, 'frozen', False)


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


# ==============================
# 🔹 Iniciar Flask
# ==============================
def iniciar_flask(port):
    from app import app
    
    app.run(
        host=APP_HOST,
        port=port,
        debug=False,
        use_reloader=False
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
    safe_print("🚀 Iniciando Nexar Tienda...")

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

        class NexarBridge:
            def closeWindow(self):
                def _close():
                    try:
                        if getattr(webview, "windows", None):
                            webview.windows[0].destroy()
                    finally:
                        os._exit(0)
                _threading.Timer(0.1, _close).start()
                return True

        webview.create_window(
            APP_TITLE,
            url,
            width=1200,
            height=800,
            maximized=True,
            confirm_close=True,
            js_api=NexarBridge(),
        )

        localization = {
            'global.quitConfirmation': '¿Está seguro de que desea cerrar el sistema?'
        }
        webview.start(localization=localization)

    except Exception as e:
        safe_print("⚠️ No se pudo abrir ventana nativa")
        safe_print(str(e))
        safe_print("🌐 Abriendo en navegador...")

        webbrowser.open(url)

        while True:
            time.sleep(1)
