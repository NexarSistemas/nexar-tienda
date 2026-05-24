#!/usr/bin/env python3
import logging
import os
import sys
import subprocess
import threading
import time
import socket
import webbrowser
import threading as _threading
import platform
import tempfile
import shutil

from services.file_open_service import open_external_target

# ==============================
# 🔹 Safe print (evita errores Unicode)
# ==============================
def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "ignore").decode())


VENV_DIR = "venv"
APP_TITLE = "Nexar Comercio"
APP_HOST = "127.0.0.1"
logger = logging.getLogger(__name__)


# ==============================
# 🔹 Detectar entorno
# ==============================
def en_virtualenv():
    return sys.prefix != sys.base_prefix


def es_ejecutable():
    return getattr(sys, 'frozen', False)


def es_desktop_empaquetado():
    return es_ejecutable() and not os.environ.get("FLASK_ENV", "").strip().lower() == "development"


def omitir_venv():
    return os.environ.get("NEXAR_SKIP_VENV", "").lower() in {"1", "true", "yes"}


def preparar_entorno_linux_frozen():
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

    if os.name == "nt":
        python_venv = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        python_venv = os.path.join(VENV_DIR, "bin", "python")

    # ✅ Crear venv
    if not os.path.exists(python_venv):
        safe_print("📦 Creando entorno virtual...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "venv",
            "--system-site-packages",
            VENV_DIR
        ])

    safe_print("📦 Instalando dependencias...")

    try:
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

        # ==============================
        # 🔥 INSTALAR SDK NEXAR LICENCIAS
        # ==============================
        ruta_sdk = os.path.abspath("../nexar_licencias")

        if os.path.exists(ruta_sdk):
            safe_print("📦 Instalando SDK Nexar Licencias...")
            safe_print(f"📁 Ruta SDK: {ruta_sdk}")

            subprocess.check_call(
                [python_venv, "-m", "pip", "install", "-e", ruta_sdk],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            safe_print("⚠️ No se encontró nexar_licencias (SDK no instalado)")
            safe_print(f"👉 Esperado en: {ruta_sdk}")

    except subprocess.CalledProcessError:
        safe_print("⚠️ Error instalando dependencias o SDK")

    # 🔁 Relanzar dentro del venv
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


def configurar_logs_servidor_local():
    if not es_desktop_empaquetado():
        return

    try:
        from flask import cli as flask_cli

        flask_cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:
        pass

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.ERROR)
    werkzeug_logger.propagate = False


