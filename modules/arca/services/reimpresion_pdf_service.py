from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import database as db
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from modules.arca.services.comprobantes_service import (
    actualizar_pdf_path,
    comprobante_es_final,
    formatear_numero_comprobante,
    obtener_comprobante_por_venta,
)
from modules.arca.services.facturacion_desde_venta_service import calcular_pdf_path_futuro
from services.arca_config_service import get_config


logger = logging.getLogger(__name__)


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 42
MARGIN_Y = 48
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)
LINE_HEIGHT = 14
HEADER_HEIGHT = 170
DEBUG_TEMPLATE_NAME = "reportlab_pdf_directo_sin_template_html"


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _to_float(value: object) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _format_currency(value: object) -> str:
    number = _to_float(value)
    entero, decimales = f"{number:,.2f}".split(".")
    return f"$ {entero.replace(',', '.')},{decimales}"


def _format_date(value: object) -> str:
    raw = _clean_text(value)
    if not raw:
        return "-"
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def _format_datetime_now() -> str:
    return datetime.now().replace(microsecond=0).strftime("%d/%m/%Y %H:%M")


def _format_condicion_fiscal(value: object) -> str:
    raw = _clean_text(value).replace("_", " ")
    return raw.title() if raw else "-"


def _format_quantity(value: object) -> str:
    number = _to_float(value)
    if float(number).is_integer():
        return str(int(number))
    return f"{number:.2f}".replace(".", ",")


def _extract_digits(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _format_document(value: object) -> str:
    digits = _extract_digits(value)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10:]}"
    return digits


def _format_comprobante_letter(tipo_comprobante: object) -> str:
    tipo = _clean_text(tipo_comprobante).upper()
    for letter in ("A", "B", "C", "M", "E"):
        if tipo.endswith(letter):
            return letter
    return "-"


def _format_comprobante_nombre(tipo_comprobante: object) -> str:
    tipo = _clean_text(tipo_comprobante)
    if not tipo:
        return "COMPROBANTE"
    if " " in tipo:
        return tipo.rsplit(" ", 1)[0].upper()
    return tipo.upper()


def _resolve_cliente_fiscal(venta: dict[str, object]) -> dict[str, str]:
    cliente_id = int(venta.get("cliente_id") or 0)
    cliente_nombre = _clean_text(venta.get("cliente_nombre"))
    cliente_row = db.get_cliente(cliente_id) if cliente_id > 0 else None
    cliente = dict(cliente_row) if cliente_row else {}

    nombre = _clean_text(cliente.get("nombre")) or cliente_nombre
    documento = _extract_digits(cliente.get("dni_cuit"))

    es_consumidor_final = cliente_id <= 0 or cliente_nombre.lower() == "mostrador" or not nombre
    if es_consumidor_final:
        return {
            "nombre": "CONSUMIDOR FINAL",
            "documento": "",
            "documento_label": "Documento fiscal",
        }

    documento_label = "CUIT" if len(documento) == 11 else "DNI" if documento else "Documento fiscal"
    return {
        "nombre": nombre,
        "documento": documento,
        "documento_label": documento_label,
    }


def _resolve_encabezado_emisor(config: dict[str, object]) -> dict[str, str]:
    negocio = db.get_config()
    nombre_fantasia = _clean_text(config.get("nombre_fantasia"))
    if not nombre_fantasia:
        nombre_fantasia = _clean_text(negocio.get("nombre_negocio"))
    razon_social = _clean_text(config.get("razon_social"))
    if not razon_social:
        razon_social = nombre_fantasia or "Nexar Comercio"
    if not nombre_fantasia:
        nombre_fantasia = razon_social or "Nexar Comercio"
    domicilio = (
        _clean_text(config.get("domicilio_fiscal"))
        or _clean_text(negocio.get("direccion"))
    )
    return {
        "nombre_fantasia": nombre_fantasia,
        "razon_social": razon_social,
        "domicilio": domicilio,
    }


def _log_reimpresion(event: str, **data: object) -> None:
    payload = " ".join(f"{key}={value!r}" for key, value in data.items())
    logger.info("[ARCA REIMPRESION] %s %s", event, payload)


