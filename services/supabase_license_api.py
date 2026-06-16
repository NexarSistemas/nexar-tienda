from __future__ import annotations

import getpass
import hashlib
import logging
import os
import platform
from typing import Any

import requests
from licensing.planes import get_plan_actions, normalize_plan

PRODUCTO_DEFAULT = os.getenv("LICENSE_PRODUCT", "nexar-tienda")
logger = logging.getLogger(__name__)
_LAST_SUPABASE_DEBUG: dict[str, Any] = {
    "configured": False,
    "operation": "",
    "status": "",
    "status_code": None,
    "last_error": "",
}
def _clean_base_url(url: str) -> str:
    return url.rstrip("/")


def build_supabase_rest_url(table_name: str) -> str:
    raw_base = (os.getenv("SUPABASE_URL", "") or "").strip()
    table = (table_name or "").strip().strip("/")
    if not raw_base or not table:
        return ""

    base = _clean_base_url(raw_base)
    lower_base = base.lower()
    if lower_base.endswith("/rest/v1"):
        base = _clean_base_url(base[:-8])

    return f"{base}/rest/v1/{table}" if base else ""


def _table_url() -> str:
    return build_supabase_rest_url("licencias")


def _requests_table_url() -> str:
    return build_supabase_rest_url("solicitudes_licencia")


def _support_requests_table_url() -> str:
    return build_supabase_rest_url("solicitudes_soporte")


def _upgrade_requests_table_url() -> str:
    return build_supabase_rest_url("solicitudes_upgrade")


def _anon_key() -> str:
    return os.getenv("SUPABASE_ANON_KEY", "")


def _headers() -> dict[str, str]:
    key = _anon_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and _anon_key())


def _set_supabase_debug(**values: Any) -> None:
    _LAST_SUPABASE_DEBUG.update(values)
    _LAST_SUPABASE_DEBUG["configured"] = is_configured()


def get_supabase_debug_state() -> dict[str, Any]:
    state = dict(_LAST_SUPABASE_DEBUG)
    state["configured"] = is_configured()
    return state


def _request_error_message(operation: str, exc: Exception) -> tuple[str, str | None]:
    if isinstance(exc, requests.Timeout):
        logger.warning("Timeout en Supabase durante %s", operation)
        return "No se pudo conectar con Supabase a tiempo.", "timeout"
    if isinstance(exc, requests.ConnectionError):
        logger.warning("Conexion caida en Supabase durante %s", operation)
        return "No se pudo conectar con Supabase.", "connection_error"
    logger.warning("Error de red en Supabase durante %s: %s", operation, exc)
    return "No se pudo completar la operacion con Supabase.", exc.__class__.__name__


def _response_error_message(operation: str, response: requests.Response) -> tuple[str, str]:
    status_code = response.status_code
    body = (response.text or "").strip().replace("\n", " ")[:240]
    if status_code in {401, 403}:
        logger.warning("Supabase rechazo %s con status=%s", operation, status_code)
        return "Supabase rechazó la operación por permisos o autenticación.", "auth_or_rls"
    logger.warning("Supabase devolvio error en %s status=%s", operation, status_code)
    return f"Error en Supabase ({status_code}). {body}".strip(), "http_error"


def _log_supabase_http_error(operation: str, url: str, response: requests.Response) -> None:
    logger.warning(
        "Supabase error en %s status=%s url=%s body=%s",
        operation,
        response.status_code,
        url,
        (response.text or "").strip()[:500],
    )


def build_machine_id(raw: str) -> str:
    value = (raw or "").strip().lower()
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_")[:120]


def _normalize_vendor_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _read_first(paths: list[str]) -> str:
    for path in paths:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    data = fh.read().strip()
                    if data:
                        return data
        except Exception:
            continue
    return ""


def generate_activation_id(user_hint: str = "") -> tuple[str, dict[str, str]]:
    """
    Genera un ID de activacion estable para enviar al desarrollador.
    Usa datos locales de la maquina y devuelve (id, detalles).
    """
    username = user_hint or getpass.getuser() or os.getenv("USERNAME", "") or os.getenv("USER", "")
    host = platform.node()
    machine_id = _read_first(["/etc/machine-id", "/var/lib/dbus/machine-id"])
    product_uuid = _read_first(["/sys/class/dmi/id/product_uuid"])
    disk_hint = os.path.abspath(os.sep)
    try:
        disk_hint = str(os.stat(disk_hint).st_dev)
    except Exception:
        pass

    raw = "|".join([username, host, machine_id, product_uuid, disk_hint])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    activation_id = f"NXID-{digest[:24]}"
    details = {
        "username": username,
        "host": host,
        "machine_id": machine_id or "(sin machine-id)",
        "disk_hint": disk_hint,
    }
    return activation_id, details


