from __future__ import annotations

from datetime import datetime

import database as db
from modules.arca.services.comprobantes_service import registrar_evento


AMBIENTES_VALIDOS = {"homologacion", "produccion"}
CONDICIONES_FISCALES_VALIDAS = (
    "responsable_inscripto",
    "monotributo",
    "exento",
    "consumidor_final",
)


def _row_to_dict(row) -> dict[str, object]:
    if not row:
        return {}
    return dict(row)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _clean_bool(value: object) -> int:
    return 1 if str(value or "").strip().lower() in {"1", "true", "on", "yes", "si"} else 0


def normalizar_cuit(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _validar_cuit(cuit: str) -> None:
    if len(cuit) != 11:
        raise ValueError("El CUIT debe tener 11 dígitos.")
    factores = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    acumulado = sum(int(digito) * factor for digito, factor in zip(cuit[:10], factores))
    resto = 11 - (acumulado % 11)
    verificador = 0 if resto == 11 else 9 if resto == 10 else resto
    if verificador != int(cuit[-1]):
        raise ValueError("El CUIT ingresado no es válido.")


def _validar_email(email: str) -> str:
    normalized = _clean_text(email).lower()
    if not normalized:
        raise ValueError("El email fiscal es obligatorio.")
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Ingresá un email fiscal válido.")
    local, _, domain = normalized.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Ingresá un email fiscal válido.")
    return normalized


def _validar_inicio_actividades(value: str) -> str:
    normalized = _clean_text(value)
    if not normalized:
        raise ValueError("La fecha de inicio de actividades es obligatoria.")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("La fecha de inicio de actividades debe tener formato AAAA-MM-DD.") from exc


def _validar_telefono(value: str) -> str:
    normalized = _clean_text(value)
    if not normalized:
        raise ValueError("El teléfono fiscal es obligatorio.")
    digits = "".join(char for char in normalized if char.isdigit())
    if len(digits) < 6:
        raise ValueError("Ingresá un teléfono fiscal válido.")
    return normalized


def _default_config() -> dict[str, object]:
    return {
        "id": 1,
        "cuit": "",
        "razon_social": "",
        "nombre_fantasia": "",
        "condicion_fiscal": "",
        "punto_venta": "",
        "ambiente": "homologacion",
        "activo": 0,
        "domicilio_fiscal": "",
        "inicio_actividades": "",
        "ingresos_brutos": "",
        "email_fiscal": "",
        "telefono_fiscal": "",
        "updated_by": "",
        "created_at": "",
        "updated_at": "",
    }


def _normalizar_data(data: dict[str, object] | None) -> dict[str, object]:
    payload = data or {}
    ambiente = _clean_text(payload.get("ambiente")).lower() or "homologacion"
    condicion_fiscal = _clean_text(payload.get("condicion_fiscal")).lower().replace(" ", "_")
    return {
        "cuit": normalizar_cuit(payload.get("cuit")),
        "razon_social": _clean_text(payload.get("razon_social")),
        "nombre_fantasia": _clean_text(payload.get("nombre_fantasia")),
        "condicion_fiscal": condicion_fiscal,
        "punto_venta": _clean_text(payload.get("punto_venta")),
        "ambiente": ambiente,
        "domicilio_fiscal": _clean_text(payload.get("domicilio_fiscal")),
        "inicio_actividades": _clean_text(payload.get("inicio_actividades")),
        "ingresos_brutos": _clean_text(payload.get("ingresos_brutos")),
        "email_fiscal": _clean_text(payload.get("email_fiscal")),
        "telefono_fiscal": _clean_text(payload.get("telefono_fiscal")),
        "activo": _clean_bool(payload.get("activo")),
        "updated_by": _clean_text(payload.get("updated_by")),
    }


def _validar_data(data: dict[str, object]) -> dict[str, object]:
    normalized = _normalizar_data(data)
    _validar_cuit(normalized["cuit"])
    if not normalized["razon_social"]:
        raise ValueError("La razón social es obligatoria.")
    if not normalized["nombre_fantasia"]:
        raise ValueError("El nombre de fantasía es obligatorio.")
    if normalized["condicion_fiscal"] not in CONDICIONES_FISCALES_VALIDAS:
        raise ValueError("Seleccioná una condición fiscal válida.")
    if not normalized["punto_venta"]:
        raise ValueError("El punto de venta es obligatorio.")
    try:
        normalized["punto_venta"] = int(str(normalized["punto_venta"]))
    except ValueError as exc:
        raise ValueError("El punto de venta debe ser numérico.") from exc
    if normalized["punto_venta"] <= 0:
        raise ValueError("El punto de venta debe ser mayor a cero.")
    if normalized["punto_venta"] > 99999:
        raise ValueError("El punto de venta no puede superar 99999.")
    if normalized["ambiente"] not in AMBIENTES_VALIDOS:
        raise ValueError("El ambiente debe ser homologacion o produccion.")
    if not normalized["domicilio_fiscal"]:
        raise ValueError("El domicilio fiscal es obligatorio.")
    normalized["inicio_actividades"] = _validar_inicio_actividades(
        normalized["inicio_actividades"]
    )
    if not normalized["ingresos_brutos"]:
        raise ValueError("Ingresá el número de ingresos brutos.")
    normalized["email_fiscal"] = _validar_email(normalized["email_fiscal"])
    normalized["telefono_fiscal"] = _validar_telefono(normalized["telefono_fiscal"])
    return normalized


def obtener_configuracion() -> dict[str, object]:
    row = db.q("SELECT * FROM arca_configuracion WHERE id=1", fetchone=True)
    config = _default_config()
    config.update(_row_to_dict(row))
    config["cuit"] = normalizar_cuit(config.get("cuit"))
    config["email_fiscal"] = _clean_text(
        config.get("email_fiscal") or config.get("email") or ""
    ).lower()
    return config


def guardar_configuracion(data: dict[str, object] | None) -> dict[str, object]:
    normalized = _validar_data(data or {})
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    existing = db.q(
        "SELECT id, created_at FROM arca_configuracion WHERE id=1",
        fetchone=True,
    )
    created_at = str(existing["created_at"] or "").strip() if existing else ""
    if not created_at:
        created_at = now

    db.q(
        """
        INSERT OR REPLACE INTO arca_configuracion
        (id, cuit, razon_social, nombre_fantasia, condicion_fiscal, punto_venta, ambiente, activo,
         email, email_fiscal, inicio_actividades, domicilio_fiscal, ingresos_brutos,
         telefono_fiscal, updated_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            normalized["cuit"],
            normalized["razon_social"],
            normalized["nombre_fantasia"],
            normalized["condicion_fiscal"],
            normalized["punto_venta"],
            normalized["ambiente"],
            normalized["activo"],
            normalized["email_fiscal"],
            normalized["email_fiscal"],
            normalized["inicio_actividades"],
            normalized["domicilio_fiscal"],
            normalized["ingresos_brutos"],
            normalized["telefono_fiscal"],
            normalized["updated_by"],
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
            "updated_by": normalized["updated_by"],
        },
    )
    return obtener_configuracion()


def arca_esta_configurado() -> bool:
    config = obtener_configuracion()
    return bool(
        config.get("cuit")
        and config.get("razon_social")
        and config.get("nombre_fantasia")
        and config.get("condicion_fiscal")
        and config.get("punto_venta")
        and config.get("domicilio_fiscal")
        and config.get("inicio_actividades")
        and config.get("ingresos_brutos")
        and config.get("email_fiscal")
        and config.get("telefono_fiscal")
        and str(config.get("ambiente", "")).strip().lower() in AMBIENTES_VALIDOS
    )


def obtener_estado_modulo() -> dict[str, object]:
    from modules.arca.services.certificados_service import obtener_certificado_activo

    config = obtener_configuracion()
    configurado = arca_esta_configurado()
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
        "modo": "placeholder",
        "mensaje": (
            "Esta fase solo prepara la configuración fiscal y los certificados locales. "
            "Todavía no hay conexión real con ARCA."
        ),
    }
