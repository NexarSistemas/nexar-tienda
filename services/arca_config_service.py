from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import database as db
from modules.arca.services.comprobantes_service import registrar_evento


AMBIENTES_VALIDOS = ("homologacion", "produccion")
CONDICIONES_FISCALES_VALIDAS = (
    "responsable_inscripto",
    "monotributo",
    "exento",
    "consumidor_final",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _clean_bool(value: object) -> int:
    return 1 if str(value or "").strip().lower() in {"1", "true", "on", "yes", "si"} else 0


def _env_flag(value: object) -> bool | None:
    normalized = _clean_text(value).lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "on", "yes", "si"}:
        return True
    if normalized in {"0", "false", "off", "no"}:
        return False
    return None


def _row_to_dict(row) -> dict[str, object]:
    return dict(row) if row else {}


def _default_config() -> dict[str, object]:
    return {
        "id": 1,
        "cuit": "",
        "razon_social": "",
        "condicion_fiscal": "",
        "punto_venta": "",
        "ambiente": "homologacion",
        "certificado_path": "",
        "key_path": "",
        "certificado_vencimiento": "",
        "activo": 0,
        "created_at": "",
        "updated_at": "",
    }


def _resolver_ruta(path_value: object) -> Path:
    path = Path(_clean_text(path_value)).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _normalizar_fecha(value: object, field_label: str) -> str:
    normalized = _clean_text(value)
    if not normalized:
        return ""
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"La fecha de {field_label} debe tener formato AAAA-MM-DD.") from exc


