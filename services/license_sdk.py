from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SDK_REPO_PATH = BASE_DIR.parent / "nexar_licencias"
PUBLIC_KEY_PATH = BASE_DIR / "keys" / "public_key.pem"


def _ensure_sdk_path() -> None:
    sdk_path = str(SDK_REPO_PATH)
    if sdk_path not in sys.path:
        sys.path.append(sdk_path)


def _import_module(module_name: str):
    _ensure_sdk_path()
    return importlib.import_module(module_name)


def import_validar_licencia():
    try:
        module = _import_module("nexar_licencias")
        return getattr(module, "validar_licencia", None)
    except Exception:
        return None


def get_license_product() -> str:
    return os.getenv("LICENSE_PRODUCT", "nexar-tienda").strip() or "nexar-tienda"


def load_public_key() -> str | None:
    env_key = os.getenv("PUBLIC_KEY", "").strip()
    if env_key:
        return env_key

    try:
        content = PUBLIC_KEY_PATH.read_text(encoding="utf-8").strip()
        return content or None
    except Exception:
        return None


def get_current_hwid() -> str:
    try:
        device_module = _import_module("nexar_licencias.device")
        return str(device_module.get_hwid())
    except Exception:
        return ""


def validate_license_key(license_key: str, debug: bool = False) -> tuple[bool, str]:
    license_key = (license_key or "").strip()
    if not license_key:
        return False, "Ingresá una licencia válida."

    validar_licencia = import_validar_licencia()
    if validar_licencia is None:
        return False, "No se pudo cargar el SDK nexar_licencias."

    try:
        ok = bool(
            validar_licencia(
                {"license_key": license_key},
                load_public_key(),
                get_license_product(),
                debug=debug,
            )
        )
    except Exception as ex:
        return False, f"Error validando licencia: {ex}"

    if not ok:
        return False, "La licencia es inválida, expiró o fue revocada."

    return True, "Licencia validada correctamente."


def validate_saved_license(debug: bool = False) -> tuple[bool, str]:
    from services.license_storage import cargar_licencia

    stored = cargar_licencia()
    if not stored:
        return False, "No hay licencia guardada."

    return validate_license_key(stored.get("license_key", ""), debug=debug)
