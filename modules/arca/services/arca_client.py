from __future__ import annotations

from modules.arca.services.comprobantes_service import registrar_evento


def _placeholder_response(operacion: str, extra: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "ok": False,
        "modo": "placeholder",
        "operacion": operacion,
        "mensaje": "Conexión real con ARCA pendiente de implementación.",
        **(extra or {}),
    }


def probar_conexion() -> dict[str, object]:
    registrar_evento(
        nivel="warning",
        mensaje="Intento placeholder de conexión ARCA",
        detalle={"operacion": "probar_conexion"},
    )
    return _placeholder_response("probar_conexion")


def obtener_ultimo_comprobante() -> dict[str, object]:
    return _placeholder_response("obtener_ultimo_comprobante")


def emitir_comprobante(data: dict[str, object] | None = None) -> dict[str, object]:
    payload = dict(data or {})
    return _placeholder_response(
        "emitir_comprobante",
        {"payload": payload},
    )
