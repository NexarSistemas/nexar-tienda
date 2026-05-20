import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from flask import abort

from licensing.planes import (
    PLANES as TIER_MODULES_MAP,
    get_modulos_activos as get_modulos_activos_env,
    get_modulos_extra,
    normalize_plan,
)


logger = logging.getLogger(__name__)
SDK_REPO_PATH = Path(__file__).resolve().parent.parent.parent / "nexar_licencias"
_last_logged_source: str | None = None
_last_modules_source: str | None = None


def _apply_extra_modules(base_modules: set[str], source: str) -> set[str]:
    extra_modules = get_modulos_extra()
    if not extra_modules:
        return set(base_modules)
    _set_source(f"{source}+env")
    return set(base_modules) | extra_modules


def _log_source(source: str, message: str) -> None:
    global _last_logged_source, _last_modules_source
    _last_modules_source = source
    if _last_logged_source == source:
        return
    logger.info(message)
    _last_logged_source = source


def _set_source(source: str) -> None:
    global _last_modules_source
    _last_modules_source = source


def _normalize_modules(value: Any) -> set[str]:
    """Normaliza un valor a conjunto de módulos en minúsculas."""
    if not value:
        return set()
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("["):
            try:
                value = json.loads(raw)
            except Exception:
                value = []
        else:
            return {module.strip().lower() for module in raw.split(",") if module.strip()}
    if isinstance(value, dict):
        value = value.get("modules") or value.get("modulos") or value.get("modulos_activos")
    try:
        return {str(module).strip().lower() for module in value if str(module).strip()}
    except TypeError:
        return set()


def _normalize_tier(tier: str) -> str:
    """Normaliza alias de tier a canonical form."""
    return normalize_plan(tier, default="DEMO")


def _get_modulos_from_tier(tier: str = None) -> set[str]:
    """Obtiene módulos asociados a un tier."""
    if not tier:
        return set()
    tier_normalized = _normalize_tier(tier)
    return TIER_MODULES_MAP.get(tier_normalized, TIER_MODULES_MAP['DEMO']).copy()


def _get_tier_from_db() -> str:
    """Lee license_tier desde la base de datos."""
    try:
        from database import get_license_tier_from_db as db_get_tier
        return db_get_tier()
    except Exception:
        return 'DEMO'


def _get_modulos_from_db_config() -> set[str]:
    """Lee módulos remotos persistidos localmente."""
    try:
        from database import get_config

        cfg = get_config()
        return _normalize_modules(cfg.get("license_modules", "[]"))
    except Exception:
        return set()


def _import_sdk():
    sdk_path = str(SDK_REPO_PATH)
    if SDK_REPO_PATH.exists() and sdk_path not in sys.path:
        sys.path.append(sdk_path)
    return importlib.import_module("nexar_licencias")


def _get_modulos_sdk() -> set[str]:
    try:
        sdk = _import_sdk()
    except Exception:
        return set()

    candidates = (
        (sdk, "get_modulos_activos"),
        (sdk, "obtener_modulos_activos"),
        (sdk, "get_active_modules"),
        (sdk, "active_modules"),
    )
    for module, attr_name in candidates:
        attr = getattr(module, attr_name, None)
        try:
            value = attr() if callable(attr) else attr
        except TypeError:
            continue
        except Exception:
            continue
        modules = _normalize_modules(value)
        if modules:
            return modules

    return set()


def get_modulos_activos() -> set[str]:
    """
    Obtiene módulos activos en el siguiente orden de prioridad:

    DEV mode (NEXAR_LICENSE_MODE=dev):
      1. NEXAR_MODULES env var si está definida
      2. Mapeo de NEXAR_PLAN a módulos si está definida

    PROD mode (NEXAR_LICENSE_MODE=prod):
      1. SDK nexar_licencias si devuelve módulos explícitamente
      2. Módulos persistidos en SQLite/config
      3. Mapping central por plan normalizado
    """
    mode = os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower()

    if mode == "dev":
        _log_source("env", "DEV mode: usando módulos desde .env")
        return get_modulos_activos_env()

    # Modo PROD: SDK -> módulos persistidos filtrados por plan efectivo -> mapping por plan
    modules = _get_modulos_sdk()
    if modules:
        _log_source("sdk", "PROD mode: usando módulos desde SDK")
        return _apply_extra_modules(modules, "sdk")

    try:
        from database import get_license_info

        license_info = get_license_info()
        effective_tier = _normalize_tier(license_info.get("tier", "DEMO"))
        if str(license_info.get("tier", "")).strip().upper() == "SIN_PLAN":
            return _apply_extra_modules(set(), "db_effective_none")
    except Exception:
        effective_tier = _get_tier_from_db()

    tier_modules = _get_modulos_from_tier(effective_tier)
    modules_from_config = _get_modulos_from_db_config()
    if modules_from_config:
        filtered_modules = modules_from_config & tier_modules
        if filtered_modules:
            source = "db_modules" if filtered_modules == modules_from_config else "db_modules_filtered"
            _log_source(source, "PROD mode: usando módulos persistidos en DB")
            return _apply_extra_modules(filtered_modules, source)

    # Leer tier desde DB y mapear a módulos
    try:
        modules_from_tier = _get_modulos_from_tier(effective_tier)
        if modules_from_tier:
            _log_source("db", f"PROD mode: usando módulos desde DB tier '{effective_tier}'")
            return _apply_extra_modules(modules_from_tier, "db")
    except Exception as e:
        logger.debug(f"Error leyendo tier desde DB: {e}")

    _set_source("fallback")
    logger.info("PROD mode: sin módulos remotos ni persistidos, usando fallback core")
    return _apply_extra_modules({"core"}, "fallback")


def get_modulos_debug_info() -> dict[str, object]:
    mode = os.getenv("NEXAR_LICENSE_MODE", "prod").strip().lower()
    persisted = _get_modulos_from_db_config()
    tier = _get_tier_from_db() if mode != "dev" else normalize_plan(os.getenv("NEXAR_PLAN", "DEMO"), default="DEMO")
    tier_modules = _get_modulos_from_tier(tier)
    env_modules = get_modulos_extra()
    sdk_modules = _get_modulos_sdk() if mode != "dev" else set()
    final_modules = get_modulos_activos()
    return {
        "mode": mode,
        "tier": tier,
        "sdk_modules": sorted(sdk_modules),
        "persisted_modules": sorted(persisted),
        "tier_modules": sorted(tier_modules),
        "env_modules": sorted(env_modules),
        "final_modules": sorted(final_modules),
        "final_source": _last_modules_source or "unknown",
    }


def modulo_activo(nombre: str) -> bool:
    return str(nombre).strip().lower() in get_modulos_activos()


def require_modulo(nombre: str) -> bool:
    if not modulo_activo(nombre):
        abort(403)
    return True
