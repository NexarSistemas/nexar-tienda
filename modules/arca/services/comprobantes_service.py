from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import database as db


ESTADOS_FINALES = {"AUTORIZADO", "AUTORIZADO_SIMULADO", "MODO_TEST"}
ESTADOS_VALIDOS = {
    "PENDIENTE",
    "AUTORIZADO",
    "ERROR_WS",
    "ERROR_CONFIG",
    "SIN_CONEXION",
    "MODO_TEST",
    "AUTORIZADO_SIMULADO",
}


def _now() -> str:
    return datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_json_loads(raw_value: object) -> dict[str, object]:
    raw = _clean_text(raw_value)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _row_to_dict(row) -> dict[str, object] | None:
    if not row:
        return None
    data = dict(row)
    numero = data.get("numero_comprobante")
    if numero in (None, ""):
        numero = data.get("numero")
    data["numero_comprobante"] = numero
    data["numero"] = numero
    importe_total = data.get("importe_total")
    if importe_total in (None, ""):
        importe_total = data.get("total")
    data["importe_total"] = float(importe_total or 0)
    data["total"] = data["importe_total"]
    data["modo"] = _clean_text(data.get("modo")) or "wsfe"
    data["payload"] = _safe_json_loads(data.get("payload_json"))
    data["respuesta"] = _safe_json_loads(data.get("respuesta_json"))
    data["numero_formateado"] = formatear_numero_comprobante(data)
    data["comprobante_formateado"] = formatear_comprobante(data)
    data["pdf_generado"] = bool(_clean_text(data.get("pdf_path")) and Path(_clean_text(data.get("pdf_path"))).exists())
    data["pdf_estado"] = "generado" if data["pdf_generado"] else "pendiente"
    return data


def _serialize_json(data: dict[str, object] | None) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def listar_comprobantes() -> list[dict[str, object]]:
    rows = db.q(
        """
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae,
               cae_vencimiento, importe_total, estado, fecha_emision, respuesta_raw, pdf_path, modo, ambiente,
               total, payload_json, respuesta_json, error_mensaje, created_at, updated_at
        FROM arca_comprobantes
        ORDER BY datetime(COALESCE(created_at, '1970-01-01 00:00:00')) DESC, id DESC
        """
    )
    return [item for row in rows if (item := _row_to_dict(row))]


def obtener_comprobante_por_id(comprobante_id: int | None) -> dict[str, object] | None:
    if not comprobante_id:
        return None
    row = db.q(
        """
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae,
               cae_vencimiento, importe_total, estado, fecha_emision, respuesta_raw, pdf_path, modo, ambiente,
               total, payload_json, respuesta_json, error_mensaje, created_at, updated_at
        FROM arca_comprobantes
        WHERE id = ?
        LIMIT 1
        """,
        (int(comprobante_id),),
        fetchone=True,
    )
    return _row_to_dict(row)


