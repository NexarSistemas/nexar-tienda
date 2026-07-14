from __future__ import annotations

import importlib
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import Any


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


def _resolve_remote_plan(license_data: dict | None) -> str:
    payload = license_data or {}
    raw_plan = (
        payload.get("plan_original")
        or payload.get("plan")
        or payload.get("tier")
        or payload.get("license_plan")
        or "DEMO"
    )
    try:
        sdk_normalize_plan = import_sdk_contracts().get("normalize_plan")
        if callable(sdk_normalize_plan):
            normalized = str(sdk_normalize_plan(raw_plan) or "").strip().upper()
            if normalized == "MENSUAL_FULL":
                return "FULL"
            if normalized in {"DEMO", "BASICA", "PRO", "FULL"}:
                return normalized
    except Exception:
        pass
    try:
        import database as db

        return db.normalize_license_plan(raw_plan)
    except Exception:
        return str(raw_plan or "DEMO").strip().upper().replace("-", "_").replace(" ", "_")


def _resolve_effective_license_data(license_data: dict | None) -> dict:
    payload = dict(license_data or {})
    if not payload:
        return {}

    original_remote_status = _normalize_remote_status(payload)
    resolver = import_sdk_contracts().get("resolve_effective_license")
    if callable(resolver):
        try:
            resolved = dict(resolver(payload) or {})
            if resolved:
                payload.update(resolved)
        except Exception as ex:
            logger.debug("No se pudo resolver licencia con SDK central: %s", ex.__class__.__name__)

    remote_status = original_remote_status or _normalize_remote_status(payload)
    if remote_status in {"suspendida", "bloqueada", "anulada", "revocada"}:
        effective_plan = "BASICA" if bool(payload.get("plan_base_permanente")) else "DEMO"
        payload.update({
            "estado": remote_status,
            "plan_efectivo": effective_plan,
            "effective_plan": effective_plan,
            "tier": effective_plan,
            "fallback_aplicado": False,
        })

    return payload


def _ensure_sdk_path() -> None:
    sdk_path = str(SDK_REPO_PATH)
    if sdk_path not in sys.path:
        sys.path.append(sdk_path)


def _import_module(module_name: str):
    _ensure_sdk_path()
    return importlib.import_module(module_name)


def import_sdk_contracts() -> dict[str, Any]:
    try:
        module = _import_module("nexar_licencias")
    except Exception:
        return {}
    return {
        "SDKConfig": getattr(module, "SDKConfig", None),
        "DEFAULT_CONFIG": getattr(module, "DEFAULT_CONFIG", None),
        "normalize_plan": getattr(module, "normalize_plan", None),
        "resolve_effective_license": getattr(module, "resolve_effective_license", None),
    }


def get_sdk_config():
    contracts = import_sdk_contracts()
    SDKConfig = contracts.get("SDKConfig")
    if SDKConfig is None:
        return contracts.get("DEFAULT_CONFIG")
    try:
        return SDKConfig.from_env()
    except Exception as ex:
        logger.warning("No se pudo cargar configuracion del SDK de licencias: %s", ex.__class__.__name__)
        _set_license_debug(last_error=ex.__class__.__name__)
        return contracts.get("DEFAULT_CONFIG")


