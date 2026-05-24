from __future__ import annotations

from modules.arca.services.comprobantes_service import emitir_comprobante_desde_venta
from services.arca.auth_service import (
    get_connection_status as obtener_estado_conexion,
    probar_conexion_wsaa,
)
from services.arca.wsfe_service import (
    get_last_wsfe_test as obtener_ultimo_resultado_wsfe,
    probar_wsfe,
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


def probar_wsfe_conexion() -> dict[str, object]:
    return probar_wsfe()


def obtener_estado_wsfe() -> dict[str, object]:
    return obtener_ultimo_resultado_wsfe()


def obtener_ultimo_comprobante() -> dict[str, object]:
    return _placeholder_response("obtener_ultimo_comprobante")


def emitir_comprobante(data: dict[str, object] | None = None) -> dict[str, object]:
    payload = dict(data or {})
    venta_id = payload.get("venta_id")
    return emitir_comprobante_desde_venta(int(venta_id or 0) if venta_id is not None else None)
