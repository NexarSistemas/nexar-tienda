from __future__ import annotations

import os
import platform
import secrets
import hashlib
import getpass
from datetime import date, timedelta
from typing import Any

import requests

PRODUCTO_DEFAULT = os.getenv("LICENSE_PRODUCT", "nexar-tienda")
PLAN_CONFIG = {
    "DEMO": {
        "duration_days": 30,
        "support": False,
        "updates": False,
        "limits": {"productos": None, "clientes": None, "proveedores": None},
    },
    "BASICA": {
        "duration_days": None,
        "support": False,
        "updates": False,
        "limits": {"productos": 200, "clientes": 100, "proveedores": 50},
    },
    "MENSUAL_FULL": {
        "duration_days": 30,
        "support": True,
        "updates": True,
        "limits": {"productos": None, "clientes": None, "proveedores": None},
    },
}


def normalize_plan(plan: str = "") -> str:
    raw = (plan or "BASICA").strip().upper().replace("-", "_").replace(" ", "_")
    return {"PRO": "MENSUAL_FULL", "FULL": "MENSUAL_FULL", "BASIC": "BASICA"}.get(raw, raw if raw in PLAN_CONFIG else "BASICA")


def _clean_base_url(url: str) -> str:
    return url.rstrip("/")


def _table_url() -> str:
    base = _clean_base_url(os.getenv("SUPABASE_URL", ""))
    return f"{base}/rest/v1/licencias" if base else ""


def _requests_table_url() -> str:
    base = _clean_base_url(os.getenv("SUPABASE_URL", ""))
    return f"{base}/rest/v1/solicitudes_licencia" if base else ""


def _anon_key() -> str:
    return os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")


def _service_role_key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers(*, require_service_role: bool = False) -> dict[str, str]:
    key = _service_role_key() if require_service_role else _anon_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and _anon_key())


def is_admin_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and _service_role_key())


