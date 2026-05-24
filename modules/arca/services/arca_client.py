from __future__ import annotations

from services.arca.auth_service import (
    get_connection_status as obtener_estado_conexion,
    probar_conexion_wsaa,
)


def _placeholder_response(operacion: str, extra: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "ok": False,
        "modo": "placeholder",
        "operacion": operacion,
        "mensaje": "Conexión real con ARCA pendiente de implementación.",
        **(extra or {}),
    }


def probar_conexion() -> dict[str, object]:
    return probar_conexion_wsaa()


def obtener_ultimo_comprobante() -> dict[str, object]:
    return _placeholder_response("obtener_ultimo_comprobante")


def emitir_comprobante(data: dict[str, object] | None = None) -> dict[str, object]:
    payload = dict(data or {})
    return _placeholder_response(
        "emitir_comprobante",
        {"payload": payload},
    )
