#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║   NEXAR TIENDA  —  v1.15.3                                           ║
║   Creado por Nexar Sistemas · Desarrollado con Claude.ai · 2026     ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os
import sys
import subprocess
import threading
import time
import socket

VENV_DIR = "venv"


# ==============================
# 🔹 Detectar si estamos en venv
# ==============================
def en_virtualenv():
    return sys.prefix != sys.base_prefix


# ==============================
# 🔹 Reiniciar dentro del venv
# ==============================
def reiniciar_en_venv():
    print("🔁 Reiniciando dentro del entorno virtual...")

    # Detectar ejecutable según el sistema operativo
    if os.name == "nt":  # Windows
        python_venv = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:                # Linux/macOS
        python_venv = os.path.join(VENV_DIR, "bin", "python")

    if not os.path.exists(python_venv):
        print("📦 Creando entorno virtual...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    # instalar dependencias
    print("📦 Instalando dependencias...")
#    subprocess.check_call([python_venv, "-m", "pip", "install", "--upgrade", "pip"])
#    subprocess.check_call([python_venv, "-m", "pip", "install", "-r", "requirements.txt"])

    subprocess.check_call(
        [python_venv, "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    subprocess.check_call(
        [python_venv, "-m", "pip", "install", "-r", "requirements.txt"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # relanzar script dentro del venv
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
        host="127.0.0.1",
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
    print("🚀 Iniciando Nexar Tienda...")

    # 🔹 asegurar entorno virtual
    if not en_virtualenv():
        reiniciar_en_venv()

    # 🔹 recién ahora importamos webview (ya dentro del venv)
    import webview

    port = obtener_puerto_libre()
    url = f"http://127.0.0.1:{port}"

    print(f"🌐 Servidor en: {url}")

    # 🔹 iniciar Flask en thread
    flask_thread = threading.Thread(
        target=iniciar_flask,
        args=(port,),
        daemon=True
    )
    flask_thread.start()

    # 🔹 esperar backend
    if not esperar_servidor(url):
        print("❌ No se pudo iniciar el servidor")
        sys.exit(1)

    print("✅ Servidor listo")

    # 🔹 abrir ventana nativa
    webview.create_window(
        "Nexar Tienda",
        url,
        width=1200,
        height=800
    )

    webview.start()