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


def import_validar_licencia_detalle():
    try:
        module = _import_module("nexar_licencias")
        return getattr(module, "validar_licencia_detalle", None)
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


def _save_sdk_cache(license_data: dict) -> None:
    if not license_data:
        return
    try:
        cache_module = _import_module("nexar_licencias.cache")
        save_cache = getattr(cache_module, "save_cache", None)
        if callable(save_cache):
            save_cache(license_data)
    except Exception:
        pass


def validate_license_key(license_key: str, debug: bool = False) -> tuple[bool, str]:
    license_key = (license_key or "").strip()
    if not license_key:
        return False, "Ingresá una licencia válida."

    validar_detalle = import_validar_licencia_detalle()
    validar_licencia = import_validar_licencia()
    if validar_detalle is None and validar_licencia is None:
        return False, "No se pudo cargar el SDK nexar_licencias."

    try:
        if validar_detalle is not None:
            result = validar_detalle(
                {"license_key": license_key},
                load_public_key(),
                get_license_product(),
                debug=debug,
            )
            ok = bool(result.get("ok"))
            license_data = result.get("license") or {}
        else:
            ok = bool(validar_licencia(
                {"license_key": license_key},
                load_public_key(),
                get_license_product(),
                debug=debug,
            ))
            license_data = {"license_key": license_key}
    except Exception as ex:
        return False, f"Error validando licencia: {ex}"

    if not ok:
        reason = result.get("reason") if validar_detalle is not None else ""
        if reason == "sin_cache":
            try:
                from services.supabase_license_api import activate_license

                fallback_ok, fallback_msg, fallback_data = activate_license(
                    license_key,
                    get_current_hwid(),
                    get_license_product(),
                )
                if fallback_ok and fallback_data:
                    ok = True
                    license_data = fallback_data
                    _save_sdk_cache(license_data)
                else:
                    return False, fallback_msg
            except Exception as ex:
                return False, f"No se pudo validar online: {ex}"

    if not ok:
        reason = result.get("reason") if validar_detalle is not None else ""
        messages = {
            "expirada": "La licencia expiró. Pedí la renovación al desarrollador.",
            "revocada": "La licencia fue revocada o está desactivada.",
            "limite_dispositivos": "La licencia alcanzó el límite de dispositivos. Pedí reset o más equipos al desarrollador.",
            "no_se_pudo_vincular_dispositivo": "La licencia existe, pero no se pudo vincular este equipo. Intentá de nuevo o pedí reset al desarrollador.",
            "no_existe": "No existe una licencia activa con esa clave para este producto.",
            "sin_cache": "No se pudo validar online y no hay cache offline para esta licencia.",
        }
        return False, messages.get(reason, "La licencia es inválida, expiró o fue revocada.")

    _save_sdk_cache(license_data)

    try:
        import database as db

        plan = db.normalize_license_plan(
            license_data.get("plan") or license_data.get("tier") or license_data.get("license_plan")
        )
        if plan == "MENSUAL_FULL" and db.get_config().get("basica_activada", "0") != "1":
            return False, "Para activar Mensual Full primero tenés que activar una licencia Básica en esta instalación."
        db.sync_license_from_remote(license_data)
    except Exception:
        pass

    return True, "Licencia validada correctamente."


def get_license_details(license_key: str, debug: bool = False) -> dict:
    validar_detalle = import_validar_licencia_detalle()
    if validar_detalle is None:
        return {}
    try:
        result = validar_detalle(
            {"license_key": license_key},
            load_public_key(),
            get_license_product(),
            debug=debug,
        )
        return result.get("license") if result.get("ok") else {}
    except Exception:
        return {}


def validate_saved_license(debug: bool = False) -> tuple[bool, str]:
    from services.license_storage import cargar_licencia

    stored = cargar_licencia()
    if not stored:
        return False, "No hay licencia guardada."

    return validate_license_key(stored.get("license_key", ""), debug=debug)
