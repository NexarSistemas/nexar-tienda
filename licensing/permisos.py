from flask import abort

from licensing.planes import get_modulos_activos


def modulo_activo(nombre: str) -> bool:
    return str(nombre).strip().lower() in get_modulos_activos()


def require_modulo(nombre: str) -> bool:
    if not modulo_activo(nombre):
        abort(403)
    return True