def create_license_request(
    *,
    nombre: str,
    email: str,
    whatsapp: str = "",
    codigo_vendedor: str = "",
    activation_id: str,
    producto: str = PRODUCTO_DEFAULT,
    plan: str = "BASICA",
    machine_details: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    operation = "create_license_request"
    if not is_configured():
        _set_supabase_debug(
            operation=operation,
            status="not_configured",
            status_code=None,
            last_error="not_configured",
            url=_requests_table_url(),
        )
        return False, "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY para enviar solicitudes.", None

    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()
    whatsapp = (whatsapp or "").strip()
    codigo_vendedor = _normalize_vendor_code(codigo_vendedor)
    activation_id = build_machine_id(activation_id)
    plan = normalize_plan(plan, default="BASICA")

    if not nombre or not email or not activation_id:
        return False, "Nombre, email e ID del equipo son obligatorios.", None

    payload = {
        "producto": producto,
        "activation_id": activation_id,
        "nombre": nombre,
        "email": email,
        "whatsapp": whatsapp,
        "plan": plan,
        "estado": "pendiente",
        "machine_details": machine_details or {},
    }
    if codigo_vendedor:
        payload["codigo_vendedor"] = codigo_vendedor
    headers = {**_headers(), "Prefer": "return=minimal"}
    request_url = _requests_table_url()
    try:
        resp = requests.post(request_url, headers=headers, json=payload, timeout=12)
    except requests.RequestException as exc:
        logger.warning("Error de conexion enviando solicitud de licencia a url=%s: %s", request_url, exc)
        _set_supabase_debug(
            operation=operation,
            status="network_error",
            status_code=None,
            last_error=exc.__class__.__name__,
            url=request_url,
        )
        return False, "No se pudo enviar la solicitud. Revisá la conexión o intentá nuevamente.", None
    if resp.status_code >= 300:
        _log_supabase_http_error(operation, request_url, resp)
        _set_supabase_debug(
            operation=operation,
            status="http_error",
            status_code=resp.status_code,
            last_error=(resp.text or "").strip()[:240],
            url=request_url,
        )
        return False, "No se pudo enviar la solicitud. Revisá la conexión o intentá nuevamente.", None

    _set_supabase_debug(
        operation=operation,
        status="ok",
        status_code=resp.status_code,
        last_error="",
        url=request_url,
    )
    return True, "Solicitud enviada correctamente. El administrador debe aprobarla.", None


def create_support_request(
    *,
    nombre: str,
    email: str,
    mensaje: str,
    whatsapp: str = "",
    motivo: str = "consulta",
    producto: str = PRODUCTO_DEFAULT,
    app_version: str = "",
    negocio: str = "",
    plan: str = "",
    user_name: str = "",
    technical_details: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_configured():
        return False, "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY para enviar solicitudes de soporte.", None

    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()
    whatsapp = (whatsapp or "").strip()
    motivo = (motivo or "consulta").strip().lower()
    mensaje = (mensaje or "").strip()

    motivos_validos = {"consulta", "error", "licencia", "actualizacion", "respaldo", "otro"}
    if motivo not in motivos_validos:
        motivo = "consulta"

    if not nombre or not email or not mensaje:
        return False, "Nombre, email y mensaje son obligatorios.", None

    payload = {
        "producto": producto,
        "app_version": app_version,
        "negocio": negocio,
        "nombre": nombre,
        "email": email,
        "whatsapp": whatsapp,
        "motivo": motivo,
        "mensaje": mensaje,
        "plan": plan,
        "user_name": user_name,
        "estado": "pendiente",
        "technical_details": technical_details or {},
    }
    headers = {**_headers(), "Prefer": "return=minimal"}
    try:
        resp = requests.post(_support_requests_table_url(), headers=headers, json=payload, timeout=12)
    except requests.RequestException as exc:
        logger.warning("Error de conexion enviando solicitud de soporte: %s", exc)
        return False, "No se pudo conectar con Supabase para enviar la solicitud de soporte.", None
    if resp.status_code >= 300:
        return False, f"Error al registrar solicitud de soporte ({resp.status_code}): {resp.text[:240]}", None

    return True, "Solicitud de soporte enviada correctamente.", None


def create_upgrade_request(data: dict[str, Any]) -> dict[str, Any]:
    operation = "create_upgrade_request"
    if not is_configured():
        _set_supabase_debug(operation=operation, status="not_configured", status_code=None, last_error="not_configured")
        return {
            "ok": False,
            "message": "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY para enviar solicitudes.",
            "error": "not_configured",
        }

    payload = dict(data or {})
    payload["producto"] = str(payload.get("producto") or PRODUCTO_DEFAULT).strip() or PRODUCTO_DEFAULT
    payload["license_key"] = str(payload.get("license_key") or "").strip()
    payload["activation_id"] = build_machine_id(payload.get("activation_id") or "")
    payload["nombre"] = str(payload.get("nombre") or "").strip() or "Administrador"
    payload["email"] = str(payload.get("email") or "").strip().lower()
    payload["whatsapp"] = str(payload.get("whatsapp") or "").strip()
    payload["tipo_solicitud"] = str(payload.get("tipo_solicitud") or "").strip().lower()
    payload["origen"] = str(payload.get("origen") or "").strip().lower()
    payload["plan_actual"] = normalize_plan(payload.get("plan_actual") or "", default="BASICA")
    payload["plan_destino"] = normalize_plan(
        payload.get("plan_destino") or payload.get("plan_solicitado") or "",
        default="BASICA",
    )
    payload["plan_solicitado"] = payload["plan_destino"]
    payload["codigo_vendedor"] = _normalize_vendor_code(payload.get("codigo_vendedor") or "")
    payload["estado"] = "pendiente"
    payload["machine_details"] = dict(payload.get("machine_details") or {})
    payload["machine_details"]["request_context"] = {
        "tipo_solicitud": payload["tipo_solicitud"] or "upgrade",
        "origen": payload["origen"] or "desconocido",
        "plan_actual": payload["plan_actual"],
        "plan_destino": payload["plan_destino"],
    }
    commercial_actions = get_plan_actions(payload["plan_actual"], tiene_checkout=True)
    allowed_targets = set(commercial_actions.get("planes_comprables", []))

    if not payload["producto"] or not payload["plan_actual"] or not payload["plan_solicitado"]:
        _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="missing_required_fields")
        return {
            "ok": False,
            "message": "La solicitud de actualización no tiene los datos mínimos requeridos.",
            "error": "missing_required_fields",
        }

    if not payload["codigo_vendedor"]:
        payload.pop("codigo_vendedor", None)

    if payload["tipo_solicitud"] == "cambio_plan":
        if payload["plan_actual"] == "FULL":
            _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="invalid_current_plan")
            return {
                "ok": False,
                "message": "El plan actual no admite solicitudes de cambio.",
                "error": "invalid_current_plan",
            }
        if payload["plan_destino"] not in allowed_targets:
            _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="invalid_target_plan")
            return {
                "ok": False,
                "message": "El cambio de plan solicitado no es vÃ¡lido para la licencia actual.",
                "error": "invalid_target_plan",
            }
        if not payload["license_key"]:
            _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="missing_license_key")
            return {
                "ok": False,
                "message": "La solicitud de cambio requiere una licencia existente.",
                "error": "missing_license_key",
            }

        headers = {**_headers(), "Prefer": "return=minimal"}
        try:
            resp = requests.post(_upgrade_requests_table_url(), headers=headers, json=payload, timeout=12)
        except requests.RequestException as exc:
            message, error = _request_error_message(operation, exc)
            _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
            return {"ok": False, "message": message, "error": error or "network_error"}

        if resp.status_code >= 300 and any(payload.get(field) for field in ("tipo_solicitud", "origen", "plan_destino")):
            fallback_payload = dict(payload)
            fallback_payload.pop("tipo_solicitud", None)
            fallback_payload.pop("origen", None)
            fallback_payload.pop("plan_destino", None)
            try:
                resp = requests.post(_upgrade_requests_table_url(), headers=headers, json=fallback_payload, timeout=12)
            except requests.RequestException as exc:
                message, error = _request_error_message(operation, exc)
                _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
                return {"ok": False, "message": message, "error": error or "network_error"}

        if resp.status_code >= 300:
            message, error = _response_error_message(operation, resp)
            _set_supabase_debug(operation=operation, status="http_error", status_code=resp.status_code, last_error=error)
            return {"ok": False, "message": message, "status_code": resp.status_code, "error": error}

        _set_supabase_debug(operation=operation, status="ok", status_code=resp.status_code, last_error="")
        return {"ok": True, "message": "Solicitud de cambio de plan enviada.", "status_code": resp.status_code}

    if not allowed_targets:
        _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="invalid_current_plan")
        return {
            "ok": False,
            "message": "El plan actual no admite solicitudes de actualización.",
            "error": "invalid_current_plan",
        }

    if payload["plan_solicitado"] not in allowed_targets:
        _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="invalid_target_plan")
        return {
            "ok": False,
            "message": "La actualización solicitada no es válida para el plan actual.",
            "error": "invalid_target_plan",
        }

    if not payload["activation_id"] and not payload["license_key"]:
        _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="missing_activation_id_and_license_key")
        return {
            "ok": False,
            "message": "La solicitud requiere al menos un ID de equipo o una licencia asociada.",
            "error": "missing_activation_id_and_license_key",
        }

    headers = {**_headers(), "Prefer": "return=minimal"}
    try:
        resp = requests.post(_upgrade_requests_table_url(), headers=headers, json=payload, timeout=12)
    except requests.RequestException as exc:
        message, error = _request_error_message(operation, exc)
        _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
        return {"ok": False, "message": message, "error": error or "network_error"}

    if resp.status_code >= 300:
        message, error = _response_error_message(operation, resp)
        _set_supabase_debug(operation=operation, status="http_error", status_code=resp.status_code, last_error=error)
        return {"ok": False, "message": message, "status_code": resp.status_code, "error": error}

    _set_supabase_debug(operation=operation, status="ok", status_code=resp.status_code, last_error="")
    return {"ok": True, "message": "Solicitud de actualización enviada.", "status_code": resp.status_code}


