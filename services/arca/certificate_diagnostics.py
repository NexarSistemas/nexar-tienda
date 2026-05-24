from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization


logger = logging.getLogger(__name__)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _default_certificate_result(path: str) -> dict[str, object]:
    return {
        "path": path,
        "exists": False,
        "valid": False,
        "format": "",
        "error": "",
        "not_valid_after": "",
        "certificate": None,
    }


def _default_key_result(path: str) -> dict[str, object]:
    return {
        "path": path,
        "exists": False,
        "valid": False,
        "format": "",
        "requires_password": False,
        "error": "",
        "private_key": None,
    }


def diagnose_certificate(path_value: object) -> dict[str, object]:
    path = Path(_clean_text(path_value)).expanduser()
    result = _default_certificate_result(str(path))
    if not result["path"]:
        result["error"] = "Ruta de certificado no configurada."
        return result
    if not path.exists():
        result["error"] = "El archivo de certificado no existe."
        return result
    if not path.is_file():
        result["error"] = "La ruta del certificado no apunta a un archivo."
        return result

    result["exists"] = True
    try:
        raw = path.read_bytes()
    except OSError as exc:
        result["error"] = f"No se pudo leer el certificado: {exc.strerror or exc.__class__.__name__}."
        logger.warning("No se pudo leer certificado ARCA path=%s", path)
        return result

    loaders = (
        ("PEM", x509.load_pem_x509_certificate),
        ("DER", x509.load_der_x509_certificate),
    )
    for cert_format, loader in loaders:
        try:
            certificate = loader(raw)
        except ValueError:
            continue
        result["valid"] = True
        result["format"] = cert_format
        result["certificate"] = certificate
        result["not_valid_after"] = certificate.not_valid_after_utc.astimezone(UTC).replace(
            microsecond=0
        ).isoformat()
        return result

    result["error"] = "El archivo no contiene un certificado X509 válido en formato PEM o DER."
    logger.warning("Certificado ARCA invalido path=%s", path)
    return result


def diagnose_private_key(path_value: object) -> dict[str, object]:
    path = Path(_clean_text(path_value)).expanduser()
    result = _default_key_result(str(path))
    if not result["path"]:
        result["error"] = "Ruta de clave privada no configurada."
        return result
    if not path.exists():
        result["error"] = "El archivo de clave privada no existe."
        return result
    if not path.is_file():
        result["error"] = "La ruta de la clave privada no apunta a un archivo."
        return result

    result["exists"] = True
    try:
        raw = path.read_bytes()
    except OSError as exc:
        result["error"] = f"No se pudo leer la clave privada: {exc.strerror or exc.__class__.__name__}."
        logger.warning("No se pudo leer key ARCA path=%s", path)
        return result

    loaders = (
        ("PEM", serialization.load_pem_private_key),
        ("DER", serialization.load_der_private_key),
    )
    for key_format, loader in loaders:
        try:
            private_key = loader(raw, password=None)
        except TypeError:
            result["format"] = key_format
            result["requires_password"] = True
            result["error"] = "La clave privada requiere contraseña y no está soportada en esta fase."
            logger.warning("Key ARCA requiere password path=%s format=%s", path, key_format)
            return result
        except ValueError:
            continue
        result["valid"] = True
        result["format"] = key_format
        result["private_key"] = private_key
        return result

    result["error"] = "El archivo no contiene una clave privada válida en formato PEM o DER."
    logger.warning("Key ARCA invalida path=%s", path)
    return result


def _public_key_fingerprint(public_key) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def diagnose_certificate_pair(cert_path: object, key_path: object) -> dict[str, object]:
    certificate = diagnose_certificate(cert_path)
    private_key = diagnose_private_key(key_path)
    match = False
    pair_error = ""

    if certificate["valid"] and private_key["valid"]:
        cert_fingerprint = _public_key_fingerprint(certificate["certificate"].public_key())
        key_fingerprint = _public_key_fingerprint(private_key["private_key"].public_key())
        match = cert_fingerprint == key_fingerprint
        if not match:
            pair_error = "El certificado y la clave privada no corresponden entre sí."

    return {
        "certificate_exists": certificate["exists"],
        "certificate_valid": certificate["valid"],
        "certificate_format": certificate["format"],
        "certificate_error": certificate["error"],
        "certificate_not_valid_after": certificate["not_valid_after"],
        "key_exists": private_key["exists"],
        "key_valid": private_key["valid"],
        "key_format": private_key["format"],
        "key_requires_password": private_key["requires_password"],
        "key_error": private_key["error"],
        "pair_match": match,
        "pair_error": pair_error,
        "certificate_result": certificate,
        "key_result": private_key,
    }
