import os

from flask import abort


def get_modulos_activos() -> set[str]:
    raw_modules = os.getenv("NEXAR_MODULES", "")
    modules = {module.strip().lower() for module in raw_modules.split(",") if module.strip()}
    return modules or {"core"}


def modulo_activo(nombre: str) -> bool:
    return str(nombre).strip().lower() in get_modulos_activos()


def require_modulo(nombre: str) -> bool:
    if not modulo_activo(nombre):
        abort(403)
    return True
