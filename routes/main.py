from __future__ import annotations

import csv
import json
import logging
import os
import time
import re
import shutil
import subprocess
import sys
import threading
import platform
import webbrowser
from uuid import uuid4
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO, StringIO
from pathlib import Path

import database as db
from flask import Blueprint, Response, abort, current_app, flash, has_request_context, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename
from licensing.planes import (
    PLANES,
    get_commercial_plan_options,
    get_plan_actions,
    get_plan_display_name,
    get_license_status_context,
    get_update_access_context,
    normalize_plan,
)
from licensing.permisos import get_modulos_activos, get_modulos_debug_info, require_modulo
from services.cuentas_corrientes import calcular_estado_factura, calcular_saldo_factura
from services.file_open_service import open_file_cross_platform
from services.license_storage import cargar_licencia, guardar_licencia
from services.print_service import print_ticket_via_cups
from services.rubros import (
    convertir_cantidad_a_base,
    convertir_cantidad_desde_base,
    convertir_precio_desde_base,
    get_categoria_default,
    get_categorias_disponibles,
    get_rubro_actual,
    get_rubro_label,
    get_rubros_disponibles,
    get_unidad_label,
    get_unidades_disponibles,
    normalizar_rubro,
    normalizar_unidad,
)
from services.mercadopago_checkout import (
    MercadoPagoCheckoutError,
    build_external_reference,
    create_checkout_preference,
    get_price_for_plan,
    plan_supports_checkout,
)
from services import pricing_resolver
from services.license_sdk import (
    get_current_hwid,
    get_license_debug_state,
    get_license_product,
    refresh_saved_license_online,
    validate_license_key,
)
from services.demo_eligibility import (
    DEMO_ACTIVE,
    DEMO_ALREADY_USED,
    DEMO_BLOCKED,
    DEMO_ELIGIBLE,
    DEMO_ERROR,
    DEMO_EXPIRED,
    DEMO_OFFLINE_UNVERIFIED,
    DemoEligibilityResult,
    build_demo_identity,
    build_demo_metadata,
    mask_identifier,
    resolve_demo_eligibility_from_records,
)
from services.paths import (
    get_app_data_dir,
    get_backups_dir,
    get_exports_dir,
    get_logs_dir,
    get_updates_dir,
)
from services.supabase_license_api import (
    create_demo_request,
    create_license_request,
    create_support_request,
    create_upgrade_request,
    find_demo_requests_for_identity,
    find_active_license_for_machine,
    generate_activation_id,
    get_supabase_debug_state,
    is_configured as supabase_configured,
    update_license_vendor_code,
)
from services.update_checker import download_release_asset, get_cached_update_info

main_bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = None
BACKUP_DIR = None
UPDATE_DIR = None
LOG_DIR = None
CHANGELOG_PATH = BASE_DIR / "CHANGELOG.md"
LICENSE_TEXT_PATH = BASE_DIR / "LICENSE.txt"
WINDOWS_UPDATE_STATUS_PATH = None
WINDOWS_UPDATE_LAUNCHER_PATH = None
WINDOWS_UPDATE_LOG_PATH = None

DESKTOP_STATE = {
    "user_logged_in": False,
    "close_warning_requested": False,
}

LICENSE_AUTO_REFRESH_INTERVAL_SECONDS = 300
_LICENSE_REFRESH_LOCK = threading.Lock()
_LICENSE_REFRESH_THREAD_LOCK = threading.Lock()
_LICENSE_REFRESH_LAST_RESULT: dict[str, object] = {
    "ok": False,
    "changed": False,
    "message": "",
}
_LICENSE_REFRESH_LAST_RUN = 0.0


def _data_dir() -> Path:
    return DATA_DIR if isinstance(DATA_DIR, Path) else get_app_data_dir()


def _backup_dir() -> Path:
    return BACKUP_DIR if isinstance(BACKUP_DIR, Path) else get_backups_dir()


def _update_dir() -> Path:
    return UPDATE_DIR if isinstance(UPDATE_DIR, Path) else get_updates_dir()


def _log_dir() -> Path:
    return LOG_DIR if isinstance(LOG_DIR, Path) else get_logs_dir()


def _windows_update_status_path() -> Path:
    if isinstance(WINDOWS_UPDATE_STATUS_PATH, Path):
        return WINDOWS_UPDATE_STATUS_PATH
    return _update_dir() / "windows_update_status.json"


def _windows_update_launcher_path() -> Path:
    if isinstance(WINDOWS_UPDATE_LAUNCHER_PATH, Path):
        return WINDOWS_UPDATE_LAUNCHER_PATH
    return _update_dir() / "windows_update_launcher.ps1"


def _windows_update_log_path() -> Path:
    if isinstance(WINDOWS_UPDATE_LOG_PATH, Path):
        return WINDOWS_UPDATE_LOG_PATH
    return _log_dir() / "update-installer.log"

PURCHASE_DRAFT_FIELDS = (
    "fecha",
    "numero_remito",
    "proveedor_id",
    "producto_id",
    "cantidad",
    "costo_unitario",
    "condicion_pago",
    "numero_factura",
    "fecha_factura",
    "fecha_vencimiento",
    "observaciones_factura",
    "observaciones",
    "producto_descripcion",
    "codigo_barras",
)

PRODUCTOS_IMPORT_CSV_COLUMNS = [
    "descripcion",
    "marca",
    "categoria",
    "proveedor_habitual",
    "codigo_barras",
    "costo",
    "precio_venta",
    "stock_actual",
    "stock_minimo",
    "stock_maximo",
    "unidad",
]
PRODUCTOS_IMPORT_REQUIRED_COLUMNS = {
    "descripcion",
    "costo",
    "precio_venta",
    "stock_actual",
}
PRODUCTOS_IMPORT_TEMPLATE_FILENAME = "plantilla_productos_nexar.csv"
PRODUCTOS_UPLOAD_SUBDIR = Path("uploads") / "productos"
PRODUCTOS_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PRODUCTOS_IMAGE_MAX_BYTES = 3 * 1024 * 1024


def _as_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes", "si"}


def _debug_license_enabled() -> bool:
    return (
        current_app.debug
        or os.getenv("ENV", "").strip().lower() == "development"
        or os.getenv("FLASK_ENV", "").strip().lower() == "development"
    )


def _is_same_origin_local_request() -> bool:
    if request.remote_addr not in {"127.0.0.1", "::1", "localhost"}:
        return False
    expected = request.host_url.rstrip("/")
    for header in ("Origin", "Referer"):
        value = request.headers.get(header, "").rstrip("/")
        if value and not value.startswith(expected):
            return False
    return True


