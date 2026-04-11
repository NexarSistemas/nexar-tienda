"""
Servicio de licencias (MVP) para Nexar Tienda.

Diseño:
- Solicitud: se arma un payload con datos de negocio/equipo.
- Activación: se recibe un token firmado por el sistema de licencias.
- Validación: se verifica firma, equipo y vencimiento.

Formato de token esperado (JWT-like simplificado):
base64url(header).base64url(payload).base64url(firma_hmac_sha256)
"""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
from typing import Any, Dict, Tuple


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _json_compact(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_machine_fingerprint(machine_id: str, negocio: str = "") -> str:
    """Genera huella del equipo para atar la licencia a una máquina."""
    seed = f"{machine_id}|{negocio.strip().lower()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def build_license_request(data: Dict[str, Any], machine_id: str) -> Dict[str, Any]:
    """Estructura estándar que puede enviarse a licencias_fh."""
    negocio = data.get("negocio", "").strip()
    request_payload = {
        "nombre": data.get("nombre", "").strip(),
        "email": data.get("email", "").strip().lower(),
        "empresa": negocio,
        "equipo": data.get("equipo", "").strip() or machine_id,
        "machine_id": machine_id,
        "machine_hash": build_machine_fingerprint(machine_id, negocio),
        "plan_solicitado": data.get("plan_solicitado", "BASICA"),
        "issued_client_at": datetime.now(timezone.utc).isoformat(),
    }
    return request_payload


def decode_and_verify_token(token: str, secret: str) -> Tuple[Dict[str, Any], str]:
    """
    Valida token firmado con HMAC SHA256.
    Devuelve (payload, '') si es válido, o ({}, error_msg) si falla.
    """
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return {}, "Formato de token inválido."

        head_b64, payload_b64, signature_b64 = parts
        signed_data = f"{head_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(secret.encode("utf-8"), signed_data, hashlib.sha256).digest()
        provided_sig = _b64url_decode(signature_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return {}, "Firma de token inválida."

        header = json.loads(_b64url_decode(head_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if header.get("alg") != "HS256":
            return {}, "Algoritmo no soportado."

        return payload, ""
    except Exception:
        return {}, "No se pudo decodificar el token."


def validate_license_payload(payload: Dict[str, Any], machine_id: str, negocio: str = "") -> Tuple[bool, str]:
    """Valida reglas mínimas del payload de licencia."""
    plan = payload.get("plan", "").upper()
    if plan not in {"DEMO", "BASICA", "PRO"}:
        return False, "Plan de licencia inválido."

    bound_machine = payload.get("machine_id", "")
    bound_hash = payload.get("machine_hash", "")
    expected_hash = build_machine_fingerprint(machine_id, negocio)

    if bound_machine and bound_machine != machine_id:
        return False, "La licencia pertenece a otra máquina."

    if bound_hash and bound_hash != expected_hash:
        return False, "La licencia no coincide con la huella del equipo."

    exp = payload.get("exp")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                return False, "Licencia vencida."
        except ValueError:
            return False, "Fecha de vencimiento inválida."

    return True, ""


def build_example_token(payload: Dict[str, Any], secret: str | None = None) -> str:
    """
    Utilidad para pruebas locales / compatibilidad inicial con licencias_fh.
    Si no llega un token externo aún, permite generar uno de ejemplo.
    """
    secret = secret or os.getenv("LICENSE_TOKEN_SECRET", "")
    header = {"alg": "HS256", "typ": "JWT"}
    head_b64 = _b64url_encode(_json_compact(header))
    payload_b64 = _b64url_encode(_json_compact(payload))
    sign = hmac.new(secret.encode("utf-8"), f"{head_b64}.{payload_b64}".encode("utf-8"), hashlib.sha256).digest()
    sign_b64 = _b64url_encode(sign)
    return f"{head_b64}.{payload_b64}.{sign_b64}"
