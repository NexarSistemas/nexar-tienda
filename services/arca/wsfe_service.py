from __future__ import annotations

import json
import logging

import database as db
from modules.arca.services.comprobantes_service import registrar_evento
from services.arca.auth_service import ArcaAuthError, get_valid_ticket
from services.arca.wsfe_client import (
    WsfeClientError,
    build_feauth_request,
    fe_comp_ultimo_autorizado,
    fe_param_get_ptos_venta,
    fe_param_get_tipos_cbte,
    fe_param_get_tipos_doc,
    fedummy,
)
from services.arca_config_service import get_config, validar_cuit


logger = logging.getLogger(__name__)

WSFE_TIPO_FACTURA_B = 6
WSFE_EVENTO_MENSAJE = "Prueba WSFE"


class ArcaWsfeError(RuntimeError):
    error_code = "error_wsfe"


class ArcaWsfeConfigError(ArcaWsfeError):
    error_code = "sin_configuracion"


class ArcaWsfeCuitError(ArcaWsfeError):
    error_code = "cuit_invalido"


class ArcaWsfeResponseError(ArcaWsfeError):
    error_code = "respuesta_invalida"


def _resumen_error(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _normalizar_contexto() -> dict[str, object]:
    config = get_config()
    ambiente = str(config.get("ambiente") or "homologacion").strip().lower()
    if ambiente != "homologacion":
        raise ArcaWsfeConfigError("WSFE real en esta fase solo está habilitado para homologación.")

    try:
        cuit = validar_cuit(config.get("cuit"))
    except ValueError as exc:
        raise ArcaWsfeCuitError("CUIT inválido.") from exc

    try:
        punto_venta = int(config.get("punto_venta") or 0)
    except (TypeError, ValueError) as exc:
        raise ArcaWsfeConfigError("Punto de venta inválido.") from exc

    if punto_venta <= 0:
        raise ArcaWsfeConfigError("Punto de venta inválido.")

    return {
        "ambiente": ambiente,
        "cuit": cuit,
        "punto_venta": punto_venta,
        "tipo_comprobante": WSFE_TIPO_FACTURA_B,
    }


def _compact_items(
    items: list[dict[str, object]],
    *,
    id_keys: tuple[str, ...],
    desc_keys: tuple[str, ...],
    limit: int = 8,
) -> list[str]:
    summary: list[str] = []
    for item in items[:limit]:
        item_id = next((str(item.get(key) or "").strip() for key in id_keys if str(item.get(key) or "").strip()), "")
        item_desc = next(
            (str(item.get(key) or "").strip() for key in desc_keys if str(item.get(key) or "").strip()),
            "",
        )
        text = " - ".join(part for part in (item_id, item_desc) if part)
        if text:
            summary.append(text)
    return summary


def _detalle_evento(resultado: dict[str, object]) -> dict[str, object]:
    ultimo = dict(resultado.get("ultimo_comprobante") or {})
    return {
        "ok": bool(resultado.get("ok")),
        "error_code": str(resultado.get("error_code") or ""),
        "mensaje": str(resultado.get("mensaje") or ""),
        "ambiente": str(resultado.get("ambiente") or "homologacion"),
        "punto_venta": resultado.get("punto_venta"),
        "ticket_reutilizado": bool(resultado.get("ticket_reutilizado")),
        "dummy": dict(resultado.get("dummy") or {}),
        "tipos_comprobante_count": len(resultado.get("tipos_comprobante") or []),
        "tipos_documento_count": len(resultado.get("tipos_documento") or []),
        "puntos_venta_count": len(resultado.get("puntos_venta") or []),
        "tipos_comprobante_preview": _compact_items(
            list(resultado.get("tipos_comprobante") or []),
            id_keys=("Id",),
            desc_keys=("Desc",),
        ),
        "tipos_documento_preview": _compact_items(
            list(resultado.get("tipos_documento") or []),
            id_keys=("Id",),
            desc_keys=("Desc",),
        ),
        "puntos_venta_preview": _compact_items(
            list(resultado.get("puntos_venta") or []),
            id_keys=("Nro",),
            desc_keys=("EmisionTipo", "Bloqueado"),
        ),
        "ultimo_comprobante": {
            "punto_venta": ultimo.get("punto_venta"),
            "tipo_comprobante": ultimo.get("tipo_comprobante"),
            "numero": ultimo.get("numero"),
            "descripcion": ultimo.get("descripcion") or "Factura B",
        },
    }


def _guardar_evento(resultado: dict[str, object]) -> None:
    ok = bool(resultado.get("ok"))
    registrar_evento(
        nivel="info" if ok else "warning",
        mensaje=WSFE_EVENTO_MENSAJE,
        detalle=_detalle_evento(resultado),
    )


def _resultado_error(exc: Exception, *, error_code: str) -> dict[str, object]:
    mensaje = _resumen_error(exc)
    logger.warning("Prueba WSFE fallida error_code=%s error=%s", error_code, mensaje)
    resultado = {
        "ok": False,
        "modo": "wsfe-homologacion",
        "error_code": error_code,
        "mensaje": mensaje,
        "ambiente": "homologacion",
        "punto_venta": "",
        "ticket_reutilizado": False,
        "dummy": {},
        "tipos_comprobante": [],
        "tipos_documento": [],
        "puntos_venta": [],
        "ultimo_comprobante": {},
    }
    _guardar_evento(resultado)
    return resultado


def _map_wsfe_error(exc: WsfeClientError) -> tuple[str, str]:
    mensaje = _resumen_error(exc)
    mensaje_lower = mensaje.lower()
    if "cuit" in mensaje_lower and "inválido" in mensaje_lower:
        return "cuit_invalido", mensaje
    if "pto" in mensaje_lower or "punto de venta" in mensaje_lower:
        return "punto_venta_no_autorizado", mensaje
    if "service not authorized" in mensaje_lower or "servicio no autorizado" in mensaje_lower:
        return "servicio_no_asociado", mensaje
    if "soap" in mensaje_lower:
        return "error_soap", mensaje
    if "respuesta inválida" in mensaje_lower:
        return "respuesta_invalida", mensaje
    return "error_wsfe", mensaje


def probar_wsfe() -> dict[str, object]:
    try:
        context = _normalizar_contexto()
        ticket = get_valid_ticket()
        if str(ticket.get("service") or "wsfe").strip().lower() != "wsfe":
            raise ArcaWsfeConfigError("El ticket WSAA disponible no corresponde al servicio wsfe.")
        auth = build_feauth_request(
            token=str(ticket.get("token") or ""),
            sign=str(ticket.get("sign") or ""),
            cuit=str(context["cuit"]),
        )
        logger.info(
            "Preparando prueba WSFE ambiente=%s cuit=%s pv=%s ticket_service=%s token_len=%s sign_len=%s ticket_reutilizado=%s",
            context["ambiente"],
            context["cuit"],
            context["punto_venta"],
            str(ticket.get("service") or "wsfe"),
            len(str(ticket.get("token") or "").strip()),
            len(str(ticket.get("sign") or "").strip()),
            bool(ticket.get("reused")),
        )

        dummy = fedummy()
        tipos_comprobante = fe_param_get_tipos_cbte(auth)["items"]
        tipos_documento = fe_param_get_tipos_doc(auth)["items"]
        puntos_venta = fe_param_get_ptos_venta(auth)["items"]
        ultimo_comprobante = fe_comp_ultimo_autorizado(
            auth,
            pto_vta=int(context["punto_venta"]),
            cbte_tipo=int(context["tipo_comprobante"]),
        )

        resultado = {
            "ok": True,
            "modo": "wsfe-homologacion",
            "error_code": "",
            "mensaje": (
                "WSFE conectado correctamente. "
                f"Último comprobante PV {context['punto_venta']} / Factura B: "
                f"{ultimo_comprobante['numero']}."
            ),
            "ambiente": context["ambiente"],
            "punto_venta": context["punto_venta"],
            "ticket_reutilizado": bool(ticket.get("reused")),
            "dummy": dummy,
            "tipos_comprobante": tipos_comprobante,
            "tipos_documento": tipos_documento,
            "puntos_venta": puntos_venta,
            "ultimo_comprobante": {
                **ultimo_comprobante,
                "descripcion": "Factura B",
            },
        }
        _guardar_evento(resultado)
        logger.info(
            "Prueba WSFE correcta ambiente=%s pv=%s ultimo=%s ticket_reutilizado=%s",
            context["ambiente"],
            context["punto_venta"],
            ultimo_comprobante["numero"],
            bool(ticket.get("reused")),
        )
        return resultado
    except ArcaAuthError as exc:
        return _resultado_error(exc, error_code=exc.error_code)
    except (ArcaWsfeError, ArcaWsfeResponseError) as exc:
        return _resultado_error(exc, error_code=exc.error_code)
    except WsfeClientError as exc:
        error_code, mensaje = _map_wsfe_error(exc)
        return _resultado_error(ArcaWsfeError(mensaje), error_code=error_code)


def get_last_wsfe_test() -> dict[str, object]:
    row = db.q(
        """
        SELECT nivel, mensaje, detalle_json, created_at
        FROM arca_eventos
        WHERE mensaje = ?
        ORDER BY datetime(COALESCE(created_at, '1970-01-01 00:00:00')) DESC, id DESC
        LIMIT 1
        """,
        (WSFE_EVENTO_MENSAJE,),
        fetchone=True,
    )
    if not row:
        return {
            "available": False,
            "ok": False,
            "mensaje": "Todavía no se ejecutó una prueba WSFE.",
            "created_at": "",
        }

    detalle_raw = str(row["detalle_json"] or "").strip()
    try:
        detalle = json.loads(detalle_raw) if detalle_raw else {}
    except json.JSONDecodeError:
        detalle = {}

    return {
        "available": True,
        "nivel": str(row["nivel"] or "info"),
        "created_at": str(row["created_at"] or ""),
        **detalle,
    }