def _safe_next_url(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if text.startswith("/") and not text.startswith("//"):
        return text
    return fallback


def _validate_password(password: str) -> tuple[bool, str]:
    if len(password or "") < 6 or len(password or "") > 12:
        return False, "La contraseña debe tener entre 6 y 12 caracteres."
    if not re.search(r"[A-Z]", password or ""):
        return False, "La contraseña debe incluir una mayúscula."
    if not re.search(r"[a-z]", password or ""):
        return False, "La contraseña debe incluir una minúscula."
    if not re.search(r"[0-9]", password or ""):
        return False, "La contraseña debe incluir un número."
    if not re.search(r"[^A-Za-z0-9]", password or ""):
        return False, "La contraseña debe incluir un símbolo."
    return True, ""


def _validate_password_confirmation(password: str, confirmation: str) -> tuple[bool, str]:
    if password != confirmation:
        return False, "Las contraseñas no coinciden."
    return _validate_password(password)


def _validate_security_recovery(question: str, answer: str) -> tuple[bool, str]:
    if not (question or "").strip() or not (answer or "").strip():
        return False, "La pregunta y la respuesta secreta son obligatorias."
    if len((answer or "").strip()) < 2:
        return False, "La respuesta secreta debe tener al menos 2 caracteres."
    return True, ""


def _purchase_draft_from_source(source) -> dict[str, str]:
    draft: dict[str, str] = {}
    for field in PURCHASE_DRAFT_FIELDS:
        value = source.get(field, "")
        draft[field] = str(value or "").strip()
    return draft


def _purchase_draft_query(draft: dict[str, str], **extra: str) -> dict[str, str]:
    query = {key: value for key, value in draft.items() if str(value or "").strip()}
    for key, value in extra.items():
        if str(value or "").strip():
            query[key] = str(value).strip()
    return query


def _limit_allows(kind: str) -> bool:
    current_sql = {
        "productos": "SELECT COUNT(*) FROM productos WHERE activo=1",
        "clientes": "SELECT COUNT(*) FROM clientes WHERE activo=1",
        "proveedores": "SELECT COUNT(*) FROM proveedores WHERE activo=1",
    }[kind]
    current = int(db.q(current_sql, fetchone=True)[0] or 0)
    check = db.check_license_limits(kind, current + 1)
    if not check["ok"]:
        flash(f"⚠️ {check['message']}", "warning")
        return False
    return True


def _first_non_empty(*values) -> str:
    for value in values:
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _parse_positive_percentage(raw_value) -> float:
    try:
        porcentaje = float(str(raw_value or "").replace(",", "."))
    except ValueError as exc:
        raise ValueError("El porcentaje debe ser un número válido.") from exc
    if porcentaje <= 0:
        raise ValueError("El porcentaje debe ser mayor a 0.")
    return porcentaje


def _build_precios_preview_rows(productos_rows, porcentaje: float) -> list[dict]:
    factor = 1 + (porcentaje / 100.0)
    preview = []
    for row in productos_rows:
        item = dict(row)
        item["costo_nuevo"] = round(float(item.get("costo") or 0) * factor, 2)
        item["precio_venta_nuevo"] = round(float(item.get("precio_venta") or 0) * factor, 2)
        preview.append(item)
    return preview


def _normalizar_csv_header(value: str) -> str:
    return str(value or "").strip().lower()


def _normalizar_codigo_barras(value) -> str:
    return str(value or "").strip()


def _validar_codigos_barras_manuales(filas: list[dict], errores: list[str], *, row_label_key: str) -> None:
    vistos: dict[str, str] = {}
    for fila in filas:
        codigo = _normalizar_codigo_barras(fila.get("codigo_barras"))
        if not codigo:
            continue
        codigo_key = codigo.lower()
        row_label = str(fila.get(row_label_key) or "fila")
        if codigo_key in vistos:
            errores.append(f"{row_label}: el código de barras '{codigo}' está repetido dentro de la carga.")
            continue
        if db.codigo_barras_exists(codigo):
            errores.append(f"{row_label}: ya existe un producto con el código de barras '{codigo}'.")
            continue
        vistos[codigo_key] = row_label


def _parse_float_csv(value, field_name: str, row_number: int, *, allow_zero: bool = True, must_be_positive: bool = False) -> float:
    texto = str(value or "").strip().replace(",", ".")
    if texto == "":
        raise ValueError(f"Fila {row_number}: {field_name} es obligatorio.")
    try:
        numero = float(texto)
    except ValueError as exc:
        raise ValueError(f"Fila {row_number}: {field_name} debe ser numérico.") from exc
    if numero < 0:
        raise ValueError(f"Fila {row_number}: {field_name} no puede ser negativo.")
    if not allow_zero and numero == 0:
        raise ValueError(f"Fila {row_number}: {field_name} no puede ser cero.")
    if must_be_positive and numero <= 0:
        raise ValueError(f"Fila {row_number}: {field_name} debe ser mayor a 0.")
    return numero


def _validar_fila_importacion_producto(row: dict[str, str], row_number: int, rubro_actual: str) -> dict[str, str] | None:
    normalized = {
        key: str(row.get(key, "") or "").strip()
        for key in PRODUCTOS_IMPORT_CSV_COLUMNS
    }
    if not any(normalized.values()):
        return None
    if not normalized["descripcion"]:
        raise ValueError(f"Fila {row_number}: descripcion es obligatoria.")

    costo = _parse_float_csv(normalized["costo"], "costo", row_number)
    precio_venta = _parse_float_csv(normalized["precio_venta"], "precio_venta", row_number)
    stock_actual = _parse_float_csv(
        normalized["stock_actual"],
        "stock_actual",
        row_number,
        allow_zero=False,
        must_be_positive=True,
    )

    stock_minimo = 5.0
    if normalized["stock_minimo"]:
        stock_minimo = _parse_float_csv(normalized["stock_minimo"], "stock_minimo", row_number)

    stock_maximo = 50.0
    if normalized["stock_maximo"]:
        stock_maximo = _parse_float_csv(normalized["stock_maximo"], "stock_maximo", row_number)

    unidad = normalizar_unidad(normalized["unidad"] or "unidad", rubro_actual)
    categoria = normalized["categoria"] or get_categoria_default(rubro_actual)

    return {
        "descripcion": normalized["descripcion"],
        "marca": normalized["marca"],
        "categoria": categoria,
        "proveedor_habitual": normalized["proveedor_habitual"],
        "codigo_barras": normalized["codigo_barras"],
        "costo": str(costo),
        "precio_venta": str(precio_venta),
        "stock_actual": str(stock_actual),
        "stock_minimo": str(stock_minimo),
        "stock_maximo": str(stock_maximo),
        "tipo_unidad": unidad,
        "unidad": unidad,
        "_row_label": f"Fila {row_number}",
    }


def _get_productos_import_template_dir() -> Path:
    return get_exports_dir() / "plantillas"


def _save_producto_image(file_storage) -> str:
    filename = str(getattr(file_storage, "filename", "") or "").strip()
    if not filename:
        return ""

    safe_name = secure_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in PRODUCTOS_IMAGE_EXTENSIONS:
        raise ValueError("La imagen debe ser JPG, JPEG, PNG o WEBP.")

    try:
        file_storage.stream.seek(0, os.SEEK_END)
        file_size = file_storage.stream.tell()
        file_storage.stream.seek(0)
    except Exception:
        file_size = 0
    if file_size <= 0:
        raise ValueError("La imagen seleccionada esta vacia o no se pudo leer.")
    if file_size > PRODUCTOS_IMAGE_MAX_BYTES:
        raise ValueError("Imagen demasiado grande. Usa una imagen de hasta 3 MB.")

    relative_path = (PRODUCTOS_UPLOAD_SUBDIR / f"producto_{uuid4().hex}{suffix}").as_posix()
    save_path = Path(current_app.static_folder) / Path(relative_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(save_path)
    return relative_path


def _build_productos_import_template_csv() -> str:
    ejemplo = [
        "Mate imperial azul",
        "Artesanal",
        "Mates",
        "Distribuidora San Juan",
        "",
        "1000",
        "1800",
        "1",
        "1",
        "10",
        "unidad",
    ]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(PRODUCTOS_IMPORT_CSV_COLUMNS)
    writer.writerow(ejemplo)
    return output.getvalue()


def _resolve_productos_import_target_dir(destino: str) -> tuple[Path, str | None]:
    destino_normalizado = str(destino or "app").strip().lower()
    app_dir = _get_productos_import_template_dir()
    if destino_normalizado == "downloads":
        xdg_download_dir = os.getenv("XDG_DOWNLOAD_DIR", "").strip()
        candidate_paths: list[Path] = []
        if xdg_download_dir:
            candidate_paths.append(Path(xdg_download_dir.replace("$HOME", str(Path.home()))).expanduser())
        candidate_paths.extend(
            [
                Path.home() / "Downloads",
                Path.home() / "Descargas",
                Path.home() / "descargas",
            ]
        )
        for candidate in candidate_paths:
            if candidate.exists():
                return candidate, None
        home_dir = Path.home()
        if home_dir.exists():
            return home_dir, "No se encontró una carpeta de descargas válida. Se usó la carpeta personal del usuario."
        return app_dir, "No se encontró una carpeta de descargas válida ni la carpeta personal. Se usó la carpeta de la aplicación."
    return app_dir, None


def _enriquecer_facturas_proveedor(facturas) -> list[dict]:
    resultado = []
    for factura in facturas:
        item = dict(factura)
        item["saldo"] = calcular_saldo_factura(factura)
        item["estado"] = calcular_estado_factura(factura)
        resultado.append(item)
    return resultado


def _get_proveedor_or_404(pid):
    proveedor = db.get_proveedor(pid)
    if not proveedor:
        abort(404)
    return proveedor


def _get_factura_proveedor_or_404(pid, factura_id):
    factura = db.get_factura_proveedor(factura_id)
    if not factura or int(factura["proveedor_id"] or 0) != int(pid):
        abort(404)
    return factura


def _mask_license_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if len(normalized) <= 6:
        return f"{normalized[:1]}***{normalized[-1:]}"
    return f"{normalized[:3]}***{normalized[-3:]}"


def _resolve_next_upgrade_plan(license_info: dict[str, object] | None) -> str:
    available = _get_available_checkout_plans(license_info)
    return available[0] if available else ""


def _get_checkout_license_key(license_info: dict[str, object] | None = None) -> str:
    info = license_info or {}
    return str(info.get("key", "") or "").strip()


def _has_checkout_license(license_info: dict[str, object] | None = None) -> bool:
    license_info = license_info or {}
    license_key = _get_checkout_license_key(license_info)
    if license_key:
        return True
    normalized_tier = normalize_plan(license_info.get("tier", "DEMO"), default="DEMO")
    return normalized_tier in {"DEMO", "SIN_PLAN"}


def _get_plan_actions_context(
    license_info: dict[str, object] | None,
    *,
    tiene_checkout: bool | None = None,
    license_status: dict[str, object] | None = None,
) -> dict[str, object]:
    license_info = license_info or {}
    basica_activada = bool(license_info.get("plan_base_permanente"))
    if not basica_activada:
        basica_activada = _as_bool(db.get_config().get("basica_activada", "0"))
    status = license_status or _get_license_status_context(license_info)
    status_expired = status.get("estado_comercial") in {"demo_vencido", "pro_vencido", "full_vencido"}
    return get_plan_actions(
        license_info.get("tier", "DEMO"),
        basica_activada=basica_activada,
        licencia_vencida=bool(license_info.get("expirada")) or bool(status_expired),
        licencia_bloqueada=status.get("estado_comercial") == "licencia_bloqueada",
        tiene_checkout=_has_checkout_license(license_info) if tiene_checkout is None else tiene_checkout,
        plan_original=status.get("plan_original"),
        dias_para_vencer=status.get("dias_para_vencer"),
    )


def _get_license_status_context(
    license_info: dict[str, object] | None,
    *,
    demo_status: dict[str, object] | None = None,
) -> dict[str, object]:
    return get_license_status_context(
        license_info,
        demo_status=db.get_demo_status() if demo_status is None else demo_status,
    )


def _get_available_checkout_plans(license_info: dict[str, object] | None) -> list[str]:
    if not _has_checkout_license(license_info):
        return []
    actions = _get_plan_actions_context(license_info, tiene_checkout=True)
    available: list[str] = [
        plan for plan in actions.get("planes_comprables", [])
        if plan_supports_checkout(plan)
    ]
    renewal_plan = str(actions.get("plan_renovable", "") or "").strip()
    if (
        actions.get("puede_renovar")
        and renewal_plan
        and renewal_plan not in available
        and plan_supports_checkout(renewal_plan)
    ):
        available.append(renewal_plan)
    return available


def _format_display_date(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw[:19])
    except Exception:
        try:
            parsed_date = date.fromisoformat(raw[:10])
        except Exception:
            return raw[:10]
        return parsed_date.strftime("%d/%m/%Y")
    return parsed.strftime("%d/%m/%Y")


def _format_price_label(plan: str, resolved_prices: dict[str, dict[str, object]] | None = None) -> str:
    normalized_plan = normalize_plan(plan, default="")
    if normalized_plan and resolved_prices and normalized_plan in resolved_prices:
        price = int(resolved_prices[normalized_plan].get("monto") or 0)
    else:
        try:
            price = get_price_for_plan(plan)
        except MercadoPagoCheckoutError:
            return ""
    return f"$ {price:,.0f}".replace(",", ".")


def _resolve_mi_plan_price_labels(
    plans: list[str] | tuple[str, ...] | set[str],
    *,
    producto: str | None = None,
) -> dict[str, str]:
    try:
        resolved_prices = pricing_resolver.resolve_plan_prices(plans, producto=producto)
    except ValueError:
        resolved_prices = {}

    labels: dict[str, str] = {}
    for plan in plans:
        normalized_plan = normalize_plan(plan, default="")
        if not normalized_plan or normalized_plan in labels:
            continue
        labels[normalized_plan] = _format_price_label(normalized_plan, resolved_prices)
    return labels


def _format_limit_label(label: str, value: object) -> str:
    if value is None:
        return f"{label}: sin limite"
    return f"{label}: hasta {value}"


def _get_plan_limits_summary(plan: str, limits: dict[str, object] | None = None) -> list[str]:
    normalized = normalize_plan(plan, default="DEMO")
    plan_limits = limits if limits is not None else db.TIER_LIMITS.get(normalized, {})
    return [
        _format_limit_label("Productos", plan_limits.get("productos")),
        _format_limit_label("Clientes", plan_limits.get("clientes")),
        _format_limit_label("Proveedores", plan_limits.get("proveedores")),
    ]


def _build_mi_plan_view(
    *,
    license_info: dict[str, object],
    license_status: dict[str, object],
    plan_actions: dict[str, object],
    license_holder: dict[str, str],
    checkout_pending: dict[str, object],
    modulos_activos: list[str],
    modulos_bloqueados: list[str],
) -> dict[str, object]:
    plan_original = str(license_status.get("plan_original", "DEMO") or "DEMO")
    plan_efectivo = str(license_status.get("plan_efectivo", license_info.get("tier", "DEMO")) or "DEMO")
    estado_comercial = str(license_status.get("estado_comercial", "") or "")
    usable = bool(license_status.get("licencia_utilizable"))
    is_basica = plan_original == "BASICA" and usable
    is_timed_plan = plan_original in {"DEMO", "PRO", "FULL"}
    expires_at = str(license_status.get("expires_at", "") or license_info.get("expires_at", "") or "").strip()
    demo_status = db.get_demo_status() if plan_original == "DEMO" else {}
    demo_remaining = demo_status.get("dias_restantes") if plan_original == "DEMO" and not demo_status.get("vencido") else None
    remaining_days = license_status.get("dias_para_vencer")
    if plan_original == "DEMO":
        remaining_days = demo_remaining

    if estado_comercial == "demo_activo":
        visible_message = "La prueba gratuita esta activa. Podes comprar BASICA, PRO o FULL cuando quieras."
    elif estado_comercial == "demo_vencido":
        visible_message = "La prueba gratuita ya fue utilizada. Elegi un plan pago para continuar."
    elif estado_comercial == "basica_permanente":
        visible_message = "BASICA esta activa como licencia permanente. No tiene vencimiento ni renovacion."
    elif estado_comercial == "mensual_activo":
        visible_message = f"Tu plan {get_plan_display_name(plan_original)} esta activo hasta la fecha indicada."
    elif estado_comercial in {"pro_vencido", "full_vencido"}:
        visible_message = f"Tu plan {get_plan_display_name(plan_original)} vencio. Renovalo para recuperar permisos."
    elif estado_comercial == "licencia_bloqueada":
        visible_message = "La licencia no esta activa por estado administrativo. Contacta soporte o revalida si ya fue regularizada."
    else:
        visible_message = str(license_status.get("mensaje_estado", "") or plan_actions.get("mensaje_estado", ""))

    summary_items = [
        {"label": "Plan efectivo", "value": str(plan_actions.get("plan_display") or license_status.get("plan_efectivo_display") or "DEMO")},
        {"label": "Estado", "value": str(license_status.get("estado_display") or "ACTIVA")},
    ]
    if plan_original != plan_efectivo:
        summary_items.append({"label": "Referencia comercial", "value": str(license_status.get("plan_original_display") or plan_original)})
    activated_display = _format_display_date(license_info.get("activated_at"))
    if activated_display:
        summary_items.append({"label": "Activacion", "value": activated_display})
    if is_basica:
        summary_items.append({"label": "Vencimiento", "value": "No vence"})
    elif is_timed_plan and expires_at:
        summary_items.append({"label": "Vencimiento", "value": _format_display_date(expires_at)})
    if remaining_days is not None and is_timed_plan and not is_basica:
        summary_items.append({"label": "Dias restantes", "value": str(max(int(remaining_days), 0))})
    if license_holder.get("email"):
        summary_items.append({"label": "Email asociado", "value": license_holder["email"]})
    if license_holder.get("codigo_vendedor"):
        summary_items.append({"label": "Codigo de vendedor", "value": license_holder["codigo_vendedor"]})

    visible_price_plans: list[str] = [
        str(action.get("plan", "") or "")
        for action in plan_actions.get("acciones", [])
    ]
    if plan_actions.get("puede_renovar"):
        visible_price_plans.append(str(plan_actions.get("plan_renovable", "") or ""))
    visible_price_plans.extend(option["plan"] for option in get_commercial_plan_options())
    price_labels = _resolve_mi_plan_price_labels(
        visible_price_plans,
        producto=get_license_product(),
    )

    checkout_actions = []
    for action in plan_actions.get("acciones", []):
        action_copy = dict(action)
        action_copy["price_label"] = price_labels.get(
            normalize_plan(str(action_copy.get("plan", "") or ""), default=""),
            "",
        )
        checkout_actions.append(action_copy)

    renewal = {
        "show": bool(plan_actions.get("puede_renovar")),
        "plan": str(plan_actions.get("plan_renovable", "") or ""),
        "plan_display": str(plan_actions.get("plan_renovable_display", "") or ""),
        "title": f"Renovacion manual de {plan_actions.get('plan_renovable_display', '')}".strip(),
        "text": str(plan_actions.get("texto_renovacion", "") or ""),
        "secondary_text": str(plan_actions.get("texto_auto_renovacion", "") or ""),
        "button_label": str(plan_actions.get("cta_renovacion", "") or "Renovar"),
        "highlighted": bool(plan_actions.get("renovacion_destacada")),
        "price_label": price_labels.get(
            normalize_plan(str(plan_actions.get("plan_renovable", "") or ""), default=""),
            "",
        ),
    }

    commercial_plans = []
    for option in get_commercial_plan_options():
        plan = option["plan"]
        commercial_plans.append({
            "plan": plan,
            "plan_display": option["plan_display"],
            "modules_count": len(PLANES.get(plan, set())),
            "price_label": price_labels.get(normalize_plan(plan, default=""), ""),
            "available_action": next((item for item in checkout_actions if item.get("plan") == plan), None),
        })

    return {
        "plan_display": str(plan_actions.get("plan_display") or license_status.get("plan_efectivo_display") or "DEMO"),
        "plan_original": plan_original,
        "plan_efectivo": plan_efectivo,
        "estado_comercial": estado_comercial,
        "estado_clase": str(plan_actions.get("estado_clase") or license_status.get("alert_class") or "info"),
        "titulo_estado": str(license_status.get("titulo_estado") or plan_actions.get("titulo_estado") or "Estado del plan"),
        "mensaje_estado": visible_message,
        "summary_items": summary_items,
        "show_expiry_alert": bool(license_status.get("mostrar_aviso_preventivo") or license_status.get("mostrar_aviso_vencimiento")),
        "expiry_alert_class": str(license_status.get("alert_class") or "info"),
        "expiry_title": str(license_status.get("titulo_estado") or ""),
        "expiry_message": str(license_status.get("mensaje_estado") or ""),
        "renewal": renewal,
        "checkout_actions": checkout_actions,
        "manual_actions": list(plan_actions.get("acciones_manuales", [])),
        "show_manual_actions": bool(plan_actions.get("mostrar_solicitud_manual")),
        "show_checkout": bool(plan_actions.get("mostrar_checkout")),
        "checkout_message": str(plan_actions.get("mensaje_checkout") or ""),
        "show_revalidate": bool(license_status.get("mostrar_revalidar") or checkout_pending.get("pending")),
        "post_payment": {
            "show": bool(checkout_pending.get("pending")),
            "plan_display": str(checkout_pending.get("plan_display", "") or ""),
        },
        "holder": license_holder,
        "has_email": bool(license_holder.get("email")),
        "has_vendor_code": bool(license_holder.get("codigo_vendedor")),
        "active_modules": modulos_activos,
        "blocked_modules": modulos_bloqueados,
        "limits": _get_plan_limits_summary(plan_efectivo, license_info.get("limits") if isinstance(license_info.get("limits"), dict) else None),
        "commercial_plans": commercial_plans,
        "no_commercial_actions_message": (
            "No hay acciones comerciales disponibles para este plan."
            if not checkout_actions and not renewal["show"]
            else ""
        ),
    }


def _resolve_requested_checkout_plan(license_info: dict[str, object] | None) -> str:
    available_plans = _get_available_checkout_plans(license_info)
    if not available_plans:
        return ""

    requested_plan = ""
    if request.is_json:
        body = request.get_json(silent=True) or {}
        requested_plan = str(body.get("plan_destino", "") or body.get("plan", "")).strip()
    if not requested_plan:
        requested_plan = str(
            request.form.get("plan_destino", "") or request.args.get("plan_destino", "")
        ).strip()

    if not requested_plan:
        return _resolve_next_upgrade_plan(license_info)

    normalized_plan = normalize_plan(requested_plan, default="")
    if normalized_plan in available_plans:
        return normalized_plan
    return ""


def _resolve_checkout_request_type(license_info: dict[str, object] | None) -> str:
    license_key = _get_checkout_license_key(license_info)
    return "cambio_plan" if license_key else "alta_licencia"


def _get_license_holder_profile(license_info: dict[str, object] | None = None) -> dict[str, str]:
    profile = _get_activation_customer_profile(license_info=license_info)
    return {
        "nombre": profile["titular_nombre"],
        "email": profile["email"],
        "telefono": profile["telefono"],
        "codigo_vendedor": profile["codigo_vendedor"],
        "palabra_recuperacion": profile["palabra_recuperacion"],
    }


def _get_persisted_activation_customer_profile(
    config: dict[str, object] | None = None,
    license_info: dict[str, object] | None = None,
) -> dict[str, str]:
    cfg = config or db.get_config()
    info = license_info or {}
    return {
        "titular_nombre": _first_non_empty(
            cfg.get("license_owner_name", ""),
            info.get("owner_name", ""),
            cfg.get("responsable", ""),
            cfg.get("nombre_negocio", ""),
        ),
        "negocio": _first_non_empty(
            cfg.get("nombre_negocio", ""),
        ),
        "email": _first_non_empty(
            cfg.get("license_owner_email", ""),
            info.get("owner_email", ""),
            cfg.get("negocio_email", ""),
            cfg.get("email_contacto", ""),
        ).lower(),
        "telefono": _first_non_empty(
            cfg.get("license_owner_phone", ""),
            info.get("owner_phone", ""),
            cfg.get("telefono", ""),
            cfg.get("telefono_contacto", ""),
            cfg.get("whatsapp", ""),
        ),
        "codigo_vendedor": _normalize_vendor_code(
            _first_non_empty(
                cfg.get("license_vendor_code", ""),
                cfg.get("codigo_vendedor", ""),
                info.get("vendor_code", ""),
                info.get("codigo_vendedor", ""),
            )
        ),
        "palabra_recuperacion": str(cfg.get("license_recovery_word", "") or "").strip(),
    }


def _get_current_user_contact_profile() -> dict[str, str]:
    if not has_request_context():
        return {}
    user_id = session.get("user", {}).get("id")
    if not user_id:
        return {}
    row = db.q(
        "SELECT nombre_completo, email, telefono FROM usuarios WHERE id=?",
        (user_id,),
        fetchone=True,
    )
    if not row:
        return {}

    def _row_value(key: str) -> str:
        try:
            return str(row[key] or "").strip()
        except Exception:
            return ""

    return {
        "nombre_completo": _row_value("nombre_completo"),
        "email": _row_value("email").lower(),
        "telefono": _row_value("telefono"),
    }


def _get_activation_customer_profile(
    license_info: dict[str, object] | None = None,
    form_data: dict[str, str] | None = None,
) -> dict[str, str]:
    cfg = db.get_config()
    license_info = license_info or {}
    data = form_data or {}
    persisted_profile = _get_persisted_activation_customer_profile(cfg, license_info)
    user_profile = _get_current_user_contact_profile()
    rubro_actual = get_rubro_actual(cfg)
    rubro = normalizar_rubro(
        data.get("rubro")
        or db.get_rubro_configurado()
        or rubro_actual
        or "tienda"
    )
    if rubro not in set(get_rubros_disponibles()):
        rubro = "tienda"

    return {
        "titular_nombre": _first_non_empty(
            data.get("titular_nombre", ""),
            data.get("nombre", ""),
            persisted_profile["titular_nombre"],
            user_profile.get("nombre_completo", ""),
        ),
        "negocio": _first_non_empty(
            data.get("negocio", ""),
            data.get("nombre_negocio", ""),
            persisted_profile["negocio"],
        ),
        "email": _first_non_empty(
            data.get("email", ""),
            data.get("titular_email", ""),
            persisted_profile["email"],
            user_profile.get("email", ""),
        ).lower(),
        "telefono": _first_non_empty(
            data.get("telefono", ""),
            data.get("titular_telefono", ""),
            data.get("whatsapp", ""),
            persisted_profile["telefono"],
            user_profile.get("telefono", ""),
        ),
        "codigo_vendedor": _normalize_vendor_code(
            _first_non_empty(
                data.get("codigo_vendedor", ""),
                persisted_profile["codigo_vendedor"],
            )
        ),
        "palabra_recuperacion": persisted_profile["palabra_recuperacion"],
        "rubro": rubro,
        "terms_accepted": str(cfg.get("license_terms_accepted_at", "") or "").strip() != "",
        "marketing_opt_in": _as_bool(data.get("marketing_opt_in", cfg.get("license_marketing_opt_in", "0"))),
    }


def _normalize_vendor_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _is_valid_paid_license_tier(value: object) -> bool:
    return normalize_plan(value, default="") in {"BASICA", "PRO", "FULL"}


def _get_stable_activation_id() -> tuple[str, dict[str, str]]:
    usuario = session.get("user", {})
    machine_id, machine_details = generate_activation_id(usuario.get("username", ""))
    return get_current_hwid() or machine_id, machine_details


def _get_demo_identity_context(profile: dict[str, str]) -> dict[str, object]:
    usuario = session.get("user", {})
    fallback_activation_id, machine_details = generate_activation_id(usuario.get("username", ""))
    hardware_id = get_current_hwid()
    activation_id = hardware_id or fallback_activation_id
    product_name = get_license_product()
    identity = build_demo_identity(
        product=product_name,
        activation_id=activation_id,
        hardware_id=hardware_id,
        email=profile.get("email", ""),
        machine_details=machine_details,
    )
    return {
        "activation_id": activation_id,
        "hardware_id": hardware_id,
        "product_name": product_name,
        "machine_details": machine_details,
        "identity": identity,
    }


def _demo_dedupe_key(activation_id: str, email: str, product_name: str) -> str:
    return "|".join([
        str(activation_id or "").strip(),
        str(email or "").strip().lower(),
        str(product_name or "").strip().lower(),
    ])


def _get_initial_demo_access_context(config: dict[str, object] | None = None) -> dict[str, object]:
    cfg = config or db.get_config()
    state = str(cfg.get("activation_demo_eligibility_state", "") or "").strip()
    messages = {
        DEMO_ALREADY_USED: "Este equipo ya utilizó la prueba gratuita. Podés elegir un plan para continuar.",
        DEMO_EXPIRED: "Este equipo ya utilizó la prueba gratuita. Podés elegir un plan para continuar.",
        DEMO_BLOCKED: "No es posible iniciar la prueba gratuita para este equipo. Contactá a soporte.",
        DEMO_OFFLINE_UNVERIFIED: "Necesitamos conexión a Internet para comprobar la disponibilidad de la prueba gratuita.",
        DEMO_ERROR: "No pudimos verificar si este equipo puede iniciar la prueba gratuita. Intentá nuevamente.",
    }
    disabled_states = {DEMO_ALREADY_USED, DEMO_EXPIRED, DEMO_BLOCKED}
    return {
        "state": state or DEMO_ELIGIBLE,
        "message": messages.get(state, ""),
        "can_start_demo": state not in disabled_states,
        "can_retry": state in {DEMO_OFFLINE_UNVERIFIED, DEMO_ERROR},
    }


def _get_initial_demo_status() -> dict[str, object]:
    cfg = db.get_config()
    completed = _as_bool(cfg.get("activation_initial_completed", "1"))
    if not completed and not str(cfg.get("activation_demo_request_key", "") or "").strip():
        return {
            "demo": False,
            "dias_restantes": 0,
            "vencido": False,
            "aviso_proximo": False,
            "install_date": "",
            "expires_at": "",
            "dias_usados": 0,
            "dias_demo": 0,
            "ventas_bloqueado": False,
            "productos_bloqueado": False,
        }
    return db.get_demo_status()


def _persist_demo_eligibility_state(result: DemoEligibilityResult) -> None:
    db.set_config({
        "activation_demo_eligibility_state": result.state,
        "activation_demo_eligibility_checked_at": datetime.now().isoformat(),
    })


def _persist_unverified_demo_without_permissions(result: DemoEligibilityResult) -> None:
    db.set_config({
        "demo_mode": "0",
        "license_tier": "SIN_PLAN",
        "license_plan": "DEMO",
        "activation_demo_eligibility_state": result.state,
        "activation_demo_eligibility_checked_at": datetime.now().isoformat(),
    })


def _recover_remote_demo(profile: dict[str, str], result: DemoEligibilityResult, activation_id: str, product_name: str) -> None:
    started_at = str(result.started_at or "").strip()
    expires_at = str(result.expires_at or "").strip()
    try:
        expires_on = date.fromisoformat(expires_at[:10])
    except Exception:
        expires_on = date.today() + timedelta(days=14)
        expires_at = expires_on.isoformat()
    try:
        started_on = date.fromisoformat(started_at[:10])
    except Exception:
        started_on = expires_on - timedelta(days=14)
        started_at = started_on.isoformat()

    demo_days = max((expires_on - started_on).days, 1)
    db.set_config({
        "demo_mode": "1",
        "demo_install_date": started_at[:10],
        "demo_dias": str(demo_days),
        "demo_expires_at": expires_at[:10],
        "license_tier": "DEMO",
        "license_plan": "DEMO",
        "activation_demo_request_key": _demo_dedupe_key(activation_id, profile["email"], product_name),
        "activation_demo_request_sent_at": datetime.now().isoformat(),
        "activation_demo_eligibility_state": result.state,
    })
    _persist_activation_customer_profile(profile, completed=True, selected_plan="DEMO")


def _is_initial_activation_completed(license_info: dict[str, object] | None = None) -> bool:
    info = license_info or db.get_license_info()
    if _is_valid_paid_license_tier(info.get("tier")):
        return True
    return _as_bool(db.get_config_valor("activation_initial_completed", "1"))


def _persist_activation_customer_profile(profile: dict[str, str], *, completed: bool, selected_plan: str) -> None:
    normalized_plan = normalize_plan(selected_plan, default="DEMO")
    db.set_config({
        "license_owner_name": profile["titular_nombre"],
        "license_owner_email": profile["email"],
        "license_owner_phone": profile["telefono"],
        "license_vendor_code": profile["codigo_vendedor"],
        "license_marketing_opt_in": "1" if profile["marketing_opt_in"] else "0",
        "license_terms_accepted_at": datetime.now().isoformat(),
        "activation_initial_completed": "1" if completed else "0",
        "activation_initial_plan": normalized_plan,
        "nombre_negocio": profile["negocio"],
        "negocio_email": profile["email"],
        "telefono": profile["telefono"],
        "responsable": profile["titular_nombre"],
    })
    if db.get_rubro_configurado() is None:
        db.set_rubro_configurado(profile["rubro"])


def _persist_checkout_started(plan: str, activation_id: str) -> None:
    db.set_config({
        "activation_checkout_status": "iniciado",
        "activation_checkout_plan": normalize_plan(plan, default=""),
        "activation_checkout_activation_id": str(activation_id or "").strip(),
        "activation_checkout_started_at": datetime.now().isoformat(),
        "activation_checkout_checked_at": "",
    })


def _clear_checkout_pending() -> None:
    db.set_config({
        "activation_checkout_status": "",
        "activation_checkout_plan": "",
        "activation_checkout_activation_id": "",
        "activation_checkout_started_at": "",
        "activation_checkout_checked_at": "",
    })


def _get_checkout_pending_context() -> dict[str, object]:
    cfg = db.get_config()
    plan = normalize_plan(cfg.get("activation_checkout_plan", ""), default="")
    status = str(cfg.get("activation_checkout_status", "") or "").strip()
    activation_id = str(cfg.get("activation_checkout_activation_id", "") or "").strip()
    return {
        "status": status,
        "plan": plan,
        "plan_display": get_plan_display_name(plan) if plan else "",
        "activation_id": activation_id,
        "started_at": str(cfg.get("activation_checkout_started_at", "") or "").strip(),
        "checked_at": str(cfg.get("activation_checkout_checked_at", "") or "").strip(),
        "pending": bool(status and plan and activation_id),
    }


def _resolve_license_from_pending_checkout() -> tuple[dict[str, object], bool]:
    pending = _get_checkout_pending_context()
    previous_info = db.get_license_info()
    if not pending["pending"]:
        return {
            "ok": False,
            "changed": False,
            "message": "No hay un pago pendiente para verificar.",
            "license_status": _get_license_status_context(previous_info),
            "modules": sorted(get_modulos_activos()),
            "checkout_pending": pending,
        }, False

    db.set_config({"activation_checkout_checked_at": datetime.now().isoformat()})
    previous_tier = normalize_plan(previous_info.get("tier", "DEMO"), default="DEMO")
    ok, _message, remote_license = find_active_license_for_machine(
        machine_id=str(pending["activation_id"]),
        producto=get_license_product(),
        expected_plan=str(pending["plan"]),
        vendor_code=_get_license_holder_profile(previous_info).get("codigo_vendedor", ""),
    )
    if not ok or not remote_license:
        supabase_status = str(get_supabase_debug_state().get("status", "") or "").strip().lower()
        temporary_error = supabase_status in {"network_error", "http_error", "invalid_response", "not_configured"}
        return {
            "ok": False,
            "changed": False,
            "message": (
                "No pudimos verificar la licencia en este momento. Revisa tu conexion e intenta nuevamente."
                if temporary_error
                else "Todavia no encontramos una licencia activa para este equipo. Si acabas de pagar, espera unos instantes y volve a verificar."
            ),
            "tier": previous_info.get("tier", previous_tier),
            "plan": previous_info.get("plan", previous_tier),
            "plan_original": previous_info.get("plan_original", previous_tier),
            "plan_efectivo": previous_info.get("plan_efectivo", previous_tier),
            "estado": previous_info.get("estado", ""),
            "fallback_aplicado": bool(previous_info.get("fallback_aplicado")),
            "expirada": bool(previous_info.get("expirada")),
            "expires_at": previous_info.get("expires_at", ""),
            "license_status": _get_license_status_context(previous_info),
            "modules": sorted(get_modulos_activos()),
            "checkout_pending": pending,
        }, False

    db.sync_license_from_remote(remote_license)
    refreshed_info = db.get_license_info()
    normalized_tier = normalize_plan(refreshed_info.get("tier", ""), default="")
    if not _is_valid_paid_license_tier(normalized_tier):
        return {
            "ok": False,
            "changed": False,
            "message": "La licencia encontrada todavia no habilita un plan activo para este equipo.",
            "license_status": _get_license_status_context(refreshed_info),
            "modules": sorted(get_modulos_activos()),
            "checkout_pending": pending,
        }, False

    guardar_licencia(str(remote_license.get("license_key") or ""), refreshed_info)
    db.set_config({"activation_initial_completed": "1"})
    _clear_checkout_pending()
    return {
        "ok": True,
        "changed": normalized_tier != previous_tier,
        "message": "Tu plan fue activado correctamente.",
        "tier": refreshed_info.get("tier", normalized_tier),
        "plan": refreshed_info.get("plan", normalized_tier),
        "plan_original": refreshed_info.get("plan_original", normalized_tier),
        "plan_efectivo": refreshed_info.get("plan_efectivo", normalized_tier),
        "estado": refreshed_info.get("estado", ""),
        "fallback_aplicado": bool(refreshed_info.get("fallback_aplicado")),
        "expirada": bool(refreshed_info.get("expirada")),
        "expires_at": refreshed_info.get("expires_at", ""),
        "license_status": _get_license_status_context(refreshed_info),
        "modules": sorted(get_modulos_activos()),
        "checkout_pending": _get_checkout_pending_context(),
    }, True


def _validate_activation_customer_profile(profile: dict[str, str]) -> tuple[bool, str]:
    if not str(profile.get("titular_nombre", "") or "").strip():
        return False, "Completá el nombre del titular."
    if not str(profile.get("negocio", "") or "").strip():
        return False, "Completá el nombre del negocio."
    ok, msg = _validate_email(profile.get("email", ""))
    if not ok:
        return False, msg
    if not str(profile.get("telefono", "") or "").strip():
        return False, "Completá un teléfono de contacto."
    if not profile.get("terms_accepted"):
        return False, "Debés aceptar los términos y condiciones para continuar."
    if profile.get("rubro") not in set(get_rubros_disponibles()):
        return False, "Seleccioná un rubro válido para continuar."
    return True, ""


def _retry_pending_demo_request_if_needed() -> None:
    license_info = db.get_license_info()
    if _is_valid_paid_license_tier(license_info.get("tier")):
        return

    demo_status = db.get_demo_status()
    if not demo_status.get("demo") or demo_status.get("vencido"):
        return

    if str(db.get_config_valor("activation_demo_request_key", "") or "").strip():
        return

    last_attempt_at = str(db.get_config_valor("activation_demo_request_retry_at", "") or "").strip()
    if last_attempt_at:
        try:
            if (datetime.now() - datetime.fromisoformat(last_attempt_at)).total_seconds() < 3600:
                return
        except Exception:
            pass

    profile = _get_activation_customer_profile(license_info=license_info)
    ok_profile, _msg_profile = _validate_activation_customer_profile(profile)
    if not ok_profile:
        return

    product_name = get_license_product()
    demo_context = _get_demo_identity_context(profile)
    activation_id = str(demo_context["activation_id"])
    machine_details = demo_context["machine_details"]
    identity = demo_context["identity"]
    install_date = str(demo_status.get("install_date", "") or "").strip()
    try:
        started_on = date.fromisoformat(install_date) if install_date else date.today()
    except Exception:
        started_on = date.today()
    expires_at = str(demo_status.get("expires_at", "") or "").strip()
    try:
        expires_on = date.fromisoformat(expires_at) if expires_at else started_on + timedelta(days=max(int(demo_status.get("dias_demo", 14) or 14), 1))
    except Exception:
        expires_on = started_on + timedelta(days=max(int(demo_status.get("dias_demo", 14) or 14), 1))
    remote_demo_dedupe_key = _demo_dedupe_key(activation_id, profile["email"], product_name)

    demo_metadata = build_demo_metadata(
        identity=identity,
        machine_details=machine_details,
        base_metadata={
            "plan": "DEMO",
            "plan_interes": "DEMO_14_DIAS",
            "rubro": profile["rubro"],
            "codigo_vendedor": profile["codigo_vendedor"],
            "terms_accepted": bool(profile["terms_accepted"]),
            "marketing_opt_in": bool(profile["marketing_opt_in"]),
            "demo_started_at": started_on.isoformat(),
            "demo_expires_at": expires_on.isoformat(),
            "demo_status": "demo_activa",
        },
    )

    db.set_config({"activation_demo_request_retry_at": datetime.now().isoformat()})
    ok_demo, msg_demo = create_demo_request(
        nombre=profile["titular_nombre"],
        email=profile["email"],
        telefono=profile["telefono"],
        negocio=profile["negocio"],
        producto=product_name,
        plan_interes="DEMO_14_DIAS",
        mensaje=json.dumps(demo_metadata, ensure_ascii=False),
        origen="app_demo_retry",
        estado="pendiente",
    )
    if ok_demo:
        db.set_config({
            "activation_demo_request_key": remote_demo_dedupe_key,
            "activation_demo_request_sent_at": datetime.now().isoformat(),
            "activation_demo_eligibility_state": DEMO_ACTIVE,
        })
        logger.info(
            "Solicitud DEMO pendiente registrada correctamente activation_id=%s producto=%s",
            mask_identifier(activation_id),
            product_name,
        )
        return

    logger.warning(
        "No se pudo reintentar el registro DEMO en Supabase activation_id=%s producto=%s detalle=%s",
        mask_identifier(activation_id),
        product_name,
        msg_demo,
    )


def _should_force_license_resolution_after_login() -> bool:
    demo_status = db.get_demo_status()
    if not demo_status.get("vencido"):
        return False

    license_info = db.get_license_info()
    return str(license_info.get("tier", "DEMO") or "DEMO").strip().upper() not in {"BASICA", "PRO", "FULL"}


def _validate_license_holder_profile(holder_profile: dict[str, str]) -> tuple[bool, str]:
    email = str(holder_profile.get("email", "") or "").strip().lower()
    recovery_word = str(holder_profile.get("palabra_recuperacion", "") or "").strip()

    if not email:
        return False, "El email del titular es obligatorio."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "El email del titular no es válido."
    if recovery_word and len(recovery_word) < 4:
        return False, "La palabra de recuperación debe tener al menos 4 caracteres."
    return True, ""


def _refresh_license_response(force: bool = True) -> tuple[dict[str, object], bool]:
    global _LICENSE_REFRESH_LAST_RUN, _LICENSE_REFRESH_LAST_RESULT

    now = time.time()
    with _LICENSE_REFRESH_LOCK:
        if (
            not force
            and _LICENSE_REFRESH_LAST_RUN
            and (now - _LICENSE_REFRESH_LAST_RUN) < LICENSE_AUTO_REFRESH_INTERVAL_SECONDS
        ):
            cached = dict(_LICENSE_REFRESH_LAST_RESULT)
            return cached, bool(cached.get("ok"))

        if _get_checkout_pending_context()["pending"] and not _get_checkout_license_key(db.get_license_info()):
            payload, ok = _resolve_license_from_pending_checkout()
            _LICENSE_REFRESH_LAST_RESULT = dict(payload)
            _LICENSE_REFRESH_LAST_RUN = now
            return payload, ok

        previous_info = db.get_license_info()
        previous_tier = normalize_plan(previous_info.get("tier", "DEMO"), default="DEMO")
        previous_effective_plan = str(previous_info.get("plan_efectivo", previous_info.get("tier", previous_tier)) or previous_tier)
        previous_status = str(previous_info.get("estado", "") or "")
        previous_expires_at = str(previous_info.get("expires_at", "") or "")
        ok, message, refreshed_info = refresh_saved_license_online(debug=False)
        current_info = refreshed_info or db.get_license_info()
        current_tier = normalize_plan(current_info.get("tier", previous_tier), default=previous_tier)
        current_effective_plan = str(current_info.get("plan_efectivo", current_info.get("tier", current_tier)) or current_tier)
        current_status = str(current_info.get("estado", "") or "")
        current_expires_at = str(current_info.get("expires_at", "") or "")
        changed = (
            current_tier != previous_tier
            or current_effective_plan != previous_effective_plan
            or current_status != previous_status
            or current_expires_at != previous_expires_at
        )
        license_status = _get_license_status_context(current_info)
        payload = {
            "ok": ok,
            "changed": changed,
            "message": message,
            "tier": current_info.get("tier", previous_tier),
            "plan": current_info.get("plan", current_tier),
            "plan_original": current_info.get("plan_original", current_info.get("plan", current_tier)),
            "plan_efectivo": current_info.get("plan_efectivo", current_info.get("tier", current_tier)),
            "estado": current_info.get("estado", ""),
            "fallback_aplicado": bool(current_info.get("fallback_aplicado")),
            "expirada": bool(current_info.get("expirada")),
            "expires_at": current_info.get("expires_at", ""),
            "license_status": license_status,
            "modules": sorted(get_modulos_activos()),
            "checkout_pending": _get_checkout_pending_context(),
        }
        _LICENSE_REFRESH_LAST_RESULT = dict(payload)
        _LICENSE_REFRESH_LAST_RUN = now
        return payload, ok


def _license_auto_refresh_loop(app) -> None:
    while True:
        time.sleep(LICENSE_AUTO_REFRESH_INTERVAL_SECONDS)
        try:
            with app.app_context():
                _refresh_license_response(force=True)
        except Exception:
            logger.exception("Auto refresh de licencia falló")


def ensure_license_auto_refresh_thread(app) -> None:
    with _LICENSE_REFRESH_THREAD_LOCK:
        thread = app.extensions.get("license_auto_refresh_thread")
        if thread and thread.is_alive():
            return

        worker = threading.Thread(
            target=_license_auto_refresh_loop,
            args=(app,),
            daemon=True,
            name="license-auto-refresh",
        )
        app.extensions["license_auto_refresh_thread"] = worker
        worker.start()
        logger.info("Auto refresh de licencia iniciado")


def _build_checkout_context() -> tuple[dict[str, object] | None, tuple[Response, int] | None]:
    license_info = db.get_license_info()
    available_plans = _get_available_checkout_plans(license_info)
    plan_destino = _resolve_requested_checkout_plan(license_info)
    tipo_solicitud = _resolve_checkout_request_type(license_info)
    requested_plan = ""
    if request.is_json:
        body = request.get_json(silent=True) or {}
        requested_plan = str(body.get("plan_destino", "") or body.get("plan", "")).strip()
    if not requested_plan:
        requested_plan = str(
            request.form.get("plan_destino", "") or request.args.get("plan_destino", "")
        ).strip()

    if requested_plan and not plan_destino:
        return None, (
            jsonify({
                "ok": False,
            "message": "El plan seleccionado no admite checkout directo para tu licencia actual.",
            }),
            400,
        )

    if not plan_destino:
        return None, (
            jsonify({
                "ok": False,
                "message": "Tu plan actual ya no requiere actualización online.",
            }),
            400,
        )

    license_key = str(license_info.get("key", "") or "").strip()
    if tipo_solicitud == "cambio_plan" and not license_key:
        return None, (
            jsonify({
                "ok": False,
                "message": "No se encontró una licencia activa para iniciar el checkout.",
            }),
            400,
        )

    holder_profile = _get_license_holder_profile()
    ok_profile, msg_profile = _validate_license_holder_profile(holder_profile)
    if not ok_profile:
        return None, (
            jsonify({
                "ok": False,
                "message": msg_profile,
            }),
            400,
        )

    producto = get_license_product()
    precio = get_price_for_plan(plan_destino)
    activation_id, machine_details = _get_stable_activation_id()
    external_reference = build_external_reference(
        producto=producto,
        plan_destino=plan_destino,
        tipo_solicitud=tipo_solicitud,
        license_key=license_key,
        activation_id=activation_id,
    )
    logger.info(
        "Checkout preparado tipo=%s plan_actual=%s plan_destino=%s licencia=%s activation_id=%s",
        tipo_solicitud,
        license_info.get("tier", "DEMO"),
        plan_destino,
        _mask_license_key(license_key),
        activation_id[:12],
    )
    return {
        "license_info": license_info,
        "available_plans": available_plans,
        "plan_destino": plan_destino,
        "tipo_solicitud": tipo_solicitud,
        "license_key": license_key,
        "activation_id": activation_id,
        "holder_profile": holder_profile,
        "producto": producto,
        "precio": precio,
        "external_reference": external_reference,
        "machine_details": machine_details,
    }, None


def _create_checkout_init_point() -> tuple[str | None, dict[str, object] | None, tuple[Response, int] | None]:
    try:
        checkout_context, error_response = _build_checkout_context()
    except MercadoPagoCheckoutError as exc:
        return None, None, (
            jsonify({
                "ok": False,
                "message": str(exc),
            }),
            400,
        )

    if error_response:
        return None, None, error_response

    assert checkout_context is not None
    license_key = str(checkout_context["license_key"])
    plan_destino = str(checkout_context["plan_destino"])
    tipo_solicitud = str(checkout_context["tipo_solicitud"])
    activation_id = str(checkout_context["activation_id"])

    try:
        init_point = create_checkout_preference(
            producto=str(checkout_context["producto"]),
            plan_destino=plan_destino,
            precio=int(checkout_context["precio"]),
            external_reference=str(checkout_context["external_reference"]),
            license_key=license_key,
            email_titular=str(checkout_context["holder_profile"]["email"]),
            activation_id=activation_id,
            tipo_solicitud=tipo_solicitud,
        )
    except MercadoPagoCheckoutError as exc:
        logger.warning(
            "Checkout Mercado Pago rechazado tipo=%s licencia=%s activation_id=%s plan_destino=%s error=%s",
            tipo_solicitud,
            _mask_license_key(license_key),
            activation_id[:12],
            plan_destino,
            exc,
        )
        return None, checkout_context, (
            jsonify({
                "ok": False,
                "message": str(exc),
            }),
            502,
        )
    except Exception:
        logger.exception(
            "Checkout Mercado Pago falló inesperadamente tipo=%s licencia=%s activation_id=%s plan_destino=%s",
            tipo_solicitud,
            _mask_license_key(license_key),
            activation_id[:12],
            plan_destino,
        )
        return None, checkout_context, (
            jsonify({
                "ok": False,
                "message": "No se pudo iniciar el checkout en este momento.",
            }),
            500,
        )

    logger.info(
        "Checkout Mercado Pago listo tipo=%s licencia=%s activation_id=%s plan_actual=%s plan_destino=%s",
        tipo_solicitud,
        _mask_license_key(license_key),
        activation_id[:12],
        checkout_context["license_info"].get("tier", "DEMO"),
        plan_destino,
    )
    if tipo_solicitud == "alta_licencia":
        _persist_checkout_started(plan_destino, activation_id)
    return init_point, checkout_context, None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("user", {}).get("rol") not in {"Administrador", "admin"}:
            flash("❌ No tenés permisos para acceder a esa sección.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def _is_admin_role(role: str | None) -> bool:
    return role in {"Administrador", "admin"}


def _is_vendedor_role(role: str | None) -> bool:
    return str(role or "").strip().lower() == "vendedor"


def vendedor_forbidden(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if _is_vendedor_role(session.get("user", {}).get("rol")):
            flash("No tenés permisos para acceder a esa sección.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def _auditar_accion(accion: str, entidad: str, entidad_id: int = 0, detalle: str = "", motivo: str = "") -> None:
    usuario = session.get("user", {}) if "user" in session else {}
    db.registrar_auditoria(
        accion,
        entidad,
        entidad_id,
        detalle=detalle,
        motivo=motivo,
        usuario=usuario.get("username", ""),
        rol=usuario.get("rol", ""),
    )


def _build_rubro_cards():
    return [
        {
            "value": rubro,
            "label": get_rubro_label(rubro),
            "unidades": get_unidades_disponibles(rubro),
        }
        for rubro in get_rubros_disponibles()
    ]


def _build_initial_setup_context(form_data: dict[str, str] | None = None) -> dict[str, object]:
    data = form_data or {}
    selected_rubro = normalizar_rubro(data.get("rubro") or "tienda")
    return {
        "rubros": _build_rubro_cards(),
        "selected_rubro": selected_rubro,
        "business_fields": {
            "nombre_completo": str(data.get("nombre_completo", "") or "").strip(),
            "username": str(data.get("username", "") or "").strip(),
            "admin_email": str(data.get("admin_email", "") or "").strip().lower(),
            "admin_telefono": str(data.get("admin_telefono", "") or "").strip(),
            "nombre_negocio": str(data.get("nombre_negocio", "") or "").strip(),
            "cuit": str(data.get("cuit", "") or "").strip(),
            "direccion": str(data.get("direccion", "") or "").strip(),
            "localidad": str(data.get("localidad", "") or "").strip(),
            "provincia": str(data.get("provincia", "") or "").strip(),
            "negocio_email": str(data.get("negocio_email", "") or "").strip().lower(),
            "telefono": str(data.get("telefono", "") or "").strip(),
        },
    }


def _validate_email(value: str, *, required: bool = True) -> tuple[bool, str]:
    email = str(value or "").strip().lower()
    if not email:
        return (False, "El email es obligatorio.") if required else (True, "")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "Ingresá un email válido."
    return True, ""


def _validate_initial_setup_payload(form_data: dict[str, str]) -> tuple[bool, str]:
    required_fields = {
        "nombre_completo": "Completá el nombre del administrador.",
        "username": "Completá el usuario administrador.",
        "nombre_negocio": "Completá el nombre comercial.",
        "cuit": "Completá el CUIT.",
        "direccion": "Completá la dirección del comercio.",
        "localidad": "Completá la localidad.",
        "provincia": "Completá la provincia.",
        "telefono": "Completá el teléfono del comercio.",
    }
    for field, message in required_fields.items():
        if not str(form_data.get(field, "") or "").strip():
            return False, message

    rubro = str(form_data.get("rubro", "") or "").strip().lower()
    if rubro not in set(get_rubros_disponibles()):
        return False, "Seleccioná un rubro válido para continuar."

    ok, msg = _validate_email(form_data.get("admin_email", ""))
    if not ok:
        return False, f"Email del administrador: {msg}"

    ok, msg = _validate_email(form_data.get("negocio_email", ""))
    if not ok:
        return False, f"Email del comercio: {msg}"

    return True, ""


def _has_license_agreement_acceptance(form_data) -> bool:
    return str(form_data.get("accept_license_agreement", "") or "").strip().lower() in {"1", "on", "true", "si", "sí"}


def _validate_license_agreement_acceptance(form_data) -> tuple[bool, str]:
    if _has_license_agreement_acceptance(form_data):
        return True, ""
    return False, "Debés aceptar el Acuerdo de Licencia de Uso para continuar."


def _requires_initial_license_acceptance(license_info: dict[str, object] | None = None) -> bool:
    info = license_info or db.get_license_info()
    tier = str(info.get("tier", "DEMO") or "DEMO").strip().upper()
    return tier in {"DEMO", "SIN_PLAN"} and not _get_checkout_license_key(info)


def _merge_categorias_visibles(rubro_actual: str, categorias_extra=None):
    categoria_actual = ""
    extras = categorias_extra or []
    for categoria in extras:
        categoria_limpia = str(categoria or "").strip()
        if categoria_limpia:
            categoria_actual = categoria_limpia
            break
    categorias = list(db.get_categorias_configurables(rubro_actual, categoria_actual=categoria_actual))
    extras = categorias_extra or []
    for categoria in extras:
        categoria_limpia = str(categoria or "").strip()
        if categoria_limpia and categoria_limpia not in categorias:
            categorias.append(categoria_limpia)
    return categorias


def formatear_cantidad_ticket(cantidad) -> str:
    try:
        cantidad_num = float(cantidad or 0)
    except (TypeError, ValueError):
        return "0"
    if cantidad_num.is_integer():
        return str(int(cantidad_num))
    texto = f"{cantidad_num:.3f}".rstrip("0").rstrip(".")
    return texto or "0"


def cantidad_para_mostrar(unidad, cantidad) -> float:
    return convertir_cantidad_desde_base(cantidad, unidad)


def formatear_unidad_ticket(unidad, cantidad) -> str:
    unidad_normalizada = normalizar_unidad(unidad or "unidad")
    cantidad_num = cantidad_para_mostrar(unidad_normalizada, cantidad)

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


def formatear_precio_ticket(valor, decimales=2) -> str:
    try:
        number = float(valor or 0)
    except (TypeError, ValueError):
        number = 0.0
    entero, dec = f"{number:,.{decimales}f}".split(".")
    entero = entero.replace(",", ".")
    return f"$ {entero},{dec}"


def formatear_precio_por_unidad_ticket(valor, unidad) -> str:
    unidad_normalizada = normalizar_unidad(unidad or "unidad")
    precio_mostrable = convertir_precio_desde_base(valor, unidad_normalizada)
    decimales = 4 if unidad_normalizada in {"gramo", "ml"} else 2
    return formatear_precio_ticket(precio_mostrable, decimales=decimales)


def _serializar_producto_pos(producto):
    payload = dict(producto)
    unidad_visual = normalizar_unidad(payload.get("unidad") or payload.get("tipo_unidad") or "unidad")
    payload["unidad"] = get_unidad_label(unidad_visual)
    payload["stock_actual"] = cantidad_para_mostrar(unidad_visual, payload.get("stock_actual", 0))
    payload["precio_venta_display"] = convertir_precio_desde_base(payload.get("precio_venta", 0), unidad_visual)
    return payload


def _enriquecer_items_reporte(items):
    enriquecidos = []
    for item in items:
        row = dict(item)
        cantidad = float(row.get("unidades") or row.get("total_vendido") or 0)
        unidad = row.get("unidad") or "unidad"
        cantidad_mostrable = cantidad_para_mostrar(unidad, cantidad)
        row["cantidad_formateada"] = formatear_cantidad_ticket(cantidad_mostrable)
        row["unidad_formateada"] = formatear_unidad_ticket(unidad, cantidad)
        row["cantidad_unidad_texto"] = f"{row['cantidad_formateada']} {row['unidad_formateada']}"
        enriquecidos.append(row)
    return enriquecidos


def _validate_sensitive_operation_authorization(form, action_label: str) -> tuple[bool, str]:
    if not _as_bool(form.get("confirmo_responsabilidad")):
        return False, f"Debés confirmar la advertencia antes de {action_label}."

    current_user = db.get_usuario_by_id(session.get("user", {}).get("id"))
    if not current_user:
        return False, "No se pudo validar el usuario logueado. Iniciá sesión nuevamente."

    if not _is_admin_role(current_user["rol"]):
        return False, "No tenes permisos para anular operaciones criticas."

    if not db.verify_password(form.get("current_password", ""), current_user["password_hash"]):
        return False, "La contraseña del administrador logueado es incorrecta."
    return True, ""


def _validate_sale_delete_authorization(form) -> tuple[bool, str]:
    return _validate_sensitive_operation_authorization(form, "anular la venta")


def _validate_purchase_cancel_authorization(form) -> tuple[bool, str]:
    return _validate_sensitive_operation_authorization(form, "anular la compra")


def _validate_provider_invoice_cancel_authorization(form) -> tuple[bool, str]:
    return _validate_sensitive_operation_authorization(form, "anular la factura")


def _cart() -> list[dict]:
    return session.setdefault("cart", [])


def _save_cart(cart: list[dict]) -> None:
    session["cart"] = cart
    session.modified = True


def _clear_cart() -> None:
    session.pop("cart", None)
    session.modified = True


def _resolver_proveedor_gasto(data: dict) -> dict | None:
    proveedor_id = str(data.get("proveedor_id", "") or "").strip()
    nuevo_nombre = str(data.get("proveedor_nuevo", "") or "").strip()

    if proveedor_id == "__nuevo__":
        if not nuevo_nombre:
            flash("⚠️ Ingresá el nombre del nuevo proveedor.", "warning")
            return None
        existente = next((p for p in db.get_proveedores() if str(p["nombre"]).strip().lower() == nuevo_nombre.lower()), None)
        if existente:
            data["proveedor"] = existente["nombre"]
            return data
        if not _limit_allows("proveedores"):
            return None
        db.add_proveedor({"nombre": nuevo_nombre})
        data["proveedor"] = nuevo_nombre
        return data

    if proveedor_id:
        proveedor = db.get_proveedor(int(proveedor_id))
        data["proveedor"] = proveedor["nombre"] if proveedor else ""
        return data

    if nuevo_nombre:
        data["proveedor"] = nuevo_nombre
    return data


def _validar_gasto_efectivo_contra_caja(data: dict) -> bool:
    medio_pago = str(data.get("medio_pago", "") or "").strip().lower()
    if medio_pago != "efectivo":
        return True
    caja_actual = _caja_abierta()
    if not caja_actual:
        flash("No podés registrar gastos con efectivo porque no hay una caja abierta.", "warning")
        return False
    fecha_gasto = str(data.get("fecha", "") or "").strip()
    fecha_caja = str(caja_actual["fecha_apertura"] or "")[:10]
    if fecha_gasto != fecha_caja:
        flash("No podés registrar gastos con efectivo fuera de la caja abierta actual.", "warning")
        return False
    return True


def _backup_list() -> list[dict]:
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append({"nombre": path.name, "fecha": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"), "tamanio_kb": round(stat.st_size / 1024, 1)})
    return items


def _update_list() -> list[dict]:
    current_version = current_app.config.get("APP_VERSION", "0.0.0")
    update_dir = _update_dir()
    update_dir.mkdir(parents=True, exist_ok=True)
    items = []
    candidates = [
        *update_dir.glob("nexar-tienda_*_amd64.deb"),
        *update_dir.glob("NexarTienda_*_Setup.exe"),
        *update_dir.glob("NexarComercio_*_Setup.exe"),
    ]
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        installer_version = _installer_version(path.name)
        if installer_version and _version_tuple(installer_version) <= _version_tuple(current_version):
            continue
        stat = path.stat()
        is_windows_installer = path.suffix.lower() == ".exe"
        items.append({
            "nombre": path.name,
            "ruta": str(path),
            "version": installer_version,
            "fecha": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "tamanio_mb": round(stat.st_size / 1024 / 1024, 1),
            "comando": str(path) if is_windows_installer else f"sudo apt install {path}",
            "tipo": "Windows" if is_windows_installer else "Linux",
        })
    return items


def _update_file(nombre: str) -> Path:
    safe_name = Path(nombre or "").name
    valid_linux = safe_name.startswith("nexar-tienda_") and safe_name.endswith("_amd64.deb")
    valid_windows = (
        safe_name.startswith("NexarTienda_") or safe_name.startswith("NexarComercio_")
    ) and safe_name.endswith("_Setup.exe")
    if safe_name != nombre or not (valid_linux or valid_windows):
        abort(404)
    update_dir = _update_dir()
    path = (update_dir / safe_name).resolve()
    if path.parent != update_dir.resolve() or not path.exists():
        abort(404)
    return path


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = []
    for chunk in (version or "0.0.0").strip().lstrip("vV").split(".")[:3]:
        parts.append(int("".join(ch for ch in chunk if ch.isdigit()) or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _installer_version(filename: str) -> str:
    patterns = (
        r"^nexar-tienda_(?P<version>[0-9]+(?:\.[0-9]+){1,2})_amd64\.deb$",
        r"^NexarTienda_(?P<version>[0-9]+(?:\.[0-9]+){1,2})_Setup\.exe$",
        r"^NexarComercio_(?P<version>[0-9]+(?:\.[0-9]+){1,2})_Setup\.exe$",
    )
    for pattern in patterns:
        match = re.match(pattern, filename or "")
        if match:
            return match.group("version")
    return ""


def _requires_manual_reopen(installer_name: str) -> bool:
    return sys.platform.startswith("win") and (installer_name or "").lower().endswith(".exe")


def _powershell_literal(value: str | Path) -> str:
    return str(value).replace("'", "''")


def _write_windows_update_status(status: str, *, target_version: str, installer_name: str, error: str = "") -> None:
    if not sys.platform.startswith("win"):
        return
    update_dir = _update_dir()
    update_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "target_version": target_version,
        "installer_name": installer_name,
        "error": error,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    _windows_update_status_path().write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _consume_windows_update_status() -> None:
    status_path = _windows_update_status_path()
    if not status_path.exists():
        return
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("No se pudo leer el estado externo de actualizacion Windows: %s", exc)
        return

    status = str(payload.get("status", "") or "").strip()
    if not status:
        return

    data = {
        "update_install_status": status,
        "update_finished_at": str(payload.get("finished_at", "") or ""),
        "update_install_error": str(payload.get("error", "") or ""),
    }
    target_version = str(payload.get("target_version", "") or "").strip()
    installer_name = str(payload.get("installer_name", "") or "").strip()
    if target_version:
        data["update_target_version"] = target_version
    if installer_name:
        data["update_installer_name"] = installer_name
    db.set_config(data)
    try:
        status_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("No se pudo limpiar el estado externo de actualizacion Windows: %s", exc)


def _build_windows_update_launcher_script(*, installer: Path, target_version: str) -> str:
    app_executable = Path(sys.executable).resolve()
    app_process_name = app_executable.stem
    app_process_path = str(app_executable) if getattr(sys, "frozen", False) else ""
    app_pid = os.getpid()
    script = f"""$ErrorActionPreference = 'Stop'
$InstallerPath = '{_powershell_literal(installer)}'
$StatusPath = '{_powershell_literal(_windows_update_status_path())}'
$LogPath = '{_powershell_literal(_windows_update_log_path())}'
$TargetVersion = '{_powershell_literal(target_version)}'
$InstallerName = '{_powershell_literal(installer.name)}'
$AppPid = {app_pid}
$AppProcessName = '{_powershell_literal(app_process_name)}'
$AppProcessPath = '{_powershell_literal(app_process_path)}'

function Write-Log([string]$Message) {{
    $logDir = Split-Path -Parent $LogPath
    if ($logDir -and -not (Test-Path $logDir)) {{
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }}
    Add-Content -Path $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
}}

function Write-Status([string]$Status, [string]$ErrorMessage = '') {{
    $statusDir = Split-Path -Parent $StatusPath
    if ($statusDir -and -not (Test-Path $statusDir)) {{
        New-Item -ItemType Directory -Path $statusDir -Force | Out-Null
    }}
    @{{
        status = $Status
        target_version = $TargetVersion
        installer_name = $InstallerName
        error = $ErrorMessage
        finished_at = (Get-Date).ToString('yyyy-MM-dd HH:mm')
    }} | ConvertTo-Json | Set-Content -Path $StatusPath -Encoding UTF8
}}

function Get-AppProcesses() {{
    $processes = Get-CimInstance Win32_Process -Filter "Name = '$($AppProcessName).exe'" -ErrorAction SilentlyContinue
    if (-not $processes) {{
        return @()
    }}
    if ($AppProcessPath) {{
        return @($processes | Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath -ieq $AppProcessPath }})
    }}
    return @($processes | Where-Object {{ $_.ProcessId -eq $AppPid }})
}}

Write-Log "Inicio helper de actualizacion Windows para $InstallerName."
Write-Status 'in_progress'

$deadline = (Get-Date).AddSeconds(45)
while ((Get-Process -Id $AppPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {{
    Start-Sleep -Milliseconds 500
}}

if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {{
    Write-Log "El proceso principal sigue vivo; forzando cierre del PID $AppPid."
    Stop-Process -Id $AppPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}}

$remaining = @(Get-AppProcesses())
if ($remaining.Count -gt 0) {{
    Write-Log ("Procesos remanentes detectados: " + (($remaining | ForEach-Object {{ $_.ProcessId }}) -join ', '))
    $remaining | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
    Start-Sleep -Seconds 2
}}

$stillRunning = @(Get-AppProcesses())
if ($stillRunning.Count -gt 0) {{
    $message = "No se pudo cerrar completamente Nexar Comercio antes de iniciar el instalador."
    Write-Log $message
    Write-Status 'install_failed' $message
    exit 1
}}

Write-Log "Lanzando instalador $InstallerPath."
try {{
    $process = Start-Process -FilePath $InstallerPath -WorkingDirectory (Split-Path -Parent $InstallerPath) -PassThru -Wait
    $exitCode = $process.ExitCode
    if ($exitCode -eq 0) {{
        Write-Log "Instalador finalizado correctamente."
        Write-Status 'ready_restart'
        exit 0
    }}

    $message = "El instalador termino con codigo $exitCode."
    Write-Log $message
    Write-Status 'install_failed' $message
    exit $exitCode
}} catch {{
    $message = $_.Exception.Message
    Write-Log ("Error al lanzar el instalador: " + $message)
    Write-Status 'install_failed' $message
    exit 1
}}
"""
    return script


def _launch_windows_update_helper(*, installer: Path, target_version: str) -> None:
    update_dir = _update_dir()
    log_dir = _log_dir()
    launcher_path = _windows_update_launcher_path()
    update_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    script_content = _build_windows_update_launcher_script(installer=installer, target_version=target_version)
    launcher_path.write_text(script_content, encoding="utf-8")
    creation_flags = 0
    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        creation_flags |= int(getattr(subprocess, flag_name, 0))

    logger.info(
        "Preparando helper externo de actualizacion Windows. installer=%s target=%s script=%s",
        installer,
        target_version,
        launcher_path,
    )
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher_path),
        ],
        creationflags=creation_flags,
        close_fds=True,
        cwd=str(update_dir),
    )


def _update_install_state(current_version: str | None = None) -> dict:
    _consume_windows_update_status()
    license_info = db.get_license_info()
    license_key = str(license_info.get("key", "") or "").strip()
    if not license_key:
        flash("No se encontró una licencia activa para enviar el cambio de plan.", "warning")
        return redirect(url_for("main.mi_plan"))

    cfg = db.get_config()
    target_version = cfg.get("update_target_version", "")
    status = cfg.get("update_install_status", "")
    if not target_version or not status:
        return {"status": ""}

    current_version = current_version or current_app.config.get("APP_VERSION", "0.0.0")
    installer_name = cfg.get("update_installer_name", "")
    manual_reopen = _requires_manual_reopen(installer_name)
    if _version_tuple(current_version) >= _version_tuple(target_version):
        if status != "installed":
            db.set_config({
                "update_install_status": "installed",
                "update_installed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            status = "installed"
        return {
            "status": status,
            "target_version": target_version,
            "current_version": current_version,
            "installer": installer_name,
            "installed_at": cfg.get("update_installed_at", ""),
            "manual_reopen": manual_reopen,
        }

    return {
        "status": status,
        "target_version": target_version,
        "current_version": current_version,
        "installer": installer_name,
        "started_at": cfg.get("update_started_at", ""),
        "finished_at": cfg.get("update_finished_at", ""),
        "error": cfg.get("update_install_error", ""),
        "manual_reopen": manual_reopen,
    }


def _mark_update_process_finished(target_version: str, process: subprocess.Popen) -> None:
    try:
        return_code = process.wait()
        status = "ready_restart" if return_code == 0 else "install_failed"
        data = {
            "update_install_status": status,
            "update_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        if return_code != 0:
            data["update_install_error"] = f"El instalador termino con codigo {return_code}."
        db.set_config(data)
    except Exception as exc:
        db.set_config({
            "update_install_status": "install_failed",
            "update_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "update_install_error": str(exc),
        })


def _track_update_process(target_version: str, process: subprocess.Popen) -> None:
    thread = threading.Thread(
        target=_mark_update_process_finished,
        args=(target_version, process),
        daemon=True,
    )
    thread.start()


def _apt_readable_copy(installer: Path) -> Path:
    temp_dir = Path("/tmp") / "nexar-tienda-updates"
    temp_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        temp_dir.chmod(0o755)
    target = temp_dir / installer.name
    shutil.copy2(installer, target)
    if os.name != "nt":
        target.chmod(0o644)
    return target


def _backup_file(nombre: str) -> Path:
    safe_name = Path(nombre or "").name
    if safe_name != nombre or not safe_name.endswith(".db"):
        abort(404)
    backup_dir = _backup_dir()
    path = (backup_dir / safe_name).resolve()
    if path.parent != backup_dir.resolve() or not path.exists():
        abort(404)
    return path


def _is_sqlite_database(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except Exception:
        return False


def _make_backup() -> Path:
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"nexar_comercio_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db"
    shutil.copy2(db.DB_PATH, target)
    try:
        if os.name != "nt":
            target.chmod(0o600)
    except Exception:
        pass
    db.set_config({"backup_ultimo": datetime.now().strftime("%Y-%m-%d %H:%M")})
    keep = int(db.get_config().get("backup_keep", "10") or 10)
    for extra in sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        extra.unlink(missing_ok=True)
    return target


def _caja_abierta():
    return db.q("SELECT * FROM caja WHERE estado=1 ORDER BY id DESC LIMIT 1", fetchone=True)


def _caja_movimientos(caja_id):
    return db.q("SELECT * FROM caja_movimientos WHERE caja_id=? ORDER BY created_at DESC, id DESC", (caja_id,))


def _caja_resumen(caja_row) -> dict:
    if not caja_row:
        return {"ventas": 0, "ingresos": 0, "egresos": 0, "total": 0}
    fecha = str(caja_row["fecha_apertura"])[:10]
    ventas = db.q("SELECT COALESCE(SUM(total),0) as total FROM ventas WHERE fecha=? AND medio_pago='Efectivo' AND COALESCE(anulada, 0)=0", (fecha,), fetchone=True)
    movs = _caja_movimientos(caja_row["id"])
    ingresos = sum(float(m["monto"] or 0) for m in movs if m["tipo"] == "INGRESO" and not int(m["anulado"] or 0))
    egresos = sum(float(m["monto"] or 0) for m in movs if m["tipo"] == "EGRESO" and not int(m["anulado"] or 0))
    total = float(caja_row["saldo_inicial"] or 0) + float(ventas["total"] or 0) + ingresos - egresos
    return {"ventas": float(ventas["total"] or 0), "ingresos": ingresos, "egresos": egresos, "total": total}


def _resumen_gastos_reportes(rows) -> tuple[float, float]:
    activos = [row for row in rows if not int(row["anulado"] or 0)]
    gastos_necesarios = sum(float(r["monto"] or 0) for r in activos if "prescindible" not in str(r["necesario"]).lower())
    gastos_prescindibles = sum(float(r["monto"] or 0) for r in activos if "prescindible" in str(r["necesario"]).lower())
    return gastos_necesarios, gastos_prescindibles


@main_bp.route("/registro-inicial", methods=["GET", "POST"])
def registro_inicial():
    if db.count_usuarios() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        form_data = request.form.to_dict()
        if "admin_email" in form_data:
            context = _build_initial_setup_context(form_data)
            negocio = context["business_fields"]
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            accepted_license = _has_license_agreement_acceptance(form_data)
            ok, msg = _validate_initial_setup_payload(form_data)
            if not ok:
                flash(f"⚠️ {msg}", "warning")
                return render_template("registro_inicial.html", **context)
            ok, msg = _validate_license_agreement_acceptance(form_data)
            if not ok:
                flash(f"⚠️ {msg}", "warning")
                return render_template("registro_inicial.html", accepted_license=accepted_license, **context)
            ok, msg = _validate_password_confirmation(password, password_confirm)
            if not ok:
                flash(f"❌ {msg}", "danger")
                return render_template("registro_inicial.html", accepted_license=accepted_license, **context)
            if db.get_usuario_by_username(negocio["username"]):
                flash("⚠️ Ese usuario administrador ya existe.", "warning")
                return render_template("registro_inicial.html", accepted_license=accepted_license, **context)
            db.add_usuario(
                negocio["username"],
                password,
                "Administrador",
                negocio["nombre_completo"],
                email=negocio["admin_email"],
                telefono=negocio["admin_telefono"],
            )
            db.set_rubro_configurado(form_data.get("rubro", "tienda"))
            db.set_config(
                {
                    "nombre_negocio": negocio["nombre_negocio"],
                    "cuit": negocio["cuit"],
                    "direccion": negocio["direccion"],
                    "localidad": negocio["localidad"],
                    "provincia": negocio["provincia"],
                    "telefono": negocio["telefono"],
                    "negocio_email": negocio["negocio_email"],
                    "responsable": negocio["nombre_completo"],
                    "activation_initial_completed": "0",
                    "activation_initial_plan": "",
                }
            )
            flash("✅ Configuración inicial completada. Ya podés iniciar sesión.", "success")
            return redirect(url_for("login"))
        nombre = request.form.get("nombre_completo", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        question = request.form.get("security_question", "").strip()
        answer = request.form.get("security_answer", "").strip()
        if not all([nombre, username, password, password_confirm, question, answer]):
            flash("⚠️ Completá todos los campos.", "warning")
            return render_template("registro_inicial.html", nombre=nombre, username=username)
        ok, msg = _validate_password_confirmation(password, password_confirm)
        if not ok:
            flash(f"❌ {msg}", "danger")
            return render_template("registro_inicial.html", nombre=nombre, username=username)
        ok, msg = _validate_security_recovery(question, answer)
        if not ok:
            flash(f"❌ {msg}", "danger")
            return render_template("registro_inicial.html", nombre=nombre, username=username)
        db.add_usuario(username, password, "Administrador", nombre, question, answer)
        flash("✅ Administrador creado. Ya podés iniciar sesión.", "success")
        return redirect(url_for("login"))
    return render_template("registro_inicial.html", **_build_initial_setup_context())


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if db.count_usuarios() == 0:
        return redirect(url_for("registro_inicial"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_usuario_by_username(username)
        if not user or not int(user["activo"] or 0) or not db.verify_password(password, user["password_hash"]):
            flash("❌ Usuario o contraseña incorrectos.", "danger")
            return render_template("login.html", next=request.form.get("next", ""))
        session["user"] = {"id": user["id"], "username": user["username"], "nombre_completo": user["nombre_completo"] or user["username"], "rol": user["rol"]}
        session["show_welcome"] = True
        DESKTOP_STATE["user_logged_in"] = True
        _auditar_accion(
            "LOGIN",
            "sesion",
            int(user["id"] or 0),
            detalle=f"Inicio de sesion de {user['username']} ({user['rol']})",
        )
        if not user["security_question"] or not user["security_answer_hash"]:
            flash("⚠️ Antes de continuar, configurá tu pregunta y respuesta secreta.", "warning")
            return redirect(url_for("configurar_recuperacion", next=request.form.get("next", "")))
        next_url = str(request.form.get("next", "") or "").strip()
        if next_url in {url_for("mi_plan"), url_for("licencia")} and not _should_force_license_resolution_after_login():
            next_url = ""
        return redirect(next_url or url_for("dashboard"))
    return render_template("login.html", next=request.args.get("next", ""))


@main_bp.route("/configurar-recuperacion", methods=["GET", "POST"])
@login_required
def configurar_recuperacion():
    usuario = db.q("SELECT * FROM usuarios WHERE id=?", (session["user"]["id"],), fetchone=True)
    if not usuario:
        session.clear()
        return redirect(url_for("login"))
    if usuario["security_question"] and usuario["security_answer_hash"]:
        return redirect(request.args.get("next") or url_for("dashboard"))

    if request.method == "POST":
        question = request.form.get("security_question", "").strip()
        answer = request.form.get("security_answer", "").strip()
        ok, msg = _validate_security_recovery(question, answer)
        if not ok:
            flash(f"⚠️ {msg}", "warning")
            return render_template("configurar_recuperacion.html", usuario=usuario)
        db.update_perfil(usuario["id"], {
            "nombre_completo": usuario["nombre_completo"],
            "security_question": question,
            "security_answer": answer,
        })
        flash("✅ Recuperación de contraseña configurada.", "success")
        return redirect(request.form.get("next") or url_for("dashboard"))

    return render_template("configurar_recuperacion.html", usuario=usuario, next=request.args.get("next", ""))


@main_bp.route("/recuperar-password", methods=["GET", "POST"])
def recuperar_password():
    step, user, username = 1, None, ""
    if request.method == "POST":
        step = int(request.form.get("step", "1") or 1)
        username = request.form.get("username", "").strip()
        if step == 1:
            session.pop("recover_user", None)
            user = db.get_usuario_by_username(username)
            if user and user["security_question"]:
                step = 2
            else:
                flash("❌ Usuario inexistente o sin recuperación configurada.", "danger")
        elif step == 2:
            user = db.get_usuario_by_username(username)
            security_answer = request.form.get("security_answer", "")
            if user and db.verify_security_answer(security_answer, user["security_answer_hash"] or ""):
                if db.needs_security_answer_rehash(user["security_answer_hash"] or ""):
                    db.set_security_answer_hash(user["id"], security_answer)
                session["recover_user"] = username
                step = 3
            else:
                flash("❌ La respuesta no coincide.", "danger")
                step = 1
        elif step == 3:
            if session.get("recover_user") != username:
                flash("⚠️ La sesión de recuperación venció. Empezá de nuevo.", "warning")
                session.pop("recover_user", None)
                return redirect(url_for("recuperar_password"))
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            ok, msg = _validate_password_confirmation(password, password_confirm)
            if ok:
                db.set_password_for_username(username, password)
                session.pop("recover_user", None)
                flash("✅ Contraseña restablecida.", "success")
                return redirect(url_for("login"))
            flash(f"❌ {msg}", "danger")
    return render_template("recuperar_password.html", step=step, user=user, username=username)


@main_bp.route("/")
@login_required
def dashboard():
    show_welcome = bool(session.pop("show_welcome", False))
    cfg = db.get_config()
    onboarding_context = db.get_onboarding_context()
    return render_template(
        "dashboard.html",
        stats=db.get_dashboard_stats(),
        show_welcome=show_welcome,
        rubro_actual=get_rubro_actual(cfg),
        onboarding_context=onboarding_context,
        mostrar_aviso_rubro_pendiente=db.debe_mostrar_aviso_rubro_pendiente(),
        resumen_financiero=db.get_resumen_dashboard_financiero(),
        facturas_vencidas=db.get_facturas_proveedores_vencidas_resumen(limit=5),
        facturas_por_vencer=db.get_facturas_proveedores_por_vencer_resumen(dias=7, limit=5),
        clientes_con_deuda=db.get_clientes_con_deuda(limit=5),
    )


@main_bp.route("/dashboard/onboarding/ocultar", methods=["POST"])
@login_required
def dashboard_onboarding_ocultar():
    db.set_config_valor("onboarding_oculto", "1")
    return redirect(url_for("dashboard"))


@main_bp.route("/configuracion/rubro-inicial", methods=["GET", "POST"])
@login_required
def configuracion_rubro_inicial():
    rubro_guardado = db.get_rubro_configurado()
    rubro_actual = get_rubro_actual(db.get_config())
    rubros = _build_rubro_cards()
    selected_rubro = request.form.get("rubro", rubro_guardado or rubro_actual)
    if rubro_guardado:
        if request.method == "POST":
            flash("El rubro ya quedó configurado. Para cambiarlo, contactá soporte.", "warning")
            return redirect(url_for("config"))
        return render_template(
            "configuracion_rubro_inicial.html",
            rubros=rubros,
            rubro_actual=rubro_actual,
            rubro_guardado=rubro_guardado,
            selected_rubro=selected_rubro,
            permitir_cambio=False,
            solo_lectura=True,
        )
    if request.method == "POST":
        rubro = str(request.form.get("rubro", "") or "").strip().lower()
        if rubro not in set(get_rubros_disponibles()):
            flash("Seleccioná un rubro válido para continuar.", "warning")
            return render_template(
                "configuracion_rubro_inicial.html",
                rubros=rubros,
                rubro_actual=rubro_actual,
                rubro_guardado=rubro_guardado,
                selected_rubro=selected_rubro,
                permitir_cambio=False,
                solo_lectura=False,
            )

        db.set_rubro_configurado(rubro)
        flash("Rubro del negocio guardado correctamente.", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "configuracion_rubro_inicial.html",
        rubros=rubros,
        rubro_actual=rubro_actual,
        rubro_guardado=rubro_guardado,
        selected_rubro=selected_rubro,
        permitir_cambio=False,
        solo_lectura=False,
    )


@main_bp.route("/productos")
@login_required
def productos():
    buscar = request.args.get("q", "")
    categoria_filtro = request.args.get("categoria", "")
    proveedor_filtro = (request.args.get("proveedor", "") or "").strip()
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    productos_para_filtros = [
        dict(r)
        for r in db.get_productos(
            search=buscar,
            rubro=rubro_actual,
        )
    ]
    productos_rows = [
        dict(r)
        for r in db.get_productos(
            search=buscar,
            rubro=rubro_actual,
            proveedor=proveedor_filtro,
        )
    ]
    categorias_visibles = _merge_categorias_visibles(
        rubro_actual,
        [row.get("categoria", "") for row in productos_rows],
    )
    proveedores_map = {}
    for row in productos_para_filtros:
        nombre = str(row.get("proveedor_habitual") or "").strip()
        if nombre:
            proveedores_map.setdefault(nombre.lower(), nombre)
    proveedores_visibles = sorted(proveedores_map.values(), key=str.lower)
    return render_template(
        "productos.html",
        productos=productos_rows,
        categorias=categorias_visibles,
        proveedores_visibles=proveedores_visibles,
        buscar=buscar,
        categoria_filtro=categoria_filtro,
        proveedor_filtro=proveedor_filtro,
        rubro_actual=rubro_actual,
    )


@main_bp.route("/productos/lote", methods=["GET", "POST"])
@vendedor_forbidden
def productos_lote():
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    proveedores = db.get_proveedores()

    def _default_common_data():
        return {
            "proveedor_habitual": "",
            "categoria": get_categoria_default(rubro_actual),
            "marca": "",
            "unidad": "unidad",
            "stock_minimo": "5",
            "stock_maximo": "50",
            "generar_codigo_barras_interno": "",
        }

    def _blank_row():
        return {
            "descripcion": "",
            "costo": "",
            "precio_venta": "",
            "stock_actual": "",
            "codigo_barras": "",
        }

    common_data = _default_common_data()
    rows_data = [_blank_row() for _ in range(10)]

    if request.method == "POST":
        common_data = {
            "proveedor_habitual": (request.form.get("proveedor_habitual", "") or "").strip(),
            "categoria": (request.form.get("categoria", "") or "").strip(),
            "marca": (request.form.get("marca", "") or "").strip(),
            "unidad": (request.form.get("unidad", "unidad") or "unidad").strip(),
            "stock_minimo": (request.form.get("stock_minimo", "5") or "5").strip(),
            "stock_maximo": (request.form.get("stock_maximo", "50") or "50").strip(),
            "generar_codigo_barras_interno": "1" if _as_bool(request.form.get("generar_codigo_barras_interno")) else "",
        }
        descripciones = request.form.getlist("descripcion[]")
        costos = request.form.getlist("costo[]")
        precios = request.form.getlist("precio_venta[]")
        stocks = request.form.getlist("stock_actual[]")
        codigos_barras = request.form.getlist("codigo_barras[]")
        total_rows = max(
            len(descripciones),
            len(costos),
            len(precios),
            len(stocks),
            len(codigos_barras),
            10,
        )
        rows_data = []
        filas_validas = []
        errores = []

        for idx in range(total_rows):
            row = {
                "descripcion": (descripciones[idx] if idx < len(descripciones) else "").strip(),
                "costo": (costos[idx] if idx < len(costos) else "").strip(),
                "precio_venta": (precios[idx] if idx < len(precios) else "").strip(),
                "stock_actual": (stocks[idx] if idx < len(stocks) else "").strip(),
                "codigo_barras": (codigos_barras[idx] if idx < len(codigos_barras) else "").strip(),
            }
            rows_data.append(row)

            if not any(row.values()):
                continue
            if not row["descripcion"]:
                errores.append(f"Fila {idx + 1}: la descripción es obligatoria si cargás datos.")
                continue
            if row["costo"] == "":
                errores.append(f"Fila {idx + 1}: el costo es obligatorio.")
                continue
            if row["precio_venta"] == "":
                errores.append(f"Fila {idx + 1}: el precio de venta es obligatorio.")
                continue
            if row["stock_actual"] == "":
                errores.append(f"Fila {idx + 1}: el stock inicial es obligatorio.")
                continue

            try:
                costo_num = float(row["costo"])
            except ValueError:
                errores.append(f"Fila {idx + 1}: el costo debe ser numérico.")
                continue
            try:
                precio_num = float(row["precio_venta"])
            except ValueError:
                errores.append(f"Fila {idx + 1}: el precio de venta debe ser numérico.")
                continue
            try:
                stock_num = float(row["stock_actual"])
            except ValueError:
                errores.append(f"Fila {idx + 1}: el stock inicial debe ser numérico.")
                continue

            if costo_num < 0:
                errores.append(f"Fila {idx + 1}: el costo no puede ser negativo.")
            if precio_num < 0:
                errores.append(f"Fila {idx + 1}: el precio de venta no puede ser negativo.")
            if stock_num <= 0:
                errores.append(f"Fila {idx + 1}: el stock inicial debe ser mayor a 0.")
            if errores:
                # Solo omitimos agregar la fila si la última validación generó error.
                fila_con_error = any(msg.startswith(f"Fila {idx + 1}:") for msg in errores)
                if fila_con_error:
                    continue

            filas_validas.append(
                {
                    "row_label": f"Fila {idx + 1}",
                    "descripcion": row["descripcion"],
                    "costo": str(costo_num),
                    "precio_venta": str(precio_num),
                    "stock_actual": str(stock_num),
                    "codigo_barras": row["codigo_barras"],
                }
            )

        if not common_data["categoria"]:
            errores.append("Seleccioná una categoría para la carga por lote.")

        try:
            unidad_normalizada = normalizar_unidad(common_data["unidad"], rubro_actual)
            common_data["unidad"] = unidad_normalizada
            stock_minimo_num = float(common_data["stock_minimo"] or 5)
            stock_maximo_num = float(common_data["stock_maximo"] or 50)
            if stock_minimo_num < 0:
                errores.append("El stock mínimo no puede ser negativo.")
            if stock_maximo_num < 0:
                errores.append("El stock máximo no puede ser negativo.")
        except ValueError:
            errores.append("Stock mínimo y stock máximo deben ser numéricos.")
            stock_minimo_num = 5.0
            stock_maximo_num = 50.0

        if not filas_validas and not errores:
            errores.append("Cargá al menos una fila válida para crear productos.")

        _validar_codigos_barras_manuales(filas_validas, errores, row_label_key="row_label")

        if filas_validas:
            current_count = int(db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"] or 0)
            check = db.check_license_limits("productos", current_count + len(filas_validas))
            if not check["ok"]:
                errores.append(check["message"])

        if not errores:
            for fila in filas_validas:
                db.add_producto(
                    {
                        "descripcion": fila["descripcion"],
                        "marca": common_data["marca"],
                        "categoria": common_data["categoria"],
                        "proveedor_habitual": common_data["proveedor_habitual"],
                        "codigo_barras": fila["codigo_barras"],
                        "costo": fila["costo"],
                        "precio_venta": fila["precio_venta"],
                        "stock_actual": fila["stock_actual"],
                        "stock_minimo": str(stock_minimo_num),
                        "stock_maximo": str(stock_maximo_num),
                        "tipo_unidad": common_data["unidad"],
                        "unidad": common_data["unidad"],
                        "generar_codigo_barras_interno": common_data["generar_codigo_barras_interno"],
                    }
                )
            flash(f"Se crearon {len(filas_validas)} productos.", "success")
            return redirect(url_for("productos"))

        for error in errores:
            flash(error, "warning")

    unidad_actual = normalizar_unidad(common_data.get("unidad", "unidad"), rubro_actual)
    unidades_disponibles = get_unidades_disponibles(rubro_actual)
    if unidad_actual not in unidades_disponibles:
        unidades_disponibles = unidades_disponibles + [unidad_actual]
    categorias_visibles = _merge_categorias_visibles(
        rubro_actual,
        [common_data.get("categoria", ""), get_categoria_default(rubro_actual)],
    )
    return render_template(
        "productos_lote.html",
        proveedores=proveedores,
        categorias=categorias_visibles,
        rubro_actual=rubro_actual,
        unidades_disponibles=unidades_disponibles,
        common_data=common_data,
        rows_data=rows_data,
        unidad_actual=unidad_actual,
    )


@main_bp.route("/productos/importar", methods=["GET", "POST"])
@vendedor_forbidden
def productos_importar():
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    import_errors: list[str] = []
    filename = ""
    generar_codigo_barras_interno = False

    if request.method == "POST":
        generar_codigo_barras_interno = _as_bool(request.form.get("generar_codigo_barras_interno"))
        archivo = request.files.get("archivo_csv")
        if not archivo or not str(archivo.filename or "").strip():
            import_errors.append("Seleccioná un archivo CSV para importar.")
        else:
            filename = str(archivo.filename or "").strip()
            if not filename.lower().endswith(".csv"):
                import_errors.append("El archivo debe tener extensión .csv.")

        filas_validas: list[dict[str, str]] = []
        if not import_errors and archivo:
            try:
                contenido = archivo.stream.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                import_errors.append("No se pudo leer el archivo. Usá UTF-8 o la plantilla descargable.")
                contenido = ""

            if not import_errors:
                buffer = StringIO(contenido)
                reader = csv.reader(buffer)
                try:
                    raw_headers = next(reader)
                except StopIteration:
                    import_errors.append("El archivo CSV está vacío.")
                    raw_headers = []

                if raw_headers:
                    headers = [_normalizar_csv_header(col) for col in raw_headers]
                    missing = [
                        col for col in PRODUCTOS_IMPORT_REQUIRED_COLUMNS
                        if col not in headers
                    ]
                    if missing:
                        import_errors.append(
                            "Faltan columnas obligatorias: " + ", ".join(sorted(missing)) + "."
                        )
                    elif len(set(headers)) != len(headers):
                        import_errors.append("El archivo tiene columnas duplicadas.")

                if not import_errors and raw_headers:
                    buffer.seek(0)
                    dict_reader = csv.DictReader(buffer, fieldnames=headers)
                    next(dict_reader, None)
                    for row_number, row in enumerate(dict_reader, start=2):
                        try:
                            validada = _validar_fila_importacion_producto(row, row_number, rubro_actual)
                        except ValueError as exc:
                            import_errors.append(str(exc))
                            continue
                        if validada is not None:
                            filas_validas.append(validada)

                if not import_errors and not filas_validas:
                    import_errors.append("El CSV no contiene filas válidas para importar.")

        _validar_codigos_barras_manuales(filas_validas, import_errors, row_label_key="_row_label")

        if filas_validas:
            current_count = int(db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"] or 0)
            check = db.check_license_limits("productos", current_count + len(filas_validas))
            if not check["ok"]:
                import_errors.append(check["message"])

        if not import_errors and filas_validas:
            for fila in filas_validas:
                if generar_codigo_barras_interno:
                    fila["generar_codigo_barras_interno"] = "1"
                db.add_producto(fila)
            flash(f"Se importaron {len(filas_validas)} productos.", "success")
            return redirect(url_for("productos"))

    return render_template(
        "productos_importar.html",
        columnas_esperadas=PRODUCTOS_IMPORT_CSV_COLUMNS,
        columnas_obligatorias=sorted(PRODUCTOS_IMPORT_REQUIRED_COLUMNS),
        rubro_actual=rubro_actual,
        import_errors=import_errors,
        filename=filename,
        template_dir=str(_get_productos_import_template_dir()),
        template_filename=PRODUCTOS_IMPORT_TEMPLATE_FILENAME,
        template_destino=request.form.get("destino", "app") if request.method == "POST" else "app",
        generar_codigo_barras_interno=generar_codigo_barras_interno,
    )


@main_bp.route("/productos/importar/plantilla", methods=["POST"])
@vendedor_forbidden
def productos_importar_generar_plantilla():
    destino = request.form.get("destino", "app")
    template_dir, warning_message = _resolve_productos_import_target_dir(destino)
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / PRODUCTOS_IMPORT_TEMPLATE_FILENAME
    template_path.write_text(_build_productos_import_template_csv(), encoding="utf-8", newline="")
    if warning_message:
        flash(warning_message, "warning")
    flash(f"Plantilla generada en: {template_path}", "success")
    return redirect(url_for("productos_importar"))


@main_bp.route("/productos/importar/plantilla/abrir-carpeta", methods=["POST"])
@vendedor_forbidden
def productos_importar_abrir_carpeta():
    template_dir = _get_productos_import_template_dir()
    template_dir.mkdir(parents=True, exist_ok=True)
    opened = open_file_cross_platform(template_dir)
    flash(opened["message"], "success" if opened.get("ok") else "warning")
    return redirect(url_for("productos_importar"))


@main_bp.route("/productos/nuevo", methods=["GET", "POST"])
@vendedor_forbidden
def producto_nuevo():
    draft_compra = _purchase_draft_from_source(request.form if request.method == "POST" else request.args)
    desde_compra = request.values.get("return_to") == "compra_nueva"
    proveedor_habitual_prefill = ""
    proveedor_id_prefill = draft_compra.get("proveedor_id") or request.values.get("prefill_proveedor_id")
    if proveedor_id_prefill and proveedor_id_prefill != "0":
        try:
            proveedor = db.get_proveedor(int(proveedor_id_prefill))
        except (TypeError, ValueError):
            proveedor = None
        if proveedor:
            proveedor_habitual_prefill = str(proveedor["nombre"] or "").strip()
    prefill = {
        "descripcion": (request.values.get("prefill_descripcion", "") or "").strip(),
        "codigo_barras": (request.values.get("prefill_codigo_barras", "") or "").strip(),
        "costo": (request.values.get("prefill_costo", "") or "").strip(),
        "proveedor_habitual": proveedor_habitual_prefill,
        "generar_codigo_barras_interno": "1" if _as_bool(request.values.get("generar_codigo_barras_interno")) else "",
    }
    if request.method == "POST":
        if not _limit_allows("productos"):
            if desde_compra:
                return redirect(url_for("compra_nueva", **_purchase_draft_query(draft_compra)))
            return redirect(url_for("productos"))
        data = request.form.to_dict()
        imagen = request.files.get("imagen")
        if desde_compra:
            data["stock_actual"] = "0"
            if not str(data.get("proveedor_habitual") or "").strip():
                proveedor_id = draft_compra.get("proveedor_id") or request.form.get("prefill_proveedor_id")
                if proveedor_id and proveedor_id != "0":
                    try:
                        proveedor = db.get_proveedor(int(proveedor_id))
                    except (TypeError, ValueError):
                        proveedor = None
                    if proveedor:
                        data["proveedor_habitual"] = str(proveedor["nombre"] or "").strip()
        try:
            imagen_relativa = _save_producto_image(imagen)
            if imagen_relativa:
                data["imagen"] = imagen_relativa
            nuevo_id = db.add_producto(data)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(request.url)
        _auditar_accion("ALTA_PRODUCTO", "producto", int(nuevo_id or 0), detalle=f"{request.form.get('descripcion', '').strip() or 'Producto'}")
        flash("Producto creado.", "success")
        if desde_compra:
            draft_compra["producto_id"] = str(nuevo_id)
            producto_creado = db.get_producto(nuevo_id)
            if not draft_compra.get("producto_descripcion"):
                draft_compra["producto_descripcion"] = request.form.get("descripcion", "")
            if not draft_compra.get("codigo_barras"):
                draft_compra["codigo_barras"] = (producto_creado["codigo_barras"] if producto_creado else request.form.get("codigo_barras", "")) or ""
            if not draft_compra.get("costo_unitario"):
                draft_compra["costo_unitario"] = request.form.get("costo", "")
            return redirect(url_for("compra_nueva", **_purchase_draft_query(draft_compra, created_product="1")))
        return redirect(url_for("productos"))
    cancel_url = url_for("compra_nueva", **_purchase_draft_query(draft_compra)) if desde_compra else url_for("productos")
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    unidad_actual = normalizar_unidad(prefill.get("unidad", "unidad"), rubro_actual)
    unidades_disponibles = get_unidades_disponibles(rubro_actual)
    if unidad_actual not in unidades_disponibles:
        unidades_disponibles = unidades_disponibles + [unidad_actual]
    categorias_visibles = _merge_categorias_visibles(
        rubro_actual,
        [prefill.get("categoria", ""), get_categoria_default(rubro_actual)],
    )
    return render_template(
        "producto_form.html",
        producto=None,
        stock=None,
        categorias=categorias_visibles,
        accion="Nuevo",
        prefill=prefill,
        from_compra=desde_compra,
        draft_compra=draft_compra,
        cancel_url=cancel_url,
        proveedores=db.get_proveedores(),
        rubro_actual=rubro_actual,
        categoria_actual=prefill.get("categoria", "") or get_categoria_default(rubro_actual),
        rubros_disponibles=get_rubros_disponibles(),
        unidades_disponibles=unidades_disponibles,
        unidad_actual=unidad_actual,
    )


@main_bp.route("/productos/<int:pid>/editar", methods=["GET", "POST"])
@vendedor_forbidden
def producto_editar(pid):
    producto = db.get_producto(pid)
    stock = db.q("SELECT * FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if not producto:
        flash("Producto inexistente.", "danger")
        return redirect(url_for("productos"))
    if request.method == "POST":
        data = request.form.to_dict()
        imagen = request.files.get("imagen")
        data["activo"] = 1 if _as_bool(data.get("activo", "1")) else 0
        producto_validacion = dict(producto)
        producto_validacion["permite_fraccionado"] = int(data.get("permite_fraccionado", 0) or 0)
        producto_validacion["tipo_unidad"] = (
            data.get("tipo_unidad")
            or data.get("unidad")
            or producto_validacion.get("tipo_unidad")
            or producto_validacion.get("unidad")
        )
        producto_validacion["por_peso"] = int(producto_validacion.get("por_peso", 0) or 0)
        unidad_formulario = normalizar_unidad(
            data.get("tipo_unidad")
            or data.get("unidad")
            or producto_validacion.get("unidad")
            or producto_validacion.get("tipo_unidad")
            or "unidad"
        )
        stock_actual_base = (
            convertir_cantidad_a_base(data.get("stock_actual", 0), unidad_formulario)
            if "stock_actual" in data
            else float(stock["stock_actual"] if stock else 0)
        )
        stock_minimo_base = (
            convertir_cantidad_a_base(data.get("stock_minimo", 0), unidad_formulario)
            if "stock_minimo" in data
            else float(stock["stock_minimo"] if stock else 5)
        )
        stock_maximo_base = (
            convertir_cantidad_a_base(data.get("stock_maximo", 0), unidad_formulario)
            if "stock_maximo" in data
            else float(stock["stock_maximo"] if stock else 50)
        )
        try:
            imagen_relativa = _save_producto_image(imagen)
            if imagen_relativa:
                data["imagen"] = imagen_relativa
            nuevo_stock = db.validar_cantidad_producto(producto_validacion, stock_actual_base, campo="stock")
            db.update_producto(pid, data)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(request.url)
        db.update_stock_item(pid, nuevo_stock, stock_minimo_base, stock_maximo_base, data.get("proveedor_habitual", ""))
        _auditar_accion("EDICION_PRODUCTO", "producto", pid, detalle=f"{data.get('descripcion', producto['descripcion']) or 'Producto'}")
        flash("Producto actualizado.", "success")
        return redirect(url_for("productos"))
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    unidad_producto = producto["unidad"] if "unidad" in producto.keys() and producto["unidad"] else producto["tipo_unidad"]
    unidad_actual = normalizar_unidad(unidad_producto, rubro_actual)
    unidades_disponibles = get_unidades_disponibles(rubro_actual)
    if unidad_actual not in unidades_disponibles:
        unidades_disponibles = unidades_disponibles + [unidad_actual]
    categorias_visibles = _merge_categorias_visibles(
        rubro_actual,
        [producto["categoria"], get_categoria_default(rubro_actual)],
    )
    return render_template(
        "producto_form.html",
        producto=producto,
        stock=stock,
        categorias=categorias_visibles,
        accion="Editar",
        proveedores=db.get_proveedores(),
        rubro_actual=rubro_actual,
        categoria_actual=producto["categoria"] or get_categoria_default(rubro_actual),
        rubros_disponibles=get_rubros_disponibles(),
        unidades_disponibles=unidades_disponibles,
        unidad_actual=unidad_actual,
    )


@main_bp.route("/productos/<int:pid>/eliminar", methods=["POST"])
@vendedor_forbidden
def producto_eliminar(pid):
    producto = db.get_producto(pid)
    if not producto:
        flash("Producto inexistente.", "danger")
        return redirect(url_for("productos"))
    descripcion = (producto["descripcion"] or "").strip() or "Producto"
    db.delete_producto(pid)
    _auditar_accion("DESACTIVACION_PRODUCTO", "producto", pid, detalle=descripcion)
    flash("Producto desactivado.", "success")
    return redirect(url_for("productos"))


@main_bp.route("/stock")
@login_required
def stock():
    buscar = request.args.get("buscar", "")
    estado = request.args.get("estado", "")
    rows = []
    for r in db.get_stock_full(search=buscar):
        item = dict(r)
        item["estado"] = item["estado"].replace(" ", "_")
        rows.append(item)
    if estado:
        rows = [r for r in rows if r["estado"] == estado]
    return render_template(
        "stock.html",
        productos=rows,
        alertas=db.get_alertas_count(),
        total_stock_value=sum(float(r["valor_stock"] or 0) for r in rows),
        usuario_puede_editar_stock=not _is_vendedor_role(session.get("user", {}).get("rol")),
    )


@main_bp.route("/stock/<int:pid>/ajustar", methods=["GET", "POST"])
@vendedor_forbidden
def stock_ajustar(pid):
    producto = db.get_producto(pid)
    stock_row = db.q("SELECT * FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if request.method == "POST":
        anterior = float(stock_row["stock_actual"] or 0)
        try:
            nuevo = db.validar_cantidad_producto(producto, request.form.get("stock_actual", anterior) or anterior, campo="stock")
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(request.url)
        db.update_stock_item(pid, nuevo, float(request.form.get("stock_minimo", 5)), float(request.form.get("stock_maximo", 50)), request.form.get("proveedor_habitual", ""))
        db.q("INSERT INTO stock_movimientos (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo) VALUES (?,?,?,?,?,?)", (pid, "AJUSTE", nuevo - anterior, anterior, nuevo, request.form.get("motivo", "Ajuste manual")), commit=True)
        _auditar_accion("AJUSTE_STOCK", "stock", pid, detalle=f"{producto['descripcion'] or 'Producto'} · {anterior:.2f} -> {nuevo:.2f}", motivo=request.form.get("motivo", "Ajuste manual"))
        flash("✅ Stock actualizado.", "success")
        return redirect(url_for("stock"))
    return render_template(
        "stock_ajustar.html",
        producto=producto,
        stock=stock_row,
        movimientos=db.get_stock_movimientos(pid),
        proveedores=db.get_proveedores(),
    )


@main_bp.route("/temporadas")
@login_required
def temporadas():
    require_modulo("temporadas")
    return render_template("temporadas.html", temporadas=db.get_temporadas())


@main_bp.route("/temporadas/nueva", methods=["GET", "POST"])
@login_required
def temporada_nueva():
    require_modulo("temporadas")
    if request.method == "POST":
        data = request.form.to_dict()
        data["activa"] = 1 if _as_bool(data.get("activa")) else 0
        db.add_temporada(data)
        flash("✅ Temporada creada.", "success")
        return redirect(url_for("temporadas"))
    return render_template("temporada_form.html", temporada={}, accion="Nueva")


@main_bp.route("/temporadas/<int:tid>/editar", methods=["GET", "POST"])
@login_required
def temporada_editar(tid):
    require_modulo("temporadas")
    temporada = db.get_temporada(tid)
    if request.method == "POST":
        data = request.form.to_dict()
        data["activa"] = 1 if _as_bool(data.get("activa")) else 0
        db.update_temporada(tid, data)
        flash("✅ Temporada actualizada.", "success")
        return redirect(url_for("temporadas"))
    return render_template("temporada_form.html", temporada=temporada, accion="Editar")


@main_bp.route("/temporadas/<int:tid>/eliminar", methods=["POST"])
@login_required
def temporada_eliminar(tid):
    require_modulo("temporadas")
    db.delete_temporada(tid)
    flash("✅ Temporada eliminada.", "success")
    return redirect(url_for("temporadas"))


@main_bp.route("/punto-venta")
@login_required
def punto_venta():
    return render_template(
        "punto_venta.html",
        clientes=db.get_clientes(),
        temporada=db.get_temporada_actual(),
        caja_abierta=bool(_caja_abierta()),
        caja_abrir_url=url_for("caja", auto_open="abrir", next=url_for("punto_venta")),
    )


@main_bp.route("/api/buscar_productos")
@login_required
def api_buscar_productos():
    productos = [_serializar_producto_pos(r) for r in db.buscar_productos_pos(request.args.get("q", ""))]
    return jsonify({"ok": True, "productos": productos})


@main_bp.route("/api/producto/buscar")
@login_required
def api_producto_buscar():
    codigo = (request.args.get("codigo", "") or "").strip()
    if not codigo:
        return jsonify({"ok": False, "msg": "Código vacío."}), 400
    producto = db.get_producto_by_codigo(codigo)
    if not producto:
        return jsonify({"ok": False, "msg": "Producto no encontrado."}), 404
    stock_row = db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto["id"],), fetchone=True)
    payload = dict(producto)
    payload["stock_actual"] = float(stock_row["stock_actual"] or 0) if stock_row else 0
    payload = _serializar_producto_pos(payload)
    return jsonify({"ok": True, "producto": payload})


@main_bp.route("/api/carrito/agregar", methods=["POST"])
@login_required
def api_carrito_agregar():
    payload = request.get_json(silent=True) or {}
    pid = int(payload.get("producto_id", -1) or -1)
    cart = _cart()
    if pid < 0:
        return jsonify({"ok": True, "carrito": cart})
    producto = db.get_producto(pid)
    stock_row = db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if not producto or not stock_row:
        return jsonify({"ok": False, "error": "Producto o cantidad invalida."}), 400
    unidad_visual = normalizar_unidad(producto["unidad"] or producto["tipo_unidad"] or "unidad")
    try:
        cantidad = db.validar_cantidad_producto(
            producto,
            convertir_cantidad_a_base(payload.get("cantidad", 0), unidad_visual),
            campo="cantidad",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if cantidad > float(stock_row["stock_actual"] or 0):
        return jsonify({"ok": False, "error": "Stock insuficiente."}), 400
    existing = next((i for i in cart if i["producto_id"] == pid), None)
    if existing:
        nueva_cantidad = db.validar_cantidad_producto(producto, float(existing["cantidad"] or 0) + cantidad, campo="cantidad")
        if nueva_cantidad > float(stock_row["stock_actual"] or 0):
            return jsonify({"ok": False, "error": "Stock insuficiente."}), 400
        existing["cantidad"] = nueva_cantidad
        existing["subtotal"] = round(existing["cantidad"] * existing["precio_unitario"], 2)
    else:
        precio = float(producto["precio_venta"] or 0)
        cart.append({
            "producto_id": pid,
            "codigo_interno": producto["codigo_interno"],
            "descripcion": producto["descripcion"],
            "categoria": producto["categoria"],
            "unidad": get_unidad_label(unidad_visual),
            "cantidad": cantidad,
            "precio_unitario": precio,
            "costo_unitario": float(producto["costo"] or 0),
            "iva": producto["iva"] or "",
            "descuento": 0,
            "subtotal": round(cantidad * precio, 2),
        })
    _save_cart(cart)
    return jsonify({"ok": True, "carrito": cart})


@main_bp.route("/api/carrito/quitar/<int:pid>", methods=["POST"])
@login_required
def api_carrito_quitar(pid):
    cart = [i for i in _cart() if i["producto_id"] != pid]
    _save_cart(cart)
    return jsonify({"ok": True, "carrito": cart})


@main_bp.route("/api/carrito/vaciar", methods=["POST"])
@login_required
def api_carrito_vaciar():
    _clear_cart()
    return jsonify({"ok": True})


@main_bp.route("/venta/finalizar", methods=["POST"])
@login_required
def venta_finalizar():
    cart = _cart()
    if not cart:
        flash("El carrito esta vacio.", "warning")
        return redirect(url_for("punto_venta"))
    if not _caja_abierta():
        flash("Necesitás abrir caja para realizar ventas.", "warning")
        return redirect(url_for("punto_venta"))
    try:
        for item in cart:
            producto = db.get_producto(int(item.get("producto_id", 0) or 0))
            if not producto:
                raise ValueError("Hay un producto del carrito que ya no existe.")
            db.validar_cantidad_producto(producto, item.get("cantidad", 0), campo="cantidad")
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("punto_venta"))
    cliente_id = int(request.form.get("cliente_id", 0) or 0)
    cliente_nombre = request.form.get("cliente_nombre", "") or "Mostrador"
    medio_pago = request.form.get("medio_pago", "Efectivo")
    if medio_pago == "Cuenta Corriente" and cliente_id <= 0:
        flash("Para vender en cuenta corriente tenes que seleccionar un cliente.", "warning")
        return redirect(url_for("punto_venta"))
    if cliente_id:
        cliente = db.get_cliente(cliente_id)
        cliente_nombre = cliente["nombre"] if cliente else cliente_nombre
    temporada_actual = db.get_temporada_actual()
    temporada_nombre = temporada_actual["nombre"] if temporada_actual else ""
    venta_id = db.crear_venta(cart, cliente_nombre, medio_pago, float(request.form.get("descuento_adicional", 0) or 0), session["user"]["username"], cliente_id=cliente_id, temporada=temporada_nombre)
    db.reconciliar_cc_clientes_desde_ventas()
    db.decrementar_stock_venta(venta_id)
    venta = db.q("SELECT numero_ticket, total, cliente_nombre, medio_pago FROM ventas WHERE id=?", (venta_id,), fetchone=True)
    _auditar_accion("VENTA_REGISTRADA", "venta", venta_id, detalle=f"Ticket #{venta['numero_ticket'] if venta else venta_id} · Cliente: {(venta['cliente_nombre'] if venta else cliente_nombre) or 'Mostrador'} · Medio: {(venta['medio_pago'] if venta else medio_pago) or medio_pago} · Total: {float((venta['total'] if venta else 0) or 0):.2f}")
    _clear_cart()
    flash(
        f"Ticket generado correctamente. Si no se abrió automáticamente, abrilo desde: {url_for('ticket', vid=venta_id)}",
        "success",
    )
    return redirect(url_for("ticket", vid=venta_id))


@main_bp.route("/ticket/<int:vid>")
@login_required
def ticket(vid):
    venta = db.q("SELECT * FROM ventas WHERE id=?", (vid,), fetchone=True)
    if not venta:
        abort(404)
    venta = dict(venta)
    detalle = db.get_venta_detalle(vid)
    vendedor_visible = str(venta.get("vendedor") or "").strip() or "No informado"
    if venta.get("vendedor"):
        usuario_vendedor = db.q(
            "SELECT username, nombre_completo FROM usuarios WHERE username = ? LIMIT 1",
            (str(venta.get("vendedor")).strip(),),
            fetchone=True,
        )
        if usuario_vendedor:
            vendedor_visible = (
                str(usuario_vendedor["nombre_completo"] or "").strip()
                or str(usuario_vendedor["username"] or "").strip()
                or vendedor_visible
            )
    arca_comprobante = None
    arca_modulo_activo = False
    arca_es_admin = _is_admin_role(session.get("user", {}).get("rol"))
    arca_puede_emitir = False
    arca_modo_operacion = ""
    if arca_es_admin:
        from licensing.permisos import modulo_activo

        arca_modulo_activo = modulo_activo("arca_facturacion")
        if arca_modulo_activo:
            from modules.arca.services.comprobantes_service import (
                comprobante_es_final,
                obtener_comprobante_por_venta,
            )
            from services.arca_config_service import obtener_modo_arca

            arca_comprobante = obtener_comprobante_por_venta(vid)
            arca_modo_operacion = str(obtener_modo_arca().get("modo") or "")
            arca_puede_emitir = not bool(venta["anulada"]) and not comprobante_es_final(arca_comprobante)

    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    iva_items = []
    iva_totales = {}
    if venta:
        for item in detalle:
            producto = db.q(
                "SELECT iva, tipo_unidad, unidad, permite_fraccionado, por_peso FROM productos WHERE id=?",
                (item["producto_id"],),
                fetchone=True,
            )
            iva_label = (item["iva"] or (producto["iva"] if producto and producto["iva"] else "21%")).strip()
            try:
                iva_rate = float(iva_label.replace("%", "").replace(",", "."))
            except ValueError:
                iva_rate = 0.0
            subtotal = float(item["subtotal"] or 0)
            cantidad = float(item["cantidad"] or 0)
            unidad_base = (
                (item["unidad"] or "")
                or (producto["unidad"] if producto and producto["unidad"] else "")
                or (producto["tipo_unidad"] if producto and producto["tipo_unidad"] else "")
                or "unidad"
            )
            unidad_normalizada = normalizar_unidad(unidad_base, rubro_actual)
            cantidad_formateada = formatear_cantidad_ticket(cantidad_para_mostrar(unidad_normalizada, cantidad))
            unidad_formateada = formatear_unidad_ticket(unidad_normalizada, cantidad)
            precio_unitario = float(item["precio_unitario"] or 0)
            base = subtotal / (1 + (iva_rate / 100)) if iva_rate > 0 else subtotal
            iva_importe = subtotal - base
            item_dict = dict(item)
            item_dict["iva_label"] = iva_label
            item_dict["iva_importe"] = round(iva_importe, 2)
            item_dict["unidad_normalizada"] = unidad_normalizada
            item_dict["cantidad_formateada"] = cantidad_formateada
            item_dict["unidad_formateada"] = unidad_formateada
            item_dict["precio_unitario_formateado"] = formatear_precio_por_unidad_ticket(precio_unitario, unidad_normalizada)
            item_dict["subtotal_formateado"] = formatear_precio_ticket(subtotal)
            item_dict["precio_por_unidad_formateado"] = f"{item_dict['precio_unitario_formateado']}/{unidad_formateada}"
            item_dict["cantidad_unidad_texto"] = f"{cantidad_formateada} {unidad_formateada}"
            item_dict["linea_resumen"] = (
                f"{cantidad_formateada} {unidad_formateada} x "
                f"{item_dict['precio_por_unidad_formateado']}"
            )
            iva_items.append(item_dict)
            bucket = iva_totales.setdefault(iva_label, {"base": 0.0, "iva": 0.0, "total": 0.0})
            bucket["base"] += base
            bucket["iva"] += iva_importe
            bucket["total"] += subtotal
    iva_resumen = [
        {
            "alicuota": alicuota,
            "base": round(valores["base"], 2),
            "iva": round(valores["iva"], 2),
            "total": round(valores["total"], 2),
        }
        for alicuota, valores in sorted(iva_totales.items(), key=lambda item: item[0])
    ]
    return render_template(
        "ticket.html",
        venta=venta,
        vendedor_visible=vendedor_visible,
        detalle=iva_items,
        iva_resumen=iva_resumen,
        cfg=cfg,
        rubro_actual=rubro_actual,
        venta_id=venta["id"],
        arca_comprobante=arca_comprobante,
        arca_modulo_activo=arca_modulo_activo,
        arca_es_admin=arca_es_admin,
        arca_puede_emitir=arca_puede_emitir,
        arca_modo_operacion=arca_modo_operacion,
        subtotal_formateado=formatear_precio_ticket(venta["subtotal"]),
        descuento_formateado=formatear_precio_ticket(venta["descuento_adicional"]),
        interes_formateado=formatear_precio_ticket(venta["interes_financiacion"]),
        total_formateado=formatear_precio_ticket(venta["total"]),
    )


@main_bp.route("/api/ticket/<int:vid>/print", methods=["POST"])
@login_required
def print_ticket_backend(vid):
    resultado = print_ticket_via_cups(vid)
    status_code = 200 if resultado.get("ok") else 400
    return jsonify(resultado), status_code


@main_bp.route("/historial")
@vendedor_forbidden
def historial():
    search = request.args.get("q", "")
    fecha_desde = request.args.get("desde", "")
    fecha_hasta = request.args.get("hasta", "")
    medio_pago = request.args.get("medio", "")
    ventas = db.get_ventas_historial(search, fecha_desde, fecha_hasta, medio_pago)
    medios = [row["medio_pago"] for row in db.get_medios_pago_ventas()]
    arca_modulo_activo = False
    arca_estado_por_venta = {}
    arca_puede_emitir_ids: set[int] = set()
    usuario_es_admin = _is_admin_role(session.get("user", {}).get("rol"))
    if usuario_es_admin:
        from licensing.permisos import modulo_activo

        arca_modulo_activo = modulo_activo("arca_facturacion")
        if arca_modulo_activo and ventas:
            from modules.arca.services.comprobantes_service import (
                comprobante_es_final,
                obtener_comprobantes_por_venta_ids,
            )

            ids = [int(venta["id"]) for venta in ventas]
            arca_estado_por_venta = obtener_comprobantes_por_venta_ids(ids)
            arca_puede_emitir_ids = {
                int(venta["id"])
                for venta in ventas
                if not int(venta["anulada"] or 0)
                and not comprobante_es_final(arca_estado_por_venta.get(int(venta["id"])))
            }
    return render_template(
        "historial.html",
        ventas=ventas,
        search=search,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        medio_pago_seleccionado=medio_pago,
        medios_pago_disponibles=medios,
        total_filtro=sum(float(v["total"] or 0) for v in ventas if not int(v["anulada"] or 0)),
        usuario_es_admin=usuario_es_admin,
        arca_modulo_activo=arca_modulo_activo,
        arca_estado_por_venta=arca_estado_por_venta,
        arca_puede_emitir_ids=arca_puede_emitir_ids,
    )


@main_bp.route("/historial/<int:vid>")
@vendedor_forbidden
def historial_detalle(vid):
    return redirect(url_for("ticket", vid=vid))


@main_bp.route("/historial/<int:vid>/eliminar", methods=["POST"])
@admin_required
def historial_eliminar(vid):
    ok, msg = _validate_sale_delete_authorization(request.form)
    if not ok:
        flash(f"❌ {msg}", "danger")
        return redirect(url_for("historial"))

    venta = db.q("SELECT id, numero_ticket, anulada FROM ventas WHERE id=?", (vid,), fetchone=True)
    if not venta:
        flash("❌ La venta indicada no existe.", "danger")
        return redirect(url_for("historial"))
    if int(venta["anulada"] or 0):
        flash(f"⚠️ La venta #{venta['numero_ticket']} ya estaba anulada.", "warning")
        return redirect(url_for("historial"))

    try:
        db.anular_venta(
            vid,
            motivo=request.form.get("motivo_anulacion", ""),
            usuario=session.get("user", {}).get("username", ""),
            rol=session.get("user", {}).get("rol", ""),
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("historial"))
    flash(f"✅ Venta #{venta['numero_ticket']} anulada correctamente. El stock fue restaurado.", "success")
    return redirect(url_for("historial"))


@main_bp.route("/compras")
@vendedor_forbidden
def compras():
    draft = _purchase_draft_from_source(request.args)
    return render_template("compras.html", compras=db.get_compras(request.args.get("q", ""), request.args.get("fecha_desde", ""), request.args.get("fecha_hasta", "")), buscar=request.args.get("q", ""), fecha_desde=request.args.get("fecha_desde", ""), fecha_hasta=request.args.get("fecha_hasta", ""), proveedores=db.get_proveedores(), productos=db.get_productos(), draft=draft, open_compra=_as_bool(request.args.get("open_compra")), created_product=_as_bool(request.args.get("created_product")), created_provider=_as_bool(request.args.get("created_provider")), hoy=date.today().isoformat(), usuario_es_admin=_is_admin_role(session.get("user", {}).get("rol")))


@main_bp.route("/compras/nueva", methods=["GET", "POST"])
@vendedor_forbidden
def compra_nueva():
    if request.method == "GET":
        return redirect(url_for("compras", **_purchase_draft_query(_purchase_draft_from_source(request.args), open_compra="1", created_product=request.args.get("created_product", ""), created_provider=request.args.get("created_provider", ""))))
    if request.method == "POST":
        data = request.form.to_dict()
        producto = db.get_producto(int(data.get("producto_id", 0) or 0))
        proveedor = db.get_proveedor(int(data.get("proveedor_id", 0) or 0))
        if producto:
            data["codigo_interno"], data["descripcion"] = producto["codigo_interno"], producto["descripcion"]
        if proveedor:
            data["proveedor_nombre"] = proveedor["nombre"]
        data["total"] = float(data.get("cantidad", 0) or 0) * float(data.get("costo_unitario", 0) or 0)
        condicion_pago = str(data.get("condicion_pago", "contado") or "contado").strip().lower()
        factura_data = {
            "condicion_pago": condicion_pago,
            "numero_factura": data.get("numero_factura", ""),
            "fecha_factura": data.get("fecha_factura", ""),
            "fecha_vencimiento": data.get("fecha_vencimiento", ""),
            "observaciones_factura": data.get("observaciones_factura", ""),
        }
        try:
            compra_id = 0
            if condicion_pago == "cuenta_corriente":
                compra_id = int(db.add_compra_con_factura(data, factura_data) or 0)
                flash("Compra registrada y factura comercial creada.", "success")
            else:
                compra_id = int(db.add_compra(data) or 0)
                flash("Compra registrada.", "success")
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("compras", **_purchase_draft_query(_purchase_draft_from_source(request.form), open_compra="1")))
        except Exception:
            flash("No se pudo registrar la compra correctamente.", "danger")
            return redirect(url_for("compras", **_purchase_draft_query(_purchase_draft_from_source(request.form), open_compra="1")))
        _auditar_accion("COMPRA_REGISTRADA", "compra", 0, detalle=f"Remito: {data.get('numero_remito', '') or 'Sin remito'} · Proveedor: {data.get('proveedor_nombre', '') or 'Sin proveedor'} · Total: {float(data.get('total', 0) or 0):.2f}")
        flash("✅ Compra registrada.", "success")
        return redirect(url_for("compras"))
    return redirect(url_for("compras"))


@main_bp.route("/compras/<int:cid>")
@vendedor_forbidden
def compra_detalle(cid):
    return render_template("compra_detalle.html", compra=db.get_compra(cid))


@main_bp.route("/compras/<int:cid>/editar", methods=["GET", "POST"])
@vendedor_forbidden
def compra_editar(cid):
    compra = db.get_compra(cid)
    if not compra:
        abort(404)
    if int(compra["anulada"] or 0):
        flash("No se puede editar una compra anulada.", "warning")
        return redirect(url_for("compra_detalle", cid=cid))

    factura = db.get_factura_por_compra(cid)
    factura_tiene_pagos = bool(factura and float(factura["pagado"] or 0) > 0)
    condicion_pago = "cuenta_corriente" if factura else "contado"

    if request.method == "POST":
        proveedor_actual_id = int(compra["proveedor_id"] or 0)
        proveedor_nuevo_id = int(request.form.get("proveedor_id", proveedor_actual_id) or 0)
        proveedor_nuevo = db.get_proveedor(proveedor_nuevo_id) if proveedor_nuevo_id > 0 else None

        if proveedor_nuevo_id > 0 and not proveedor_nuevo:
            flash("El proveedor seleccionado no existe.", "warning")
            return redirect(url_for("main.compra_editar", cid=cid))

        if factura_tiene_pagos and proveedor_nuevo_id != proveedor_actual_id:
            flash("No se puede cambiar el proveedor porque la factura asociada ya registra pagos.", "warning")
            proveedor_nuevo_id = proveedor_actual_id
            proveedor_nuevo = db.get_proveedor(proveedor_actual_id) if proveedor_actual_id > 0 else None

        fecha = str(request.form.get("fecha", compra["fecha"] or "") or "").strip()
        if not fecha:
            flash("La fecha de la compra es obligatoria.", "warning")
            return redirect(url_for("main.compra_editar", cid=cid))

        try:
            db.actualizar_compra_basica(
                cid,
                proveedor_nuevo_id,
                fecha,
                request.form.get("observaciones", compra["observaciones"] or ""),
                condicion_pago=condicion_pago,
                numero_remito=request.form.get("numero_remito", compra["numero_remito"] or ""),
                proveedor_nombre=proveedor_nuevo["nombre"] if proveedor_nuevo else "",
            )
            if factura:
                db.actualizar_factura_compra_basica(
                    int(factura["id"]),
                    request.form.get("numero_factura", factura["numero_factura"] or f"COMPRA-{cid}"),
                    request.form.get("fecha_factura", factura["fecha"] or fecha),
                    request.form.get("fecha_vencimiento", factura["fecha_vencimiento"] or ""),
                    request.form.get("observaciones_factura", factura["observaciones"] or ""),
                    proveedor_id=proveedor_nuevo_id or int(factura["proveedor_id"] or 0),
                )
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("main.compra_editar", cid=cid))

        flash("Compra actualizada sin recalcular stock ni modificar el detalle.", "success")
        return redirect(url_for("compra_detalle", cid=cid))

    return render_template(
        "compra_editar.html",
        compra=compra,
        factura=factura,
        proveedores=db.get_proveedores(),
        condicion_pago=condicion_pago,
        factura_tiene_pagos=factura_tiene_pagos,
    )


@main_bp.route("/compras/<int:cid>/eliminar", methods=["POST"])
@admin_required
def compra_eliminar(cid):
    ok, msg = _validate_purchase_cancel_authorization(request.form)
    if not ok:
        flash(msg, "warning")
        return redirect(url_for("compras"))
    try:
        compra = db.get_compra(cid)
        if not compra:
            flash("La compra indicada no existe.", "warning")
            return redirect(url_for("compras"))
        if int(compra["anulada"] or 0):
            flash(f"La compra #{compra['id']} ya estaba anulada.", "warning")
            return redirect(url_for("compras"))
        db.anular_compra(
            cid,
            motivo=request.form.get("motivo_anulacion", ""),
            usuario=session.get("user", {}).get("username", ""),
            rol=session.get("user", {}).get("rol", ""),
        )
        flash("Compra anulada correctamente. El stock fue ajustado.", "success")
        return redirect(url_for("compras"))
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("compras"))


@main_bp.route("/caja")
@login_required
def caja():
    caja_actual = _caja_abierta()
    next_url = _safe_next_url(request.args.get("next"), url_for("caja"))
    auto_open = (request.args.get("auto_open", "") or "").strip().lower()
    return render_template(
        "caja.html",
        caja=caja_actual,
        movimientos=_caja_movimientos(caja_actual["id"]) if caja_actual else [],
        resumen=_caja_resumen(caja_actual),
        historial=db.q("SELECT * FROM caja WHERE estado=0 ORDER BY fecha_cierre DESC LIMIT 20"),
        next_url=next_url,
        auto_open_abrir=auto_open == "abrir" and not caja_actual,
        auto_open_cerrar=auto_open == "cerrar" and bool(caja_actual),
        solo_lectura=False,
    )


@main_bp.route("/caja/<int:cid>")
@login_required
def caja_detalle(cid):
    caja_row = db.q("SELECT * FROM caja WHERE id=?", (cid,), fetchone=True)
    if not caja_row:
        flash("La caja indicada no existe.", "warning")
        return redirect(url_for("caja"))
    if int(caja_row["estado"] or 0) == 1:
        return redirect(url_for("caja"))
    return render_template(
        "caja.html",
        caja=caja_row,
        movimientos=_caja_movimientos(caja_row["id"]),
        resumen=_caja_resumen(caja_row),
        historial=db.q("SELECT * FROM caja WHERE estado=0 ORDER BY fecha_cierre DESC LIMIT 20"),
        next_url=url_for("caja"),
        auto_open_abrir=False,
        auto_open_cerrar=False,
        solo_lectura=True,
    )


@main_bp.route("/caja/abrir", methods=["POST"])
@login_required
def caja_abrir():
    if not _caja_abierta():
        marca_tiempo = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        saldo_inicial = float(request.form.get("saldo_inicial", 0) or 0)
        caja_id = db.q("INSERT INTO caja (usuario_id,fecha_apertura,saldo_inicial,estado) VALUES (?,?,?,1)", (session["user"]["id"], marca_tiempo, saldo_inicial), commit=True)
        db.registrar_auditoria(
            "APERTURA_CAJA",
            "caja",
            caja_id,
            detalle=f"Caja abierta con saldo inicial {saldo_inicial:.2f}",
            usuario=session.get("user", {}).get("username", ""),
            rol=session.get("user", {}).get("rol", ""),
        )
    return redirect(_safe_next_url(request.form.get("next"), url_for("caja")))


@main_bp.route("/caja/movimiento", methods=["POST"])
@login_required
def caja_movimiento():
    caja_actual = _caja_abierta()
    if not caja_actual:
        flash("No hay una caja abierta para registrar movimientos.", "warning")
        return redirect(url_for("caja"))
    db.registrar_movimiento_caja_abierta(
        request.form.get("tipo", "INGRESO"),
        float(request.form.get("monto", 0) or 0),
        request.form.get("motivo", ""),
    )
    return redirect(url_for("caja"))


@main_bp.route("/caja/movimiento/<int:mid>/anular", methods=["POST"])
@login_required
def caja_movimiento_anular(mid):
    motivo = (request.form.get("motivo_anulacion", "") or "").strip()
    if not motivo:
        flash("El motivo de anulación es obligatorio.", "warning")
        return redirect(url_for("caja"))
    try:
        db.anular_caja_movimiento(mid, motivo, usuario=session.get("user", {}).get("username", ""))
        flash("Movimiento de caja anulado correctamente. El historial fue conservado.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("caja"))


@main_bp.route("/caja/cerrar", methods=["POST"])
@login_required
def caja_cerrar():
    caja_actual = _caja_abierta()
    if not caja_actual:
        flash("No hay una caja abierta para cerrar.", "warning")
        return redirect(url_for("caja"))
    marca_tiempo = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    saldo_real = float(request.form.get("saldo_real", 0) or 0)
    db.q("UPDATE caja SET fecha_cierre=?,saldo_final_real=?,estado=0 WHERE id=?", (marca_tiempo, saldo_real, caja_actual["id"]), commit=True)
    db.registrar_auditoria(
        "CIERRE_CAJA",
        "caja",
        int(caja_actual["id"] or 0),
        detalle=f"Caja cerrada con saldo real {saldo_real:.2f}",
        usuario=session.get("user", {}).get("username", ""),
        rol=session.get("user", {}).get("rol", ""),
    )
    return redirect(_safe_next_url(request.form.get("next"), url_for("caja")))


@main_bp.route("/gastos")
@vendedor_forbidden
def gastos():
    rows = db.get_gastos(request.args.get("q", ""), request.args.get("fecha_desde", ""), request.args.get("fecha_hasta", ""))
    activos = [r for r in rows if not int(r["anulado"] or 0)]
    return render_template("gastos.html", gastos=rows, buscar=request.args.get("q", ""), fecha_desde=request.args.get("fecha_desde", ""), fecha_hasta=request.args.get("fecha_hasta", ""), total_gastos=sum(float(r["monto"] or 0) for r in activos), total_necesarios=sum(float(r["monto"] or 0) for r in activos if "prescindible" not in str(r["necesario"]).lower()), total_prescind=sum(float(r["monto"] or 0) for r in activos if "prescindible" in str(r["necesario"]).lower()), cats=db.get_gasto_categorias(), usuario_es_admin=_is_admin_role(session.get("user", {}).get("rol")))


@main_bp.route("/gastos/nuevo", methods=["GET", "POST"])
@vendedor_forbidden
def gasto_nuevo():
    if request.method == "POST":
        data = _resolver_proveedor_gasto(request.form.to_dict())
        if not data:
            return render_template(
                "gasto_form.html",
                gasto=None,
                categorias_gastos=db.get_gasto_categorias(),
                clasificaciones_gastos=db.get_gasto_clasificaciones(),
                proveedores=db.get_proveedores(),
                accion="Nuevo",
                hoy=datetime.now().strftime("%Y-%m-%d"),
            )
        if not _validar_gasto_efectivo_contra_caja(data):
            return render_template(
                "gasto_form.html",
                gasto=None,
                categorias_gastos=db.get_gasto_categorias(),
                clasificaciones_gastos=db.get_gasto_clasificaciones(),
                proveedores=db.get_proveedores(),
                accion="Nuevo",
                hoy=data.get("fecha") or datetime.now().strftime("%Y-%m-%d"),
                gasto_form=data,
            )
        try:
            gasto_id = int(db.add_gasto(data) or 0)
        except ValueError as exc:
            flash(str(exc), "warning")
            return render_template(
                "gasto_form.html",
                gasto=None,
                categorias_gastos=db.get_gasto_categorias(),
                clasificaciones_gastos=db.get_gasto_clasificaciones(),
                proveedores=db.get_proveedores(),
                accion="Nuevo",
                hoy=data.get("fecha") or datetime.now().strftime("%Y-%m-%d"),
                gasto_form=data,
            )
        flash("✅ Gasto registrado.", "success")
        _auditar_accion(
            "GASTO_REGISTRADO",
            "gasto",
            gasto_id,
            detalle=f"{data.get('categoria', '') or 'Sin categoria'} · {data.get('descripcion', '') or 'Sin descripcion'} · {float(data.get('monto', 0) or 0):.2f}",
        )
        return redirect(url_for("gastos"))
    return render_template(
        "gasto_form.html",
        categorias_gastos=db.get_gasto_categorias(),
        clasificaciones_gastos=db.get_gasto_clasificaciones(),
        proveedores=db.get_proveedores(),
        accion="Nuevo",
        hoy=datetime.now().strftime("%Y-%m-%d"),
        gasto_form=None,
    )


@main_bp.route("/gastos/<int:gid>/editar", methods=["GET", "POST"])
@admin_required
def gasto_editar(gid):
    gasto = db.get_gasto(gid)
    if not gasto:
        flash("Gasto no encontrado.", "danger")
        return redirect(url_for("gastos"))
    if int(gasto["anulado"] or 0):
        flash("El gasto seleccionado ya está anulado y no se puede editar.", "warning")
    else:
        flash("Los gastos registrados no se editan para conservar caja y reportes. Anulalo y cargalo nuevamente.", "warning")
    return redirect(url_for("gastos"))


@main_bp.route("/gastos/<int:gid>/eliminar", methods=["POST"])
@admin_required
def gasto_eliminar(gid):
    try:
        db.anular_gasto(
            gid,
            request.form.get("motivo_anulacion", ""),
            usuario=session.get("user", {}).get("username", ""),
            rol=session.get("user", {}).get("rol", ""),
        )
        flash("Gasto anulado correctamente. El historial fue conservado.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("gastos"))


@main_bp.route("/clientes")
@login_required
def clientes():
    db.reconciliar_cc_clientes_desde_ventas()
    return render_template("clientes.html", clientes=db.get_clientes(request.args.get("q", ""), _as_bool(request.args.get("solo_deuda"))), buscar=request.args.get("q", ""), solo_deuda=_as_bool(request.args.get("solo_deuda")), usuario_puede_editar_clientes=not _is_vendedor_role(session.get("user", {}).get("rol")))


@main_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@vendedor_forbidden
def cliente_nuevo():
    if request.method == "POST":
        if not _limit_allows("clientes"):
            return redirect(url_for("clientes"))
        nuevo_id = int(db.add_cliente(request.form.to_dict()) or 0)
        _auditar_accion(
            "ALTA_CLIENTE",
            "cliente",
            nuevo_id,
            detalle=request.form.get("nombre", "").strip() or "Cliente",
        )
        return redirect(url_for("clientes"))
    return render_template("cliente_form.html", cliente=None, accion="Crear")


@main_bp.route("/clientes/<int:cid>/editar", methods=["GET", "POST"])
@vendedor_forbidden
def cliente_editar(cid):
    cliente = db.get_cliente(cid)
    if request.method == "POST":
        data = request.form.to_dict()
        data["activo"] = 1 if _as_bool(data.get("activo")) else 0
        db.update_cliente(cid, data)
        _auditar_accion(
            "EDICION_CLIENTE",
            "cliente",
            cid,
            detalle=data.get("nombre", cliente["nombre"] if cliente else "") or "Cliente",
        )
        return redirect(url_for("cliente_detalle", cid=cid))
    return render_template("cliente_form.html", cliente=cliente, accion="Editar")


@main_bp.route("/clientes/<int:cid>")
@login_required
def cliente_detalle(cid):
    db.reconciliar_cc_clientes_desde_ventas()
    return render_template(
        "cliente_detalle.html",
        cliente=db.get_cliente(cid),
        saldo=db.get_saldo_cliente(cid),
        movimientos=db.get_movimientos_cliente(cid),
        historial_ventas=db.get_historial_ventas_cliente(cid),
        estadisticas=db.get_estadisticas_cliente(cid),
        today=datetime.now().strftime("%Y-%m-%d"),
        usuario_es_admin=_is_admin_role(session.get("user", {}).get("rol")),
        usuario_puede_editar_cliente=not _is_vendedor_role(session.get("user", {}).get("rol")),
    )


@main_bp.route("/clientes/<int:cid>/movimiento", methods=["POST"])
@vendedor_forbidden
def cliente_agregar_movimiento(cid):
    tipo = (request.form.get("tipo", "Ajuste") or "").strip()
    try:
        if tipo.lower() == "pago":
            db.registrar_pago_cliente(
                cid,
                float(request.form.get("haber", 0) or 0),
                numero_comprobante=request.form.get("numero_comprobante", ""),
                observaciones=request.form.get("observaciones", ""),
                fecha=request.form.get("fecha", ""),
                medio_pago=request.form.get("medio_pago", "Efectivo"),
            )
            flash("Pago registrado correctamente.", "success")
        else:
            db.registrar_movimiento_cliente_manual(
                cid,
                tipo,
                request.form.get("numero_comprobante", ""),
                float(request.form.get("debe", 0) or 0),
                float(request.form.get("haber", 0) or 0),
                request.form.get("vencimiento", ""),
                request.form.get("observaciones", ""),
                fecha=request.form.get("fecha", ""),
                medio_pago=request.form.get("medio_pago", ""),
            )
            flash("Movimiento registrado correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("cliente_detalle", cid=cid))


@main_bp.route("/clientes/<int:cid>/movimiento/<int:mid>/anular", methods=["POST"])
@admin_required
def cliente_anular_movimiento(cid, mid):
    movimiento = db.get_movimiento_cliente(mid)
    if not movimiento or int(movimiento["cliente_id"] or 0) != cid:
        flash("El movimiento indicado no existe para este cliente.", "warning")
        return redirect(url_for("cliente_detalle", cid=cid))

    try:
        db.anular_movimiento_cliente(
            mid,
            request.form.get("motivo_anulacion", ""),
            usuario=session.get("user", {}).get("username", ""),
            rol=session.get("user", {}).get("rol", ""),
        )
        flash("Movimiento anulado correctamente. El historial fue conservado.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("cliente_detalle", cid=cid))


@main_bp.route("/clientes/<int:cid>/eliminar", methods=["POST"])
@vendedor_forbidden
def cliente_eliminar(cid):
    db.delete_cliente(cid)
    return redirect(url_for("clientes"))


@main_bp.route("/proveedores")
@vendedor_forbidden
def proveedores():
    buscar = request.args.get("q", "")
    proveedores_list = db.get_proveedores(activo_only=False, search=buscar)
    proveedores_con_deuda = sum(
        1 for proveedor in proveedores_list
        if db.get_deuda_proveedor_desde_facturas(proveedor["id"]) > 0
    )
    return render_template(
        "proveedores.html",
        proveedores=proveedores_list,
        buscar=buscar,
        proveedores_con_deuda=proveedores_con_deuda,
    )


@main_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@vendedor_forbidden
def proveedor_nuevo():
    if request.method == "POST":
        if not _limit_allows("proveedores"):
            if request.form.get("return_to") == "compras":
                return redirect(url_for("compras", **_purchase_draft_query(_purchase_draft_from_source(request.form), open_compra="1")))
            return redirect(url_for("proveedores"))
        nuevo_id = db.add_proveedor(request.form.to_dict())
        if request.form.get("return_to") == "compras":
            draft = _purchase_draft_from_source(request.form)
            draft["proveedor_id"] = str(nuevo_id)
            return redirect(url_for("compras", **_purchase_draft_query(draft, open_compra="1", created_provider="1")))
        return redirect(url_for("proveedores"))
    return render_template("proveedor_form.html", proveedor=None, accion="Crear")


@main_bp.route("/proveedores/<int:pid>/editar", methods=["GET", "POST"])
@vendedor_forbidden
def proveedor_editar(pid):
    proveedor = db.get_proveedor(pid)
    if request.method == "POST":
        db.update_proveedor(pid, request.form.to_dict())
        return redirect(url_for("proveedor_detalle", pid=pid))
    return render_template("proveedor_form.html", proveedor=proveedor, accion="Editar")


@main_bp.route("/proveedores/<int:pid>")
@vendedor_forbidden
def proveedor_detalle(pid):
    proveedor = _get_proveedor_or_404(pid)
    saldo_auxiliar = db.get_saldo_proveedor(pid)
    movimientos_auxiliares = db.get_movimientos_proveedor(pid)
    resumen_facturas = db.get_resumen_facturas_proveedor(pid)
    facturas = _enriquecer_facturas_proveedor(db.get_facturas_proveedor(pid))
    return render_template(
        "proveedor_detalle.html",
        proveedor=proveedor,
        saldo_auxiliar=saldo_auxiliar,
        deuda_comercial=resumen_facturas["deuda_total"],
        resumen_facturas=resumen_facturas,
        facturas=facturas[:5],
        movimientos_auxiliares=movimientos_auxiliares,
        historial_compras=db.get_historial_compras_proveedor(pid),
        estadisticas=db.get_estadisticas_proveedor(pid),
    )


@main_bp.route("/precios/proveedor")
@vendedor_forbidden
def precios_proveedor():
    proveedor_filtro = (request.args.get("proveedor", "") or "").strip()
    categoria_filtro = (request.args.get("categoria", "") or "").strip()
    porcentaje = (request.args.get("porcentaje", "") or "").strip()
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    productos_rubro = [dict(r) for r in db.get_productos(rubro=rubro_actual)]
    proveedores_map = {}
    for row in productos_rubro:
        nombre = str(row.get("proveedor_habitual") or "").strip()
        if nombre:
            proveedores_map.setdefault(nombre.lower(), nombre)
    proveedores_visibles = sorted(proveedores_map.values(), key=str.lower)
    categorias_visibles = _merge_categorias_visibles(
        rubro_actual,
        [row.get("categoria", "") for row in productos_rubro],
    )
    return render_template(
        "precios_proveedor.html",
        proveedores=proveedores_visibles,
        categorias=categorias_visibles,
        proveedor_filtro=proveedor_filtro,
        categoria_filtro=categoria_filtro,
        porcentaje=porcentaje,
        productos_preview=[],
        total_afectados=0,
        rubro_actual=rubro_actual,
    )


@main_bp.route("/precios/proveedor/previsualizar", methods=["POST"])
@vendedor_forbidden
def precios_proveedor_previsualizar():
    proveedor_filtro = (request.form.get("proveedor", "") or "").strip()
    categoria_filtro = (request.form.get("categoria", "") or "").strip()
    porcentaje_raw = (request.form.get("porcentaje", "") or "").strip()
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    productos_rubro = [dict(r) for r in db.get_productos(rubro=rubro_actual)]
    proveedores_map = {}
    for row in productos_rubro:
        nombre = str(row.get("proveedor_habitual") or "").strip()
        if nombre:
            proveedores_map.setdefault(nombre.lower(), nombre)
    proveedores_visibles = sorted(proveedores_map.values(), key=str.lower)
    categorias_visibles = _merge_categorias_visibles(
        rubro_actual,
        [row.get("categoria", "") for row in productos_rubro],
    )

    productos_preview = []
    total_afectados = 0
    try:
        if not proveedor_filtro:
            raise ValueError("Debes seleccionar un proveedor.")
        porcentaje = _parse_positive_percentage(porcentaje_raw)
        productos_rows = [
            dict(r)
            for r in db.get_productos_por_proveedor_categoria(
                proveedor_filtro,
                categoria_filtro,
                rubro=rubro_actual,
            )
        ]
        productos_preview = _build_precios_preview_rows(productos_rows, porcentaje)
        total_afectados = len(productos_preview)
        if total_afectados == 0:
            flash("No se encontraron productos para ese proveedor/categoría.", "warning")
    except ValueError as exc:
        flash(str(exc), "warning")

    return render_template(
        "precios_proveedor.html",
        proveedores=proveedores_visibles,
        categorias=categorias_visibles,
        proveedor_filtro=proveedor_filtro,
        categoria_filtro=categoria_filtro,
        porcentaje=porcentaje_raw,
        productos_preview=productos_preview,
        total_afectados=total_afectados,
        rubro_actual=rubro_actual,
    )


@main_bp.route("/precios/proveedor/aplicar", methods=["POST"])
@vendedor_forbidden
def precios_proveedor_aplicar():
    proveedor_filtro = (request.form.get("proveedor", "") or "").strip()
    categoria_filtro = (request.form.get("categoria", "") or "").strip()
    porcentaje_raw = (request.form.get("porcentaje", "") or "").strip()
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    try:
        if not proveedor_filtro:
            raise ValueError("Debes seleccionar un proveedor.")
        porcentaje = _parse_positive_percentage(porcentaje_raw)
        productos_rows = db.get_productos_por_proveedor_categoria(
            proveedor_filtro,
            categoria_filtro,
            rubro=rubro_actual,
        )
        if not productos_rows:
            flash("No se encontraron productos para ese proveedor/categoría.", "warning")
            return redirect(
                url_for(
                    "precios_proveedor",
                    proveedor=proveedor_filtro,
                    categoria=categoria_filtro,
                    porcentaje=porcentaje_raw,
                )
            )
        afectados = db.aplicar_aumento_precios([row["id"] for row in productos_rows], porcentaje)
        flash(f"Se actualizaron {afectados} productos correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(
            url_for(
                "precios_proveedor",
                proveedor=proveedor_filtro,
                categoria=categoria_filtro,
                porcentaje=porcentaje_raw,
            )
        )

    return redirect(
        url_for(
            "precios_proveedor",
            proveedor=proveedor_filtro,
            categoria=categoria_filtro,
        )
    )


@main_bp.route("/proveedores/<int:pid>/facturas")
@vendedor_forbidden
def proveedor_facturas(pid):
    proveedor = _get_proveedor_or_404(pid)
    facturas = _enriquecer_facturas_proveedor(db.get_facturas_proveedor(pid))
    resumen_facturas = db.get_resumen_facturas_proveedor(pid)
    return render_template(
        "proveedor_facturas.html",
        proveedor=proveedor,
        deuda_comercial=resumen_facturas["deuda_total"],
        resumen_facturas=resumen_facturas,
        facturas=facturas,
        usuario_es_admin=_is_admin_role(session.get("user", {}).get("rol")),
    )


@main_bp.route("/proveedores/<int:pid>/facturas/nueva", methods=["GET", "POST"])
@vendedor_forbidden
def proveedor_factura_nueva(pid):
    proveedor = _get_proveedor_or_404(pid)
    if request.method == "POST":
        try:
            db.crear_factura_proveedor(
                pid,
                request.form.get("numero_factura", ""),
                request.form.get("fecha", ""),
                request.form.get("fecha_vencimiento", ""),
                request.form.get("importe", 0),
                request.form.get("observaciones", ""),
            )
            flash("Factura creada correctamente.", "success")
            return redirect(url_for("proveedor_facturas", pid=pid))
        except ValueError as exc:
            flash(str(exc), "warning")
    return render_template(
        "proveedor_factura_form.html",
        proveedor=proveedor,
        factura=None,
        accion="Nueva factura",
    )


@main_bp.route("/proveedores/<int:pid>/facturas/<int:factura_id>/editar", methods=["GET", "POST"])
@admin_required
def proveedor_factura_editar(pid, factura_id):
    proveedor = _get_proveedor_or_404(pid)
    factura = _get_factura_proveedor_or_404(pid, factura_id)
    if int(factura["anulada"] or 0):
        flash("No se puede editar una factura anulada.", "warning")
        return redirect(url_for("proveedor_facturas", pid=pid))
    if request.method == "POST":
        try:
            db.actualizar_factura_proveedor(
                factura_id,
                request.form.get("numero_factura", ""),
                request.form.get("fecha", ""),
                request.form.get("fecha_vencimiento", ""),
                request.form.get("importe", 0),
                request.form.get("observaciones", ""),
            )
            flash("Factura actualizada correctamente.", "success")
            return redirect(url_for("proveedor_facturas", pid=pid))
        except ValueError as exc:
            flash(str(exc), "warning")
            factura = db.get_factura_proveedor(factura_id)
    return render_template(
        "proveedor_factura_form.html",
        proveedor=proveedor,
        factura=factura,
        accion="Editar factura",
    )


@main_bp.route("/proveedores/<int:pid>/facturas/<int:factura_id>/pagar", methods=["POST"])
@vendedor_forbidden
def proveedor_factura_pagar(pid, factura_id):
    _get_proveedor_or_404(pid)
    factura = _get_factura_proveedor_or_404(pid, factura_id)
    if int(factura["anulada"] or 0):
        flash("No se puede registrar un pago sobre una factura anulada.", "warning")
        return redirect(request.form.get("next") or url_for("proveedor_facturas", pid=pid))
    try:
        db.registrar_pago_factura_proveedor(
            factura_id,
            request.form.get("monto", 0),
        )
        flash("Pago registrado correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(request.form.get("next") or url_for("proveedor_facturas", pid=pid))


@main_bp.route("/proveedores/<int:pid>/facturas/<int:factura_id>/eliminar", methods=["POST"])
@admin_required
def proveedor_factura_eliminar(pid, factura_id):
    _get_proveedor_or_404(pid)
    factura = _get_factura_proveedor_or_404(pid, factura_id)
    ok, msg = _validate_provider_invoice_cancel_authorization(request.form)
    if not ok:
        flash(msg, "warning")
        return redirect(request.form.get("next") or url_for("proveedor_facturas", pid=pid))
    if int(factura["anulada"] or 0):
        flash("La factura ya estaba anulada.", "warning")
        return redirect(request.form.get("next") or url_for("proveedor_facturas", pid=pid))
    try:
        db.anular_factura_proveedor(
            factura_id,
            motivo=request.form.get("motivo_anulacion", ""),
            usuario=session.get("user", {}).get("username", ""),
            rol=session.get("user", {}).get("rol", ""),
        )
        flash("Factura anulada correctamente. El historial se conservó.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(request.form.get("next") or url_for("proveedor_facturas", pid=pid))


@main_bp.route("/proveedores/<int:pid>/movimiento", methods=["POST"])
@vendedor_forbidden
def proveedor_agregar_movimiento(pid):
    db.agregar_movimiento_proveedor(pid, request.form.get("tipo", "Ajuste"), request.form.get("numero_comprobante", ""), float(request.form.get("debe", 0) or 0), float(request.form.get("haber", 0) or 0), request.form.get("vencimiento", ""), request.form.get("observaciones", ""))
    return redirect(url_for("proveedor_detalle", pid=pid))


@main_bp.route("/proveedores/<int:pid>/eliminar", methods=["POST"])
@vendedor_forbidden
def proveedor_eliminar(pid):
    db.delete_proveedor(pid)
    return redirect(url_for("proveedores"))


@main_bp.route("/reportes")
@vendedor_forbidden
def reportes():
    require_modulo("reportes")
    rubro_actual = get_rubro_actual(db.get_config())
    rent = db.get_stats_rentabilidad(rubro=rubro_actual)
    pagos = [{"medio_pago": r["medio_pago"], "monto": r["total"]} for r in db.get_ventas_por_medio_pago(date.today().year, date.today().month, rubro=rubro_actual)]
    rubro_cond, rubro_params = db._build_rubro_compatible_filter_sql("p", rubro_actual)
    ventas_7 = db.q(
        f"""
        SELECT v.fecha as dia, ROUND(SUM(v.total),2) as monto
        FROM ventas v
        WHERE v.fecha >= date('now','-6 days')
          AND COALESCE(v.anulada, 0)=0
          AND EXISTS (
              SELECT 1
              FROM ventas_detalle vd
              LEFT JOIN productos p ON p.id = vd.producto_id
              WHERE vd.venta_id = v.id AND {rubro_cond}
          )
        GROUP BY v.fecha ORDER BY v.fecha
        """,
        tuple(rubro_params),
    )
    gastos_nec, gastos_pre = _resumen_gastos_reportes(db.get_gastos())
    total_g = gastos_nec + gastos_pre
    pct = round((gastos_pre / total_g) * 100, 1) if total_g else 0
    return render_template(
        "reportes.html",
        rentabilidad=rent,
        top_productos=_enriquecer_items_reporte(db.get_top_productos_vendidos(5, rubro=rubro_actual)),
        pagos=pagos,
        ventas_7_dias=ventas_7,
        gastos_necesarios=gastos_nec,
        gastos_prescindibles=gastos_pre,
        pct_prescindibles=pct,
        recomendacion_gastos="Revisar gastos prescindibles." if pct > 20 else "Gastos prescindibles controlados.",
        rubro_actual=rubro_actual,
        categorias_rubro=get_categorias_disponibles(rubro_actual),
    )


@main_bp.route("/estadisticas")
@vendedor_forbidden
def estadisticas():
    require_modulo("reportes")
    year = int(request.args.get("year", date.today().year))
    rubro_actual = get_rubro_actual(db.get_config())
    ventas_mes = db.get_ventas_por_mes(year, rubro=rubro_actual)
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    semanas = db.get_ventas_por_semana(8, rubro=rubro_actual)
    medios = db.get_ventas_por_medio_pago(year, date.today().month, rubro=rubro_actual)
    cats = db.get_ventas_por_categoria(rubro=rubro_actual)
    return render_template("estadisticas.html", year=year, meses_labels=json.dumps(meses), ventas_vals=json.dumps([ventas_mes.get(m, {}).get("total", 0) for m in range(1, 13)]), tickets_vals=json.dumps([ventas_mes.get(m, {}).get("tickets", 0) for m in range(1, 13)]), semanas=semanas, semanas_labels=json.dumps([s["label"] for s in semanas]), semanas_vals=json.dumps([s["total"] for s in semanas]), medios=medios, medios_labels=json.dumps([m["medio_pago"] for m in medios]), medios_vals=json.dumps([m["total"] for m in medios]), temporadas=db.get_ventas_por_temporada(rubro=rubro_actual), cats=cats, cats_labels=json.dumps([c["categoria"] for c in cats[:8]]), cats_vals=json.dumps([c["total"] for c in cats[:8]]), rubro_actual=rubro_actual, categorias_rubro=get_categorias_disponibles(rubro_actual))


@main_bp.route("/analisis")
@vendedor_forbidden
def analisis():
    require_modulo("ia")
    desde = request.args.get("desde", (date.today() - timedelta(days=30)).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    rubro_actual = get_rubro_actual(db.get_config())
    top = _enriquecer_items_reporte(db.get_top_productos_analisis(15, desde, hasta, rubro=rubro_actual))
    return render_template(
        "analisis.html",
        top=top,
        bottom=_enriquecer_items_reporte(db.get_bottom_productos(10, rubro=rubro_actual)),
        temporadas=db.get_ventas_por_temporada(rubro=rubro_actual),
        rent=db.get_stats_rentabilidad(rubro=rubro_actual),
        rent_hist=db.get_rentabilidad_historica(rubro=rubro_actual),
        gastos_cat=db.q("SELECT categoria, ROUND(SUM(monto),2) as total, necesario FROM gastos WHERE COALESCE(anulado, 0)=0 GROUP BY categoria ORDER BY total DESC"),
        fecha_desde=desde,
        fecha_hasta=hasta,
        resumen_bruto=db.get_resumen_rentabilidad_periodo(desde, hasta, rubro=rubro_actual),
        top_labels=json.dumps([t["descripcion"][:20] for t in top]),
        top_vals=json.dumps([t["total_pesos"] for t in top]),
        rubro_actual=rubro_actual,
    )


@main_bp.route("/rentabilidad-detallada")
@admin_required
def rentabilidad_detallada():
    require_modulo("reportes")
    rubro_actual = get_rubro_actual(db.get_config())
    hoy = date.today()
    semana_desde = hoy - timedelta(days=hoy.weekday())
    mes_desde = date(hoy.year, hoy.month, 1)
    anio_desde = date(hoy.year, 1, 1)
    periodo = request.args.get("periodo", "mes")
    tabs_validos = {"resumen", "gastos_mensual", "gastos_semanal", "articulos", "diario", "mensual", "anual"}
    tab = request.args.get("tab", "resumen")
    if tab not in tabs_validos:
        tab = "resumen"
    rangos = {
        "semana": (semana_desde.isoformat(), hoy.isoformat(), "semanal"),
        "mes": (mes_desde.isoformat(), hoy.isoformat(), "diario"),
        "anio": (anio_desde.isoformat(), hoy.isoformat(), "mensual"),
    }
    if periodo not in rangos:
        periodo = "mes"
    desde_default, hasta_default, granularidad = rangos[periodo]
    desde = request.args.get("desde", desde_default)
    hasta = request.args.get("hasta", hasta_default)
    return render_template(
        "rentabilidad_detallada.html",
        fecha_desde=desde,
        fecha_hasta=hasta,
        tab=tab,
        periodo=periodo,
        resumen_simple=db.get_resumen_rentabilidad_simple(desde, hasta, rubro=rubro_actual),
        gastos_categoria=db.get_gastos_por_categoria_periodo(desde, hasta),
        evolucion_simple=db.get_evolucion_rentabilidad_simple(granularidad, desde, hasta, rubro=rubro_actual),
        articulos=_enriquecer_items_reporte(db.get_rentabilidad_detallada_articulos(desde, hasta, rubro=rubro_actual)),
        diario=db.get_rentabilidad_detallada_periodos("diario", desde, hasta, rubro=rubro_actual),
        mensual=db.get_rentabilidad_detallada_periodos("mensual", desde, hasta, rubro=rubro_actual),
        anual=db.get_rentabilidad_detallada_periodos("anual", desde, hasta, rubro=rubro_actual),
        gastos_mensual=db.get_composicion_gastos_rentabilidad("mensual", desde, hasta, rubro=rubro_actual),
        gastos_semanal=db.get_composicion_gastos_rentabilidad("semanal", desde, hasta, rubro=rubro_actual),
        rubro_actual=rubro_actual,
        categorias_rubro=get_categorias_disponibles(rubro_actual),
    )


@main_bp.route("/auditoria")
@admin_required
def auditoria():
    filtros = {
        "accion": request.args.get("accion", ""),
        "entidad": request.args.get("entidad", ""),
        "fecha_desde": request.args.get("fecha_desde", ""),
        "fecha_hasta": request.args.get("fecha_hasta", ""),
    }
    opciones = db.get_auditoria_filtros()
    return render_template(
        "auditoria.html",
        registros=db.get_auditoria(
            filtros["accion"],
            filtros["entidad"],
            filtros["fecha_desde"],
            filtros["fecha_hasta"],
        ),
        acciones=opciones["acciones"],
        entidades=opciones["entidades"],
        **filtros,
    )


@main_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    usuario = db.q("SELECT * FROM usuarios WHERE id=?", (session["user"]["id"],), fetchone=True)
    if request.method == "POST":
        data = request.form.to_dict()
        if data.get("password"):
            ok, msg = _validate_password_confirmation(data["password"], data.get("password_confirm", ""))
            if not ok:
                flash(f"❌ {msg}", "danger")
                return render_template("perfil.html", usuario=usuario)
        if bool(data.get("security_question", "").strip()) != bool(data.get("security_answer", "").strip()):
            flash("⚠️ Para cambiar la recuperación, ingresá pregunta y respuesta secreta.", "warning")
            return render_template("perfil.html", usuario=usuario)
        if data.get("security_question", "").strip() and data.get("security_answer", "").strip():
            ok, msg = _validate_security_recovery(data["security_question"], data["security_answer"])
            if not ok:
                flash(f"⚠️ {msg}", "warning")
                return render_template("perfil.html", usuario=usuario)
        data.pop("password_confirm", None)
        db.update_perfil(usuario["id"], data)
        flash("✅ Perfil actualizado.", "success")
        return redirect(url_for("perfil"))
    return render_template("perfil.html", usuario=usuario)


@main_bp.route("/config", methods=["GET", "POST"])
@admin_required
def config():
    db.cleanup_categorias_duplicadas()
    if request.method == "POST":
        data = request.form.to_dict()
        data["ticket_mostrar_iva"] = "1" if _as_bool(data.get("ticket_mostrar_iva")) else "0"
        data.pop("rubro_negocio", None)
        data.pop("rubro_negocio_confirmado", None)
        db.set_config(data)
        _auditar_accion(
            "EDICION_CONFIG",
            "configuracion",
            0,
            detalle=f"Claves actualizadas: {', '.join(sorted(data.keys()))}",
        )
        return redirect(url_for("config"))
    cfg = db.get_config()
    rubro_actual = get_rubro_actual(cfg)
    return render_template(
        "config.html",
        cfg=cfg,
        categorias_configurables=db.get_categorias_configuracion(rubro_actual),
        categorias_rubro=get_categorias_disponibles(rubro_actual),
        categorias_gastos=db.get_gasto_categorias(),
        rubro_actual=rubro_actual,
        rubro_guardado=db.get_rubro_configurado(),
        mostrar_aviso_rubro_pendiente=db.debe_mostrar_aviso_rubro_pendiente(),
        rubros_disponibles=get_rubros_disponibles(),
        unidades_disponibles=get_unidades_disponibles(rubro_actual),
    )


@main_bp.route("/mi-plan")
@login_required
def mi_plan():
    refresh_ok, refresh_msg, refreshed_info = refresh_saved_license_online(debug=False)
    modulos_activos = sorted(get_modulos_activos())
    todos_los_modulos = sorted(set().union(*PLANES.values()))
    modulos_bloqueados = [modulo for modulo in todos_los_modulos if modulo not in modulos_activos]
    license_info = refreshed_info or db.get_license_info()
    license_status = _get_license_status_context(license_info)
    plan_actions = _get_plan_actions_context(license_info, license_status=license_status)
    available_checkout_plans = _get_available_checkout_plans(license_info)
    next_upgrade_plan = _resolve_next_upgrade_plan(license_info)
    checkout_pending = _get_checkout_pending_context()
    license_holder = _get_license_holder_profile(license_info)
    mi_plan_view = _build_mi_plan_view(
        license_info=license_info,
        license_status=license_status,
        plan_actions=plan_actions,
        license_holder=license_holder,
        checkout_pending=checkout_pending,
        modulos_activos=modulos_activos,
        modulos_bloqueados=modulos_bloqueados,
    )
    return render_template(
        "mi_plan.html",
        plan_activo=license_info.get("tier", "DEMO"),
        plan_display=mi_plan_view["plan_display"],
        mi_plan_view=mi_plan_view,
        plan_actions=plan_actions,
        license_status=license_status,
        license_info=license_info,
        modulos_activos=modulos_activos,
        modulos_bloqueados=modulos_bloqueados,
        next_upgrade_plan=next_upgrade_plan,
        next_upgrade_plan_display=get_plan_display_name(next_upgrade_plan) if next_upgrade_plan else "",
        available_checkout_plans=available_checkout_plans,
        supabase_ok=supabase_configured(),
        license_refresh_ok=refresh_ok,
        license_refresh_message=refresh_msg,
        license_holder=license_holder,
        checkout_enabled=bool(available_checkout_plans),
        checkout_pending=checkout_pending,
    )


@main_bp.route("/mi-plan/refrescar", methods=["GET"])
@admin_required
def licencia_refrescar():
    response, _ok = _refresh_license_response(force=True)
    return jsonify(response)


@main_bp.route("/mi-plan/actualizar-licencia", methods=["POST"])
@admin_required
def mi_plan_actualizar_licencia():
    response, ok = _refresh_license_response(force=True)
    if ok:
        plan = str(response.get("tier", "DEMO"))
        plan_label = get_plan_display_name(plan)
        flash(f"Estado de licencia actualizado. Plan actual: {plan_label}.", "success")
    else:
        flash(str(response.get("message") or "No se pudo actualizar online el estado de la licencia."), "warning")
    return redirect(url_for("main.mi_plan"))


@main_bp.route("/api/licencia/estado", methods=["GET"])
@login_required
def api_licencia_estado():
    try:
        stored_license = cargar_licencia() or {}
        license_info = db.get_license_info()
        license_key = str(license_info.get("key", "") or stored_license.get("license_key", "") or "").strip()

        if not license_key:
            if _get_checkout_pending_context()["pending"]:
                response, ok = _refresh_license_response(force=True)
                return jsonify({
                    **response,
                    "estado": "licencia_activada" if ok else "pago_pendiente",
                })
            return jsonify({
                "ok": False,
                "estado": "sin_licencia",
                "message": "No hay licencia activa",
            })

        last_refresh = ""
        if _LICENSE_REFRESH_LAST_RUN:
            last_refresh = datetime.fromtimestamp(_LICENSE_REFRESH_LAST_RUN).isoformat(timespec="seconds")
        elif str(license_info.get("last_check", "") or "").strip():
            last_refresh = str(license_info.get("last_check", "") or "").strip()

        needs_refresh = False
        if _LICENSE_REFRESH_LAST_RUN:
            needs_refresh = (time.time() - _LICENSE_REFRESH_LAST_RUN) >= LICENSE_AUTO_REFRESH_INTERVAL_SECONDS

        return jsonify({
            "ok": True,
            "license_key": _mask_license_key(license_key),
            "plan": str(license_info.get("plan", "") or ""),
            "plan_display": get_plan_display_name(license_info.get("tier", "DEMO")),
            "tier": str(license_info.get("tier", "DEMO") or "DEMO"),
            "plan_original": str(license_info.get("plan_original", license_info.get("plan", "")) or ""),
            "plan_efectivo": str(license_info.get("plan_efectivo", license_info.get("tier", "DEMO")) or "DEMO"),
            "estado": str(license_info.get("estado", "") or "activa"),
            "fallback_aplicado": bool(license_info.get("fallback_aplicado")),
            "expirada": bool(license_info.get("expirada")),
            "expires_at": str(license_info.get("expires_at", "") or ""),
            "license_status": _get_license_status_context(license_info),
            "modules": sorted(license_info.get("modules", []) or []),
            "last_refresh": last_refresh,
            "needs_refresh": needs_refresh,
            "checkout_pending": _get_checkout_pending_context(),
        })
    except Exception:
        logger.exception("No se pudo exponer el estado de licencia por API")
        return jsonify({
            "ok": False,
            "estado": "error",
            "message": "No se pudo obtener el estado de la licencia",
        }), 500


@main_bp.route("/mi-plan/titular", methods=["POST"])
@admin_required
def mi_plan_guardar_titular():
    holder_profile = {
        "nombre": request.form.get("titular_nombre", "").strip(),
        "email": request.form.get("titular_email", "").strip().lower(),
        "telefono": request.form.get("titular_telefono", "").strip(),
        "palabra_recuperacion": request.form.get("titular_palabra_recuperacion", "").strip(),
    }
    ok_profile, msg_profile = _validate_license_holder_profile(holder_profile)
    if not ok_profile:
        flash(msg_profile, "warning")
        return redirect(url_for("main.mi_plan"))

    db.set_config({
        "license_owner_name": holder_profile["nombre"],
        "license_owner_email": holder_profile["email"],
        "license_owner_phone": holder_profile["telefono"],
        "license_recovery_word": holder_profile["palabra_recuperacion"],
    })
    flash("Datos del titular actualizados.", "success")
    return redirect(url_for("main.mi_plan"))


@main_bp.route("/mi-plan/codigo-vendedor", methods=["POST"])
@admin_required
def mi_plan_guardar_codigo_vendedor():
    current_info = db.get_license_info()
    current_vendor_code = _normalize_vendor_code(current_info.get("vendor_code", ""))
    if current_vendor_code:
        flash("Esta licencia ya tiene un código de vendedor asociado.", "info")
        return redirect(url_for("main.mi_plan"))

    vendor_code = _normalize_vendor_code(request.form.get("codigo_vendedor", ""))
    if not vendor_code:
        flash("Ingresá un código de vendedor válido.", "warning")
        return redirect(url_for("main.mi_plan"))

    db.set_config({"license_vendor_code": vendor_code})

    license_key = str(current_info.get("key", "") or "").strip()
    if not license_key:
        flash(
            "Código de vendedor guardado en esta instalación. Esta DEMO no tiene una licencia remota activa para sincronizar todavía.",
            "info",
        )
        return redirect(url_for("main.mi_plan"))

    ok, message, _remote_license = update_license_vendor_code(
        license_key=license_key,
        vendor_code=vendor_code,
        producto=get_license_product(),
    )
    if ok:
        flash("Código de vendedor guardado y sincronizado con la licencia actual.", "success")
    else:
        flash(
            f"Se guardó el código de vendedor localmente, pero no pudimos sincronizarlo con Supabase. {message}",
            "warning",
        )
    return redirect(url_for("main.mi_plan"))


@main_bp.route("/mi-plan/checkout", methods=["POST"])
@admin_required
def mi_plan_checkout():
    init_point, _checkout_context, error_response = _create_checkout_init_point()
    if error_response:
        return error_response

    return jsonify({
        "ok": True,
        "init_point": init_point,
    })


@main_bp.route("/mi-plan/checkout/open", methods=["POST"])
@admin_required
def mi_plan_checkout_open():
    init_point, checkout_context, error_response = _create_checkout_init_point()
    if error_response:
        return error_response

    assert init_point is not None
    assert checkout_context is not None

    try:
        opened = webbrowser.open(init_point)
    except Exception:
        logger.exception(
            "Checkout Mercado Pago no pudo abrir navegador externo licencia=%s plan_destino=%s",
            _mask_license_key(str(checkout_context["license_key"])),
            checkout_context["plan_destino"],
        )
        return jsonify({
            "ok": False,
            "message": "No se pudo abrir Mercado Pago en el navegador externo.",
        }), 500

    if not opened:
        logger.warning(
            "Checkout Mercado Pago navegador externo no confirmado licencia=%s plan_destino=%s",
            _mask_license_key(str(checkout_context["license_key"])),
            checkout_context["plan_destino"],
        )

    logger.info(
        "Checkout Mercado Pago abierto en navegador externo licencia=%s plan_destino=%s",
        _mask_license_key(str(checkout_context["license_key"])),
        checkout_context["plan_destino"],
    )
    return jsonify({
        "ok": True,
        "message": "Checkout abierto en navegador externo",
    })


@main_bp.route("/mi-plan/solicitar-upgrade", methods=["POST"])
@admin_required
def mi_plan_solicitar_upgrade():
    license_info = db.get_license_info()
    plan_actions = _get_plan_actions_context(license_info, tiene_checkout=_has_checkout_license(license_info))
    plan_actual = str(plan_actions.get("plan_actual", "DEMO"))
    allowed_targets = list(plan_actions.get("planes_comprables", []))
    plan_solicitado = normalize_plan(
        request.form.get("plan_destino", "") or request.form.get("plan_solicitado", ""),
        default="",
    )

    if plan_solicitado and plan_solicitado not in allowed_targets:
        flash("El cambio de plan solicitado no está disponible para tu licencia actual.", "info")
        return redirect(url_for("main.mi_plan"))

    if not plan_solicitado:
        if allowed_targets:
            plan_solicitado = allowed_targets[0]
        else:
            flash("Tu plan actual ya está completo o no admite actualización.", "info")
            return redirect(url_for("main.mi_plan"))

    license_key = str(license_info.get("key", "") or "").strip()
    tipo_solicitud = "cambio_plan" if license_key else "alta_licencia"

    cfg = db.get_config()
    usuario = session.get("user", {})
    activation_id, machine_details = _get_stable_activation_id()
    payload = {
        "producto": get_license_product(),
        "license_key": license_key,
        "activation_id": activation_id,
        "nombre": _first_non_empty(
            license_info.get("owner_name", ""),
            usuario.get("nombre_completo"),
            usuario.get("username"),
            cfg.get("nombre_negocio", ""),
            "Administrador",
        ),
        "email": _first_non_empty(
            license_info.get("owner_email", ""),
            usuario.get("email"),
            usuario.get("correo"),
            cfg.get("email_contacto", ""),
        ).lower(),
        "whatsapp": _first_non_empty(
            license_info.get("owner_phone", ""),
            usuario.get("whatsapp"),
            usuario.get("telefono"),
            cfg.get("telefono", ""),
        ),
        "tipo_solicitud": tipo_solicitud,
        "origen": "mi_plan",
        "plan_actual": plan_actual,
        "plan_destino": plan_solicitado,
        "plan_solicitado": plan_solicitado,
        "estado": "pendiente",
        "codigo_vendedor": _get_license_holder_profile(license_info).get("codigo_vendedor", ""),
        "machine_details": machine_details,
    }

    if not payload["email"]:
        flash("Completá el email del titular antes de solicitar el upgrade.", "warning")
        return redirect(url_for("main.mi_plan"))

    logger.info(
        "Solicitud manual de licencia tipo=%s plan_actual=%s plan_destino=%s licencia=%s activation_id=%s",
        tipo_solicitud,
        plan_actual,
        plan_solicitado,
        _mask_license_key(license_key),
        activation_id[:12],
    )
    result = create_upgrade_request(payload)
    if result.get("ok"):
        flash(
            "Solicitud de cambio de plan enviada." if tipo_solicitud == "cambio_plan" else "Solicitud de alta de licencia enviada.",
            "success",
        )
    else:
        flash(result.get("message", "No se pudo enviar la solicitud de actualización."), "danger")
    return redirect(url_for("main.mi_plan"))


@main_bp.route("/activacion-inicial", methods=["GET", "POST"])
@login_required
def activacion_inicial():
    license_info = db.get_license_info()
    if _is_initial_activation_completed(license_info):
        if not _as_bool(db.get_config_valor("activation_initial_completed", "1")):
            db.set_config({"activation_initial_completed": "1"})
        return redirect(url_for("dashboard"))

    profile = _get_activation_customer_profile(
        license_info=license_info,
        form_data=request.form.to_dict() if request.method == "POST" else None,
    )
    selected_plan = normalize_plan(
        request.form.get("plan_destino", "")
        or request.form.get("plan", "")
        or db.get_config_valor("activation_initial_plan", ""),
        default="DEMO",
    )

    if request.method == "POST":
        profile["terms_accepted"] = _has_license_agreement_acceptance(request.form)
        ok_profile, msg_profile = _validate_activation_customer_profile(profile)
        if not ok_profile:
            flash(msg_profile, "warning")
        elif selected_plan == "DEMO":
            demo_context = _get_demo_identity_context(profile)
            activation_id = str(demo_context["activation_id"])
            hardware_id = str(demo_context["hardware_id"])
            machine_details = demo_context["machine_details"]
            product_name = str(demo_context["product_name"])
            identity = demo_context["identity"]
            cfg = db.get_config()
            demo_status = _get_initial_demo_status()
            local_confirmed = bool(str(cfg.get("activation_demo_request_key", "") or "").strip())
            if local_confirmed and demo_status.get("vencido"):
                result = DemoEligibilityResult(
                    state=DEMO_EXPIRED,
                    message="Tu periodo de prueba finalizo. Elegi BASICA, PRO o FULL para continuar usando Nexar Comercio.",
                )
                _persist_demo_eligibility_state(result)
                flash(
                    "Tu periodo de prueba finalizo. Elegi BASICA, PRO o FULL para continuar usando Nexar Comercio.",
                    "warning",
                )
                return render_template(
                    "activacion_inicial.html",
                    customer_profile=profile,
                    selected_plan="BASICA",
                    available_plans=["DEMO", "BASICA", "PRO", "FULL"],
                    license_info=license_info,
                    plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
                    demo_status=demo_status,
                    checkout_pending=_get_checkout_pending_context(),
                    demo_access=_get_initial_demo_access_context(),
                )
            if local_confirmed and demo_status.get("demo") and not demo_status.get("vencido"):
                _persist_activation_customer_profile(profile, completed=True, selected_plan=selected_plan)
                flash("DEMO activada correctamente por 14 días. Ya podés usar el sistema.", "success")
                return redirect(url_for("dashboard"))

            ok_lookup, msg_lookup, demo_records = find_demo_requests_for_identity(
                producto=product_name,
                activation_id=activation_id,
                hardware_id=hardware_id,
                machine_id=getattr(identity, "machine_id", ""),
                email=profile["email"],
            )
            if not ok_lookup:
                result = DemoEligibilityResult(
                    state=DEMO_OFFLINE_UNVERIFIED,
                    message="Necesitamos conexión a Internet para comprobar la disponibilidad de la prueba gratuita.",
                )
                _persist_activation_customer_profile(profile, completed=False, selected_plan=selected_plan)
                _persist_unverified_demo_without_permissions(result)
                logger.warning(
                    "No se pudo verificar DEMO previa producto=%s activation_id=%s detalle=%s",
                    product_name,
                    mask_identifier(activation_id),
                    msg_lookup,
                )
                flash(result.message, "warning")
                return render_template(
                    "activacion_inicial.html",
                    customer_profile=profile,
                    selected_plan="DEMO",
                    available_plans=["DEMO", "BASICA", "PRO", "FULL"],
                    license_info=license_info,
                    plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
                    demo_status=_get_initial_demo_status(),
                    checkout_pending=_get_checkout_pending_context(),
                    demo_access=_get_initial_demo_access_context(),
                )

            result = resolve_demo_eligibility_from_records(identity=identity, records=demo_records)
            _persist_demo_eligibility_state(result)
            if result.state == DEMO_ACTIVE and result.can_recover_demo:
                _recover_remote_demo(profile, result, activation_id, product_name)
                flash("Encontramos una DEMO vigente para este equipo. Ya podés continuar.", "success")
                return redirect(url_for("dashboard"))
            if result.state != DEMO_ELIGIBLE:
                _persist_activation_customer_profile(profile, completed=False, selected_plan=selected_plan)
                _persist_unverified_demo_without_permissions(result)
                flash(result.message, "warning")
                return render_template(
                    "activacion_inicial.html",
                    customer_profile=profile,
                    selected_plan="BASICA",
                    available_plans=["DEMO", "BASICA", "PRO", "FULL"],
                    license_info=license_info,
                    plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
                    demo_status=_get_initial_demo_status(),
                    checkout_pending=_get_checkout_pending_context(),
                    demo_access=_get_initial_demo_access_context(),
                )

            started_on = date.today()
            expires_on = started_on + timedelta(days=14)
            remote_demo_dedupe_key = _demo_dedupe_key(activation_id, profile["email"], product_name)
            demo_metadata = build_demo_metadata(
                identity=identity,
                machine_details=machine_details,
                base_metadata={
                    "plan": "DEMO",
                    "plan_interes": "DEMO_14_DIAS",
                    "rubro": profile["rubro"],
                    "codigo_vendedor": profile["codigo_vendedor"],
                    "terms_accepted": bool(profile["terms_accepted"]),
                    "marketing_opt_in": bool(profile["marketing_opt_in"]),
                    "demo_started_at": started_on.isoformat(),
                    "demo_expires_at": expires_on.isoformat(),
                    "demo_status": "demo_activa",
                },
            )
            ok_demo, msg_demo = create_demo_request(
                nombre=profile["titular_nombre"],
                email=profile["email"],
                telefono=profile["telefono"],
                negocio=profile["negocio"],
                producto=product_name,
                plan_interes="DEMO_14_DIAS",
                mensaje=json.dumps(demo_metadata, ensure_ascii=False),
                origen="app_activacion_inicial",
                estado="pendiente",
            )
            if ok_demo:
                db.set_config({
                    "demo_mode": "1",
                    "demo_install_date": started_on.isoformat(),
                    "demo_dias": "14",
                    "demo_expires_at": expires_on.isoformat(),
                    "license_tier": "DEMO",
                    "license_plan": "DEMO",
                    "activation_demo_request_key": remote_demo_dedupe_key,
                    "activation_demo_request_sent_at": datetime.now().isoformat(),
                    "activation_demo_eligibility_state": DEMO_ACTIVE,
                })
                _persist_activation_customer_profile(profile, completed=True, selected_plan=selected_plan)
                flash("DEMO activada correctamente por 14 días. Ya podés usar el sistema.", "success")
                return redirect(url_for("dashboard"))

            retry_lookup_ok, _retry_msg, retry_records = find_demo_requests_for_identity(
                producto=product_name,
                activation_id=activation_id,
                hardware_id=hardware_id,
                machine_id=getattr(identity, "machine_id", ""),
                email=profile["email"],
            )
            if retry_lookup_ok:
                retry_result = resolve_demo_eligibility_from_records(identity=identity, records=retry_records)
                _persist_demo_eligibility_state(retry_result)
                if retry_result.state == DEMO_ACTIVE and retry_result.can_recover_demo:
                    _recover_remote_demo(profile, retry_result, activation_id, product_name)
                    flash("Tu prueba gratuita fue activada correctamente.", "success")
                    return redirect(url_for("dashboard"))
                if retry_result.state != DEMO_ELIGIBLE:
                    _persist_activation_customer_profile(profile, completed=False, selected_plan=selected_plan)
                    _persist_unverified_demo_without_permissions(retry_result)
                    flash(retry_result.message, "warning")
                    return render_template(
                        "activacion_inicial.html",
                        customer_profile=profile,
                        selected_plan="BASICA",
                        available_plans=["DEMO", "BASICA", "PRO", "FULL"],
                        license_info=license_info,
                        plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
                        demo_status=_get_initial_demo_status(),
                        checkout_pending=_get_checkout_pending_context(),
                        demo_access=_get_initial_demo_access_context(),
                    )

            result = DemoEligibilityResult(
                state=DEMO_OFFLINE_UNVERIFIED,
                message="No pudimos verificar si este equipo ya utilizó la prueba gratuita. Conectate a Internet para iniciar la DEMO o elegí un plan pago.",
            )
            _persist_activation_customer_profile(profile, completed=False, selected_plan=selected_plan)
            _persist_unverified_demo_without_permissions(result)
            logger.warning(
                "No se pudo registrar DEMO inicial producto=%s activation_id=%s detalle=%s",
                product_name,
                mask_identifier(activation_id),
                msg_demo,
            )
            flash(result.message, "warning")
            return render_template(
                "activacion_inicial.html",
                customer_profile=profile,
                selected_plan="DEMO",
                available_plans=["DEMO", "BASICA", "PRO", "FULL"],
                license_info=license_info,
                plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
                demo_status=_get_initial_demo_status(),
                checkout_pending=_get_checkout_pending_context(),
                demo_access=_get_initial_demo_access_context(),
            )
        else:
            _persist_activation_customer_profile(profile, completed=False, selected_plan=selected_plan)
            init_point, _checkout_context, error_response = _create_checkout_init_point()
            if error_response:
                response, _status_code = error_response
                payload = response.get_json(silent=True) or {}
                flash(payload.get("message") or "No se pudo iniciar el checkout en este momento.", "danger")
            elif init_point:
                try:
                    opened = webbrowser.open(init_point)
                except Exception:
                    logger.exception("No se pudo abrir el checkout inicial en navegador externo")
                    opened = False
                if opened:
                    flash(
                        "Abrimos Mercado Pago en tu navegador. Cuando termines el pago, refrescá la licencia para completar la activación.",
                        "info",
                    )
                    return redirect(url_for("main.activacion_inicial"))
                return redirect(init_point)

    return render_template(
        "activacion_inicial.html",
        customer_profile=profile,
        selected_plan=selected_plan,
        available_plans=["DEMO", "BASICA", "PRO", "FULL"],
        license_info=license_info,
        plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
        demo_status=_get_initial_demo_status(),
        checkout_pending=_get_checkout_pending_context(),
        demo_access=_get_initial_demo_access_context(),
    )


@main_bp.route("/config/categoria", methods=["POST"])
@admin_required
def config_categoria():
    try:
        db.add_categoria(request.form.get("nombre", "").strip())
        flash("Categoría guardada correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("config"))


@main_bp.route("/config/categoria/editar", methods=["POST"])
@admin_required
def config_categoria_editar():
    try:
        db.update_categoria(
            request.form.get("nombre_actual", ""),
            request.form.get("nuevo_nombre", ""),
            request.form.get("categoria_id", ""),
        )
        flash("Categoría actualizada correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("config"))


@main_bp.route("/config/categoria/toggle", methods=["POST"])
@admin_required
def config_categoria_toggle():
    nombre = request.form.get("nombre", "")
    activa = _as_bool(request.form.get("activa", "1"))
    try:
        db.set_categoria_activa(nombre, activa)
        flash(
            "Categoría activada correctamente." if activa else "Categoría desactivada correctamente.",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("config"))


@main_bp.route("/config/categoria/eliminar", methods=["POST"])
@admin_required
def config_categoria_eliminar():
    try:
        db.delete_categoria(request.form.get("nombre", ""))
        flash("Categoría desactivada correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("config"))


@main_bp.route("/config/gasto-categoria", methods=["POST"])
@admin_required
def config_gasto_categoria():
    try:
        db.add_gasto_categoria(request.form.get("nombre", ""), request.form.get("tipo", "Necesario"))
        flash("Categoría de gasto guardada correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("config"))


@main_bp.route("/config/gasto-categoria/eliminar", methods=["POST"])
@admin_required
def config_gasto_categoria_eliminar():
    db.delete_gasto_categoria(request.form.get("nombre", ""))
    return redirect(url_for("config"))


@main_bp.route("/config/gasto-categoria/editar", methods=["POST"])
@admin_required
def config_gasto_categoria_editar():
    try:
        db.update_gasto_categoria(
            request.form.get("nombre_actual", ""),
            request.form.get("nuevo_nombre", ""),
            request.form.get("tipo", "Necesario"),
        )
        flash("Categoría de gasto actualizada correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("config"))


@main_bp.route("/licencia")
@admin_required
def licencia():
    machine_id, machine_details = generate_activation_id(session.get("user", {}).get("username", ""))
    local_lic = cargar_licencia() or {}
    license_info = db.get_license_info()
    demo_status = db.get_demo_status()
    license_status = _get_license_status_context(license_info, demo_status=demo_status)
    requires_initial_acceptance = _requires_initial_license_acceptance(license_info)
    return render_template(
        "licencia.html",
        supabase_ok=supabase_configured(),
        machine_id=machine_id,
        device_hwid=get_current_hwid(),
        machine_details=machine_details,
        producto=get_license_product(),
        license_key_local=local_lic.get("license_key", ""),
        license_info=license_info,
        license_status=license_status,
        demo_status=demo_status,
        plan_display=get_plan_display_name(license_info.get("tier", "DEMO")),
        plan_actions=_get_plan_actions_context(license_info, license_status=license_status),
        plan_request_options=get_commercial_plan_options(),
        license_holder=_get_license_holder_profile(license_info),
        requires_initial_license_acceptance=requires_initial_acceptance,
        checkout_pending=_get_checkout_pending_context(),
    )


@main_bp.route("/licencia/activar", methods=["POST"])
@admin_required
def licencia_activar():
    if _requires_initial_license_acceptance():
        ok, msg = _validate_license_agreement_acceptance(request.form)
        if not ok:
            flash(msg, "warning")
            return redirect(url_for("licencia"))
    vendor_code = _normalize_vendor_code(
        request.form.get("codigo_vendedor", "") or _get_license_holder_profile().get("codigo_vendedor", "")
    )
    if vendor_code:
        db.set_config({"license_vendor_code": vendor_code})
    license_key = request.form.get("license_key", "")
    ok, msg = validate_license_key(request.form.get("license_key", ""), debug=False, vendor_code=vendor_code)
    if ok:
        guardar_licencia(license_key, db.get_license_info())
        flash(f"✅ {msg} La licencia quedó vinculada a este equipo.", "success")
    else:
        flash(f"❌ {msg}", "danger")
    return redirect(url_for("licencia"))


@main_bp.route("/licencia/solicitar", methods=["POST"])
@admin_required
def licencia_solicitar():
    if _requires_initial_license_acceptance():
        ok, msg = _validate_license_agreement_acceptance(request.form)
        if not ok:
            flash(msg, "warning")
            return redirect(url_for("licencia"))
    machine_id, machine_details = generate_activation_id(session.get("user", {}).get("username", ""))
    activation_id = request.form.get("activation_id") or get_current_hwid() or machine_id
    holder_profile = {
        "nombre": request.form.get("nombre", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "telefono": request.form.get("whatsapp", "").strip(),
        "codigo_vendedor": _normalize_vendor_code(
            request.form.get("codigo_vendedor", "") or _get_license_holder_profile().get("codigo_vendedor", "")
        ),
        "palabra_recuperacion": _get_license_holder_profile().get("palabra_recuperacion", ""),
    }
    ok_profile, msg_profile = _validate_license_holder_profile(holder_profile)
    if not ok_profile:
        flash(msg_profile, "warning")
        return redirect(url_for("licencia"))

    db.set_config({
        "license_owner_name": holder_profile["nombre"],
        "license_owner_email": holder_profile["email"],
        "license_owner_phone": holder_profile["telefono"],
        "license_vendor_code": holder_profile["codigo_vendedor"],
    })

    ok, msg, _ = create_license_request(
        nombre=holder_profile["nombre"],
        email=holder_profile["email"],
        whatsapp=holder_profile["telefono"],
        codigo_vendedor=holder_profile["codigo_vendedor"],
        activation_id=activation_id,
        producto=get_license_product(),
        plan=request.form.get("plan", "BASICA"),
        machine_details=machine_details,
    )
    flash(f"Solicitud enviada: {msg}" if ok else msg, "success" if ok else "danger")
    return redirect(url_for("licencia"))


@main_bp.route("/usuarios")
@admin_required
def usuarios():
    require_modulo("multiusuario")
    return render_template("usuarios.html", usuarios=db.get_usuarios())


@main_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@admin_required
def usuario_nuevo():
    require_modulo("multiusuario")
    if request.method == "POST":
        ok, msg = _validate_password_confirmation(
            request.form.get("password", ""),
            request.form.get("password_confirm", ""),
        )
        if not ok:
            flash(f"❌ {msg}", "danger")
        else:
            db.add_usuario(request.form.get("username", ""), request.form.get("password", ""), request.form.get("rol", "Vendedor"), request.form.get("nombre_completo", ""))
            nuevo_usuario = db.get_usuario_by_username(request.form.get("username", ""))
            _auditar_accion(
                "ALTA_USUARIO",
                "usuario",
                int(nuevo_usuario["id"] or 0) if nuevo_usuario else 0,
                detalle=f"{request.form.get('username', '').strip()} ({request.form.get('rol', 'Vendedor').strip()})",
            )
            return redirect(url_for("usuarios"))
    return render_template("usuario_form.html", usuario=None, roles=db.get_roles(), accion="Nuevo")


@main_bp.route("/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@admin_required
def usuario_editar(uid):
    require_modulo("multiusuario")
    usuario = db.q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)
    if not usuario:
        flash("❌ Usuario inexistente.", "danger")
        return redirect(url_for("usuarios"))
    if request.method == "POST":
        activo = 1 if _as_bool(request.form.get("activo")) else 0
        nuevo_rol = request.form.get("rol", usuario["rol"])
        if not activo and uid == session["user"]["id"]:
            flash("⚠️ No podés desactivar tu propio usuario.", "warning")
            return redirect(url_for("usuarios"))
        if not activo and usuario["rol"] in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
            flash("⚠️ No podés desactivar el último administrador activo.", "warning")
            return redirect(url_for("usuarios"))
        if usuario["rol"] in {"Administrador", "admin"} and nuevo_rol not in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
            flash("⚠️ No podés quitar el rol al último administrador activo.", "warning")
            return redirect(url_for("usuarios"))
        db.update_usuario(uid, {"rol": nuevo_rol, "nombre_completo": request.form.get("nombre_completo", usuario["nombre_completo"]), "activo": activo})
        _auditar_accion(
            "EDICION_USUARIO",
            "usuario",
            uid,
            detalle=f"{usuario['username']} -> rol {nuevo_rol} · activo {activo}",
        )
        return redirect(url_for("usuarios"))
    return render_template("usuario_form.html", usuario=usuario, roles=db.get_roles(), accion="Editar")


@main_bp.route("/usuarios/<int:uid>/toggle-activo", methods=["POST"])
@admin_required
def usuario_toggle_activo(uid):
    require_modulo("multiusuario")
    user = db.q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)
    if not user:
        flash("❌ Usuario inexistente.", "danger")
        return redirect(url_for("usuarios"))
    if uid == session["user"]["id"]:
        flash("⚠️ No podés cambiar el estado de tu propio usuario.", "warning")
        return redirect(url_for("usuarios"))

    nuevo_estado = 0 if int(user["activo"] or 0) else 1
    if nuevo_estado == 0 and user["rol"] in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
        flash("⚠️ No podés desactivar el último administrador activo.", "warning")
        return redirect(url_for("usuarios"))

    db.set_usuario_activo(uid, nuevo_estado)
    _auditar_accion(
        "CAMBIO_ESTADO_USUARIO",
        "usuario",
        uid,
        detalle=f"{user['username']} -> {'activo' if nuevo_estado else 'inactivo'}",
    )
    flash("✅ Usuario activado." if nuevo_estado else "✅ Usuario desactivado.", "success")
    return redirect(url_for("usuarios"))


@main_bp.route("/usuarios/<int:uid>/eliminar", methods=["POST"])
@admin_required
def usuario_eliminar(uid):
    require_modulo("multiusuario")
    user = db.q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)
    if not user:
        flash("❌ Usuario inexistente.", "danger")
        return redirect(url_for("usuarios"))
    if uid == session["user"]["id"]:
        flash("⚠️ No podés eliminar tu propio usuario.", "warning")
        return redirect(url_for("usuarios"))
    if user["rol"] in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
        flash("⚠️ No podés eliminar el último administrador activo.", "warning")
        return redirect(url_for("usuarios"))
    _auditar_accion(
        "ELIMINACION_USUARIO",
        "usuario",
        uid,
        detalle=f"{user['username']} ({user['rol']})",
    )
    db.delete_usuario(uid)
    flash("✅ Usuario eliminado definitivamente.", "success")
    return redirect(url_for("usuarios"))


@main_bp.route("/respaldo")
@admin_required
def respaldo():
    license_info = db.get_license_info()
    license_key = str(license_info.get("key", "") or "").strip()
    if not license_key:
        flash("No se encontró una licencia activa para enviar el cambio de plan.", "warning")
        return redirect(url_for("main.mi_plan"))

    cfg = db.get_config()
    license_info = db.get_license_info()
    update_access = get_update_access_context(license_info)
    can_use_updates = update_access["puede_actualizar"]
    update_state = _update_install_state(current_app.config.get("APP_VERSION", "0.0.0"))
    update_info = (
        get_cached_update_info(current_app, current_app.config.get("APP_VERSION", "0.0.0"))
        if can_use_updates and update_state.get("status") not in {"in_progress", "ready_restart"}
        else {"available": False, "restricted": True}
    )
    return render_template(
        "respaldo.html",
        archivos=_backup_list(),
        actualizaciones=_update_list() if can_use_updates else [],
        update_info=update_info,
        update_state=update_state,
        can_use_updates=can_use_updates,
        update_access=update_access,
        ultimo=cfg.get("backup_ultimo", "Nunca"),
        intervalo=cfg.get("backup_intervalo_h", "24"),
        keep=cfg.get("backup_keep", "10"),
    )


@main_bp.route("/respaldo/ahora", methods=["POST"])
@admin_required
def respaldo_ahora():
    _make_backup()
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/config", methods=["POST"])
@admin_required
def respaldo_config():
    db.set_config({"backup_intervalo_h": request.form.get("backup_intervalo_h", "24"), "backup_keep": request.form.get("backup_keep", "10")})
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/descargar/<nombre>")
@admin_required
def respaldo_descargar(nombre):
    return send_file(_backup_file(nombre), as_attachment=True)


@main_bp.route("/respaldo/restaurar/<nombre>", methods=["POST"])
@admin_required
def respaldo_restaurar(nombre):
    source = _backup_file(nombre)
    if not _is_sqlite_database(source):
        abort(400)
    _make_backup()
    shutil.copy2(source, db.DB_PATH)
    try:
        if os.name != "nt":
            Path(db.DB_PATH).chmod(0o600)
    except Exception:
        pass
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/descargar", methods=["POST"])
@admin_required
def actualizacion_descargar():
    license_info = db.get_license_info()
    update_access = get_update_access_context(license_info)
    if not update_access["puede_actualizar"]:
        flash(update_access["mensaje"], "warning")
        return redirect(url_for("respaldo"))

    update_info = get_cached_update_info(current_app, current_app.config.get("APP_VERSION", "0.0.0"))
    if not update_info.get("available"):
        flash("No hay una actualizacion nueva disponible.", "info")
        return redirect(url_for("respaldo"))
    if not update_info.get("asset_url"):
        flash("La release existe, pero no tiene instalador compatible para este sistema. Abrila en GitHub.", "warning")
        return redirect(url_for("respaldo"))

    backup_path = _make_backup()
    try:
        target = download_release_asset(update_info["asset_url"], _update_dir())
    except Exception as exc:
        flash(f"No se pudo descargar la actualizacion: {exc}", "danger")
        return redirect(url_for("respaldo"))

    flash(
        f"Actualizacion descargada: {target.name}. Respaldo creado antes de actualizar: {backup_path.name}.",
        "success",
    )
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/abrir-carpeta", methods=["POST"])
@admin_required
def actualizacion_abrir_carpeta():
    opened = open_file_cross_platform(_update_dir())
    flash(opened["message"], "success" if opened.get("ok") else "warning")
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/instalar/<nombre>", methods=["POST"])
@admin_required
def actualizacion_instalar(nombre):
    license_info = db.get_license_info()
    update_access = get_update_access_context(license_info)
    if not update_access["puede_actualizar"]:
        flash(update_access["mensaje"], "warning")
        return redirect(url_for("respaldo"))

    installer = _update_file(nombre)
    target_version = _installer_version(installer.name)
    if not target_version:
        flash("No se pudo identificar la version del instalador.", "warning")
        return redirect(url_for("respaldo"))

    db.set_config({
        "update_install_status": "in_progress",
        "update_target_version": target_version,
        "update_installer_name": installer.name,
        "update_started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "update_finished_at": "",
        "update_installed_at": "",
        "update_install_error": "",
    })

    backup_path = _make_backup()
    is_windows_installer = installer.suffix.lower() == ".exe"
    command = str(installer) if is_windows_installer else f"sudo apt install /tmp/nexar-tienda-updates/{installer.name}"

    if is_windows_installer:
        try:
            _write_windows_update_status(
                "in_progress",
                target_version=target_version,
                installer_name=installer.name,
            )
            _launch_windows_update_helper(installer=installer, target_version=target_version)
            logger.info(
                "Actualizacion Windows preparada. installer=%s target=%s backup=%s",
                installer,
                target_version,
                backup_path.name,
            )
            return render_template(
                "apagado.html",
                titulo="Cerrando Nexar Comercio para actualizar",
                mensaje="La app se va a cerrar para iniciar el instalador de Windows de forma segura.",
                estado="Esperando que se liberen Flask, pywebview y el ejecutable antes de abrir la actualización.",
                delay_ms=1600,
            )
        except Exception as exc:
            db.set_config({"update_install_status": "install_failed", "update_install_error": str(exc)})
            logger.exception("No se pudo preparar la actualizacion Windows.")
            flash(f"No se pudo iniciar el instalador: {exc}. Ejecuta manualmente: {command}", "warning")
            return redirect(url_for("respaldo"))

    if not sys.platform.startswith("linux"):
        db.set_config({
            "update_install_status": "ready_restart",
            "update_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        flash(f"Respaldo creado ({backup_path.name}). Instala manualmente: {command}", "info")
        return redirect(url_for("respaldo"))

    try:
        apt_installer = _apt_readable_copy(installer)
        process = subprocess.Popen(["pkexec", "apt", "install", "-y", str(apt_installer)])
        _track_update_process(target_version, process)
        flash(
            f"Instalador iniciado con permisos de administrador. Respaldo previo: {backup_path.name}. "
                "Cuando termine, Nexar Comercio te va a pedir reiniciar la app.",
            "success",
        )
    except FileNotFoundError:
        db.set_config({
            "update_install_status": "ready_restart",
            "update_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        flash(f"Respaldo creado ({backup_path.name}). pkexec no esta disponible; ejecuta: {command}", "warning")
    except Exception as exc:
        db.set_config({"update_install_status": "install_failed", "update_install_error": str(exc)})
        flash(f"No se pudo iniciar el instalador: {exc}. Ejecuta: {command}", "warning")
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/estado")
@admin_required
def actualizacion_estado():
    return jsonify(_update_install_state(current_app.config.get("APP_VERSION", "0.0.0")))


@main_bp.route("/respaldo/actualizacion/reiniciar", methods=["POST"])
@admin_required
def actualizacion_reiniciar():
    session.clear()
    installer_name = db.get_config().get("update_installer_name", "")
    if _requires_manual_reopen(installer_name):
        return render_template(
            "apagado.html",
            titulo="Cerrando Nexar Comercio",
            mensaje="La actualizacion ya se instalo. Volve a abrir Nexar Comercio desde el acceso directo.",
            estado="Windows puede tardar unos segundos en liberar el instalador antes del proximo inicio.",
            delay_ms=1200,
        )

    return render_template(
        "apagado.html",
        titulo="Reiniciando Nexar Comercio",
        mensaje="La app se cerrara y volvera a abrirse con la version nueva.",
        estado="Esto puede tardar unos segundos mientras el sistema libera el instalador.",
        delay_ms=5000,
        restart_delay_ms=5000,
    )


@main_bp.route("/respaldo/actualizacion/limpiar-estado", methods=["POST"])
@admin_required
def actualizacion_limpiar_estado():
    db.set_config({
        "update_install_status": "",
        "update_target_version": "",
        "update_installer_name": "",
        "update_started_at": "",
        "update_finished_at": "",
        "update_installed_at": "",
        "update_install_error": "",
    })
    return redirect(url_for("respaldo"))


@main_bp.route("/productos/exportar/excel")
@admin_required
def exportar_excel():
    require_modulo("export")
    rows = db.get_catalogo_export()
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Codigo", "Descripcion", "Categoria", "Precio", "Stock", "Activo"])
        for row in rows:
            ws.append([row["codigo"], row["descripcion"], row["categoria"], row["precio_venta"], row["stock_actual"], row["activo"]])
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name="catalogo_nexar_tienda.xlsx")
    except Exception:
        csv = "codigo,descripcion,categoria,precio,stock,activo\n" + "\n".join(f'{r["codigo"]},"{r["descripcion"]}","{r["categoria"]}",{r["precio_venta"]},{r["stock_actual"]},{r["activo"]}' for r in rows)
        return Response(csv, headers={"Content-Disposition": "attachment; filename=catalogo_nexar_tienda.csv"}, mimetype="text/csv")


@main_bp.route("/productos/exportar/pdf")
@admin_required
def exportar_pdf():
    require_modulo("export")
    rows = db.get_catalogo_export()
    text = "\n".join(f'{r["codigo"]} - {r["descripcion"]} - $ {float(r["precio_venta"] or 0):.2f}' for r in rows)
    return Response(text, headers={"Content-Disposition": "attachment; filename=lista_precios.txt"}, mimetype="text/plain")


@main_bp.route("/ayuda", methods=["GET", "POST"])
@login_required
def ayuda():
    license_info = db.get_license_info()
    license_key = str(license_info.get("key", "") or "").strip()
    if not license_key:
        flash("No se encontró una licencia activa para enviar el cambio de plan.", "warning")
        return redirect(url_for("main.mi_plan"))

    cfg = db.get_config()
    licencia = db.get_license_info()
    usuario = session.get("user", {})
    negocio = cfg.get("nombre_negocio", "Nexar Comercio")
    support_defaults = {
        "nombre": _first_non_empty(
            licencia.get("owner_name", ""),
            usuario.get("nombre_completo"),
            usuario.get("username"),
        ),
        "email": _first_non_empty(
            licencia.get("owner_email", ""),
            cfg.get("email_contacto", ""),
        ),
        "whatsapp": _first_non_empty(
            licencia.get("owner_phone", ""),
            cfg.get("telefono", ""),
        ),
        "motivo": request.args.get("motivo", "consulta"),
        "mensaje": "",
    }

    if request.method == "POST":
        support_defaults.update({
            "nombre": request.form.get("nombre", "").strip(),
            "email": request.form.get("email", "").strip(),
            "whatsapp": request.form.get("whatsapp", "").strip(),
            "motivo": request.form.get("motivo", "consulta").strip(),
            "mensaje": request.form.get("mensaje", "").strip(),
        })
        ok, msg, _ = create_support_request(
            nombre=support_defaults["nombre"],
            email=support_defaults["email"],
            whatsapp=support_defaults["whatsapp"],
            motivo=support_defaults["motivo"],
            mensaje=support_defaults["mensaje"],
            app_version=current_app.config.get("APP_VERSION", "0.0.0"),
            negocio=negocio,
            plan=licencia.get("tier", ""),
            user_name=usuario.get("username", ""),
            technical_details={
                "os": platform.platform(),
                "python": platform.python_version(),
                "host": platform.node(),
                "license_tier": licencia.get("tier", ""),
                "license_plan": licencia.get("plan", ""),
                "updates": licencia.get("updates", False),
            },
        )
        if ok:
            flash("Solicitud de soporte enviada correctamente.", "success")
            return redirect(url_for("ayuda", soporte="enviado"))
        flash(msg, "warning")

    return render_template(
        "ayuda.html",
        supabase_ok=supabase_configured(),
        support_defaults=support_defaults,
        negocio=negocio,
        licencia=licencia,
    )


@main_bp.route("/debug/licencia")
@admin_required
def debug_licencia():
    if not _debug_license_enabled():
        abort(404)

    license_info = db.get_license_info()
    license_key = str(license_info.get("key", "") or "").strip()
    if not license_key:
        flash("No se encontró una licencia activa para enviar el cambio de plan.", "warning")
        return redirect(url_for("main.mi_plan"))

    cfg = db.get_config()
    debug_state = get_license_debug_state()
    modulos_debug = get_modulos_debug_info()
    persisted_modules = []
    try:
        persisted_modules = json.loads(cfg.get("license_modules", "[]") or "[]")
    except Exception:
        persisted_modules = []
    return jsonify({
        "product": get_license_product(),
        "license_mode": os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower(),
        "validation_mode": debug_state.get("validation_mode", ""),
        "plan_display": get_plan_display_name(license_info.get("plan")),
        "plan": license_info.get("plan"),
        "plan_original": license_info.get("plan_original", license_info.get("plan")),
        "plan_efectivo": license_info.get("plan_efectivo", license_info.get("tier")),
        "effective_plan": license_info.get("effective_plan", license_info.get("tier")),
        "plan_normalized": normalize_plan(license_info.get("plan"), default="DEMO"),
        "tier": license_info.get("tier"),
        "tier_normalized": normalize_plan(license_info.get("tier"), default="DEMO"),
        "estado": license_info.get("estado", ""),
        "fallback_aplicado": bool(license_info.get("fallback_aplicado")),
        "plan_base_permanente": bool(license_info.get("plan_base_permanente")),
        "expirada": bool(license_info.get("expirada")),
        "modules_detected": debug_state.get("modules", []),
        "active_modules": sorted(license_info.get("modules", [])),
        "license_modules_persisted": sorted(str(module).strip().lower() for module in persisted_modules if str(module).strip()),
        "resolved_modules": modulos_debug.get("final_modules", []),
        "modules_by_tier_or_plan": modulos_debug.get("tier_modules", []),
        "modules_source": modulos_debug.get("final_source"),
        "supabase": {
            **get_supabase_debug_state(),
        },
        "last_license_error": debug_state.get("last_error", ""),
        "masked_license_key": debug_state.get("masked_license_key", ""),
    })


@main_bp.route("/debug/modulos")
@admin_required
def debug_modulos():
    if not _debug_license_enabled():
        abort(404)
    modulos_debug = get_modulos_debug_info()
    return jsonify({
        "active_modules_final": modulos_debug.get("final_modules", []),
        "modules_by_tier_or_plan": modulos_debug.get("tier_modules", []),
        "persisted_modules": modulos_debug.get("persisted_modules", []),
        "extras_from_env": modulos_debug.get("env_modules", []),
        "sdk_modules": modulos_debug.get("sdk_modules", []),
        "tier": modulos_debug.get("tier", ""),
        "mode": modulos_debug.get("mode", ""),
        "final_source": modulos_debug.get("final_source", "unknown"),
    })


@main_bp.route("/changelog")
@login_required
def changelog():
    content = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else "# Sin changelog"
    try:
        import markdown
        html = markdown.markdown(content, extensions=["extra", "sane_lists"])
    except Exception:
        html = "<pre>" + content + "</pre>"
    return render_template("changelog.html", contenido_html=html)


@main_bp.route("/acuerdo-licencia")
def acuerdo_licencia():
    content = LICENSE_TEXT_PATH.read_text(encoding="utf-8") if LICENSE_TEXT_PATH.exists() else "No se encontró el acuerdo de licencia."
    return render_template("acuerdo_licencia.html", license_content=content)


@main_bp.route("/acerca")
@login_required
def acerca():
    return render_template("acerca.html")


@main_bp.route("/logout")
def logout():
    if "user" in session and _caja_abierta() and not _as_bool(request.args.get("force")):
        flash("Hay una caja abierta. Confirmá explícitamente el cierre de sesión o revisá la caja antes de salir.", "warning")
        return redirect(url_for("dashboard"))
    if "user" in session:
        _auditar_accion(
            "LOGOUT",
            "sesion",
            int(session.get("user", {}).get("id") or 0),
            detalle=f"Cierre de sesion de {session.get('user', {}).get('username', '')}",
        )
    session.clear()
    DESKTOP_STATE["user_logged_in"] = False
    return redirect(url_for("login"))


@main_bp.route("/api/desktop/close-warning")
@login_required
def desktop_close_warning():
    requested = bool(DESKTOP_STATE.get("close_warning_requested"))
    DESKTOP_STATE["close_warning_requested"] = False
    caja_actual = _caja_abierta()
    return jsonify({
        "requested": requested,
        "caja_abierta": bool(caja_actual),
        "fecha_apertura": caja_actual["fecha_apertura"] if caja_actual else "",
        "caja_url": url_for("caja", auto_open="cerrar"),
        "caja_cerrar_y_salir_url": url_for("caja", auto_open="cerrar", next=url_for("main.salida_protegida_cerrar_app")),
        "apagar_url": url_for("apagar_rapido"),
        "logout_url": url_for("logout"),
        "logout_force_url": url_for("logout", force="1"),
    })


@main_bp.route("/salida-protegida/cerrar-app")
@login_required
def salida_protegida_cerrar_app():
    session.clear()
    DESKTOP_STATE["user_logged_in"] = False
    return render_template(
        "apagado.html",
        titulo="Caja cerrada",
        mensaje="La caja se cerró correctamente y la aplicación se cerrará ahora.",
        estado="Cerrando Nexar Comercio de forma segura...",
        delay_ms=900,
    )


@main_bp.route("/apagar-rapido", methods=["POST"])
def apagar_rapido():
    session.clear()
    DESKTOP_STATE["user_logged_in"] = False
    return render_template("apagado.html")


@main_bp.route("/apagar", methods=["POST"])
@admin_required
def apagar_sistema():
    session.clear()
    DESKTOP_STATE["user_logged_in"] = False
    return render_template("apagado.html")


@main_bp.route("/shutdown", methods=["POST"])
def shutdown():
    if not _is_same_origin_local_request():
        abort(403)
    logger.info("Shutdown solicitado desde la interfaz local.")
    fn = request.environ.get("werkzeug.server.shutdown")
    if fn:
        fn()
        return ("", 204)
    current_app.logger.info("Shutdown solicitado, pero no disponible en este servidor.")
    return ("", 202)
