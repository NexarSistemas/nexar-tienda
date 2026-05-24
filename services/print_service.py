from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import database as db
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from services.rubros import (
    convertir_cantidad_desde_base,
    convertir_precio_desde_base,
    get_rubro_actual,
    get_unidad_label,
    normalizar_unidad,
)


logger = logging.getLogger(__name__)

PRINT_TIMEOUT_SECONDS = 30
LPSTAT_TIMEOUT_SECONDS = 10
MM_TO_POINTS = 72 / 25.4
DEFAULT_TICKET_WIDTH_MM = 210
DEFAULT_TICKET_MIN_HEIGHT_MM = 110
DEFAULT_TICKET_MARGIN_MM = 10
HELD_JOB_KEYWORDS = ("held", "delay", "demor", "stop", "paused", "reten")


def is_linux_platform() -> bool:
    return platform.system().lower() == "linux"


def get_print_command() -> list[str] | None:
    lp_path = shutil.which("lp")
    if lp_path:
        return [lp_path]

    lpr_path = shutil.which("lpr")
    if lpr_path:
        return [lpr_path]

    return None


def get_default_printer() -> dict[str, object]:
    lpstat_path = shutil.which("lpstat")
    if not lpstat_path:
        logger.warning("No se encontró lpstat para detectar impresora por defecto")
        return {
            "ok": False,
            "printer": "",
            "message": "No se encontró lpstat para detectar la impresora por defecto.",
        }

    try:
        completed = subprocess.run(
            [lpstat_path, "-d"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        logger.exception("Fallo detectando impresora por defecto")
        return {
            "ok": False,
            "printer": "",
            "message": f"No se pudo detectar la impresora por defecto: {exc}",
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    logger.info(
        "Detección impresora por defecto returncode=%s stdout=%s stderr=%s",
        completed.returncode,
        stdout or "-",
        stderr or "-",
    )

    if completed.returncode != 0:
        return {
            "ok": False,
            "printer": "",
            "message": stderr or stdout or f"lpstat devolvió código {completed.returncode}",
        }

    marker = ":"
    printer = stdout.split(marker, 1)[1].strip() if marker in stdout else stdout.strip()
    return {
        "ok": bool(printer),
        "printer": printer,
        "message": stdout or "Impresora por defecto detectada.",
    }


def _formatear_cantidad_ticket(cantidad) -> str:
    try:
        cantidad_num = float(cantidad or 0)
    except (TypeError, ValueError):
        return "0"
    if cantidad_num.is_integer():
        return str(int(cantidad_num))
    return f"{cantidad_num:.3f}".rstrip("0").rstrip(".") or "0"


def _formatear_unidad_ticket(unidad, cantidad) -> str:
    unidad_normalizada = normalizar_unidad(unidad or "unidad")
    cantidad_num = convertir_cantidad_desde_base(cantidad or 0, unidad_normalizada)
    if unidad_normalizada == "unidad":
        return "unidad" if abs(cantidad_num) == 1 else "unidades"
    if unidad_normalizada == "paquete":
        return "paquete" if abs(cantidad_num) == 1 else "paquetes"
    if unidad_normalizada == "gramo":
        return "gramo" if abs(cantidad_num) == 1 else "gramos"
    if unidad_normalizada == "ml":
        return "ml"
    if unidad_normalizada == "docena":
        return "docena"
    if unidad_normalizada == "kg":
        return "kg"
    if unidad_normalizada == "litro":
        return "litro"
    return get_unidad_label(unidad_normalizada).lower()


def _formatear_precio(valor, decimales=2) -> str:
    try:
        number = float(valor or 0)
    except (TypeError, ValueError):
        number = 0.0
    entero, dec = f"{number:,.{decimales}f}".split(".")
    return f"$ {entero.replace(',', '.')},{dec}"


def _formatear_precio_por_unidad(valor, unidad) -> str:
    unidad_normalizada = normalizar_unidad(unidad or "unidad")
    precio_mostrable = convertir_precio_desde_base(valor or 0, unidad_normalizada)
    decimales = 4 if unidad_normalizada in {"gramo", "ml"} else 2
    return _formatear_precio(precio_mostrable, decimales=decimales)


def _wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _parse_float_env(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        logger.warning("Variable %s inválida: %s", name, raw)
        return default


def _resolve_cups_print_mode(value: str | None = None) -> str:
    mode = str(value or os.getenv("NEXAR_CUPS_PRINT_MODE", "auto")).strip().lower()
    if mode not in {"auto", "fit-to-page", "raw"}:
        logger.warning("Modo CUPS desconocido=%s; se usará auto", mode)
        return "auto"
    return mode


def _count_pdf_pages(path: str | Path) -> int:
    try:
        content = Path(path).read_bytes()
    except OSError:
        return 0
    return len(re.findall(rb"/Type\s*/Page\b", content))


def _extract_cups_job_id(output: str) -> str:
    match = re.search(r"\b([A-Za-z0-9_.-]+-\d+)\b", str(output or ""))
    return match.group(1) if match else ""


def _run_subprocess(command: list[str], timeout: int = PRINT_TIMEOUT_SECONDS):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _get_cups_job_status(printer_name: str, job_id: str) -> dict[str, object]:
    lpstat_path = shutil.which("lpstat")
    if not lpstat_path:
        return {
            "ok": False,
            "message": "No se encontró lpstat para consultar el estado de CUPS.",
            "queue_stdout": "",
            "detail_stdout": "",
            "state": "unknown",
        }

    commands: list[tuple[str, list[str]]] = []
    if printer_name:
        commands.append(("queue", [lpstat_path, "-W", "all", "-o", printer_name]))
    if job_id:
        commands.append(("detail", [lpstat_path, "-l", "-o", job_id]))

    outputs: dict[str, str] = {"queue": "", "detail": ""}
    stderrs: dict[str, str] = {"queue": "", "detail": ""}
    returncodes: dict[str, int] = {}

    for label, command in commands:
        try:
            completed = _run_subprocess(command, timeout=LPSTAT_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.exception("Fallo consultando CUPS label=%s command=%s", label, " ".join(command))
            stderrs[label] = str(exc)
            returncodes[label] = -1
            continue

        outputs[label] = (completed.stdout or "").strip()
        stderrs[label] = (completed.stderr or "").strip()
        returncodes[label] = completed.returncode
        logger.info(
            "Estado CUPS label=%s returncode=%s stdout=%s stderr=%s",
            label,
            completed.returncode,
            outputs[label] or "-",
            stderrs[label] or "-",
        )

    combined = " ".join(
        part for part in (outputs.get("queue", ""), outputs.get("detail", ""), stderrs.get("queue", ""), stderrs.get("detail", "")) if part
    ).lower()
    is_held = any(keyword in combined for keyword in HELD_JOB_KEYWORDS)
    in_queue = bool(job_id and job_id in outputs.get("queue", ""))
    detail_found = bool(job_id and job_id in outputs.get("detail", ""))

    if is_held:
        state = "held"
        message = "CUPS recibió el trabajo, pero quedó demorado, retenido o detenido."
    elif detail_found or in_queue:
        state = "queued"
        message = "CUPS recibió el trabajo y lo dejó registrado en cola."
    else:
        state = "unknown"
        message = "No se pudo confirmar el estado final del trabajo en CUPS."

    return {
        "ok": True,
        "message": message,
        "queue_stdout": outputs.get("queue", ""),
        "queue_stderr": stderrs.get("queue", ""),
        "detail_stdout": outputs.get("detail", ""),
        "detail_stderr": stderrs.get("detail", ""),
        "returncodes": returncodes,
        "state": state,
        "held": is_held,
    }


def _estimate_ticket_height_points(
    venta: dict,
    detalle: list,
    cfg: dict,
    rubro_actual,
    content_width: float,
) -> float:
    line_points = 0
    line_points += 11
    line_points += 3
    line_points += 4
    line_points += 1
    line_points += 1

    if cfg.get("direccion"):
        line_points += 1
    if cfg.get("telefono"):
        line_points += 1
    if cfg.get("negocio_email"):
        line_points += 1

    line_points += 2

    for item in detalle:
        producto = db.q(
            "SELECT iva, tipo_unidad, unidad FROM productos WHERE id=?",
            (item["producto_id"],),
            fetchone=True,
        )
        unidad_base = (
            (item["unidad"] or "")
            or (producto["unidad"] if producto and producto["unidad"] else "")
            or (producto["tipo_unidad"] if producto and producto["tipo_unidad"] else "")
            or "unidad"
        )
        unidad_normalizada = normalizar_unidad(unidad_base, rubro_actual)
        cantidad = float(item["cantidad"] or 0)
        precio_unitario = float(item["precio_unitario"] or 0)
        cantidad_formateada = _formatear_cantidad_ticket(convertir_cantidad_desde_base(cantidad, unidad_normalizada))
        unidad_formateada = _formatear_unidad_ticket(unidad_normalizada, cantidad)
        precio_formateado = _formatear_precio_por_unidad(precio_unitario, unidad_normalizada)

        descripcion_lines = _wrap_text(str(item["descripcion"] or ""), "Helvetica-Bold", 10, content_width)
        resumen = f"{cantidad_formateada} {unidad_formateada} x {precio_formateado}/{unidad_formateada}"
        resumen_lines = _wrap_text(resumen, "Helvetica", 9, content_width)
        line_points += len(descripcion_lines) + len(resumen_lines) + 1

    line_points += 6

    if cfg.get("ticket_pie"):
        line_points += len(_wrap_text(str(cfg["ticket_pie"]), "Helvetica", 9, content_width)) + 1

    base_height = max(
        DEFAULT_TICKET_MIN_HEIGHT_MM * MM_TO_POINTS,
        (line_points * 12) + (DEFAULT_TICKET_MARGIN_MM * MM_TO_POINTS * 2),
    )
    return min(base_height, 2000 * MM_TO_POINTS)


def build_ticket_pdf(venta_id: int, output_path: str | Path | None = None) -> dict[str, object]:
    venta = db.q("SELECT * FROM ventas WHERE id=?", (venta_id,), fetchone=True)
    if not venta:
        return {
            "ok": False,
            "message": f"No se encontró la venta #{venta_id}.",
            "pdf_path": "",
        }

    detalle = db.get_venta_detalle(venta_id)
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)

    if output_path is None:
        temp_file = tempfile.NamedTemporaryFile(prefix="nexar-ticket-", suffix=".pdf", delete=False)
        temp_file.close()
        pdf_path = Path(temp_file.name)
    else:
        pdf_path = Path(output_path).expanduser().resolve()
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

    width_mm = _parse_float_env("NEXAR_TICKET_PAPER_WIDTH_MM", DEFAULT_TICKET_WIDTH_MM)
    margin_mm = _parse_float_env("NEXAR_TICKET_MARGIN_MM", DEFAULT_TICKET_MARGIN_MM)
    page_width = width_mm * MM_TO_POINTS
    margin_x = margin_mm * MM_TO_POINTS
    content_width = max(page_width - (margin_x * 2), 120)
    page_height = _estimate_ticket_height_points(venta, detalle, cfg, rubro_actual, content_width)
    current_y = page_height - margin_x
    line_height = 13
    c = canvas.Canvas(str(pdf_path), pagesize=(page_width, page_height))

    logger.info(
        "Generando PDF temporal de ticket venta_id=%s path=%s width_mm=%.2f height_mm=%.2f",
        venta_id,
        pdf_path,
        width_mm,
        page_height / MM_TO_POINTS,
    )

    def draw_text(text: str, x: float, size=10, bold=False):
        nonlocal current_y
        font_name = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font_name, size)
        c.drawString(x, current_y, str(text or ""))

    c.setTitle(f"Ticket {venta['numero_ticket']}")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin_x, current_y, str(cfg.get("nombre_negocio") or "Nexar Comercio"))
    current_y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(margin_x, current_y, f"Ticket #{venta['numero_ticket']} · Venta interna #{venta_id}")
    current_y -= line_height
    c.drawString(
        margin_x,
        current_y,
        f"Fecha: {venta['fecha']} {str(venta['hora'] or '')[:5]} · Medio: {venta['medio_pago'] or 'No informado'}",
    )
    current_y -= line_height
    c.drawString(margin_x, current_y, f"Cliente: {venta['cliente_nombre'] or 'Mostrador'}")
    current_y -= line_height
    c.drawString(margin_x, current_y, f"Vendedor: {venta['vendedor'] or 'No informado'} · Rubro: {str(rubro_actual).capitalize()}")
    current_y -= 18

    if cfg.get("direccion"):
        c.drawString(margin_x, current_y, f"Dirección: {cfg['direccion']}")
        current_y -= line_height
    if cfg.get("telefono"):
        c.drawString(margin_x, current_y, f"Teléfono: {cfg['telefono']}")
        current_y -= line_height
    if cfg.get("negocio_email"):
        c.drawString(margin_x, current_y, f"Email: {cfg['negocio_email']}")
        current_y -= line_height

    current_y -= 6
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_x, current_y, "Detalle")
    current_y -= 14

    for item in detalle:
        producto = db.q(
            "SELECT iva, tipo_unidad, unidad FROM productos WHERE id=?",
            (item["producto_id"],),
            fetchone=True,
        )
        unidad_base = (
            (item["unidad"] or "")
            or (producto["unidad"] if producto and producto["unidad"] else "")
            or (producto["tipo_unidad"] if producto and producto["tipo_unidad"] else "")
            or "unidad"
        )
        unidad_normalizada = normalizar_unidad(unidad_base, rubro_actual)
        cantidad = float(item["cantidad"] or 0)
        subtotal = float(item["subtotal"] or 0)
        precio_unitario = float(item["precio_unitario"] or 0)
        cantidad_formateada = _formatear_cantidad_ticket(convertir_cantidad_desde_base(cantidad, unidad_normalizada))
        unidad_formateada = _formatear_unidad_ticket(unidad_normalizada, cantidad)
        precio_formateado = _formatear_precio_por_unidad(precio_unitario, unidad_normalizada)
        subtotal_formateado = _formatear_precio(subtotal)

        descripcion_lines = _wrap_text(str(item["descripcion"] or ""), "Helvetica-Bold", 10, content_width - 110)
        resumen = f"{cantidad_formateada} {unidad_formateada} x {precio_formateado}/{unidad_formateada}"
        resumen_lines = _wrap_text(resumen, "Helvetica", 9, content_width - 110)

        for line in descripcion_lines:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin_x, current_y, line)
            current_y -= 12

        for line in resumen_lines:
            c.setFont("Helvetica", 9)
            c.drawString(margin_x, current_y, line)
            current_y -= 10

        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(page_width - margin_x, current_y + 10, subtotal_formateado)
        current_y -= 6

    current_y -= 6
    c.line(margin_x, current_y, page_width - margin_x, current_y)
    current_y -= 16

    totals = [
        ("Subtotal", _formatear_precio(venta["subtotal"])),
    ]
    if float(venta["descuento_adicional"] or 0) > 0:
        totals.append(("Descuento", f"-{_formatear_precio(venta['descuento_adicional'])}"))
    if float(venta["interes_financiacion"] or 0) > 0:
        totals.append(("Interés financiación", f"+{_formatear_precio(venta['interes_financiacion'])}"))
    totals.append(("Total", _formatear_precio(venta["total"])))

    for label, value in totals:
        c.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 11 if label == "Total" else 10)
        c.drawString(margin_x, current_y, label)
        c.drawRightString(page_width - margin_x, current_y, value)
        current_y -= 15

    if cfg.get("ticket_pie"):
        current_y -= 8
        for line in _wrap_text(str(cfg["ticket_pie"]), "Helvetica", 9, content_width):
            c.setFont("Helvetica", 9)
            c.drawString(margin_x, current_y, line)
            current_y -= 11

    c.save()
    page_count = _count_pdf_pages(pdf_path)
    logger.info(
        "PDF temporal generado venta_id=%s path=%s pages=%s width_mm=%.2f height_mm=%.2f",
        venta_id,
        pdf_path,
        page_count,
        width_mm,
        page_height / MM_TO_POINTS,
    )
    return {
        "ok": True,
        "message": "PDF temporal del ticket generado correctamente.",
        "pdf_path": str(pdf_path),
        "pdf_pages": page_count,
        "page_width_mm": round(width_mm, 2),
        "page_height_mm": round(page_height / MM_TO_POINTS, 2),
    }