def obtener_comprobante_por_venta(venta_id: int | None) -> dict[str, object] | None:
    if not venta_id:
        return None
    row = db.q(
        """
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae,
               cae_vencimiento, importe_total, estado, fecha_emision, respuesta_raw, pdf_path, modo, ambiente,
               total, payload_json, respuesta_json, error_mensaje, created_at, updated_at
        FROM arca_comprobantes
        WHERE venta_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(venta_id),),
        fetchone=True,
    )
    return _row_to_dict(row)


def comprobante_es_final(comprobante: dict[str, object] | None) -> bool:
    if not comprobante:
        return False
    return _clean_text(comprobante.get("estado")).upper() in ESTADOS_FINALES


def venta_tiene_comprobante_final(venta_id: int | None) -> bool:
    return comprobante_es_final(obtener_comprobante_por_venta(venta_id))


def formatear_numero_comprobante(comprobante: dict[str, object] | None) -> str:
    if not comprobante:
        return "-"
    punto_venta = int(comprobante.get("punto_venta") or 0)
    numero = int(comprobante.get("numero_comprobante") or comprobante.get("numero") or 0)
    if punto_venta <= 0 or numero <= 0:
        return "-"
    return f"{punto_venta:04d}-{numero:08d}"


def formatear_comprobante(comprobante: dict[str, object] | None) -> str:
    if not comprobante:
        return "-"
    tipo = _clean_text(comprobante.get("tipo_comprobante")) or "Comprobante"
    numero = formatear_numero_comprobante(comprobante)
    if numero == "-":
        return tipo
    return f"{tipo} {numero}"


def obtener_comprobantes_por_venta_ids(venta_ids: list[int]) -> dict[int, dict[str, object]]:
    ids = [int(venta_id) for venta_id in venta_ids if int(venta_id or 0) > 0]
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    rows = db.q(
        f"""
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae,
               cae_vencimiento, importe_total, estado, fecha_emision, respuesta_raw, pdf_path, modo, ambiente,
               total, payload_json, respuesta_json, error_mensaje, created_at, updated_at
        FROM arca_comprobantes
        WHERE venta_id IN ({placeholders})
        ORDER BY id DESC
        """,
        tuple(ids),
    )
    resultado: dict[int, dict[str, object]] = {}
    for row in rows:
        item = _row_to_dict(row)
        if not item:
            continue
        venta_id = int(item.get("venta_id") or 0)
        if venta_id and venta_id not in resultado:
            resultado[venta_id] = item
    return resultado


def obtener_siguiente_numero_comprobante(punto_venta: int, tipo_comprobante: str) -> int:
    row = db.q(
        """
        SELECT MAX(COALESCE(numero_comprobante, numero)) AS max_num
        FROM arca_comprobantes
        WHERE punto_venta = ? AND tipo_comprobante = ?
        """,
        (int(punto_venta), _clean_text(tipo_comprobante)),
        fetchone=True,
    )
    last_number = int((row["max_num"] if row and row["max_num"] is not None else 0) or 0)
    return last_number + 1
def _upsert_comprobante(
    *,
    venta_id: int,
    tipo_comprobante: str,
    punto_venta: int,
    numero_comprobante: int | None,
    cae: str,
    cae_vencimiento: str,
    estado: str,
    fecha_emision: str = "",
    respuesta_raw: str = "",
    pdf_path: str | None = None,
    modo: str,
    total: float,
    payload: dict[str, object] | None = None,
    respuesta: dict[str, object] | None = None,
    error_mensaje: str = "",
    ambiente: str = "homologacion",
) -> dict[str, object]:
    now = _now()
    existing = obtener_comprobante_por_venta(venta_id)
    estado_normalizado = _clean_text(estado).upper() or "PENDIENTE"
    if estado_normalizado not in ESTADOS_VALIDOS:
        estado_normalizado = "PENDIENTE"

    params = (
        _clean_text(tipo_comprobante),
        int(punto_venta or 0),
        numero_comprobante,
        numero_comprobante,
        _clean_text(cae),
        _clean_text(cae_vencimiento),
        float(total or 0),
        estado_normalizado,
        _clean_text(fecha_emision),
        _clean_text(respuesta_raw),
        _clean_text(pdf_path),
        _clean_text(modo).lower() or "wsfe",
        _clean_text(ambiente).lower() or "homologacion",
        float(total or 0),
        _serialize_json(payload),
        _serialize_json(respuesta),
        _clean_text(error_mensaje),
        now,
    )

    if existing:
        db.q(
            """
            UPDATE arca_comprobantes
            SET tipo_comprobante = ?, punto_venta = ?, numero = ?, numero_comprobante = ?, cae = ?,
                cae_vencimiento = ?, importe_total = ?, estado = ?, fecha_emision = ?, respuesta_raw = ?,
                pdf_path = ?, modo = ?, ambiente = ?, total = ?, payload_json = ?, respuesta_json = ?,
                error_mensaje = ?, updated_at = ?
            WHERE id = ?
            """,
            (*params, existing["id"]),
            commit=True,
        )
    else:
        db.q(
            """
            INSERT INTO arca_comprobantes
            (venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae, cae_vencimiento,
             importe_total, estado, fecha_emision, respuesta_raw, pdf_path, modo, ambiente, total, payload_json,
             respuesta_json, error_mensaje, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(venta_id),
                *params[:-1],
                now,
                now,
            ),
            commit=True,
        )
    return obtener_comprobante_por_venta(venta_id) or {}