def activate_license(
    license_key: str,
    machine_id: str,
    producto: str = PRODUCTO_DEFAULT,
    vendor_code: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    operation = "activate_license"
    if not is_configured():
        _set_supabase_debug(operation=operation, status="not_configured", status_code=None, last_error="not_configured")
        return False, "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY.", None

    key = (license_key or "").strip()
    machine_id = build_machine_id(machine_id)
    vendor_code = _normalize_vendor_code(vendor_code)
    if not key or not machine_id:
        _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="missing_license_key_or_machine_id")
        return False, "La clave y el ID de maquina son obligatorios.", None

    params = {"license_key": f"eq.{key}", "producto": f"eq.{producto}", "select": "*"}
    try:
        resp = requests.get(_table_url(), headers=_headers(), params=params, timeout=12)
    except requests.RequestException as exc:
        message, error = _request_error_message(operation, exc)
        _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
        return False, message, None
    if resp.status_code >= 300:
        message, error = _response_error_message(operation, resp)
        _set_supabase_debug(operation=operation, status="http_error", status_code=resp.status_code, last_error=error)
        return False, message, None

    try:
        rows = resp.json() if resp.text else []
    except ValueError:
        logger.warning("Respuesta invalida de Supabase al consultar licencia")
        _set_supabase_debug(operation=operation, status="invalid_response", status_code=resp.status_code, last_error="invalid_json")
        return False, "Supabase devolvió una respuesta inválida al validar la licencia.", None
    if not rows:
        _set_supabase_debug(operation=operation, status="not_found", status_code=resp.status_code, last_error="license_not_found")
        return False, "No existe esa licencia para este producto.", None

    row = rows[0]
    if not row.get("activa", True):
        _set_supabase_debug(operation=operation, status="inactive", status_code=resp.status_code, last_error="license_inactive")
        return False, "La licencia esta desactivada/revocada.", row

    db_hwid = row.get("hwid") or ""
    db_hwids = row.get("hwids") or []
    if isinstance(db_hwids, str):
        db_hwids = [db_hwids] if db_hwids else []
    max_devices = max(int(row.get("max_devices") or 1), 1)

    if db_hwid == machine_id or machine_id in db_hwids:
        update_hwids = sorted(set([*db_hwids, machine_id]))
    elif not db_hwid or len(db_hwids) < max_devices:
        update_hwids = sorted(set([*db_hwids, machine_id]))[:max_devices]
    else:
        return False, "La licencia alcanzo el limite de dispositivos.", row

    try:
        patch_payload = {"hwid": db_hwid or machine_id, "hwids": update_hwids}
        if vendor_code:
            patch_payload["codigo_vendedor"] = vendor_code
        upd = requests.patch(
            _table_url(),
            headers={**_headers(), "Prefer": "return=representation"},
            params={"id": f"eq.{row['id']}"},
            json=patch_payload,
            timeout=12,
        )
    except requests.RequestException as exc:
        message, error = _request_error_message(operation, exc)
        _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
        return False, f"Licencia encontrada, pero {message.lower()}", row
    if upd.status_code >= 300:
        message, error = _response_error_message(operation, upd)
        _set_supabase_debug(operation=operation, status="http_error", status_code=upd.status_code, last_error=error)
        return False, f"Licencia encontrada, pero {message.lower()}", row

    try:
        updated_rows = upd.json() if upd.text else [row]
    except ValueError:
        logger.warning("Respuesta invalida de Supabase al actualizar HWID")
        _set_supabase_debug(operation=operation, status="invalid_response", status_code=upd.status_code, last_error="invalid_json")
        return False, "Licencia encontrada, pero Supabase devolvió una respuesta inválida al vincular este equipo.", row
    updated = updated_rows[0] if updated_rows else row
    _set_supabase_debug(operation=operation, status="ok", status_code=upd.status_code, last_error="")
    return True, "Licencia activada correctamente para esta maquina.", updated


