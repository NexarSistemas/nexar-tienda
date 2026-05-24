from __future__ import annotations

import json
from datetime import datetime, timedelta

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
    data["modo"] = _clean_text(data.get("modo")) or "wsfe"
    data["payload"] = _safe_json_loads(data.get("payload_json"))
    data["respuesta"] = _safe_json_loads(data.get("respuesta_json"))
    return data


def _serialize_json(data: dict[str, object] | None) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def listar_comprobantes() -> list[dict[str, object]]:
    rows = db.q(
        """
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae,
               cae_vencimiento, estado, modo, ambiente, total, payload_json, respuesta_json, error_mensaje,
               created_at, updated_at
        FROM arca_comprobantes
        ORDER BY datetime(COALESCE(created_at, '1970-01-01 00:00:00')) DESC, id DESC
        """
    )
    return [item for row in rows if (item := _row_to_dict(row))]


def obtener_comprobante_por_venta(venta_id: int | None) -> dict[str, object] | None:
    if not venta_id:
        return None
    row = db.q(
        """
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, numero_comprobante, cae,
               cae_vencimiento, estado, modo, ambiente, total, payload_json, respuesta_json, error_mensaje,
               created_at, updated_at
        FROM arca_comprobantes
        WHERE venta_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(venta_id),),
        fetchone=True,
    )
    return _row_to_dict(row)


def _next_simulated_number(punto_venta: int, tipo_comprobante: str) -> int:
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


def _simulated_cae(venta_id: int) -> str:
    return f"{datetime.now():%y%m%d%H%M%S}{int(venta_id) % 100:02d}"


def _upsert_comprobante(
    *,
    venta_id: int,
    tipo_comprobante: str,
    punto_venta: int,
    numero_comprobante: int | None,
    cae: str,
    cae_vencimiento: str,
    estado: str,
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
        estado_normalizado,
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
                cae_vencimiento = ?, estado = ?, modo = ?, ambiente = ?, total = ?, payload_json = ?,
                respuesta_json = ?, error_mensaje = ?, updated_at = ?
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
             estado, modo, ambiente, total, payload_json, respuesta_json, error_mensaje, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    if not venta_id:
        return {
            "ok": False,
            "error_code": "venta_invalida",
            "mensaje": "Venta inválida.",
        }

    venta = db.q("SELECT * FROM ventas WHERE id = ?", (int(venta_id),), fetchone=True)
    if not venta:
        return {
            "ok": False,
            "error_code": "venta_no_encontrada",
            "mensaje": "La venta indicada no existe.",
        }

    comprobante_existente = obtener_comprobante_por_venta(int(venta_id))
    if comprobante_existente and _clean_text(comprobante_existente.get("estado")).upper() in ESTADOS_FINALES:
        return {
            "ok": False,
            "error_code": "duplicado",
            "mensaje": "La venta ya tiene un comprobante ARCA registrado.",
            "comprobante": comprobante_existente,
            "ya_existia": True,
        }

    from services.arca_config_service import (
        arca_esta_configurado,
        arca_modo_simulacion_activo,
        get_config,
    )

    config = get_config()
    punto_venta = int(config.get("punto_venta") or 0) if str(config.get("punto_venta") or "").strip() else 0
    if punto_venta <= 0:
        punto_venta = 1

    tipo_comprobante = "Factura B"
    total = float(venta["total"] or 0)
    simulacion = arca_modo_simulacion_activo()
    ambiente = _clean_text(config.get("ambiente")).lower() or "homologacion"

    if simulacion:
        numero = _next_simulated_number(punto_venta, tipo_comprobante)
        cae = _simulated_cae(int(venta_id))
        cae_vencimiento = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        comprobante = _upsert_comprobante(
            venta_id=int(venta_id),
            tipo_comprobante=tipo_comprobante,
            punto_venta=punto_venta,
            numero_comprobante=numero,
            cae=cae,
            cae_vencimiento=cae_vencimiento,
            estado="MODO_TEST",
            modo="simulacion",
            total=total,
            payload={"venta_id": int(venta_id), "simulado": True},
            respuesta={
                "resultado": "aprobado_simulado",
                "cae": cae,
                "cae_vencimiento": cae_vencimiento,
            },
            ambiente="simulacion",
        )
        registrar_evento(
            comprobante_id=comprobante.get("id"),
            nivel="info",
            mensaje="Emisión ARCA simulada",
            detalle={
                "venta_id": int(venta_id),
                "punto_venta": punto_venta,
                "numero_comprobante": numero,
                "modo": "simulacion",
            },
        )
        return {
            "ok": True,
            "error_code": "",
            "mensaje": "Comprobante ARCA simulado generado correctamente.",
            "comprobante": comprobante,
            "modo": "simulacion",
        }

    if not arca_esta_configurado():
        comprobante = _upsert_comprobante(
            venta_id=int(venta_id),
            tipo_comprobante=tipo_comprobante,
            punto_venta=punto_venta,
            numero_comprobante=None,
            cae="",
            cae_vencimiento="",
            estado="ERROR_CONFIG",
            modo="wsfe",
            total=total,
            payload={"venta_id": int(venta_id), "simulado": False},
            respuesta={},
            error_mensaje="Configuración ARCA incompleta para emisión real.",
            ambiente=ambiente,
        )
        registrar_evento(
            comprobante_id=comprobante.get("id"),
            nivel="warning",
            mensaje="Emisión ARCA pendiente por configuración",
            detalle={"venta_id": int(venta_id), "modo": "wsfe"},
        )
        return {
            "ok": False,
            "error_code": "ERROR_CONFIG",
            "mensaje": "Configuración ARCA incompleta para emisión real.",
            "comprobante": comprobante,
            "modo": "wsfe",
        }

    comprobante = _upsert_comprobante(
        venta_id=int(venta_id),
        tipo_comprobante=tipo_comprobante,
        punto_venta=punto_venta,
        numero_comprobante=None,
        cae="",
        cae_vencimiento="",
        estado="SIN_CONEXION",
        modo="wsfe",
        total=total,
        payload={"venta_id": int(venta_id), "simulado": False},
        respuesta={"pendiente": "wsfe_real"},
        error_mensaje="La emisión WSFE real todavía no está habilitada en esta fase.",
        ambiente=ambiente,
    )
    registrar_evento(
        comprobante_id=comprobante.get("id"),
        nivel="warning",
        mensaje="Emisión ARCA real pendiente",
        detalle={"venta_id": int(venta_id), "modo": "wsfe"},
    )
    return {
        "ok": False,
        "error_code": "SIN_CONEXION",
        "mensaje": "La emisión WSFE real todavía no está habilitada en esta fase.",
        "comprobante": comprobante,
        "modo": "wsfe",
    }
