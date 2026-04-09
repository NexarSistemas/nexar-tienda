@echo off
SETLOCAL
title Nexar Tienda

cd /d "%~dp0"

:: Verificar que Python esté instalado
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  ERROR: Python no está instalado en este equipo     ║
    echo ╠══════════════════════════════════════════════════════╣
    echo ║  Descargarlo de: https://www.python.org/downloads/  ║
    echo ║  Marcar la opción "Add Python to PATH"              ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

python iniciar.py
