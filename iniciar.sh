#!/bin/bash
# ============================================================
#  Nexar Tienda — Launcher Linux
#  El usuario hace doble clic en este archivo o lo ejecuta
#  desde la terminal. Todo lo demás es automático.
# ============================================================

# Ir al directorio donde está este script
cd "$(dirname "$0")"

# Verificar que Python 3 esté instalado
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  ERROR: Python 3 no está instalado en este equipo   ║"
    echo "╠══════════════════════════════════════════════════════╣"
    echo "║  Instalar con:                                       ║"
    echo "║    sudo apt install python3                          ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    # Si corremos en entorno gráfico, mostrar ventana de error
    if command -v zenity &>/dev/null; then
        zenity --error \
            --title="Nexar Tienda" \
            --text="Python 3 no está instalado.\n\nInstalalo con:\n  sudo apt install python3" \
            --width=350 2>/dev/null
    fi
    read -p "Presioná Enter para cerrar..." dummy
    exit 1
fi

# Lanzar el sistema
python3 iniciar.py
