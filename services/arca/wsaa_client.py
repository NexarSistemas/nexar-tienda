from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

import requests


logger = logging.getLogger(__name__)

WSAA_HOMOLOGACION_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"


class WsaaClientError(RuntimeError):
    pass


def _soap_envelope(cms_base64: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms_base64}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>"""


def _extract_login_ticket_xml(soap_xml: str) -> str:
    try:
        root = ET.fromstring(soap_xml)
    except ET.ParseError as exc:
        raise WsaaClientError("WSAA devolvió una respuesta SOAP inválida.") from exc

    fault = root.find(".//{*}Fault")
    if fault is not None:
        fault_text = "".join(text.strip() for text in fault.itertext() if text and text.strip())
        raise WsaaClientError(f"WSAA devolvió un fault SOAP: {fault_text or 'sin detalle'}")

    response_node = root.find(".//{*}loginCmsReturn")
    if response_node is None:
        raise WsaaClientError("WSAA no devolvió loginCmsReturn en la respuesta.")

    text_content = (response_node.text or "").strip()
    if text_content:
        return text_content

    children = list(response_node)
    if children:
        return ET.tostring(children[0], encoding="unicode")
    raise WsaaClientError("WSAA devolvió loginCmsReturn vacío.")


def _parse_login_ticket_response(login_ticket_xml: str) -> dict[str, str]:
    try:
        root = ET.fromstring(login_ticket_xml)
    except ET.ParseError as exc:
        raise WsaaClientError("La respuesta interna de WSAA no contiene XML válido.") from exc

    token = (root.findtext(".//token") or "").strip()
    sign = (root.findtext(".//sign") or "").strip()
    generation_time = (root.findtext(".//generationTime") or "").strip()
    expiration_time = (root.findtext(".//expirationTime") or "").strip()

    if not token or not sign or not generation_time or not expiration_time:
        raise WsaaClientError("La respuesta de WSAA no incluye token, sign o fechas requeridas.")

    return {
        "token": token,
        "sign": sign,
        "generation_time": generation_time,
        "expiration_time": expiration_time,
    }


def login_cms(
    cms_base64: str,
    *,
    ambiente: str = "homologacion",
    timeout: int = 30,
) -> dict[str, str]:
    ambiente_normalizado = str(ambiente or "").strip().lower() or "homologacion"
    if ambiente_normalizado != "homologacion":
        raise WsaaClientError(
            "La autenticación WSAA real en esta fase solo está habilitada para homologación."
        )

    try:
        response = requests.post(
            WSAA_HOMOLOGACION_URL,
            data=_soap_envelope(cms_base64).encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise WsaaClientError("No se pudo conectar con WSAA homologación.") from exc

    if response.status_code >= 400:
        logger.warning("WSAA homologacion devolvio HTTP %s", response.status_code)
        raise WsaaClientError(f"WSAA homologación devolvió HTTP {response.status_code}.")

    login_ticket_xml = _extract_login_ticket_xml(response.text)
    return _parse_login_ticket_response(login_ticket_xml)