def _resolve_output_path(venta_id: int, comprobante: dict[str, object]) -> Path:
    existing = _clean_text(comprobante.get("pdf_path"))
    if existing:
        return Path(existing).expanduser().resolve()

    generated = calcular_pdf_path_futuro(
        venta_id=int(venta_id),
        fecha_emision=comprobante.get("fecha_emision"),
        punto_venta=int(comprobante.get("punto_venta") or 0),
        numero_comprobante=int(comprobante.get("numero_comprobante") or comprobante.get("numero") or 0),
    )
    return Path(generated).expanduser().resolve()


def _wrap_text(text: object, font_name: str, font_size: int, max_width: float) -> list[str]:
    raw = _clean_text(text)
    if not raw:
        return [""]
    words = raw.split()
    if not words:
        return [raw]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _build_context(venta_id: int) -> dict[str, object]:
    venta_row = db.q("SELECT * FROM ventas WHERE id = ?", (int(venta_id),), fetchone=True)
    if not venta_row:
        return {
            "ok": False,
            "error_code": "venta_no_encontrada",
            "message": f"No se encontró la venta #{venta_id}.",
        }

    comprobante = obtener_comprobante_por_venta(int(venta_id))
    if not comprobante or not comprobante_es_final(comprobante):
        return {
            "ok": False,
            "error_code": "comprobante_no_encontrado",
            "message": "La venta no tiene un comprobante ARCA autorizado para reimprimir.",
            "venta": dict(venta_row),
        }

    detalle = [dict(item) for item in db.get_venta_detalle(int(venta_id))]
    return {
        "ok": True,
        "venta": dict(venta_row),
        "detalle": detalle,
        "comprobante": comprobante,
        "config": get_config(),
        "cliente_fiscal": _resolve_cliente_fiscal(dict(venta_row)),
        "qr": {
            "enabled": False,
            "data": "",
            "label": "QR fiscal pendiente de implementación",
            "todo": "Fase futura: generar QR oficial ARCA/AFIP desde datos persistidos del comprobante.",
        },
    }


def get_comprobante_pdf_context(venta_id: int) -> dict[str, object]:
    context = _build_context(int(venta_id))
    _log_reimpresion(
        "context_built",
        venta_id=int(venta_id),
        ok=bool(context.get("ok")),
        service="modules.arca.services.reimpresion_pdf_service.get_comprobante_pdf_context",
        template=DEBUG_TEMPLATE_NAME,
    )
    return context


def _draw_label_value(c: canvas.Canvas, x: float, y: float, label: str, value: str) -> None:
    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica", 8)
    c.drawString(x, y, label)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y - 12, value)


def _draw_box(c: canvas.Canvas, x: float, y: float, width: float, height: float, *, fill_color: str, stroke_color: str = "#D7DEE7", radius: int = 10) -> None:
    c.setFillColor(colors.HexColor(fill_color))
    c.setStrokeColor(colors.HexColor(stroke_color))
    c.roundRect(x, y, width, height, radius, fill=1, stroke=1)


