from __future__ import annotations

import logging
import os

import requests

from licensing.planes import normalize_plan

DEFAULT_NEXAR_PAGOS_API = "https://nexar-pagos.netlify.app/.netlify/functions"
REQUEST_TIMEOUT_SECONDS = 12
PRICE_BY_PLAN = {
    "PRO": 9900,
    "MENSUAL_FULL": 19900,
}

logger = logging.getLogger(__name__)


class MercadoPagoCheckoutError(RuntimeError):
    """Error controlado del flujo de checkout."""


def _mask_license_key(license_key: str) -> str:
    value = str(license_key or "").strip()
    if not value:
        return ""
    if len(value) <= 6:
        return f"{value[:1]}***{value[-1:]}"
    return f"{value[:3]}***{value[-3:]}"


def get_nexar_pagos_api_base() -> str:
    return (
        os.getenv("NEXAR_PAGOS_API", DEFAULT_NEXAR_PAGOS_API).strip().rstrip("/")
        or DEFAULT_NEXAR_PAGOS_API
    )


def get_price_for_plan(plan_destino: str) -> int:
    plan = normalize_plan(plan_destino, default="")
    price = PRICE_BY_PLAN.get(plan)
    if not price:
        raise MercadoPagoCheckoutError("El plan solicitado no admite checkout online todavía.")
    return price


def build_external_reference(license_key: str, producto: str, plan_destino: str) -> str:
    license_value = str(license_key or "").strip()
    product_value = str(producto or "").strip()
    plan_value = normalize_plan(plan_destino, default="")

    if not license_value:
        raise MercadoPagoCheckoutError("No se encontró una licencia válida para iniciar el checkout.")
    if not product_value:
        raise MercadoPagoCheckoutError("No se pudo resolver el producto de la licencia.")
    if plan_value not in {"PRO", "MENSUAL_FULL"}:
        raise MercadoPagoCheckoutError("El plan solicitado no admite checkout online todavía.")

    return f"{license_value}|{product_value}|{plan_value}"


def create_checkout_preference(
    *,
    producto: str,
    plan_destino: str,
    precio: int,
    external_reference: str,
    license_key: str,
    email_titular: str,
) -> str:
    plan = normalize_plan(plan_destino, default="")
    email = str(email_titular or "").strip().lower()
    reference = str(external_reference or "").strip()
    api_base = get_nexar_pagos_api_base()

    if plan not in {"PRO", "MENSUAL_FULL"}:
        raise MercadoPagoCheckoutError("El plan solicitado no admite checkout online todavía.")
    if not email:
        raise MercadoPagoCheckoutError("Necesitás cargar un email del titular antes de continuar.")
    if not reference:
        raise MercadoPagoCheckoutError("No se pudo generar la referencia del checkout.")

    payload = {
        "producto": str(producto or "").strip(),
        "plan_destino": plan,
        "precio": int(precio),
        "external_reference": reference,
        "license_key": str(license_key or "").strip(),
        "email": email,
    }

    request_url = f"{api_base}/create-preference"
    logger.info(
        "Checkout Mercado Pago: creando preferencia producto=%s plan_destino=%s licencia=%s api=%s",
        payload["producto"],
        plan,
        _mask_license_key(payload["license_key"]),
        request_url,
    )

    try:
        response = requests.post(request_url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        logger.warning(
            "Checkout Mercado Pago timeout plan=%s licencia=%s",
            plan,
            _mask_license_key(payload["license_key"]),
        )
        raise MercadoPagoCheckoutError("El servicio de pagos tardó demasiado en responder.") from exc
    except requests.ConnectionError as exc:
        logger.warning(
            "Checkout Mercado Pago sin conexion plan=%s licencia=%s",
            plan,
            _mask_license_key(payload["license_key"]),
        )
        raise MercadoPagoCheckoutError("No se pudo conectar con el servicio de pagos.") from exc
    except requests.RequestException as exc:
        logger.warning(
            "Checkout Mercado Pago error de red plan=%s licencia=%s error=%s",
            plan,
            _mask_license_key(payload["license_key"]),
            exc.__class__.__name__,
        )
        raise MercadoPagoCheckoutError("No se pudo iniciar el checkout en este momento.") from exc

    body = {}
    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {}

    if response.status_code >= 400:
        detail = str(body.get("detalle") or body.get("error") or "").strip()
        logger.warning(
            "Checkout Mercado Pago rechazo status=%s plan=%s licencia=%s detalle=%s",
            response.status_code,
            plan,
            _mask_license_key(payload["license_key"]),
            detail[:200],
        )
        raise MercadoPagoCheckoutError(
            detail or "El servicio de pagos no pudo crear la preferencia."
        )

    init_point = str(body.get("init_point") or "").strip()
    if not init_point:
        logger.warning(
            "Checkout Mercado Pago respuesta incompleta plan=%s licencia=%s body=%s",
            plan,
            _mask_license_key(payload["license_key"]),
            body,
        )
        raise MercadoPagoCheckoutError("La preferencia de pago no devolvió un enlace válido.")

    logger.info(
        "Checkout Mercado Pago preferencia creada plan=%s licencia=%s",
        plan,
        _mask_license_key(payload["license_key"]),
    )
    return init_point