def update_license_vendor_code(
    license_key: str,
    vendor_code: str,
    producto: str = PRODUCTO_DEFAULT,
) -> tuple[bool, str, dict[str, Any] | None]:
    operation = "update_license_vendor_code"
    if not is_configured():
        _set_supabase_debug(operation=operation, status="not_configured", status_code=None, last_error="not_configured")
        return False, "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY.", None

    key = (license_key or "").strip()
    normalized_vendor_code = _normalize_vendor_code(vendor_code)
    if not key or not normalized_vendor_code:
        _set_supabase_debug(operation=operation, status="validation_error", status_code=None, last_error="missing_license_key_or_vendor_code")
        return False, "La licencia y el código de vendedor son obligatorios.", None

    params = {"license_key": f"eq.{key}", "producto": f"eq.{producto}", "select": "*"}
    try:
        resp = requests.get(_table_url(), headers=_headers(), params=params, timeout=12)
    except requests.RequestException as exc:
        message, error = _request_error_message(operation, exc)
        _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
        return False, message, None

    if resp.status_code >= 300:
        message, error = _response_error_message(operation, resp)
        _set_supabase_debug(operation=operation, status="http_error", status_code=resp.status_code, last_error=error)
        return False, message, None

    try:
        rows = resp.json() if resp.text else []
    except ValueError:
        _set_supabase_debug(operation=operation, status="invalid_response", status_code=resp.status_code, last_error="invalid_json")
        return False, "Supabase devolvió una respuesta inválida al buscar la licencia.", None

    if not rows:
        _set_supabase_debug(operation=operation, status="not_found", status_code=resp.status_code, last_error="license_not_found")
        return False, "No encontramos una licencia remota para sincronizar el código de vendedor.", None

    row = rows[0]
    try:
        upd = requests.patch(
            _table_url(),
            headers={**_headers(), "Prefer": "return=representation"},
            params={"id": f"eq.{row['id']}"},
            json={"codigo_vendedor": normalized_vendor_code},
            timeout=12,
        )
    except requests.RequestException as exc:
        message, error = _request_error_message(operation, exc)
        _set_supabase_debug(operation=operation, status="network_error", status_code=None, last_error=error or "network_error")
        return False, message, row

    if upd.status_code >= 300:
        message, error = _response_error_message(operation, upd)
        _set_supabase_debug(operation=operation, status="http_error", status_code=upd.status_code, last_error=error)
        return False, message, row

    try:
        updated_rows = upd.json() if upd.text else [row]
    except ValueError:
        _set_supabase_debug(operation=operation, status="invalid_response", status_code=upd.status_code, last_error="invalid_json")
        return False, "Supabase devolvió una respuesta inválida al guardar el código de vendedor.", row

    updated = updated_rows[0] if updated_rows else row
    _set_supabase_debug(operation=operation, status="ok", status_code=upd.status_code, last_error="")
    return True, "Código de vendedor sincronizado correctamente.", updated
