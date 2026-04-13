@echo off
setlocal

set "APP_DIR=%~dp0"
set "LOG_DIR=%APPDATA%\Nexar Tienda\logs"
set "LOG_FILE=%LOG_DIR%\launcher.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ==================================================>> "%LOG_FILE%"
echo [%date% %time%] Iniciando NexarTienda.exe >> "%LOG_FILE%"

pushd "%APP_DIR%"
"%APP_DIR%NexarTienda.exe" >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
popd

echo [%date% %time%] Fin de ejecución. ExitCode=%EXIT_CODE% >> "%LOG_FILE%"

if not "%EXIT_CODE%"=="0" (
  echo La aplicación no pudo iniciarse correctamente.
  echo Revisá el log en: "%LOG_FILE%"
)

exit /b %EXIT_CODE%
