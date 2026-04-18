from __future__ import annotations

import os
import platform
import secrets
import hashlib
import getpass
from datetime import date, timedelta
from typing import Any

import requests

PRODUCTO_DEFAULT = "nexar-tienda"


def _clean_base_url(url: str) -> str:
    return url.rstrip("/")


def _table_url() -> str:
    base = _clean_base_url(os.getenv("SUPABASE_URL", ""))
    return f"{base}/rest/v1/licencias" if base else ""


def _headers() -> dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")))


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


def create_license(machine_id: str, usuario: str = "", producto: str = PRODUCTO_DEFAULT, dias: int = 365) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_configured():
        return False, "Falta configurar SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY/ANON_KEY.", None

    machine_id = build_machine_id(machine_id)
    if not machine_id:
        return False, "El ID de máquina es obligatorio.", None

    payload = {
        "license_key": f"NXR-{secrets.token_hex(4).upper()}",
        "producto": producto,
        "usuario": usuario or "Cliente",
        "activa": True,
        "expira": (date.today() + timedelta(days=max(1, dias))).isoformat(),
        "hwid": machine_id,
        "hwids": [machine_id],
        "max_devices": 1,
    }

    resp = requests.post(_table_url(), headers=_headers(), json=payload, timeout=12)
    if resp.status_code >= 300:
        return False, f"Error al crear licencia en Supabase ({resp.status_code}): {resp.text[:240]}", None

    data = resp.json()
    row = data[0] if isinstance(data, list) and data else data
    return True, "Licencia creada correctamente en Supabase.", row


def activate_license(license_key: str, machine_id: str, producto: str = PRODUCTO_DEFAULT) -> tuple[bool, str, dict[str, Any] | None]:
    if not is_configured():
        return False, "Falta configurar SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY/ANON_KEY.", None

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

    if db_hwid and db_hwid != machine_id and machine_id not in db_hwids:
        return False, "La licencia pertenece a otra máquina.", row

    update_data = {
        "hwid": machine_id,
        "hwids": sorted(set([*db_hwids, machine_id]))[: max(int(row.get("max_devices") or 1), 1)],
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