def _draw_header(c: canvas.Canvas, context: dict[str, object]) -> float:
    config = dict(context["config"])
    comprobante = dict(context["comprobante"])
    emisor = _resolve_encabezado_emisor(config)
    nombre_fantasia = emisor["nombre_fantasia"]
    razon_social = emisor["razon_social"]
    tipo_comprobante = _clean_text(comprobante.get("tipo_comprobante")) or "Comprobante"
    letra = _format_comprobante_letter(tipo_comprobante)
    nombre_comprobante = _format_comprobante_nombre(tipo_comprobante)
    header_top = PAGE_HEIGHT - MARGIN_Y
    left_width = CONTENT_WIDTH - 166
    right_width = 154
    left_x = MARGIN_X
    right_x = MARGIN_X + left_width + 12
    box_y = header_top - 122

    _draw_box(c, left_x, box_y, left_width, 122, fill_color="#F8FAFC")
    _draw_box(c, right_x, box_y, right_width, 122, fill_color="#FFF7ED", stroke_color="#F2C58B")

    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(left_x + 14, header_top - 16, "ORIGINAL")
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(left_x + 14, header_top - 38, nombre_fantasia)
    c.setFont("Helvetica", 11)
    c.drawString(left_x + 14, header_top - 56, razon_social)
    c.setFont("Helvetica", 9)
    c.drawString(left_x + 14, header_top - 74, f"CUIT: {_format_document(config.get('cuit')) or '-'}")
    c.drawString(left_x + 14, header_top - 88, f"Condición frente al IVA: {_format_condicion_fiscal(config.get('condicion_fiscal'))}")
    if emisor.get("domicilio"):
        domicilio_lines = _wrap_text(emisor["domicilio"], "Helvetica", 9, left_width - 28)
        c.drawString(left_x + 14, header_top - 102, f"Domicilio comercial: {domicilio_lines[0]}")
        if len(domicilio_lines) > 1:
            c.drawString(left_x + 14, header_top - 114, domicilio_lines[1])

    c.setFillColor(colors.HexColor("#92400E"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(right_x + (right_width / 2), header_top - 18, "COMPROBANTE")
    c.setFillColor(colors.HexColor("#7C2D12"))
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(right_x + (right_width / 2), header_top - 58, letra)
    c.setFillColor(colors.HexColor("#9A3412"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(right_x + (right_width / 2), header_top - 82, nombre_comprobante)
    c.setFillColor(colors.HexColor("#78350F"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(right_x + (right_width / 2), header_top - 100, formatear_numero_comprobante(comprobante))

    return box_y - 14


def _draw_summary(c: canvas.Canvas, context: dict[str, object], start_y: float) -> float:
    venta = dict(context["venta"])
    comprobante = dict(context["comprobante"])
    cliente_fiscal = dict(context["cliente_fiscal"])
    y = start_y
    left_width = CONTENT_WIDTH * 0.57
    right_width = CONTENT_WIDTH - left_width - 12
    left_x = MARGIN_X
    right_x = MARGIN_X + left_width + 12

    _draw_box(c, left_x, y - 82, left_width, 82, fill_color="#FFFFFF")
    _draw_box(c, right_x, y - 82, right_width, 82, fill_color="#FFFFFF")

    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(left_x + 12, y - 14, "DATOS DEL CLIENTE")
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left_x + 12, y - 30, _clean_text(cliente_fiscal.get("nombre")) or "CONSUMIDOR FINAL")
    c.setFont("Helvetica", 9)
    c.drawString(
        left_x + 12,
        y - 46,
        f"{_clean_text(cliente_fiscal.get('documento_label')) or 'Documento'}: {_format_document(cliente_fiscal.get('documento')) or '-'}",
    )
    c.drawString(left_x + 12, y - 60, f"Condición de venta: {_clean_text(venta.get('medio_pago')) or 'No informada'}")

    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(right_x + 12, y - 14, "DATOS DEL COMPROBANTE")
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica", 9)
    c.drawString(right_x + 12, y - 30, f"Tipo: {_clean_text(comprobante.get('tipo_comprobante')) or '-'}")
    c.drawString(right_x + 12, y - 44, f"Punto de venta: {int(comprobante.get('punto_venta') or 0):04d}")
    c.drawString(right_x + 12, y - 58, f"Comp. Nro: {formatear_numero_comprobante(comprobante)}")
    c.drawString(
        right_x + 12,
        y - 72,
        f"Fecha de emisión: {_format_date(comprobante.get('fecha_emision') or venta.get('fecha'))}",
    )

    y -= 98
    _draw_box(c, MARGIN_X, y - 56, CONTENT_WIDTH, 56, fill_color="#EFF6FF", stroke_color="#BFDBFE")
    gap = 10
    inner_x = MARGIN_X + 10
    inner_y = y - 48
    inner_height = 38
    inner_width = (CONTENT_WIDTH - 20 - (gap * 2)) / 3
    bloques = [
        ("CAE", _clean_text(comprobante.get("cae")) or "-"),
        ("Vto. CAE", _format_date(comprobante.get("cae_vencimiento"))),
        ("Reimpresión", _format_datetime_now()),
    ]
    for index, (label, value) in enumerate(bloques):
        box_x = inner_x + (index * (inner_width + gap))
        _draw_box(
            c,
            box_x,
            inner_y,
            inner_width,
            inner_height,
            fill_color="#FFFFFF",
            stroke_color="#D6E4FF",
            radius=8,
        )
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(box_x + (inner_width / 2), inner_y + 25, label)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(box_x + (inner_width / 2), inner_y + 11, value)
    return y - 70


def _draw_items_table(c: canvas.Canvas, context: dict[str, object], start_y: float) -> float:
    detalle = list(context["detalle"])
    venta = dict(context["venta"])
    y = start_y

    c.setFillColor(colors.HexColor("#E2E8F0"))
    c.roundRect(MARGIN_X, y - 24, CONTENT_WIDTH, 24, 6, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN_X + 10, y - 15, "Producto / Servicio")
    c.drawString(MARGIN_X + 302, y - 15, "Cantidad")
    c.drawRightString(MARGIN_X + 420, y - 15, "Precio Unit.")
    c.drawRightString(PAGE_WIDTH - MARGIN_X - 10, y - 15, "Subtotal")
    y -= 36

    for item in detalle:
        descripcion = _clean_text(item.get("descripcion")) or "Producto"
        cantidad = _format_quantity(item.get("cantidad"))
        precio_unitario = _format_currency(item.get("precio_unitario"))
        subtotal = _format_currency(item.get("subtotal"))
        description_lines = _wrap_text(descripcion, "Helvetica", 10, 270)
        row_top_y = y
        text_top_padding = 2
        text_bottom_padding = 8
        text_y = row_top_y - text_top_padding
        for line in description_lines:
            c.setFont("Helvetica", 10)
            c.drawString(MARGIN_X + 10, text_y, line)
            text_y -= LINE_HEIGHT
        row_height = max(24, len(description_lines) * LINE_HEIGHT + text_top_padding + text_bottom_padding)
        row_bottom_y = row_top_y - row_height
        value_y = row_top_y - 11
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN_X + 302, value_y, cantidad)
        c.drawRightString(MARGIN_X + 420, value_y, precio_unitario)
        c.drawRightString(PAGE_WIDTH - MARGIN_X - 10, value_y, subtotal)
        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.line(MARGIN_X + 10, row_bottom_y, PAGE_WIDTH - MARGIN_X - 10, row_bottom_y)
        y = row_bottom_y - 10

    subtotal_venta = _to_float(venta.get("subtotal"))
    descuento_venta = _to_float(venta.get("descuento_adicional"))
    total_venta = _to_float(venta.get("total"))

    c.setFont("Helvetica", 10)
    c.drawRightString(PAGE_WIDTH - MARGIN_X - 120, y - 10, "Subtotal")
    c.drawRightString(PAGE_WIDTH - MARGIN_X - 10, y - 10, _format_currency(subtotal_venta))
    y -= 24

    if descuento_venta > 0:
        c.setFillColor(colors.HexColor("#B91C1C"))
        c.setFont("Helvetica", 10)
        c.drawRightString(PAGE_WIDTH - MARGIN_X - 120, y - 10, "Descuento")
        c.drawRightString(PAGE_WIDTH - MARGIN_X - 10, y - 10, f"-{_format_currency(descuento_venta)}")
        c.setFillColor(colors.HexColor("#0F172A"))
        y -= 24

    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(PAGE_WIDTH - MARGIN_X - 120, y - 2, "Total")
    c.drawRightString(PAGE_WIDTH - MARGIN_X - 10, y - 2, _format_currency(total_venta))
    return y - 28


def _draw_qr_placeholder(c: canvas.Canvas, context: dict[str, object], y: float) -> float:
    qr = dict(context["qr"])
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.roundRect(MARGIN_X, y - 90, CONTENT_WIDTH, 90, 10, fill=1, stroke=1)
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.rect(MARGIN_X + 16, y - 74, 58, 58, fill=0, stroke=1)
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN_X + 90, y - 28, _clean_text(qr.get("label")) or "QR fiscal")
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN_X + 90, y - 44, "Espacio reservado para QR fiscal.")
    c.drawString(MARGIN_X + 90, y - 58, "La reimpresión actual usa solo datos persistidos del comprobante.")
    return y - 108


def _draw_footer(c: canvas.Canvas, context: dict[str, object], y: float) -> None:
    comprobante = dict(context["comprobante"])
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.line(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y)
    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica", 8)
    c.drawString(
        MARGIN_X,
        y - 16,
        "Reimpresión local generada desde datos persistidos. No se solicitó un nuevo CAE.",
    )
    c.drawRightString(
        PAGE_WIDTH - MARGIN_X,
        y - 16,
        f"Estado: {_clean_text(comprobante.get('estado')) or '-'}",
    )


def generar_pdf_comprobante_arca(venta_id: int, force_regenerate: bool = False) -> dict[str, object]:
    context = _build_context(int(venta_id))
    _log_reimpresion(
        "generar_pdf_inicio",
        venta_id=int(venta_id),
        service="modules.arca.services.reimpresion_pdf_service.generar_pdf_comprobante_arca",
        template=DEBUG_TEMPLATE_NAME,
        force_regenerate=bool(force_regenerate),
        context_ok=bool(context.get("ok")),
    )
    if not context.get("ok"):
        _log_reimpresion(
            "generar_pdf_context_error",
            venta_id=int(venta_id),
            error_code=context.get("error_code"),
            message=context.get("message"),
        )
        return context

    comprobante = dict(context["comprobante"])
    venta = dict(context["venta"])
    config = dict(context["config"])
    cliente_fiscal = dict(context["cliente_fiscal"])
    emisor = _resolve_encabezado_emisor(config)
    output_path = _resolve_output_path(int(venta_id), comprobante)
    tipo_comprobante = _clean_text(comprobante.get("tipo_comprobante")) or "-"
    numero_comprobante = formatear_numero_comprobante(comprobante)
    _log_reimpresion(
        "contexto_resuelto",
        venta_id=int(venta_id),
        ruta_flask="/arca/comprobante/<venta_id>/pdf o /arca/comprobante/<venta_id>/abrir",
        service="modules.arca.services.reimpresion_pdf_service.generar_pdf_comprobante_arca",
        template=DEBUG_TEMPLATE_NAME,
        nombre_fantasia=emisor.get("nombre_fantasia"),
        razon_social=emisor.get("razon_social"),
        nombre_fantasia_source=(
            "arca_configuracion.nombre_fantasia"
            if _clean_text(config.get("nombre_fantasia"))
            else "config.nombre_negocio"
            if _clean_text(db.get_config().get("nombre_negocio"))
            else "fallback:Nexar Comercio/razon_social"
        ),
        razon_social_source=(
            "arca_configuracion.razon_social"
            if _clean_text(config.get("razon_social"))
            else "fallback:nombre_fantasia"
        ),
        tipo_comprobante=tipo_comprobante,
        numero_comprobante=numero_comprobante,
        cliente_fiscal_nombre=cliente_fiscal.get("nombre"),
        cliente_fiscal_documento=cliente_fiscal.get("documento"),
        cliente_fiscal_label=cliente_fiscal.get("documento_label"),
        venta_cliente_nombre=venta.get("cliente_nombre"),
        comprobante_id=comprobante.get("id"),
        comprobante_estado=comprobante.get("estado"),
        comprobante_pdf_path=comprobante.get("pdf_path"),
        output_path=str(output_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not force_regenerate:
        _log_reimpresion(
            "pdf_existente_reutilizado",
            venta_id=int(venta_id),
            output_path=str(output_path),
            reused_existing=True,
        )
        return {
            "ok": True,
            "message": "PDF ARCA listo para descarga.",
            "venta": context["venta"],
            "comprobante": comprobante,
            "pdf_path": str(output_path),
            "reused_existing": True,
            "generated": False,
            "qr": context["qr"],
        }

    c = canvas.Canvas(str(output_path), pagesize=A4, pageCompression=0)
    c.setTitle(_clean_text(comprobante.get("comprobante_formateado")) or f"Comprobante ARCA venta {venta_id}")

    next_y = _draw_header(c, context)
    next_y = _draw_summary(c, context, next_y)
    next_y = _draw_items_table(c, context, next_y)
    next_y = _draw_qr_placeholder(c, context, next_y)
    _draw_footer(c, context, max(next_y, 64))
    c.save()

    updated = actualizar_pdf_path(int(comprobante.get("id") or 0), str(output_path))
    _log_reimpresion(
        "pdf_generado",
        venta_id=int(venta_id),
        output_path=str(output_path),
        updated_pdf_path=(updated or comprobante).get("pdf_path"),
        tipo_comprobante=tipo_comprobante,
        numero_comprobante=numero_comprobante,
    )
    return {
        "ok": True,
        "message": "PDF ARCA generado correctamente.",
        "venta": context["venta"],
        "comprobante": updated or comprobante,
        "pdf_path": str(output_path),
        "reused_existing": False,
        "generated": True,
        "qr": context["qr"],
    }