def _supports_keyword(func, keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    return keyword in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _call_sdk_validator(func, licencia_dict: dict, public_key: str | None, product: str, debug: bool):
    config = get_sdk_config()
    kwargs = {"debug": debug}
    if config is not None and _supports_keyword(func, "config"):
        kwargs["config"] = config
    return func(licencia_dict, public_key, product, **kwargs)


def _mask_license_key(value: str) -> str:
    key = (value or "").strip()
    if len(key) <= 7:
        return key[:2] + "..." if key else ""
    return f"{key[:4]}...{key[-3:]}"


def _normalize_vendor_code(value: str | None) -> str:
    return str(value or "").strip().upper()


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
            if _supports_keyword(save_cache, "config"):
                save_cache(license_data, config=get_sdk_config())
            else:
                save_cache(license_data)
    except Exception:
        pass


def _normalize_remote_status(license_data: dict | None) -> str:
    payload = license_data or {}
    status = str(payload.get("estado") or "").strip().lower()
    if status in {"revocada", "suspendida", "bloqueada", "anulada"}:
        return status
    for flag_name, normalized in (
        ("suspendida", "suspendida"),
        ("bloqueada", "bloqueada"),
        ("anulada", "anulada"),
        ("revocada", "revocada"),
    ):
        if str(payload.get(flag_name, "")).strip().lower() in {"1", "true", "yes", "si", "on"}:
            return normalized
    if not payload.get("activa", True):
        return "revocada"
    return status


def _has_valid_local_premium_cache(license_info: dict[str, object] | None) -> bool:
    info = license_info or {}
    return (
        _resolve_remote_plan(info) in {"PRO", "FULL"}
        and not bool(info.get("expirada"))
        and _resolve_remote_plan({"plan": info.get("tier")}) in {"PRO", "FULL"}
    )


def _persist_local_license_state(
    db_module,
    previous_info: dict[str, object],
    *,
    target_plan: str,
    status: str,
) -> dict[str, object]:
    normalized_plan = target_plan if target_plan in {"BASICA", "DEMO"} else "DEMO"
    payload = {
        "license_key": previous_info.get("key", ""),
        "plan_original": normalized_plan,
        "plan_efectivo": normalized_plan,
        "plan": normalized_plan,
        "tier": normalized_plan,
        "estado": status,
        "fallback_aplicado": normalized_plan == "BASICA",
        "plan_base_permanente": normalized_plan == "BASICA",
        "expires_at": "",
        "max_machines": previous_info.get("max_machines", 1),
        "modules": [],
    }
    db_module.sync_license_from_remote(payload)
    return db_module.get_license_info()


def validate_license_key(license_key: str, debug: bool = False, vendor_code: str = "") -> tuple[bool, str]:
    license_key = (license_key or "").strip()
    vendor_code = _normalize_vendor_code(vendor_code)
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
            result = _call_sdk_validator(
                validar_detalle,
                {"license_key": license_key},
                load_public_key(),
                product,
                debug,
            )
            ok = bool(result.get("ok"))
            license_data = result.get("license") or {}
            source = str(result.get("source") or "online")
        else:
            ok = bool(_call_sdk_validator(
                validar_licencia,
                {"license_key": license_key},
                load_public_key(),
                product,
                debug,
            ))
            license_data = {"license_key": license_key}
            source = "fallback"
    except Exception as ex:
        logger.warning("Error validando licencia producto=%s modo=%s: %s", product, license_mode, ex)
        _set_license_debug(status="online_error", validation_mode="online", last_error=ex.__class__.__name__)
        return False, "No se pudo validar la licencia en este momento."

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
                    vendor_code=vendor_code,
                )
                if fallback_ok and fallback_data:
                    ok = True
                    license_data = _resolve_effective_license_data(fallback_data)
                    source = "fallback"
                    _save_sdk_cache(license_data)
                    logger.info("Fallback online exitoso producto=%s clave=%s", product, masked_key)
                else:
                    _set_license_debug(status="online_error", validation_mode="fallback", last_error=fallback_msg)
                    return False, fallback_msg
            except Exception as ex:
                logger.warning("Error en fallback online producto=%s: %s", product, ex)
                _set_license_debug(status="online_error", validation_mode="fallback", last_error=ex.__class__.__name__)
                return False, "No se pudo validar la licencia en este momento."

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

    license_data = _resolve_effective_license_data(license_data)
    _save_sdk_cache(license_data)
    modules = license_data.get("modules") or license_data.get("features") or license_data.get("modulos") or []
    plan = _resolve_remote_plan(license_data)

    if vendor_code:
        try:
            from services.supabase_license_api import activate_license as sync_activation

            sync_ok, _sync_msg, sync_data = sync_activation(
                license_key,
                get_current_hwid(),
                product,
                vendor_code=vendor_code,
            )
            if sync_ok and sync_data:
                license_data = _resolve_effective_license_data(sync_data)
                modules = license_data.get("modules") or license_data.get("features") or license_data.get("modulos") or []
                plan = _resolve_remote_plan(license_data)
                _save_sdk_cache(license_data)
        except Exception:
            logger.warning("No se pudo sincronizar codigo_vendedor al activar la licencia", exc_info=True)

    try:
        import database as db
        from licensing.permisos import get_modulos_debug_info

        raw_plan = license_data.get("plan") or license_data.get("tier") or license_data.get("license_plan")
        db.sync_license_from_remote(license_data)
        modulos_debug = get_modulos_debug_info()
        logger.info(
            "Diagnostico licencia producto=%s fuente=%s plan_supabase=%s plan_normalizado=%s sdk_modules=%s persisted_modules=%s final_modules=%s modules_source=%s",
            product,
            source,
            raw_plan,
            plan,
            modules,
            modulos_debug.get("persisted_modules", []),
            modulos_debug.get("final_modules", []),
            modulos_debug.get("final_source", "unknown"),
        )
    except Exception:
        pass

    status = "cache_ok" if source == "cache" else "online_ok"
    _set_license_debug(
        status=status,
        validation_mode=source,
        plan=plan,
        tier=plan,
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
        result = _call_sdk_validator(
            validar_detalle,
            {"license_key": license_key},
            load_public_key(),
            get_license_product(),
            debug,
        )
        return _resolve_effective_license_data(result.get("license")) if result.get("ok") else {}
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


def refresh_saved_license_online(debug: bool = False) -> tuple[bool, str, dict[str, object] | None]:
    """
    Fuerza una sincronizacion online de la licencia guardada contra Supabase.

    Si la consulta online falla, conserva el estado local existente y no lo pisa
    con cache vieja del SDK.
    """
    from services.license_storage import cargar_licencia, guardar_licencia
    from services.supabase_license_api import activate_license, generate_activation_id, get_supabase_debug_state
    import database as db

    stored = cargar_licencia()
    if not stored:
        _set_license_debug(
            product=get_license_product(),
            license_mode=os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower(),
            validation_mode="supabase_refresh",
            status="missing_local_license",
            masked_license_key="",
            last_error="stored_license_missing",
            plan="",
            tier="",
            modules=[],
        )
        return False, "No hay licencia guardada.", None

    license_key = (stored.get("license_key", "") or "").strip()
    masked_key = _mask_license_key(license_key)
    if not license_key:
        _set_license_debug(
            product=get_license_product(),
            license_mode=os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower(),
            validation_mode="supabase_refresh",
            status="missing_local_license_key",
            masked_license_key="",
            last_error="stored_license_key_missing",
            plan="",
            tier="",
            modules=[],
        )
        return False, "La licencia guardada no tiene una clave valida.", None

    previous_info = db.get_license_info()
    previous_tier = previous_info.get("tier", "DEMO")
    previous_plan = previous_info.get("plan", previous_tier)
    hwid = get_current_hwid()
    if not hwid:
        hwid, _machine_details = generate_activation_id()

    logger.info(
        "Refresco online licencia inicio clave=%s tier_anterior=%s plan_anterior=%s",
        masked_key,
        previous_tier,
        previous_plan,
    )

    ok, message, remote_license = activate_license(
        license_key,
        hwid,
        get_license_product(),
        vendor_code=str(previous_info.get("vendor_code", "") or ""),
    )
    remote_status = _normalize_remote_status(remote_license)
    supabase_status = str(get_supabase_debug_state().get("status", "") or "").strip().lower()

    if (ok and remote_license and remote_status in {"suspendida", "bloqueada", "anulada", "revocada"}) or supabase_status == "inactive":
        fallback_plan = "BASICA" if bool(previous_info.get("plan_base_permanente")) else "DEMO"
        current_info = _persist_local_license_state(
            db,
            previous_info,
            target_plan=fallback_plan,
            status=remote_status or "suspendida",
        )
        return False, "La licencia fue suspendida. Contacta soporte.", current_info

    if not ok or not remote_license:
        if supabase_status == "not_found":
            if _has_valid_local_premium_cache(previous_info):
                return (
                    False,
                    "No pudimos validar la licencia en el servidor. Tu plan seguira activo hasta la fecha registrada localmente. Contacta soporte si el problema continua.",
                    previous_info,
                )
            fallback_plan = "BASICA" if bool(previous_info.get("plan_base_permanente")) else "DEMO"
            current_info = _persist_local_license_state(
                db,
                previous_info,
                target_plan=fallback_plan,
                status="sin_licencia_remota",
            )
            return False, "No encontramos una licencia activa para esta instalacion.", current_info

        if supabase_status in {"network_error", "http_error", "invalid_response", "not_configured"}:
            return (
                False,
                "No pudimos conectar con el servidor de licencias. Se mantiene el estado local hasta el vencimiento.",
                previous_info,
            )

        logger.warning(
            "Refresco online licencia fallo clave=%s tier_local=%s plan_local=%s error=%s",
            masked_key,
            previous_tier,
            previous_plan,
            message,
        )
        _set_license_debug(
            product=get_license_product(),
            license_mode=os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower(),
            validation_mode="supabase_refresh",
            status="online_error",
            masked_license_key=masked_key,
            last_error=message,
            plan=previous_plan,
            tier=previous_tier,
            modules=previous_info.get("modules", []),
        )
        return False, message, previous_info

    from licensing.permisos import get_modulos_debug_info

    remote_plan = remote_license.get("plan") or remote_license.get("tier") or remote_license.get("license_plan") or ""
    normalized_plan = db.normalize_license_plan(remote_plan)
    remote_modules = remote_license.get("modules") or remote_license.get("features") or remote_license.get("modulos") or []

    remote_license = _resolve_effective_license_data(remote_license)
    db.sync_license_from_remote(remote_license)
    refreshed_info = db.get_license_info()
    merged_license = dict(stored)
    merged_license.update(remote_license)
    guardar_licencia(license_key, merged_license)
    _save_sdk_cache(remote_license)
    modulos_debug = get_modulos_debug_info()

    logger.info(
        "Refresco online licencia ok clave=%s tier_anterior=%s plan_anterior=%s plan_supabase=%s plan_normalizado=%s sdk_modules=%s persisted_modules=%s final_modules=%s modules_source=%s sqlite_actualizado=%s",
        masked_key,
        previous_tier,
        previous_plan,
        remote_plan,
        normalized_plan,
        remote_modules,
        modulos_debug.get("persisted_modules", []),
        modulos_debug.get("final_modules", []),
        modulos_debug.get("final_source", "unknown"),
        "si",
    )
    _set_license_debug(
        product=get_license_product(),
        license_mode=os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower(),
        validation_mode="supabase_refresh",
        status="online_ok",
        masked_license_key=masked_key,
        last_error="",
        plan=refreshed_info.get("plan", normalized_plan),
        tier=refreshed_info.get("tier", normalized_plan),
        modules=remote_modules,
    )
    return True, "Licencia actualizada desde Supabase.", refreshed_info
