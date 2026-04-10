@echo off
SETLOCAL
TITLE Nexar Tienda - Sistema de Gestion

:: Asegurar que estamos en el directorio del proyecto
CD /D "%~dp0"

echo ======================================================
echo   🚀 Iniciando Nexar Tienda para Windows
echo ======================================================
echo.

:: 1. Verificar si Python está instalado
echo 🔍 Verificando instalacion de Python...
WHERE python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  ERROR: Python no esta instalado en este equipo      ║
    echo ╠══════════════════════════════════════════════════════╣
    echo ║  Descargarlo de: https://www.python.org/downloads/  ║
    echo ║  Marcar la opcion "Add Python to PATH"              ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    PAUSE
    EXIT /B 1
)

:: 2. Ejecutar el lanzador principal
:: iniciar.py gestionara el entorno virtual y las dependencias automaticamente
echo 📦 Cargando lanzador inteligente...
python iniciar.py

:: 3. Capturar errores si el script falla al iniciar
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Ocurrio un error al intentar iniciar el sistema (Codigo: %ERRORLEVEL%)
    PAUSE
)
