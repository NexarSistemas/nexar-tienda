#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import time
import socket

# ✅ Agregar acá
def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "ignore").decode())

VENV_DIR = "venv"
APP_TITLE = "Nexar Tienda"
APP_HOST = "127.0.0.1"


# ==============================
# 🔹 Detectar si estamos en venv
# ==============================
def en_virtualenv():
    return sys.prefix != sys.base_prefix


# ==============================
# 🔹 Detectar si es ejecutable (.exe)
# ==============================
def es_ejecutable():
    return getattr(sys, 'frozen', False)


def omitir_venv():
    return os.environ.get("NEXAR_SKIP_VENV", "").lower() in {"1", "true", "yes"}


def secret_key_configurada():
    if os.environ.get("SECRET_KEY", "").strip():
        return True

    posibles_env = [".env", os.path.join(os.path.dirname(__file__), ".env")]
    for env_path in posibles_env:
        if not os.path.exists(env_path):
            continue

        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    txt = line.strip()
                    if not txt or txt.startswith("#"):
                        continue
                    if txt.startswith("SECRET_KEY=") and txt.split("=", 1)[1].strip():
                        return True
        except Exception:
            continue

    return False


def preparar_entorno_linux_frozen():
    """Evita colisiones de schemas GSettings en binarios PyInstaller."""
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

    if os.name == "nt":  # Windows
        python_venv = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        python_venv = os.path.join(VENV_DIR, "bin", "python")

    if not os.path.exists(python_venv):
        safe_print("📦 Creando entorno virtual...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    safe_print("📦 Instalando dependencias...")

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

    # 🔴 relanzar SOLO en desarrollo
    result = subprocess.run([python_venv, __file__])
    sys.exit(result.returncode)


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

    # ✅ SOLO en desarrollo usamos venv
    if not es_ejecutable() and not omitir_venv():
        if not en_virtualenv():
            reiniciar_en_venv()

    if not secret_key_configurada():
        safe_print("❌ SECRET_KEY no definida. Configurá la variable de entorno o archivo .env")
        sys.exit(1)

    preparar_entorno_linux_frozen()

    # 🔹 recién ahora importamos webview
    import webview

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

    webview.create_window(
        APP_TITLE,
        url,
        width=1200,
        height=800
    )

    webview.start()
