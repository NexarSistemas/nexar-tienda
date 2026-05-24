from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import database as db
from modules.arca.services import arca_client
from modules.arca.services.comprobantes_service import (
    ESTADOS_FINALES,
    obtener_comprobante_por_venta,
    obtener_siguiente_numero_comprobante,
    registrar_comprobante_fiscal,
    registrar_evento,
)
from services.arca_config_service import arca_modo_simulacion_activo, get_config


logger = logging.getLogger(__name__)

WSFE_TIPO_FACTURA_B = 6
WSFE_CONCEPTO_PRODUCTOS = 1
WSFE_DOC_TIPO_CONSUMIDOR_FINAL = 99
ARCA_TIPO_COMPROBANTE = "Factura B"
ALICUOTAS_IVA = {
    "0": {"id": 3, "rate": 0.0},
    "0%": {"id": 3, "rate": 0.0},
    "2.5": {"id": 9, "rate": 2.5},
    "2.5%": {"id": 9, "rate": 2.5},
    "5": {"id": 8, "rate": 5.0},
    "5%": {"id": 8, "rate": 5.0},
    "10.5": {"id": 4, "rate": 10.5},
    "10.5%": {"id": 4, "rate": 10.5},
    "21": {"id": 5, "rate": 21.0},
    "21%": {"id": 5, "rate": 21.0},
    "27": {"id": 6, "rate": 27.0},
    "27%": {"id": 6, "rate": 27.0},
}


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _to_float(value: object) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _normalizar_alicuota(label: object) -> dict[str, float | int]:
    raw = _clean_text(label).replace(",", ".")
    normalized = raw[:-1] if raw.endswith("%") else raw
    return ALICUOTAS_IVA.get(raw) or ALICUOTAS_IVA.get(normalized) or {"id": 5, "rate": 21.0}


def _fecha_wsfe(fecha_iso: object) -> str:
    raw = _clean_text(fecha_iso)
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        return datetime.now().strftime("%Y%m%d")


def calcular_pdf_path_futuro(*, venta_id: int, fecha_emision: object, punto_venta: int, numero_comprobante: int | None) -> str:
    raw = _clean_text(fecha_emision)
    try:
        fecha = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        fecha = datetime.now()

    base_dir = Path("data") / "arca" / "comprobantes" / fecha.strftime("%Y") / fecha.strftime("%m")
    filename = f"venta-{int(venta_id)}-pv-{int(punto_venta):04d}"
    if numero_comprobante:
        filename += f"-cbte-{int(numero_comprobante):08d}"

    # TODO Fase 8: generar el PDF final y crear la carpeta en disco antes de guardar el archivo.
    return (base_dir / f"{filename}.pdf").as_posix()


def _agrupar_iva(items: list[dict[str, object]]) -> list[dict[str, object]]:
    buckets: dict[int, dict[str, object]] = {}
    for item in items:
        subtotal = _to_float(item.get("subtotal"))
        if subtotal <= 0:
            continue

        alicuota = _normalizar_alicuota(item.get("iva"))
        rate = float(alicuota["rate"])
        base = round(subtotal / (1 + (rate / 100)), 2) if rate > 0 else subtotal
        importe_iva = round(subtotal - base, 2)
        bucket = buckets.setdefault(
            int(alicuota["id"]),
            {
                "Id": int(alicuota["id"]),
                "BaseImp": 0.0,
                "Importe": 0.0,
                "Alic": rate,
            },
        )
        bucket["BaseImp"] = round(float(bucket["BaseImp"]) + base, 2)
        bucket["Importe"] = round(float(bucket["Importe"]) + importe_iva, 2)
    return list(buckets.values())


