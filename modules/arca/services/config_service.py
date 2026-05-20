from __future__ import annotations

from datetime import datetime

import database as db


AMBIENTES_VALIDOS = {"homologacion", "produccion"}


def _row_to_dict(row) -> dict[str, object]:
    if not row:
        return {}
    return dict(row)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _clean_bool(value: object) -> int:
    return 1 if str(value or "").strip().lower() in {"1", "true", "on", "yes", "si"} else 0


def _default_config() -> dict[str, object]:
    return {
        "id": 1,
        "cuit": "",
        "razon_social": "",
        "condicion_fiscal": "",
        "punto_venta": "",
        "ambiente": "homologacion",
        "activo": 0,
        "created_at": "",
        "updated_at": "",
    }


def _normalizar_data(data: dict[str, object] | None) -> dict[str, object]:
    payload = data or {}
    ambiente = _clean_text(payload.get("ambiente")).lower() or "homologacion"
    return {
        "cuit": _clean_text(payload.get("cuit")),
        "razon_social": _clean_text(payload.get("razon_social")),
        "condicion_fiscal": _clean_text(payload.get("condicion_fiscal")),
        "punto_venta": _clean_text(payload.get("punto_venta")),
        "ambiente": ambiente,
        "activo": _clean_bool(payload.get("activo")),
    }


def _validar_data(data: dict[str, object]) -> dict[str, object]:
    normalized = _normalizar_data(data)
    if not normalized["cuit"]:
        raise ValueError("El CUIT es obligatorio.")
    if not normalized["razon_social"]:
        raise ValueError("La razón social es obligatoria.")
    if not normalized["punto_venta"]:
        raise ValueError("El punto de venta es obligatorio.")
    try:
        normalized["punto_venta"] = int(str(normalized["punto_venta"]))
    except ValueError as exc:
        raise ValueError("El punto de venta debe ser numérico.") from exc
    if normalized["ambiente"] not in AMBIENTES_VALIDOS:
        raise ValueError("El ambiente debe ser homologacion o produccion.")
    return normalized


def obtener_configuracion() -> dict[str, object]:
    row = db.q("SELECT * FROM arca_configuracion WHERE id=1", fetchone=True)
    config = _default_config()
    config.update(_row_to_dict(row))
    return config


def guardar_configuracion(data: dict[str, object] | None) -> dict[str, object]:
    normalized = _validar_data(data or {})
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    existing = db.q("SELECT id, created_at FROM arca_configuracion WHERE id=1", fetchone=True)
    created_at = ""
    if existing:
        created_at = str(existing["created_at"] or "").strip()
    if not created_at:
        created_at = now

    db.q(
        """
        INSERT OR REPLACE INTO arca_configuracion
        (id, cuit, razon_social, condicion_fiscal, punto_venta, ambiente, activo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            normalized["cuit"],
            normalized["razon_social"],
            normalized["condicion_fiscal"],
            normalized["punto_venta"],
            normalized["ambiente"],
            normalized["activo"],
            created_at,
            now,
        ),
        commit=True,
    )
    return obtener_configuracion()


def arca_esta_configurado() -> bool:
    config = obtener_configuracion()
    return bool(
        str(config.get("cuit", "")).strip()
        and str(config.get("razon_social", "")).strip()
        and str(config.get("punto_venta", "")).strip()
        and str(config.get("ambiente", "")).strip().lower() in AMBIENTES_VALIDOS
    )


def obtener_estado_modulo() -> dict[str, object]:
    config = obtener_configuracion()
    return {
        "configuracion": config,
        "configurado": arca_esta_configurado(),
        "activo": bool(int(config.get("activo") or 0)),
        "ambiente": str(config.get("ambiente", "homologacion") or "homologacion"),
        "cuit": str(config.get("cuit", "") or ""),
        "punto_venta": config.get("punto_venta", ""),
        "modo": "placeholder",
        "mensaje": "Esta fase solo prepara la configuración. La emisión real se implementará en una fase posterior.",
    }
