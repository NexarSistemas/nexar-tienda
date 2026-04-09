@echo off
SETLOCAL
title Nexar Tienda - Startup Script

echo ======================================================
echo   - Iniciando Nexar Tienda para Windows -
echo ======================================================

:: 1. Verificar Python
where python >nul 2>nul
if errorlevel 1 goto error_python

:: 2. Crear entorno virtual si no existe
if not exist venv (
    echo [INFO] Creando entorno virtual...
    python -m venv venv
)

:: 3. Activar entorno
echo [INFO] Activando entorno virtual...
call venv\Scripts\activate

:: 4. Instalar dependencias
echo [INFO] Instalando dependencias...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 5. Crear .env si no existe
if not exist .env (
    echo [INFO] Creando archivo .env...
    python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" > .env
)

:: 6. Inicializar base de datos
echo [INFO] Inicializando base de datos...
python -c "import database; database.init_db()"
if errorlevel 1 goto error_db

:: 7. Ejecutar app
echo [OK] Iniciando aplicacion...
python app.py
if errorlevel 1 goto error_app

goto end

:: =========================
:error_python
echo [ERROR] Python no esta instalado o no esta en PATH
pause
exit /b 1

:error_db
echo [ERROR] Fallo la inicializacion de la base de datos
pause
exit /b 1

:error_app
echo [ERROR] La aplicacion se cerro con errores
pause
exit /b 1

:end
echo.
echo Proceso finalizado.
pause