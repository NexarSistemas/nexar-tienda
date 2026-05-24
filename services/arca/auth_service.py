from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from modules.arca.services.certificados_service import obtener_certificado_activo
from modules.arca.services.comprobantes_service import registrar_evento
from services.arca.certificate_diagnostics import diagnose_certificate_pair
from services.arca.ticket_storage import get_latest_ticket, is_ticket_valid, save_ticket
from services.arca.wsaa_client import WsaaClientError, login_cms
from services.arca.xml_signer import XmlSignerError, sign_tra
from services.arca_config_service import get_config


logger = logging.getLogger(__name__)
WSAA_SERVICE = "wsfe"


class ArcaAuthError(RuntimeError):
    error_code = "auth_error"


class ArcaConfigError(ArcaAuthError):
    error_code = "configuracion_incompleta"


class ArcaSigningError(ArcaAuthError):
    error_code = "error_firma"


class ArcaWsaaError(ArcaAuthError):
    error_code = "error_wsaa"


class ArcaResponseError(ArcaAuthError):
    error_code = "respuesta_invalida"


def _safe_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resumen_error(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def build_tra_xml(*, service: str = WSAA_SERVICE, now: datetime | None = None) -> dict[str, object]:
    current = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    generation_time = current - timedelta(minutes=10)
    expiration_time = current + timedelta(hours=12)
    unique_id = int(current.timestamp())

    login_ticket_request = ET.Element("loginTicketRequest", version="1.0")
    header = ET.SubElement(login_ticket_request, "header")
    ET.SubElement(header, "uniqueId").text = str(unique_id)
    ET.SubElement(header, "generationTime").text = _safe_iso(generation_time)
    ET.SubElement(header, "expirationTime").text = _safe_iso(expiration_time)
    ET.SubElement(login_ticket_request, "service").text = str(service or "").strip().lower()

    xml_payload = ET.tostring(
        login_ticket_request,
        encoding="utf-8",
        xml_declaration=True,
    ).decode("utf-8")
    return {
        "xml": xml_payload,
        "unique_id": unique_id,
        "generation_time": _safe_iso(generation_time),
        "expiration_time": _safe_iso(expiration_time),
        "service": str(service or "").strip().lower(),
    }


def _validar_archivo(path_value: str, field_label: str) -> str:
    normalized = str(path_value or "").strip()
    if not normalized:
        raise ArcaConfigError(f"Falta {field_label} para autenticación WSAA.")
    path = Path(normalized).expanduser()
    if not path.exists() or not path.is_file():
        if field_label == "certificado":
            raise ArcaConfigError("Certificado faltante o no encontrado en la ruta configurada.")
        if field_label == "key privada":
            raise ArcaConfigError("Key faltante o no encontrada en la ruta configurada.")
        raise ArcaConfigError(f"{field_label.capitalize()} no encontrado/a en la ruta configurada.")
    return str(path.resolve())


def get_auth_context() -> dict[str, object]:
    config = get_config()
    ambiente = str(config.get("ambiente") or "homologacion").strip().lower()
    cuit = str(config.get("cuit") or "").strip()
    if not cuit:
        raise ArcaConfigError("Falta CUIT configurado para autenticación WSAA.")

    certificado_activo = obtener_certificado_activo(ambiente)
    cert_path = ""
    key_path = ""
    certificado_origen = "configuracion"
    if certificado_activo:
        cert_path = str(certificado_activo.get("certificado_path") or "").strip()
        key_path = str(certificado_activo.get("key_path") or "").strip()
        certificado_origen = "certificado_activo"

    cert_path = cert_path or str(config.get("certificado_path") or "").strip()
    key_path = key_path or str(config.get("key_path") or "").strip()

    cert_path = _validar_archivo(cert_path, "certificado")
    key_path = _validar_archivo(key_path, "key privada")
    diagnostico = diagnose_certificate_pair(cert_path, key_path)
    if not diagnostico["certificate_valid"]:
        raise ArcaConfigError(
            diagnostico["certificate_error"] or "No se pudo interpretar el certificado ARCA configurado."
        )
    if not diagnostico["key_valid"]:
        raise ArcaConfigError(
            diagnostico["key_error"] or "No se pudo interpretar la clave privada ARCA configurada."
        )
    if not diagnostico["pair_match"]:
        raise ArcaConfigError("El certificado y la clave privada no corresponden entre sí.")

    return {
        "config": config,
        "ambiente": ambiente,
        "cuit": cuit,
        "service": WSAA_SERVICE,
        "cert_path": cert_path,
        "key_path": key_path,
        "certificado_origen": certificado_origen,
        "diagnostico": diagnostico,
    }


def _store_wsaa_ticket(context: dict[str, object], ticket: dict[str, str]) -> dict[str, object]:
    saved = save_ticket(
        ambiente=str(context["ambiente"]),
        service=str(context["service"]),
        token=ticket["token"],
        sign=ticket["sign"],
        generation_time=ticket["generation_time"],
        expiration_time=ticket["expiration_time"],
    )
    registrar_evento(
        nivel="info",
        mensaje="Ticket WSAA actualizado",
        detalle={
            "ambiente": context["ambiente"],
            "service": context["service"],
            "expiration_time": ticket["expiration_time"],
            "generation_time": ticket["generation_time"],
        },
    )
    logger.info(
        "Ticket WSAA actualizado ambiente=%s service=%s expira=%s",
        context["ambiente"],
        context["service"],
        ticket["expiration_time"],
    )
    return saved


def get_valid_ticket(*, force_refresh: bool = False) -> dict[str, object]:
    context = get_auth_context()
    latest = get_latest_ticket(str(context["ambiente"]), str(context["service"]))
    if not force_refresh and is_ticket_valid(latest):
        registrar_evento(
            nivel="info",
            mensaje="Ticket WSAA reutilizado",
            detalle={
                "ambiente": context["ambiente"],
                "service": context["service"],
                "expiration_time": latest.get("expiration_time"),
            },
        )
        logger.info(
            "Ticket WSAA reutilizado ambiente=%s service=%s expira=%s",
            context["ambiente"],
            context["service"],
            latest.get("expiration_time"),
        )
        return {**latest, "reused": True}

    tra = build_tra_xml(service=str(context["service"]))
    try:
        cms_base64 = sign_tra(
            tra["xml"],
            cert_path=str(context["cert_path"]),
            key_path=str(context["key_path"]),
        )
    except XmlSignerError as exc:
        raise ArcaSigningError(f"Error al firmar TRA para WSAA: {_resumen_error(exc)}") from exc

    try:
        ticket = login_cms(cms_base64, ambiente=str(context["ambiente"]))
    except WsaaClientError as exc:
        raise ArcaWsaaError(_resumen_error(exc)) from exc

    if not ticket.get("token") or not ticket.get("sign"):
        raise ArcaResponseError("WSAA respondió sin token o sign válido.")

    saved = _store_wsaa_ticket(context, ticket)
    return {**saved, "reused": False}


def _resultado_error(exc: ArcaAuthError) -> dict[str, object]:
    registrar_evento(
        nivel="warning",
        mensaje="Conexión WSAA fallida",
        detalle={
            "error_code": exc.error_code,
            "error": _resumen_error(exc),
            "service": WSAA_SERVICE,
        },
    )
    logger.warning("Conexión WSAA fallida service=%s error=%s", WSAA_SERVICE, _resumen_error(exc))
    return {
        "ok": False,
        "modo": "wsaa",
        "error_code": exc.error_code,
        "mensaje": str(exc),
    }


def probar_conexion_wsaa() -> dict[str, object]:
    try:
        ticket = get_valid_ticket()
    except ArcaAuthError as exc:
        return _resultado_error(exc)
    mensaje = (
        f"Conexión ARCA homologación correcta. Ticket válido hasta {ticket.get('expiration_time')}."
    )
    return {
        "ok": True,
        "modo": "wsaa",
        "error_code": "",
        "mensaje": mensaje,
        "ticket_vigente": True,
        "expiration_time": ticket.get("expiration_time"),
        "generation_time": ticket.get("generation_time"),
        "service": WSAA_SERVICE,
        "reused": bool(ticket.get("reused")),
    }


def get_connection_status() -> dict[str, object]:
    try:
        context = get_auth_context()
    except ArcaAuthError as exc:
        return {
            "ok": False,
            "modo": "wsaa",
            "mensaje": str(exc),
            "detalle_corto": "Configuración incompleta",
            "ticket_vigente": False,
            "generation_time": "",
            "expiration_time": "",
            "service": WSAA_SERVICE,
            "ambiente": get_config().get("ambiente", "homologacion"),
        }

    latest = get_latest_ticket(str(context["ambiente"]), str(context["service"]))
    ticket_vigente = is_ticket_valid(latest)
    expiration_time = str(latest.get("expiration_time") or "") if latest else ""
    generation_time = str(latest.get("generation_time") or "") if latest else ""
    if ticket_vigente:
        mensaje = f"Ticket WSAA listo para usar hasta {expiration_time}."
        detalle_corto = "Ticket vigente"
    elif latest:
        mensaje = (
            f"Existe un ticket WSAA almacenado pero ya venció el {expiration_time}. "
            "Podés renovarlo con Probar conexión."
        )
        detalle_corto = "Ticket vencido"
    else:
        mensaje = (
            "Todavía no hay ticket WSAA almacenado para este ambiente. "
            "La emisión de comprobantes sigue deshabilitada en esta fase."
        )
        detalle_corto = "Sin ticket"
    return {
        "ok": ticket_vigente,
        "modo": "wsaa-homologacion" if context["ambiente"] == "homologacion" else "wsaa-produccion-bloqueado",
        "mensaje": mensaje,
        "detalle_corto": detalle_corto,
        "ticket_vigente": ticket_vigente,
        "generation_time": generation_time,
        "expiration_time": expiration_time,
        "service": str(context["service"]),
        "ambiente": str(context["ambiente"]),
    }