def registrar_comprobante_fiscal(
    *,
    venta_id: int,
    tipo_comprobante: str,
    punto_venta: int,
    numero_comprobante: int | None,
    cae: str,
    cae_vencimiento: str,
    importe_total: float,
    estado: str,
    fecha_emision: str,
    payload: dict[str, object] | None = None,
    respuesta: dict[str, object] | None = None,
    respuesta_raw: str = "",
    pdf_path: str | None = None,
    modo: str = "wsfe",
    ambiente: str = "homologacion",
    error_mensaje: str = "",
) -> dict[str, object]:
    return _upsert_comprobante(
        venta_id=venta_id,
        tipo_comprobante=tipo_comprobante,
        punto_venta=punto_venta,
        numero_comprobante=numero_comprobante,
        cae=cae,
        cae_vencimiento=cae_vencimiento,
        estado=estado,
        fecha_emision=fecha_emision,
        respuesta_raw=respuesta_raw,
        pdf_path=pdf_path,
        modo=modo,
        total=importe_total,
        payload=payload,
        respuesta=respuesta,
        error_mensaje=error_mensaje,
        ambiente=ambiente,
    )


def actualizar_pdf_path(comprobante_id: int | None, pdf_path: str | None) -> dict[str, object] | None:
    if not comprobante_id:
        return None
    now = _now()
    db.q(
        """
        UPDATE arca_comprobantes
        SET pdf_path = ?, updated_at = ?
        WHERE id = ?
        """,
        (_clean_text(pdf_path), now, int(comprobante_id)),
        commit=True,
    )
    return obtener_comprobante_por_id(int(comprobante_id))


def registrar_comprobante_pendiente(
    *,
    venta_id: int | None = None,
    tipo_comprobante: str = "",
    punto_venta: int | None = None,
    numero: int | None = None,
    total: float = 0.0,
    payload: dict[str, object] | None = None,
    ambiente: str = "homologacion",
    estado: str = "pendiente",
) -> int:
    comprobante = _upsert_comprobante(
        venta_id=int(venta_id or 0),
        tipo_comprobante=tipo_comprobante,
        punto_venta=int(punto_venta or 0),
        numero_comprobante=numero,
        cae="",
        cae_vencimiento="",
        estado=estado,
        fecha_emision="",
        respuesta_raw="",
        pdf_path=None,
        modo="wsfe",
        total=float(total or 0),
        payload=payload,
        respuesta={},
        ambiente=ambiente,
    )
    return int(comprobante.get("id") or 0)


def registrar_evento(
    *,
    comprobante_id: int | None = None,
    nivel: str = "info",
    mensaje: str = "",
    detalle: dict[str, object] | None = None,
) -> int:
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    return int(
        db.q(
            """
            INSERT INTO arca_eventos (comprobante_id, nivel, mensaje, detalle_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                comprobante_id,
                str(nivel or "info").strip().lower(),
                str(mensaje or "").strip(),
                json.dumps(detalle or {}, ensure_ascii=False),
                now,
            ),
            commit=True,
        )
    )


def emitir_comprobante_desde_venta(venta_id: int | None) -> dict[str, object]:
    from modules.arca.services.facturacion_desde_venta_service import facturar_venta_desde_existente

    return facturar_venta_desde_existente(venta_id)
