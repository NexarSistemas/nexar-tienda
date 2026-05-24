from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

import requests


logger = logging.getLogger(__name__)

WSFE_HOMOLOGACION_WSDL_URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
WSFE_HOMOLOGACION_URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
WSFE_NAMESPACE = "http://ar.gov.afip.dif.FEV1/"
SOAP_ENV_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"


class WsfeClientError(RuntimeError):
    pass


class WsfeResultError(WsfeClientError):
    def __init__(
        self,
        operation: str,
        errors: list[dict[str, str]],
        events: list[dict[str, str]] | None = None,
    ) -> None:
        self.operation = operation
        self.errors = errors
        self.events = events or []
        message = "; ".join(
            filter(
                None,
                [
                    f"{error.get('code', '').strip()}: {error.get('message', '').strip()}".strip(": ")
                    for error in self.errors
                ],
            )
        )
        super().__init__(f"{operation} devolvió error WSFE: {message or 'sin detalle'}")


ET.register_namespace("soapenv", SOAP_ENV_NAMESPACE)
ET.register_namespace("ar", WSFE_NAMESPACE)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _first_child(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    for child in list(node):
        if _local_name(child.tag) == name:
            return child
    return None


def _children(node: ET.Element | None, name: str) -> list[ET.Element]:
    if node is None:
        return []
    return [child for child in list(node) if _local_name(child.tag) == name]


def _find_text(node: ET.Element | None, name: str) -> str:
    if node is None:
        return ""
    for child in node.iter():
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _qname(name: str, namespace: str = WSFE_NAMESPACE) -> str:
    return f"{{{namespace}}}{name}"


def _append_value(parent: ET.Element, name: str, value: object, *, namespace: str = WSFE_NAMESPACE) -> None:
    element = ET.SubElement(parent, _qname(name, namespace))
    if isinstance(value, dict):
        for child_name, child_value in value.items():
            _append_value(element, child_name, child_value, namespace=namespace)
        return
    if value is not None:
        element.text = str(value)


def build_feauth_request(*, token: str, sign: str, cuit: str | int) -> dict[str, object]:
    token_text = str(token or "").strip()
    sign_text = str(sign or "").strip()
    cuit_text = str(cuit or "").strip()

    if not token_text or not sign_text:
        raise WsfeClientError("No hay token/sign WSAA válidos para construir FEAuthRequest.")
    if not cuit_text.isdigit() or len(cuit_text) != 11:
        raise WsfeClientError("CUIT inválido para FEAuthRequest.")

    return {
        "Token": token_text,
        "Sign": sign_text,
        "Cuit": int(cuit_text),
    }


def _soap_envelope(operation: str, payload: dict[str, object] | None = None) -> bytes:
    envelope = ET.Element(
        _qname("Envelope", SOAP_ENV_NAMESPACE),
    )
    ET.SubElement(envelope, _qname("Header", SOAP_ENV_NAMESPACE))
    body = ET.SubElement(envelope, _qname("Body", SOAP_ENV_NAMESPACE))
    operation_node = ET.SubElement(body, _qname(operation))
    for key, value in (payload or {}).items():
        _append_value(operation_node, key, value)
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _extract_fault(root: ET.Element) -> None:
    fault = root.find(".//{*}Fault")
    if fault is None:
        return
    fault_text = " ".join(text.strip() for text in fault.itertext() if text and text.strip())
    raise WsfeClientError(f"WSFE devolvió un fault SOAP: {fault_text or 'sin detalle'}")


def _request_soap(
    operation: str,
    payload: dict[str, object] | None = None,
    *,
    timeout: int = 30,
) -> ET.Element:
    request_xml = _soap_envelope(operation, payload)
    logger.info(
        "WSFE request metodo=%s cuit=%s token_len=%s sign_len=%s",
        operation,
        _extract_auth_field(payload, "Cuit"),
        _field_length(_extract_auth_field(payload, "Token")),
        _field_length(_extract_auth_field(payload, "Sign")),
    )
    try:
        response = requests.post(
            WSFE_HOMOLOGACION_URL,
            data=request_xml,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f"{WSFE_NAMESPACE}{operation}",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise WsfeClientError("No se pudo conectar con WSFE homologación.") from exc

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        if response.status_code >= 400:
            logger.warning("WSFE homologacion devolvio HTTP %s en %s", response.status_code, operation)
            raise WsfeClientError(f"WSFE homologación devolvió HTTP {response.status_code}.") from exc
        raise WsfeClientError("WSFE devolvió una respuesta SOAP inválida.") from exc

    _extract_fault(root)

    if response.status_code >= 400:
        logger.warning("WSFE homologacion devolvio HTTP %s en %s", response.status_code, operation)
        raise WsfeClientError(f"WSFE homologación devolvió HTTP {response.status_code}.")

    result_node = root.find(f".//{{*}}{operation}Result")
    if result_node is not None:
        return result_node

    response_node = root.find(f".//{{*}}{operation}Response")
    if response_node is not None and list(response_node):
        return list(response_node)[0]

    raise WsfeClientError(f"WSFE no devolvió {operation}Result en la respuesta.")


def _parse_messages(result_node: ET.Element, container_name: str, item_name: str) -> list[dict[str, str]]:
    container = _first_child(result_node, container_name)
    items = _children(container, item_name)
    result: list[dict[str, str]] = []
    for item in items:
        result.append(
            {
                "code": _find_text(item, "Code"),
                "message": _find_text(item, "Msg"),
            }
        )
    return result


def _field_length(value: object) -> int:
    return len(str(value or "").strip())


def _extract_auth_field(payload: dict[str, object] | None, field_name: str) -> object:
    auth = dict((payload or {}).get("Auth") or {})
    return auth.get(field_name)


def _raise_if_errors(
    operation: str,
    result_node: ET.Element,
    *,
    allow_empty_result: bool = False,
) -> None:
    errors = _parse_messages(result_node, "Errors", "Err")
    if errors:
        raise WsfeResultError(operation, errors, _parse_messages(result_node, "Events", "Ev"))
    if allow_empty_result:
        return
    if _first_child(result_node, "ResultGet") is None and not list(result_node):
        raise WsfeClientError(f"{operation} devolvió una respuesta inválida.")


def _parse_result_get_items(result_node: ET.Element, item_name: str) -> list[dict[str, str]]:
    result_get = _first_child(result_node, "ResultGet")
    if result_get is None:
        return []

    items = _children(result_get, item_name)
    if not items and _local_name(result_get.tag) == item_name:
        items = [result_get]

    parsed: list[dict[str, str]] = []
    for item in items:
        row: dict[str, str] = {}
        for child in list(item):
            row[_local_name(child.tag)] = (child.text or "").strip()
        parsed.append(row)
    return parsed


def _parse_ultimo_resultado(result_node: ET.Element) -> dict[str, int | str | list[dict[str, str]]]:
    _raise_if_errors("FECompUltimoAutorizado", result_node, allow_empty_result=True)
    cbte_nro = _find_text(result_node, "CbteNro")
    pto_vta = _find_text(result_node, "PtoVta")
    cbte_tipo = _find_text(result_node, "CbteTipo")

    if not cbte_nro:
        raise WsfeClientError("FECompUltimoAutorizado devolvió una respuesta inválida.")

    return {
        "numero": int(cbte_nro),
        "punto_venta": int(pto_vta or 0),
        "tipo_comprobante": int(cbte_tipo or 0),
        "events": _parse_messages(result_node, "Events", "Ev"),
    }


def fedummy(*, timeout: int = 30) -> dict[str, str]:
    result_node = _request_soap("FEDummy", timeout=timeout)
    return {
        "appserver": _find_text(result_node, "AppServer"),
        "dbserver": _find_text(result_node, "DbServer"),
        "authserver": _find_text(result_node, "AuthServer"),
    }


def fe_param_get_tipos_cbte(auth: dict[str, object], *, timeout: int = 30) -> dict[str, object]:
    result_node = _request_soap("FEParamGetTiposCbte", {"Auth": auth}, timeout=timeout)
    _raise_if_errors("FEParamGetTiposCbte", result_node)
    return {
        "items": _parse_result_get_items(result_node, "CbteTipo"),
        "events": _parse_messages(result_node, "Events", "Ev"),
    }


def fe_param_get_tipos_doc(auth: dict[str, object], *, timeout: int = 30) -> dict[str, object]:
    result_node = _request_soap("FEParamGetTiposDoc", {"Auth": auth}, timeout=timeout)
    _raise_if_errors("FEParamGetTiposDoc", result_node)
    return {
        "items": _parse_result_get_items(result_node, "DocTipo"),
        "events": _parse_messages(result_node, "Events", "Ev"),
    }


def fe_param_get_ptos_venta(auth: dict[str, object], *, timeout: int = 30) -> dict[str, object]:
    result_node = _request_soap("FEParamGetPtosVenta", {"Auth": auth}, timeout=timeout)
    _raise_if_errors("FEParamGetPtosVenta", result_node)
    return {
        "items": _parse_result_get_items(result_node, "PtoVenta"),
        "events": _parse_messages(result_node, "Events", "Ev"),
    }


def fe_comp_ultimo_autorizado(
    auth: dict[str, object],
    *,
    pto_vta: int,
    cbte_tipo: int,
    timeout: int = 30,
) -> dict[str, int | str | list[dict[str, str]]]:
    result_node = _request_soap(
        "FECompUltimoAutorizado",
        {
            "Auth": auth,
            "PtoVta": int(pto_vta),
            "CbteTipo": int(cbte_tipo),
        },
        timeout=timeout,
    )
    return _parse_ultimo_resultado(result_node)