# ==============================
# 🔹 Iniciar Flask
# ==============================
def iniciar_flask(port):
    from app import app

    configurar_logs_servidor_local()
    logger.info("Servidor local iniciado en http://%s:%s", APP_HOST, port)
    app.run(
        host=APP_HOST,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
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
    safe_print("🚀 Iniciando Nexar Comercio...")

    if not es_ejecutable() and not omitir_venv():
        if not en_virtualenv():
            reiniciar_en_venv()

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

    try:
        import webview

        def install_linux_native_print(window):
            if platform.system().lower() != "linux":
                return

            def _attach_print_hook():
                try:
                    native_window = getattr(window, "native", None)
                    browser = getattr(native_window, "webview", None)
                    page = browser.page() if browser else None
                    renderer_name = getattr(webview, "renderer", "desconocido")

                    if getattr(window, "_linux_native_print_hook_installed", False):
                        safe_print(f"[ticket] Hook de impresion ya instalado renderer={renderer_name}")
                        return

                    if native_window is None or browser is None or page is None:
                        safe_print(f"[ticket] No se pudo instalar hook de impresion renderer={renderer_name} motivo=ventana_nativa_no_lista")
                        return

                    from PySide6.QtPrintSupport import QPrintDialog, QPrinter
                    from PySide6.QtWidgets import QMessageBox

                    if not getattr(window, "_linux_print_signal_hook_installed", False):
                        try:
                            if hasattr(browser, "printFinished"):
                                browser.printFinished.connect(
                                    lambda success: safe_print(
                                        f"[ticket] Signal printFinished ok={bool(success)} renderer={renderer_name}"
                                    )
                                )
                            if hasattr(page, "pdfPrintingFinished"):
                                page.pdfPrintingFinished.connect(
                                    lambda path, success: safe_print(
                                        f"[ticket] Signal page.pdfPrintingFinished path={path} ok={bool(success)} "
                                        f"renderer={renderer_name}"
                                    )
                                )
                            window._linux_print_signal_hook_installed = True
                        except Exception as exc:
                            safe_print(f"[ticket] No se pudo conectar signal printFinished: {exc}")

                    if not hasattr(window, "_linux_print_jobs"):
                        window._linux_print_jobs = {}
                    if not hasattr(window, "_linux_print_job_seq"):
                        window._linux_print_job_seq = 0

                    def _printer_state_name(printer):
                        try:
                            return str(printer.printerState()).split(".")[-1]
                        except Exception:
                            return "desconocido"

                    def _output_format_name(printer):
                        try:
                            return str(printer.outputFormat()).split(".")[-1]
                        except Exception:
                            return "desconocido"

                    def _log_printer(prefix, printer):
                        safe_print(
                            f"[ticket] {prefix} printerName={printer.printerName() or 'sin_nombre'} "
                            f"isValid={bool(printer.isValid())} outputFormat={_output_format_name(printer)} "
                            f"printerState={_printer_state_name(printer)}"
                        )

                    def _show_print_error(title, message):
                        try:
                            QMessageBox.warning(native_window, title, message)
                        except Exception:
                            safe_print(f"[ticket] No se pudo mostrar QMessageBox titulo={title} mensaje={message}")

                    safe_print(
                        f"[ticket] Objetos Qt view_type={type(browser).__name__} page_type={type(page).__name__} "
                        f"view_print_methods={[name for name in dir(browser) if 'print' in name.lower()]} "
                        f"page_print_methods={[name for name in dir(page) if 'print' in name.lower()]}"
                    )

                    def _cleanup_job(job_id):
                        job = window._linux_print_jobs.pop(job_id, None)
                        pdf_path = str(job.get("pdf_path") or "").strip() if job else ""
                        remove_pdf = bool(job.get("remove_pdf")) if job else False
                        if remove_pdf and pdf_path and os.path.exists(pdf_path):
                            try:
                                os.remove(pdf_path)
                            except OSError:
                                safe_print(f"[ticket] No se pudo borrar PDF temporal path={pdf_path}")

                    def _send_pdf_to_cups(pdf_path, printer_name):
                        printer_name = str(printer_name or "").strip()
                        lp_path = shutil.which("lp")
                        lpr_path = shutil.which("lpr")

                        if lp_path:
                            command = [lp_path]
                            if printer_name:
                                command.extend(["-d", printer_name])
                            command.append(pdf_path)
                        elif lpr_path:
                            command = [lpr_path]
                            if printer_name:
                                command.extend(["-P", printer_name])
                            command.append(pdf_path)
                        else:
                            return {
                                "ok": False,
                                "message": "No se encontró lp ni lpr para enviar el ticket a CUPS.",
                                "command": [],
                            }

                        safe_print(
                            f"[ticket] Fallback CUPS iniciado comando={' '.join(command)} printerName={printer_name or 'default'} "
                            f"pdf={pdf_path}"
                        )
                        try:
                            completed = subprocess.run(
                                command,
                                capture_output=True,
                                text=True,
                                check=False,
                                timeout=30,
                            )
                        except Exception as exc:
                            return {
                                "ok": False,
                                "message": f"No se pudo ejecutar CUPS: {exc}",
                                "command": command,
                            }

                        stdout = (completed.stdout or "").strip()
                        stderr = (completed.stderr or "").strip()
                        safe_print(
                            f"[ticket] Fallback CUPS resultado returncode={completed.returncode} stdout={stdout or '-'} stderr={stderr or '-'}"
                        )
                        return {
                            "ok": completed.returncode == 0,
                            "message": stderr or stdout or f"CUPS devolvió código {completed.returncode}",
                            "command": command,
                        }

                    def _fallback_pdf_to_cups(job_id, reason):
                        job = window._linux_print_jobs.get(job_id)
                        if not job:
                            safe_print(f"[ticket] Fallback PDF omitido job={job_id} motivo=job_inexistente")
                            return
                        if job.get("fallback_started"):
                            safe_print(f"[ticket] Fallback PDF omitido job={job_id} motivo=ya_iniciado")
                            return

                        job["fallback_started"] = True
                        printer = job["printer"]
                        printer_name = str(printer.printerName() or "").strip()
                        pdf_path = os.path.join(tempfile.gettempdir(), f"nexar-ticket-{job_id}.pdf")
                        job["pdf_path"] = pdf_path

                        safe_print(
                            f"[ticket] Fallback PDF iniciado job={job_id} motivo={reason} printerName={printer_name or 'default'} "
                            f"path={pdf_path}"
                        )

                        def _pdf_done(path, ok):
                            try:
                                if hasattr(page, "pdfPrintingFinished"):
                                    page.pdfPrintingFinished.disconnect(_pdf_done)
                            except Exception:
                                pass
                            safe_print(
                                f"[ticket] PDF temporal generado job={job_id} path={path} ok={bool(ok)} "
                                f"printerName={printer_name or 'default'}"
                            )
                            if not ok:
                                _cleanup_job(job_id)
                                _show_print_error(
                                    "No se pudo imprimir",
                                    "La impresión nativa falló y tampoco se pudo generar el PDF temporal del ticket.",
                                )
                                return

                            result = _send_pdf_to_cups(path, printer_name)
                            if result.get("ok"):
                                job["remove_pdf"] = True
                                _cleanup_job(job_id)
                                return

                            _cleanup_job(job_id)
                            _show_print_error(
                                "No se pudo imprimir",
                                f"La impresión falló también por CUPS. Detalle: {result.get('message', 'sin detalle')}",
                            )

                        try:
                            if hasattr(page, "pdfPrintingFinished"):
                                page.pdfPrintingFinished.connect(_pdf_done)
                            safe_print(
                                f"[ticket] Ejecutando printToPdf sobre page job={job_id} path={pdf_path} "
                                f"page_type={type(page).__name__}"
                            )
                            page.printToPdf(pdf_path)
                        except Exception as exc:
                            safe_print(f"[ticket] Error iniciando fallback PDF job={job_id} detalle={exc}")
                            try:
                                if hasattr(page, "pdfPrintingFinished"):
                                    page.pdfPrintingFinished.disconnect(_pdf_done)
                            except Exception:
                                pass
                            _cleanup_job(job_id)
                            _show_print_error(
                                "No se pudo imprimir",
                                f"La impresión nativa falló y no se pudo iniciar el fallback PDF. Detalle: {exc}",
                            )

                    def _handle_print_request(*args):
                        safe_print(
                            f"[ticket] printRequested recibido plataforma=linux renderer={renderer_name} "
                            f"backend={getattr(webview.windows[0], 'gui', 'desconocido') if getattr(webview, 'windows', None) else 'desconocido'} "
                            f"args={len(args)}"
                        )
                        try:
                            native_window.raise_()
                            native_window.activateWindow()
                            browser.setFocus()

                            printer = QPrinter()
                            _log_printer("Antes del dialog", printer)
                            dialog = QPrintDialog(printer, native_window)
                            dialog.setWindowTitle("Imprimir ticket")
                            dialog_result = bool(dialog.exec())
                            safe_print(f"[ticket] Dialogo de impresion resultado={dialog_result}")
                            _log_printer("Despues del dialog", printer)

                            if dialog_result:
                                window._linux_print_job_seq += 1
                                job_id = f"{int(time.time())}-{window._linux_print_job_seq}"
                                window._linux_print_jobs[job_id] = {
                                    "printer": printer,
                                    "created_at": time.time(),
                                    "fallback_started": False,
                                    "remove_pdf": False,
                                }
                                safe_print(f"[ticket] Job de impresion creado job={job_id}")

                                if hasattr(page, "print"):
                                    def _print_finished(success):
                                        safe_print(
                                            f"[ticket] Callback Qt page.print ok={bool(success)} renderer={renderer_name} job={job_id}"
                                        )
                                        _log_printer("Callback Qt", printer)
                                        if success:
                                            _cleanup_job(job_id)
                                            return
                                        _fallback_pdf_to_cups(job_id, "qt_callback_false")

                                    safe_print(
                                        f"[ticket] Ejecutando page.print job={job_id} page_type={type(page).__name__}"
                                    )
                                    page.print(printer, _print_finished)
                                else:
                                    safe_print(
                                        f"[ticket] page.print no disponible; usando PDF+CUPS job={job_id} "
                                        f"page_type={type(page).__name__}"
                                    )
                                    _fallback_pdf_to_cups(job_id, "page_print_unavailable")
                            else:
                                safe_print(f"[ticket] Impresion Qt cancelada por usuario renderer={renderer_name}")
                        except Exception as exc:
                            safe_print(f"[ticket] Error en impresion Qt renderer={renderer_name} detalle={exc}")

                    page.printRequested.connect(_handle_print_request)
                    if hasattr(page, "printRequestedByFrame"):
                        page.printRequestedByFrame.connect(lambda *_: _handle_print_request(*_))

                    window._linux_native_print_hook_installed = True
                    safe_print(f"[ticket] Hook de impresion nativa instalado plataforma=linux renderer={renderer_name}")
                except Exception as exc:
                    safe_print(f"[ticket] No se pudo instalar impresion nativa Linux: {exc}")

            window.events.shown += _attach_print_hook

        class DesktopController:
            def __init__(self):
                self.allow_close = False

            def handle_closing(self):
                try:
                    from routes.main import DESKTOP_STATE, _caja_abierta

                    if not self.allow_close and DESKTOP_STATE.get("user_logged_in"):
                        DESKTOP_STATE["close_warning_requested"] = True
                        return False
                except Exception:
                    pass
                self.allow_close = True
                return True

        class NexarBridge:
            def restartApp(self, delay_ms=5000):
                def _restart():
                    try:
                        safe_print(f"[update] Reinicio solicitado. Esperando {max(int(delay_ms or 5000), 1000)} ms antes de relanzar.")
                        time.sleep(max(int(delay_ms or 5000), 1000) / 1000)
                        if es_ejecutable():
                            subprocess.Popen([sys.executable], cwd=os.path.dirname(sys.executable) or None)
                        else:
                            subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=os.path.dirname(os.path.abspath(__file__)))
                    finally:
                        os._exit(0)

                _threading.Thread(target=_restart, daemon=True).start()
                return True

            def closeWindow(self):
                def _close():
                    try:
                        safe_print("[update] Cierre de ventana solicitado desde la app.")
                        if getattr(webview, "windows", None):
                            webview.windows[0].destroy()
                    finally:
                        os._exit(0)
                _threading.Timer(0.1, _close).start()
                return True

            def openExternalUrl(self, url):
                target = str(url or "").strip()
                safe_print(f"[ticket] Apertura externa solicitada plataforma={platform.system().lower()} target={target or 'vacio'}")
                result = open_external_target(target)
                if result.get("ok"):
                    safe_print(
                        f"[ticket] Apertura externa OK metodo={result.get('method', 'desconocido')} target={result.get('target', target)}"
                    )
                else:
                    safe_print(
                        f"[ticket] Apertura externa fallo plataforma={result.get('platform', platform.system().lower())} "
                        f"error={result.get('error', result.get('message', 'sin detalle'))}"
                    )
                return result

        controller = DesktopController()
        window = webview.create_window(
            APP_TITLE,
            url,
            width=1200,
            height=800,
            maximized=True,
            js_api=NexarBridge(),
        )
        install_linux_native_print(window)
        window.events.closing += controller.handle_closing

        localization = {
            'global.quitConfirmation': '¿Está seguro de que desea cerrar el sistema?'
        }
        start_kwargs = {"localization": localization}
        if platform.system().lower() == "linux":
            start_kwargs["gui"] = "qt"
        webview.start(**start_kwargs)

    except Exception as e:
        safe_print("⚠️ No se pudo abrir ventana nativa")
        safe_print(str(e))
        safe_print("🌐 Abriendo en navegador...")

        webbrowser.open(url)

        while True:
            time.sleep(1)
