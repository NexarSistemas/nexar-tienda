import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

from flask import abort

from licensing.planes import get_modulos_activos as get_modulos_activos_env


logger = logging.getLogger(__name__)
SDK_REPO_PATH = Path(__file__).resolve().parent.parent.parent / "nexar_licencias"
_last_logged_source: str | None = None


def _log_source(source: str, message: str) -> None:
    global _last_logged_source
    if _last_logged_source == source:
        return
    logger.info(message)
    _last_logged_source = source


def _normalize_modules(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        return {module.strip().lower() for module in value.split(",") if module.strip()}
    if isinstance(value, dict):
        value = value.get("modules") or value.get("modulos") or value.get("modulos_activos")
    try:
        return {str(module).strip().lower() for module in value if str(module).strip()}
    except TypeError:
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
    if os.getenv("NEXAR_LICENSE_MODE", "dev").strip().lower() == "dev":
        _log_source("env", "Usando módulos desde .env")
        return get_modulos_activos_env()

    modules = _get_modulos_sdk()
    if modules:
        _log_source("sdk", "Usando módulos desde SDK")
        return modules

    _log_source("env", "Usando módulos desde .env")
    return get_modulos_activos_env()


def modulo_activo(nombre: str) -> bool:
    return str(nombre).strip().lower() in get_modulos_activos()


def require_modulo(nombre: str) -> bool:
    if not modulo_activo(nombre):
        abort(403)
    return True