def normalizar_cuit(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def validar_cuit(cuit: object) -> str:
    normalized = normalizar_cuit(cuit)
    if len(normalized) != 11:
        raise ValueError("CUIT inválido.")
    factores = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    acumulado = sum(int(digito) * factor for digito, factor in zip(normalized[:10], factores))
    resto = 11 - (acumulado % 11)
    verificador = 0 if resto == 11 else 9 if resto == 10 else resto
    if verificador != int(normalized[-1]):
        raise ValueError("CUIT inválido.")
    return normalized


def validar_rutas_certificados(certificado_path: object, key_path: object) -> tuple[str, str]:
    certificado = _clean_text(certificado_path)
    key = _clean_text(key_path)

    certificado_normalizado = ""
    key_normalizado = ""

    if certificado:
        ruta_cert = _resolver_ruta(certificado)
        if not ruta_cert.exists() or not ruta_cert.is_file():
            raise ValueError("Certificado no encontrado.")
        certificado_normalizado = str(ruta_cert)

    if key:
        ruta_key = _resolver_ruta(key)
        if not ruta_key.exists() or not ruta_key.is_file():
            raise ValueError("Key no encontrada.")
        key_normalizado = str(ruta_key)

    return certificado_normalizado, key_normalizado


def validate_config(data: dict[str, object] | None) -> dict[str, object]:
    payload = data or {}
    ambiente = _clean_text(payload.get("ambiente")).lower() or "homologacion"
    condicion_fiscal = _clean_text(payload.get("condicion_fiscal")).lower().replace(" ", "_")

    if ambiente not in AMBIENTES_VALIDOS:
        raise ValueError("El ambiente debe ser homologacion o produccion.")
    if not _clean_text(payload.get("razon_social")):
        raise ValueError("La razón social es obligatoria.")
    if condicion_fiscal not in CONDICIONES_FISCALES_VALIDAS:
        raise ValueError("Seleccioná una condición fiscal válida.")

    punto_venta_raw = _clean_text(payload.get("punto_venta"))
    if not punto_venta_raw:
        raise ValueError("Punto de venta inválido.")
    try:
        punto_venta = int(punto_venta_raw)
    except ValueError as exc:
        raise ValueError("Punto de venta inválido.") from exc
    if punto_venta <= 0:
        raise ValueError("Punto de venta inválido.")

    certificado_path, key_path = validar_rutas_certificados(
        payload.get("certificado_path"),
        payload.get("key_path"),
    )

    return {
        "cuit": validar_cuit(payload.get("cuit")),
        "razon_social": _clean_text(payload.get("razon_social")),
        "condicion_fiscal": condicion_fiscal,
        "punto_venta": punto_venta,
        "ambiente": ambiente,
        "certificado_path": certificado_path,
        "key_path": key_path,
        "certificado_vencimiento": _normalizar_fecha(
            payload.get("certificado_vencimiento"),
            "vencimiento del certificado",
        ),
        "activo": _clean_bool(payload.get("activo")),
    }


def get_config() -> dict[str, object]:
    row = db.q("SELECT * FROM arca_configuracion WHERE id = 1", fetchone=True)
    config = _default_config()
    config.update(_row_to_dict(row))
    config["cuit"] = normalizar_cuit(config.get("cuit"))
    config["ambiente"] = _clean_text(config.get("ambiente")).lower() or "homologacion"
    config["activo"] = int(config.get("activo") or 0)
    config["certificado_path"] = _clean_text(config.get("certificado_path"))
    config["key_path"] = _clean_text(config.get("key_path"))
    config["certificado_vencimiento"] = _clean_text(config.get("certificado_vencimiento"))
    config["certificado_path_exists"] = bool(
        config["certificado_path"] and _resolver_ruta(config["certificado_path"]).exists()
    )
    config["key_path_exists"] = bool(
        config["key_path"] and _resolver_ruta(config["key_path"]).exists()
    )
    return config


def arca_modo_simulacion_activo() -> bool:
    env_value = _env_flag(os.getenv("ARCA_MODO_SIMULACION"))
    if env_value is not None:
        return env_value

    flask_env = _clean_text(os.getenv("FLASK_ENV") or os.getenv("ENV")).lower() or "development"
    return flask_env != "production"


def obtener_modo_arca() -> dict[str, object]:
    env_value = _env_flag(os.getenv("ARCA_MODO_SIMULACION"))
    simulacion = arca_modo_simulacion_activo()
    source = "ARCA_MODO_SIMULACION" if env_value is not None else "default_desarrollo"
    return {
        "simulacion": simulacion,
        "modo": "simulacion" if simulacion else "wsfe",
        "origen": source,
    }


def save_config(data: dict[str, object] | None) -> dict[str, object]:
    normalized = validate_config(data)
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    existing = db.q("SELECT created_at FROM arca_configuracion WHERE id = 1", fetchone=True)
    created_at = _clean_text(existing["created_at"]) if existing else ""
    if not created_at:
        created_at = now

    params = (
        normalized["cuit"],
        normalized["razon_social"],
        normalized["condicion_fiscal"],
        normalized["punto_venta"],
        normalized["ambiente"],
        normalized["certificado_path"],
        normalized["key_path"],
        normalized["certificado_vencimiento"] or None,
        normalized["activo"],
        now,
    )
    if existing:
        db.q(
            """
            UPDATE arca_configuracion
            SET cuit = ?, razon_social = ?, condicion_fiscal = ?, punto_venta = ?, ambiente = ?,
                certificado_path = ?, key_path = ?, certificado_vencimiento = ?, activo = ?,
                updated_at = ?
            WHERE id = 1
            """,
            params,
            commit=True,
        )
    else:
        db.q(
            """
            INSERT INTO arca_configuracion
            (id, cuit, razon_social, condicion_fiscal, punto_venta, ambiente, certificado_path,
             key_path, certificado_vencimiento, activo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                *params[:-1],
                created_at,
                now,
            ),
            commit=True,
        )
    registrar_evento(
        nivel="info",
        mensaje="Configuración ARCA guardada",
        detalle={
            "ambiente": normalized["ambiente"],
            "cuit": normalized["cuit"],
            "punto_venta": normalized["punto_venta"],
            "certificado_path": bool(normalized["certificado_path"]),
            "key_path": bool(normalized["key_path"]),
        },
    )
    return get_config()


def arca_esta_configurado() -> bool:
    config = get_config()
    return bool(
        config.get("cuit")
        and config.get("razon_social")
        and config.get("condicion_fiscal")
        and config.get("punto_venta")
        and _clean_text(config.get("ambiente")).lower() in AMBIENTES_VALIDOS
    )


def obtener_estado_modulo() -> dict[str, object]:
    from modules.arca.services.certificados_service import obtener_certificado_activo
    from services.arca.auth_service import get_connection_status

    config = get_config()
    configurado = arca_esta_configurado()
    conexion = get_connection_status()
    modo_runtime = obtener_modo_arca()
    return {
        "configuracion": config,
        "configurado": configurado,
        "estado_configuracion": "completa" if configurado else "incompleta",
        "activo": bool(int(config.get("activo") or 0)),
        "ambiente": str(config.get("ambiente", "homologacion") or "homologacion"),
        "cuit": str(config.get("cuit", "") or ""),
        "punto_venta": config.get("punto_venta", ""),
        "certificado_homologacion": obtener_certificado_activo("homologacion"),
        "certificado_produccion": obtener_certificado_activo("produccion"),
        "modo": conexion["modo"],
        "mensaje": conexion["mensaje"],
        "wsaa_ok": conexion["ok"],
        "ticket_vigente": conexion["ticket_vigente"],
        "ticket_expiration_time": conexion["expiration_time"],
        "modo_operacion": modo_runtime["modo"],
        "modo_simulacion": modo_runtime["simulacion"],
        "modo_origen": modo_runtime["origen"],
    }


obtener_configuracion = get_config
guardar_configuracion = save_config
