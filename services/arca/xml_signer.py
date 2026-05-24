from __future__ import annotations

import base64
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7


class XmlSignerError(RuntimeError):
    pass


def _read_bytes(path: str) -> bytes:
    file_path = Path(path).expanduser()
    try:
        return file_path.read_bytes()
    except OSError as exc:
        raise XmlSignerError(f"No se pudo leer el archivo requerido: {file_path}") from exc


def _load_certificate(cert_path: str) -> x509.Certificate:
    cert_bytes = _read_bytes(cert_path)
    loaders = (x509.load_pem_x509_certificate, x509.load_der_x509_certificate)
    for loader in loaders:
        try:
            return loader(cert_bytes)
        except ValueError:
            continue
    raise XmlSignerError("No se pudo interpretar el certificado ARCA configurado.")


def _load_private_key(key_path: str):
    key_bytes = _read_bytes(key_path)
    loaders = (
        serialization.load_pem_private_key,
        serialization.load_der_private_key,
    )
    for loader in loaders:
        try:
            return loader(key_bytes, password=None)
        except ValueError:
            continue
        except TypeError as exc:
            raise XmlSignerError("La clave privada configurada requiere una passphrase no soportada.") from exc
    raise XmlSignerError("No se pudo interpretar la clave privada ARCA configurada.")


def sign_tra(tra_xml: str, *, cert_path: str, key_path: str) -> str:
    try:
        certificate = _load_certificate(cert_path)
        private_key = _load_private_key(key_path)
        cms_der = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(tra_xml.encode("utf-8"))
            .add_signer(certificate, private_key, hashes.SHA256())
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
        )
    except XmlSignerError:
        raise
    except Exception as exc:
        raise XmlSignerError("Ocurrió un error inesperado al firmar el TRA para WSAA.") from exc
    return base64.b64encode(cms_der).decode("ascii")