def send_file_to_printer(
    path: str | Path,
    printer_name: str | None = None,
    cups_print_mode: str | None = None,
) -> dict[str, object]:
    target_path = Path(path).expanduser().resolve()
    if not target_path.exists():
        logger.warning("Archivo a imprimir inexistente path=%s", target_path)
        return {
            "ok": False,
            "message": f"No se encontró el archivo a imprimir: {target_path}",
            "path": str(target_path),
        }

    command = get_print_command()
    if not command:
        logger.warning("No se encontró lp ni lpr para imprimir path=%s", target_path)
        return {
            "ok": False,
            "message": "No se encontró servicio de impresión Linux. Verifique CUPS.",
            "path": str(target_path),
            "command": [],
        }

    printer_name = str(printer_name or "").strip()
    detected_printer = get_default_printer()
    if not printer_name:
        printer_name = str(detected_printer.get("printer") or "").strip()
    print_mode = _resolve_cups_print_mode(cups_print_mode)

    final_command = list(command)
    uses_lp = Path(final_command[0]).name == "lp"
    if printer_name:
        final_command.extend(["-d", printer_name] if uses_lp else ["-P", printer_name])
    if print_mode in {"fit-to-page", "raw"}:
        final_command.extend(["-o", print_mode])
    final_command.append(str(target_path))

    logger.info(
        "Enviando ticket a impresión plataforma=%s path=%s printer=%s command=%s",
        platform.system().lower(),
        target_path,
        printer_name or "default",
        " ".join(final_command),
    )

    try:
        completed = _run_subprocess(final_command)
    except Exception as exc:
        logger.exception("Fallo al ejecutar comando de impresión")
        return {
            "ok": False,
            "message": f"No se pudo ejecutar el comando de impresión: {exc}",
            "path": str(target_path),
            "command": final_command,
            "printer": printer_name,
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    logger.info(
        "Resultado impresión returncode=%s printer=%s stdout=%s stderr=%s",
        completed.returncode,
        printer_name or "default",
        stdout or "-",
        stderr or "-",
    )

    if completed.returncode != 0:
        return {
            "ok": False,
            "message": stderr or stdout or f"El servicio de impresión devolvió código {completed.returncode}.",
            "path": str(target_path),
            "command": final_command,
            "printer": printer_name,
            "print_mode": print_mode,
            "stdout": stdout,
            "stderr": stderr,
        }

    job_id = _extract_cups_job_id(stdout)
    cups_status = _get_cups_job_status(printer_name, job_id)
    if cups_status.get("ok"):
        logger.info(
            "Estado real CUPS printer=%s job_id=%s state=%s held=%s",
            printer_name or "default",
            job_id or "-",
            cups_status.get("state"),
            cups_status.get("held"),
        )

    message = "Ticket enviado a impresión."
    ok = True
    if job_id and cups_status.get("held"):
        ok = False
        message = (
            f"CUPS recibió el trabajo {job_id}, pero quedó demorado/retenido/detenido. "
            "Revise la cola o el estado de la impresora."
        )
    elif job_id and cups_status.get("state") == "queued":
        message = f"Ticket enviado a CUPS como trabajo {job_id}."

    return {
        "ok": ok,
        "message": message,
        "path": str(target_path),
        "command": final_command,
        "printer": printer_name,
        "print_mode": print_mode,
        "stdout": stdout,
        "stderr": stderr,
        "default_printer": detected_printer.get("printer", ""),
        "job_id": job_id,
        "cups_status": cups_status,
    }


def print_ticket_via_cups(venta_id: int) -> dict[str, object]:
    if not is_linux_platform():
        return {
            "ok": False,
            "message": "La impresión backend Linux solo está disponible en esta plataforma.",
        }

    pdf_result = build_ticket_pdf(venta_id)
    if not pdf_result.get("ok"):
        return pdf_result

    print_result = send_file_to_printer(pdf_result["pdf_path"])
    print_result["pdf_path"] = pdf_result["pdf_path"]
    print_result["pdf_pages"] = pdf_result.get("pdf_pages", 0)
    print_result["page_width_mm"] = pdf_result.get("page_width_mm")
    print_result["page_height_mm"] = pdf_result.get("page_height_mm")
    return print_result
