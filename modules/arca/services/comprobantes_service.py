from __future__ import annotations

import json
from datetime import datetime

import database as db


def listar_comprobantes() -> list[dict[str, object]]:
    rows = db.q(
        """
        SELECT id, venta_id, tipo_comprobante, punto_venta, numero, cae, cae_vencimiento,
               estado, ambiente, total, payload_json, respuesta_json, error_mensaje,
               created_at, updated_at
        FROM arca_comprobantes
        ORDER BY datetime(COALESCE(created_at, '1970-01-01 00:00:00')) DESC, id DESC
        """
    )
    return [dict(row) for row in rows]


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
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    return int(
        db.q(
            """
            INSERT INTO arca_comprobantes
            (venta_id, tipo_comprobante, punto_venta, numero, cae, cae_vencimiento, estado,
             ambiente, total, payload_json, respuesta_json, error_mensaje, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                venta_id,
                str(tipo_comprobante or "").strip(),
                punto_venta,
                numero,
                "",
                "",
                str(estado or "pendiente").strip().lower(),
                str(ambiente or "homologacion").strip().lower(),
                float(total or 0),
                payload_json,
                "",
                "",
                now,
                now,
            ),
            commit=True,
        )
    )


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
