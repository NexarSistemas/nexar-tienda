# build/hooks/rthook_error_logger.py
#
# Runtime hook de PyInstaller para Windows (console=False)
#
# PROBLEMA QUE RESUELVE:
#   Con console=False, si la app falla al iniciar, el proceso muere
#   silenciosamente sin mostrar ningun error. Esto hace imposible
#   diagnosticar problemas en PCs limpias.
#
# SOLUCION:
#   Este hook se ejecuta ANTES que cualquier otro codigo de la app.
#   Redirige stderr a un archivo de log y captura excepciones no manejadas.
#   Si la app falla, el usuario puede encontrar el log y reportar el error.
#
# UBICACION DEL LOG:
#   %APPDATA%\Nexar Tienda\logs\error.log
#   Ejemplo: C:\Users\usuario\AppData\Roaming\Nexar Tienda\logs\error.log

import logging
import os
import sys
import traceback
from datetime import datetime


def setup_error_logging():
    """Configura el sistema de logs antes de que arranque la app."""

    # Mantenemos la carpeta tecnica existente para no romper compatibilidad
    # con instalaciones ya desplegadas.
    log_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Nexar Tienda",
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "error.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        encoding="utf-8",
    )

    logging.info("=" * 60)
    logging.info(f"Nexar Comercio iniciando - {datetime.now().isoformat()}")
    logging.info(f"Python: {sys.version}")
    logging.info(f"Executable: {sys.executable}")
    logging.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    if getattr(sys, "frozen", False):
        logging.info(f"MEIPASS: {sys._MEIPASS}")
    logging.info("=" * 60)

    try:
        sys.stderr = open(log_file, "a", encoding="utf-8")
    except Exception:
        pass

    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical("EXCEPCION NO MANEJADA:\n" + error_msg)

        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"Nexar Comercio encontro un error al iniciar.\n\n"
                f"El detalle del error fue guardado en:\n{log_file}\n\n"
                f"Envia ese archivo para obtener soporte.",
                "Nexar Comercio - Error",
                0x10,
            )
        except Exception:
            pass

    sys.excepthook = handle_exception

    return log_file


_log_file = setup_error_logging()
