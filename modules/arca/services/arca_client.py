from __future__ import annotations

from datetime import datetime, timedelta

from services.arca.auth_service import (
    get_connection_status as obtener_estado_conexion,
    probar_conexion_wsaa,
)
from services.arca.wsfe_service import (
    get_last_wsfe_test as obtener_ultimo_resultado_wsfe,
    probar_wsfe,
)
from services.arca_config_service import arca_esta_configurado, arca_modo_simulacion_activo, get_config


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


def emitir_factura(payload: dict[str, object] | None = None) -> dict[str, object]:
    data = dict(payload or {})
    config = get_config()
    punto_venta = int(data.get("punto_venta") or config.get("punto_venta") or 1)
    numero_comprobante = int(data.get("numero_sugerido") or 0)
    fecha_emision = str(data.get("fecha_emision") or datetime.now().strftime("%Y-%m-%d")).strip()
    importe_total = float((data.get("totales") or {}).get("importe_total") or 0)

    if arca_modo_simulacion_activo():
        cae = f"{datetime.now():%y%m%d%H%M%S}{int(data.get('venta_id') or 0) % 100:02d}"
        return {
            "ok": True,
            "modo": "simulacion",
            "estado": "MODO_TEST",
            "resultado": "aprobado_simulado",
            "mensaje": "Comprobante ARCA simulado generado correctamente.",
            "tipo_comprobante": str(data.get("tipo_comprobante") or "Factura B"),
            "punto_venta": punto_venta,
            "numero_comprobante": numero_comprobante,
            "cae": cae,
            "cae_vencimiento": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "importe_total": importe_total,
            "fecha_emision": fecha_emision,
            "ambiente": "simulacion",
            "pdf_path": str((data.get("metadata") or {}).get("pdf_path_sugerido") or ""),
            "observaciones": [],
        }

    if not arca_esta_configurado():
        return {
            "ok": False,
            "modo": "wsfe",
            "error_code": "ERROR_CONFIG",
            "mensaje": "Configuración ARCA incompleta para emisión real.",
        }

    return {
        "ok": False,
        "modo": "wsfe",
        "error_code": "SIN_CONEXION",
        "mensaje": "La emisión WSFE real todavía no está habilitada en esta fase.",
    }


def emitir_comprobante(data: dict[str, object] | None = None) -> dict[str, object]:
    from modules.arca.services.facturacion_desde_venta_service import facturar_venta_desde_existente

    payload = dict(data or {})
    venta_id = payload.get("venta_id")
    return facturar_venta_desde_existente(int(venta_id or 0) if venta_id is not None else None)
