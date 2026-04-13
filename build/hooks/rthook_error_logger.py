# build/hooks/rthook_error_logger.py
#
# Runtime hook de PyInstaller para Windows (console=False)
#
# PROBLEMA QUE RESUELVE:
#   Con console=False, si la app falla al iniciar, el proceso muere
#   silenciosamente sin mostrar ningún error. Esto hace imposible
#   diagnosticar problemas en PCs limpias.
#
# SOLUCIÓN:
#   Este hook se ejecuta ANTES que cualquier otro código de la app.
#   Redirige stderr a un archivo de log y captura excepciones no manejadas.
#   Si la app falla, el usuario puede encontrar el log y reportar el error.
#
# UBICACIÓN DEL LOG:
#   %APPDATA%\Nexar Tienda\logs\error.log
#   Ejemplo: C:\Users\usuario\AppData\Roaming\Nexar Tienda\logs\error.log

import sys
import os
import logging
import traceback
from datetime import datetime


def setup_error_logging():
    """Configura el sistema de logs antes de que arranque la app."""

    # Carpeta de logs en AppData del usuario (persiste entre ejecuciones)
    log_dir = os.path.join(
        os.environ.get('APPDATA', os.path.expanduser('~')),
        'Nexar Tienda',
        'logs'
    )
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'error.log')

    # Configurar logging básico
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding='utf-8',
    )

    # Registrar inicio de sesión
    logging.info('=' * 60)
    logging.info(f'Nexar Tienda iniciando — {datetime.now().isoformat()}')
    logging.info(f'Python: {sys.version}')
    logging.info(f'Executable: {sys.executable}')
    logging.info(f'Frozen: {getattr(sys, "frozen", False)}')
    if getattr(sys, 'frozen', False):
        logging.info(f'MEIPASS: {sys._MEIPASS}')
    logging.info('=' * 60)

    # Redirigir stderr al log (captura errores de librerías C/DLL)
    try:
        sys.stderr = open(log_file, 'a', encoding='utf-8')
    except Exception:
        pass  # Si falla, no es crítico

    # Capturar excepciones no manejadas
    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical('EXCEPCIÓN NO MANEJADA:\n' + error_msg)

        # Mostrar mensaje al usuario con la ruta del log
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f'Nexar Tienda encontró un error al iniciar.\n\n'
                f'El detalle del error fue guardado en:\n{log_file}\n\n'
                f'Enviá ese archivo para obtener soporte.',
                'Nexar Tienda — Error',
                0x10  # MB_ICONERROR
            )
        except Exception:
            pass

    sys.excepthook = handle_exception

    return log_file


# Ejecutar al importar el hook (PyInstaller lo hace automáticamente)
_log_file = setup_error_logging()