def build_machine_id(raw: str) -> str:
    value = (raw or "").strip().lower()
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_")[:120]


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
    Genera un ID de activación estable para enviar al desarrollador.
    Usa datos locales (máquina + disco + usuario) y devuelve (id, detalles).
    """
    username = user_hint or getpass.getuser() or os.getenv("USERNAME", "") or os.getenv("USER", "")
    host = platform.node()
    machine_id = _read_first(["/etc/machine-id", "/var/lib/dbus/machine-id"])
    product_uuid = _read_first(["/sys/class/dmi/id/product_uuid"])
    disk_hint = os.path.abspath(os.sep)
    try:
        disk_hint = os.stat(disk_hint).st_dev.__str__()
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


def create_license(
    usuario: str = "",
    producto: str = PRODUCTO_DEFAULT,
    dias: int = None,
    plan: str = "BASICA",
    machine_id: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_admin_configured():
        return False, "Falta configurar SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY para emitir licencias.", None

    plan = normalize_plan(plan)
    cfg = PLAN_CONFIG[plan]
    expira = ""
    if cfg["duration_days"] is not None:
        expira = (date.today() + timedelta(days=max(1, int(dias or cfg["duration_days"])))).isoformat()

    clean_machine_id = build_machine_id(machine_id)
    payload = {
        "license_key": f"NXR-{secrets.token_hex(4).upper()}",
        "producto": producto,
        "usuario": usuario or "Cliente",
        "plan": plan,
        "tier": plan,
        "activa": True,
        "expira": expira or None,
        "hwid": clean_machine_id,
        "hwids": [clean_machine_id] if clean_machine_id else [],
        "max_devices": 1,
        "support": cfg["support"],
        "updates": cfg["updates"],
        "limits": cfg["limits"],
    }

    resp = requests.post(_table_url(), headers=_headers(require_service_role=True), json=payload, timeout=12)
    if resp.status_code >= 300:
        return False, f"Error al crear licencia en Supabase ({resp.status_code}): {resp.text[:240]}", None

    data = resp.json()
    row = data[0] if isinstance(data, list) and data else data
    return True, "Licencia creada correctamente en Supabase.", row


def create_license_request(
    *,
    nombre: str,
    email: str,
    whatsapp: str = "",
    activation_id: str,
    producto: str = PRODUCTO_DEFAULT,
    plan: str = "BASICA",
    machine_details: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_configured():
        return False, "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY para enviar solicitudes.", None

    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()
    whatsapp = (whatsapp or "").strip()
    activation_id = build_machine_id(activation_id)
    plan = normalize_plan(plan)

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
    headers = {**_headers(), "Prefer": "return=minimal"}
    resp = requests.post(_requests_table_url(), headers=headers, json=payload, timeout=12)
    if resp.status_code >= 300:
        return False, f"Error al registrar solicitud en Supabase ({resp.status_code}): {resp.text[:240]}", None

    return True, "Solicitud enviada correctamente. El administrador debe aprobarla.", None


def list_license_requests(producto: str = PRODUCTO_DEFAULT, estado: str = "", limit: int = 25) -> tuple[bool, str, list[dict[str, Any]]]:
    if not is_admin_configured():
        return False, "Falta SUPABASE_SERVICE_ROLE_KEY para listar solicitudes.", []

    params: dict[str, str] = {
        "producto": f"eq.{producto}",
        "select": "*",
        "order": "created_at.desc",
        "limit": str(max(1, min(int(limit or 25), 100))),
    }
    if estado:
        params["estado"] = f"eq.{estado}"

    resp = requests.get(_requests_table_url(), headers=_headers(require_service_role=True), params=params, timeout=12)
    if resp.status_code >= 300:
        return False, f"Error al listar solicitudes ({resp.status_code}): {resp.text[:240]}", []

    rows = resp.json() if resp.text else []
    return True, "Solicitudes cargadas.", rows if isinstance(rows, list) else []


def get_license_request(request_id: int | str, producto: str = PRODUCTO_DEFAULT) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_admin_configured():
        return False, "Falta SUPABASE_SERVICE_ROLE_KEY para consultar solicitudes.", None

    params = {"id": f"eq.{request_id}", "producto": f"eq.{producto}", "select": "*"}
    resp = requests.get(_requests_table_url(), headers=_headers(require_service_role=True), params=params, timeout=12)
    if resp.status_code >= 300:
        return False, f"Error al consultar solicitud ({resp.status_code}): {resp.text[:240]}", None

    rows = resp.json() if resp.text else []
    if not rows:
        return False, "No se encontro la solicitud.", None
    return True, "Solicitud encontrada.", rows[0]


def update_license_request_status(
    request_id: int | str,
    *,
    estado: str,
    license_key: str = "",
    admin_note: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_admin_configured():
        return False, "Falta SUPABASE_SERVICE_ROLE_KEY para actualizar solicitudes.", None

    payload = {
        "estado": estado,
        "license_key": license_key or None,
        "admin_note": admin_note or None,
    }
    resp = requests.patch(
        _requests_table_url(),
        headers=_headers(require_service_role=True),
        params={"id": f"eq.{request_id}"},
        json=payload,
        timeout=12,
    )
    if resp.status_code >= 300:
        return False, f"Error al actualizar solicitud ({resp.status_code}): {resp.text[:240]}", None

    data = resp.json() if resp.text else []
    row = data[0] if isinstance(data, list) and data else data
    return True, "Solicitud actualizada.", row


def activate_license(license_key: str, machine_id: str, producto: str = PRODUCTO_DEFAULT) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_configured():
        return False, "Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY.", None

    key = (license_key or "").strip()
    machine_id = build_machine_id(machine_id)
    if not key or not machine_id:
        return False, "La clave y el ID de máquina son obligatorios.", None

    params = {"license_key": f"eq.{key}", "producto": f"eq.{producto}", "select": "*"}
    resp = requests.get(_table_url(), headers=_headers(), params=params, timeout=12)
    if resp.status_code >= 300:
        return False, f"Error consultando licencia ({resp.status_code}): {resp.text[:240]}", None

    rows = resp.json() if resp.text else []
    if not rows:
        return False, "No existe esa licencia para este producto.", None

    row = rows[0]
    if not row.get("activa", True):
        return False, "La licencia está desactivada/revocada.", row

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
        return False, "La licencia alcanzó el límite de dispositivos.", row

    update_data = {
        "hwid": db_hwid or machine_id,
        "hwids": update_hwids,
    }
    upd = requests.patch(
        _table_url(),
        headers={**_headers(), "Prefer": "return=representation"},
        params={"id": f"eq.{row['id']}"},
        json=update_data,
        timeout=12,
    )
    if upd.status_code >= 300:
        return False, f"Licencia encontrada, pero no se pudo actualizar HWID ({upd.status_code}).", row

    updated_rows = upd.json() if upd.text else [row]
    updated = updated_rows[0] if updated_rows else row
    return True, "Licencia activada correctamente para esta máquina.", updated
