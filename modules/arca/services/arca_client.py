from __future__ import annotations


def probar_conexion() -> dict[str, object]:
    return {
        "ok": False,
        "modo": "placeholder",
        "mensaje": "Conexión real con ARCA pendiente de implementación.",
    }


def emitir_comprobante_mock(data: dict[str, object] | None = None) -> dict[str, object]:
    payload = dict(data or {})
    return {
        "ok": False,
        "modo": "placeholder",
        "mensaje": "Conexión real con ARCA pendiente de implementación.",
        "payload": payload,
    }