def _serializar_respuesta_segura(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _build_respuesta_tecnica_segura(
    *,
    respuesta: dict[str, object],
    payload: dict[str, object],
    numero_comprobante: int,
    fecha_emision: str,
    pdf_path: str,
) -> str:
    resumen = {
        "resultado": _clean_text(respuesta.get("resultado")) or ("aprobado" if respuesta.get("ok") else "error"),
        "estado": _clean_text(respuesta.get("estado")) or "PENDIENTE",
        "tipo_comprobante": _clean_text(respuesta.get("tipo_comprobante")) or _clean_text(payload.get("tipo_comprobante")),
        "punto_venta": int(respuesta.get("punto_venta") or payload.get("punto_venta") or 0),
        "numero_comprobante": int(numero_comprobante or 0),
        "cae": _clean_text(respuesta.get("cae")),
        "cae_vencimiento": _clean_text(respuesta.get("cae_vencimiento")),
        "fecha_emision": fecha_emision,
        "importe_total": _to_float(respuesta.get("importe_total") or payload.get("totales", {}).get("importe_total")),
        "modo": _clean_text(respuesta.get("modo")) or _clean_text(payload.get("metadata", {}).get("modo_sugerido")) or "wsfe",
        "ambiente": _clean_text(respuesta.get("ambiente") or payload.get("metadata", {}).get("ambiente")) or "homologacion",
        "observaciones": list(respuesta.get("observaciones") or []),
        "pdf_path": pdf_path,
    }
    return _serializar_respuesta_segura(resumen)


def _obtener_venta(venta_id: int) -> dict[str, object] | None:
    venta = db.q("SELECT * FROM ventas WHERE id = ?", (int(venta_id),), fetchone=True)
    return dict(venta) if venta else None


def _obtener_items(venta_id: int) -> list[dict[str, object]]:
    return [dict(item) for item in db.get_venta_detalle(int(venta_id))]


def _comprobante_final_existente(venta_id: int) -> dict[str, object] | None:
    comprobante = obtener_comprobante_por_venta(int(venta_id))
    if comprobante and _clean_text(comprobante.get("estado")).upper() in ESTADOS_FINALES:
        return comprobante
    return None


def _build_payload_fiscal(venta: dict[str, object], items: list[dict[str, object]]) -> dict[str, object]:
    config = get_config()
    punto_venta = int(config.get("punto_venta") or 0) if _clean_text(config.get("punto_venta")) else 1
    total = _to_float(venta.get("total"))
    numero_sugerido = obtener_siguiente_numero_comprobante(
        punto_venta=punto_venta,
        tipo_comprobante=ARCA_TIPO_COMPROBANTE,
    )
    iva = _agrupar_iva(items)
    importe_neto = round(sum(float(item["BaseImp"]) for item in iva), 2)
    importe_iva = round(sum(float(item["Importe"]) for item in iva), 2)
    fecha_emision = _clean_text(venta.get("fecha")) or datetime.now().strftime("%Y-%m-%d")
    pdf_path = calcular_pdf_path_futuro(
        venta_id=int(venta["id"]),
        fecha_emision=fecha_emision,
        punto_venta=punto_venta,
        numero_comprobante=numero_sugerido,
    )
    return {
        "venta_id": int(venta["id"]),
        "tipo_comprobante": ARCA_TIPO_COMPROBANTE,
        "tipo_cbte": WSFE_TIPO_FACTURA_B,
        "punto_venta": punto_venta,
        "numero_sugerido": numero_sugerido,
        "fecha_emision": fecha_emision,
        "fecha_emision_wsfe": _fecha_wsfe(fecha_emision),
        "cliente": {
            "nombre": _clean_text(venta.get("cliente_nombre")) or "Mostrador",
            "doc_tipo": WSFE_DOC_TIPO_CONSUMIDOR_FINAL,
            "doc_nro": 0,
        },
        "totales": {
            "importe_total": total,
            "importe_neto": importe_neto,
            "importe_iva": importe_iva,
            "importe_exento": 0.0,
            "importe_tributos": 0.0,
        },
        "wsfe": {
            "Concepto": WSFE_CONCEPTO_PRODUCTOS,
            "DocTipo": WSFE_DOC_TIPO_CONSUMIDOR_FINAL,
            "DocNro": 0,
            "CbteTipo": WSFE_TIPO_FACTURA_B,
            "PtoVta": punto_venta,
            "CbteDesde": numero_sugerido,
            "CbteHasta": numero_sugerido,
            "CbteFch": _fecha_wsfe(fecha_emision),
            "ImpTotal": total,
            "ImpTotConc": 0.0,
            "ImpNeto": importe_neto,
            "ImpOpEx": 0.0,
            "ImpTrib": 0.0,
            "ImpIVA": importe_iva,
            "MonId": "PES",
            "MonCotiz": 1.0,
            "Iva": iva,
        },
        "items": [
            {
                "producto_id": int(item.get("producto_id") or 0),
                "codigo_interno": _clean_text(item.get("codigo_interno")),
                "descripcion": _clean_text(item.get("descripcion")),
                "cantidad": _to_float(item.get("cantidad")),
                "precio_unitario": _to_float(item.get("precio_unitario")),
                "subtotal": _to_float(item.get("subtotal")),
                "iva": _clean_text(item.get("iva")) or "21%",
            }
            for item in items
        ],
        "metadata": {
            "ambiente": _clean_text(config.get("ambiente")).lower() or "homologacion",
            "modo_sugerido": "simulacion" if arca_modo_simulacion_activo() else "wsfe",
            "pdf_path_sugerido": pdf_path,
        },
    }


def _resultado_error(*, error_code: str, mensaje: str, venta_id: int | None = None, payload: dict[str, object] | None = None) -> dict[str, object]:
    if venta_id:
        registrar_evento(
            nivel="warning",
            mensaje="Facturación ARCA desde venta fallida",
            detalle={
                "venta_id": int(venta_id),
                "error_code": error_code,
                "mensaje": mensaje,
                "payload_preview": {
                    "tipo_comprobante": (payload or {}).get("tipo_comprobante"),
                    "punto_venta": (payload or {}).get("punto_venta"),
                    "numero_sugerido": (payload or {}).get("numero_sugerido"),
                },
            },
        )
    return {
        "ok": False,
        "error_code": error_code,
        "mensaje": mensaje,
        "modo": _clean_text((payload or {}).get("metadata", {}).get("modo_sugerido")) or "wsfe",
    }


def facturar_venta_desde_existente(venta_id: int | None) -> dict[str, object]:
    if not venta_id:
        return _resultado_error(error_code="venta_invalida", mensaje="Venta inválida.")

    venta = _obtener_venta(int(venta_id))
    if not venta:
        return _resultado_error(
            error_code="venta_no_encontrada",
            mensaje="La venta indicada no existe.",
            venta_id=int(venta_id),
        )

    if int(venta.get("anulada") or 0):
        return _resultado_error(
            error_code="venta_anulada",
            mensaje="No se puede facturar con ARCA una venta anulada.",
            venta_id=int(venta_id),
        )

    comprobante_existente = _comprobante_final_existente(int(venta_id))
    if comprobante_existente:
        return {
            "ok": False,
            "error_code": "duplicado",
            "mensaje": "La venta ya fue facturada con ARCA.",
            "comprobante": comprobante_existente,
            "ya_existia": True,
            "modo": _clean_text(comprobante_existente.get("modo")) or "wsfe",
        }

    items = _obtener_items(int(venta_id))
    if not items:
        return _resultado_error(
            error_code="venta_sin_items",
            mensaje="La venta no tiene ítems para facturar.",
            venta_id=int(venta_id),
        )

    payload = _build_payload_fiscal(venta, items)
    try:
        respuesta = arca_client.emitir_factura(payload)
    except Exception:
        logger.exception("Error técnico facturando venta %s con ARCA", venta_id)
        return _resultado_error(
            error_code="error_arca",
            mensaje="No se pudo generar la factura ARCA para esta venta.",
            venta_id=int(venta_id),
            payload=payload,
        )

    if not respuesta.get("ok"):
        mensaje = _clean_text(respuesta.get("mensaje")) or "ARCA rechazó la facturación de la venta."
        logger.warning(
            "Facturación ARCA rechazada venta_id=%s error_code=%s mensaje=%s",
            venta_id,
            respuesta.get("error_code"),
            mensaje,
        )
        return _resultado_error(
            error_code=_clean_text(respuesta.get("error_code")) or "error_arca",
            mensaje=mensaje,
            venta_id=int(venta_id),
            payload=payload,
        )

    fecha_emision = _clean_text(respuesta.get("fecha_emision")) or _clean_text(payload.get("fecha_emision"))
    numero_comprobante = int(
        respuesta.get("numero_comprobante")
        or respuesta.get("numero")
        or payload.get("numero_sugerido")
        or 0
    )
    pdf_path = _clean_text(respuesta.get("pdf_path")) or calcular_pdf_path_futuro(
        venta_id=int(venta_id),
        fecha_emision=fecha_emision,
        punto_venta=int(respuesta.get("punto_venta") or payload.get("punto_venta") or 1),
        numero_comprobante=numero_comprobante,
    )
    respuesta_safe = {
        "resultado": _clean_text(respuesta.get("resultado")) or "aprobado",
        "cae": _clean_text(respuesta.get("cae")),
        "cae_vencimiento": _clean_text(respuesta.get("cae_vencimiento")),
        "numero_comprobante": numero_comprobante,
        "observaciones": list(respuesta.get("observaciones") or []),
        "modo": _clean_text(respuesta.get("modo")) or _clean_text(payload.get("metadata", {}).get("modo_sugerido")),
    }
    comprobante = registrar_comprobante_fiscal(
        venta_id=int(venta_id),
        tipo_comprobante=_clean_text(respuesta.get("tipo_comprobante")) or _clean_text(payload.get("tipo_comprobante")),
        punto_venta=int(respuesta.get("punto_venta") or payload.get("punto_venta") or 1),
        numero_comprobante=numero_comprobante,
        cae=_clean_text(respuesta.get("cae")),
        cae_vencimiento=_clean_text(respuesta.get("cae_vencimiento")),
        importe_total=_to_float(respuesta.get("importe_total") or payload.get("totales", {}).get("importe_total")),
        estado=_clean_text(respuesta.get("estado")) or "AUTORIZADO",
        fecha_emision=fecha_emision,
        payload=payload,
        respuesta=respuesta_safe,
        respuesta_raw=_build_respuesta_tecnica_segura(
            respuesta=dict(respuesta),
            payload=payload,
            numero_comprobante=numero_comprobante,
            fecha_emision=fecha_emision,
            pdf_path=pdf_path,
        ),
        pdf_path=pdf_path,
        modo=_clean_text(respuesta.get("modo")) or _clean_text(payload.get("metadata", {}).get("modo_sugerido")) or "wsfe",
        ambiente=_clean_text(respuesta.get("ambiente") or payload.get("metadata", {}).get("ambiente")) or "homologacion",
    )
    registrar_evento(
        comprobante_id=comprobante.get("id"),
        nivel="info",
        mensaje="Facturación ARCA desde venta exitosa",
        detalle={
            "venta_id": int(venta_id),
            "numero_comprobante": numero_comprobante,
            "cae": _clean_text(respuesta.get("cae")),
            "modo": comprobante.get("modo"),
            "pdf_path": pdf_path,
        },
    )
    return {
        "ok": True,
        "error_code": "",
        "mensaje": "Factura ARCA generada correctamente para la venta.",
        "modo": comprobante.get("modo"),
        "comprobante": comprobante,
        "payload": payload,
        "respuesta": respuesta_safe,
    }
