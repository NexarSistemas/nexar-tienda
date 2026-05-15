# build/hooks/rthook_error_logger.py
#
# Runtime hook de PyInstaller para Windows (console=False)
#
# UBICACION DEL LOG:
#   %LOCALAPPDATA%\NexarComercio\logs\error.log

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from services.paths import get_logs_dir


def setup_error_logging():
    """Configura el sistema de logs antes de que arranque la app."""

    log_dir = get_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "error.log"

    logging.basicConfig(
        filename=str(log_file),
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        encoding="utf-8",
    )

    logging.info("=" * 60)
    logging.info("Nexar Comercio iniciando - %s", datetime.now().isoformat())
    logging.info("Python: %s", sys.version)
    logging.info("Executable: %s", sys.executable)
    logging.info("Frozen: %s", getattr(sys, "frozen", False))
    if getattr(sys, "frozen", False):
        logging.info("MEIPASS: %s", getattr(sys, "_MEIPASS", ""))
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
        logging.critical("EXCEPCION NO MANEJADA:\n%s", error_msg)

        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "Nexar Comercio encontro un error al iniciar.\n\n"
                f"El detalle del error fue guardado en:\n{log_file}\n\n"
                "Envia ese archivo para obtener soporte.",
                "Nexar Comercio - Error",
                0x10,
            )
        except Exception:
            pass

    sys.excepthook = handle_exception
    return log_file


_log_file = setup_error_logging()
