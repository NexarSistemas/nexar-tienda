from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SDK_REPO_PATH = BASE_DIR.parent / "nexar_licencias"
PUBLIC_KEY_PATH = BASE_DIR / "keys" / "public_key.pem"
logger = logging.getLogger(__name__)
_LAST_LICENSE_DEBUG: dict[str, object] = {
    "product": "",
    "license_mode": "",
    "validation_mode": "",
    "status": "",
    "plan": "",
    "tier": "",
    "modules": [],
    "masked_license_key": "",
    "last_error": "",
}


def _ensure_sdk_path() -> None:
    sdk_path = str(SDK_REPO_PATH)
    if sdk_path not in sys.path:
        sys.path.append(sdk_path)


def _import_module(module_name: str):
    _ensure_sdk_path()
    return importlib.import_module(module_name)


def _mask_license_key(value: str) -> str:
    key = (value or "").strip()
    if len(key) <= 7:
        return key[:2] + "..." if key else ""
    return f"{key[:4]}...{key[-3:]}"


def _set_license_debug(**values) -> None:
    _LAST_LICENSE_DEBUG.update(values)


def get_license_debug_state() -> dict[str, object]:
    return dict(_LAST_LICENSE_DEBUG)


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
    product = get_license_product()
    license_mode = os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower()
    masked_key = _mask_license_key(license_key)
    logger.info(
        "Inicio validacion de licencia producto=%s modo=%s clave=%s",
        product,
        license_mode,
        masked_key,
    )
    _set_license_debug(
        product=product,
        license_mode=license_mode,
        validation_mode="start",
        status="starting",
        masked_license_key=masked_key,
        last_error="",
        plan="",
        tier="",
        modules=[],
    )
    if not license_key:
        _set_license_debug(status="online_error", last_error="license_key_missing")
        return False, "Ingresá una licencia válida."

    validar_detalle = import_validar_licencia_detalle()
    validar_licencia = import_validar_licencia()
    if validar_detalle is None and validar_licencia is None:
        logger.error("No se pudo cargar el SDK nexar_licencias para producto=%s", product)
        _set_license_debug(status="online_error", last_error="sdk_missing")
        return False, "No se pudo cargar el SDK nexar_licencias."

    try:
        if validar_detalle is not None:
            result = validar_detalle(
                {"license_key": license_key},
                load_public_key(),
                product,
                debug=debug,
            )
            ok = bool(result.get("ok"))
            license_data = result.get("license") or {}
            source = str(result.get("source") or "online")
        else:
            ok = bool(validar_licencia(
                {"license_key": license_key},
                load_public_key(),
                product,
                debug=debug,
            ))
            license_data = {"license_key": license_key}
            source = "fallback"
    except Exception as ex:
        logger.exception("Error validando licencia producto=%s modo=%s", product, license_mode)
        _set_license_debug(status="online_error", validation_mode="online", last_error=str(ex))
        return False, f"Error validando licencia: {ex}"

    if not ok:
        reason = result.get("reason") if validar_detalle is not None else ""
        if source == "cache":
            _set_license_debug(status="cache_missing", validation_mode="cache", last_error=reason or "cache_missing")
        else:
            _set_license_debug(status="online_error", validation_mode=source, last_error=reason or "online_error")
        if reason == "sin_cache":
            logger.warning(
                "Validacion online sin cache disponible producto=%s modo=%s clave=%s",
                product,
                license_mode,
                masked_key,
            )
            try:
                from services.supabase_license_api import activate_license

                fallback_ok, fallback_msg, fallback_data = activate_license(
                    license_key,
                    get_current_hwid(),
                    product,
                )
                if fallback_ok and fallback_data:
                    ok = True
                    license_data = fallback_data
                    source = "fallback"
                    _save_sdk_cache(license_data)
                    logger.info("Fallback online exitoso producto=%s clave=%s", product, masked_key)
                else:
                    _set_license_debug(status="online_error", validation_mode="fallback", last_error=fallback_msg)
                    return False, fallback_msg
            except Exception as ex:
                logger.exception("Error en fallback online producto=%s", product)
                _set_license_debug(status="online_error", validation_mode="fallback", last_error=str(ex))
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
        logger.warning(
            "Licencia invalida producto=%s modo=%s fuente=%s razon=%s clave=%s",
            product,
            license_mode,
            source,
            reason or "unknown",
            masked_key,
        )
        return False, messages.get(reason, "La licencia es inválida, expiró o fue revocada.")

    _save_sdk_cache(license_data)
    modules = license_data.get("modules") or license_data.get("features") or license_data.get("modulos") or []
    plan = license_data.get("plan") or license_data.get("tier") or license_data.get("license_plan") or ""

    try:
        import database as db

        plan = db.normalize_license_plan(
            license_data.get("plan") or license_data.get("tier") or license_data.get("license_plan")
        )
        if plan == "MENSUAL_FULL" and db.get_config().get("basica_activada", "0") != "1":
            _set_license_debug(
                status="online_error",
                validation_mode=source,
                plan=plan,
                tier=plan,
                modules=modules,
                last_error="basica_required_before_full",
            )
            return False, "Para activar Mensual Full primero tenés que activar una licencia Básica en esta instalación."
        db.sync_license_from_remote(license_data)
    except Exception:
        pass

    status = "cache_ok" if source == "cache" else "online_ok"
    _set_license_debug(
        status=status,
        validation_mode=source,
        plan=license_data.get("plan") or plan,
        tier=license_data.get("tier") or plan,
        modules=modules,
        last_error="",
    )
    logger.info(
        "Licencia validada producto=%s fuente=%s plan=%s tier=%s modules=%s clave=%s",
        product,
        source,
        license_data.get("plan") or plan,
        license_data.get("tier") or plan,
        modules,
        masked_key,
    )

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
        _set_license_debug(
            product=get_license_product(),
            license_mode=os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower(),
            validation_mode="cache",
            status="cache_missing",
            masked_license_key="",
            last_error="stored_license_missing",
            plan="",
            tier="",
            modules=[],
        )
        return False, "No hay licencia guardada."

    return validate_license_key(stored.get("license_key", ""), debug=debug)
