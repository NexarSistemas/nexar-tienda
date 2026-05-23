from __future__ import annotations

from datetime import datetime
from pathlib import Path

import database as db
from modules.arca.services.comprobantes_service import registrar_evento
from modules.arca.services.config_service import AMBIENTES_VALIDOS, normalizar_cuit


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _validar_ambiente(ambiente: str) -> str:
    normalized = _clean_text(ambiente).lower()
    if normalized not in AMBIENTES_VALIDOS:
        raise ValueError("El ambiente debe ser homologacion o produccion.")
    return normalized


def _ensure_certificate_dirs() -> None:
    for directory in (
        PROJECT_ROOT / "data" / "arca" / "certificados",
        PROJECT_ROOT / "data" / "arca" / "keys",
    ):
        directory.mkdir(parents=True, exist_ok=True)


def _resolver_ruta(path_value: object) -> Path:
    path = Path(_clean_text(path_value)).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _validar_archivo(path_value: object, field_label: str) -> str:
    normalized = _clean_text(path_value)
    if not normalized:
        raise ValueError(f"La ruta de {field_label} es obligatoria.")
    path = _resolver_ruta(normalized)
    if not path.exists():
        raise ValueError(f"La ruta de {field_label} no existe.")
    if not path.is_file():
        raise ValueError(f"La ruta de {field_label} debe apuntar a un archivo.")
    return str(path)


def _validar_vencimiento(value: object) -> str | None:
    normalized = _clean_text(value)
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("La fecha de vencimiento debe tener formato AAAA-MM-DD.") from exc


def _estado_desde_datos(vencimiento: str | None, activo: int) -> str:
    if activo:
        return "activo"
    if vencimiento:
        try:
            if datetime.strptime(vencimiento, "%Y-%m-%d").date() < datetime.now().date():
                return "vencido"
        except ValueError:
            return "pendiente"
    return "pendiente"


def _row_to_dict(row) -> dict[str, object]:
    if not row:
        return {}
    data = dict(row)
    cert_path = _resolver_ruta(data.get("certificado_path", "")) if data.get("certificado_path") else None
    key_path = _resolver_ruta(data.get("key_path", "")) if data.get("key_path") else None
    data["certificado_existe"] = bool(cert_path and cert_path.exists())
    data["key_existe"] = bool(key_path and key_path.exists())
    data["activo"] = int(data.get("activo") or 0)
    data["estado"] = _estado_desde_datos(data.get("vencimiento"), data["activo"])
    return data


def listar_certificados() -> list[dict[str, object]]:
    _ensure_certificate_dirs()
    rows = db.q(
        """
        SELECT id, nombre, ambiente, cuit, certificado_path, key_path, vencimiento, estado,
               activo, observaciones, created_at, updated_at
        FROM arca_certificados
        ORDER BY ambiente ASC, activo DESC, datetime(COALESCE(updated_at, created_at)) DESC, id DESC
        """
    )
    return [_row_to_dict(row) for row in rows]


def registrar_certificado(data: dict[str, object] | None) -> dict[str, object]:
    _ensure_certificate_dirs()
    payload = data or {}
    nombre = _clean_text(payload.get("nombre"))
    if not nombre:
        raise ValueError("El nombre del certificado es obligatorio.")
    ambiente = _validar_ambiente(payload.get("ambiente", "homologacion"))
    cuit = normalizar_cuit(payload.get("cuit"))
    certificado_path = _validar_archivo(payload.get("certificado_path"), "certificado")
    key_path = _validar_archivo(payload.get("key_path"), "clave privada")
    vencimiento = _validar_vencimiento(payload.get("vencimiento"))
    observaciones = _clean_text(payload.get("observaciones"))
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    estado = _estado_desde_datos(vencimiento, 0)

    certificado_id = int(
        db.q(
            """
            INSERT INTO arca_certificados
            (nombre, ambiente, certificado_path, key_path, activo, cuit, vencimiento, estado,
             observaciones, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre,
                ambiente,
                certificado_path,
                key_path,
                0,
                cuit,
                vencimiento,
                estado,
                observaciones,
                now,
                now,
            ),
            commit=True,
        )
    )
    registrar_evento(
        nivel="info",
        mensaje="Certificado ARCA registrado",
        detalle={
            "certificado_id": certificado_id,
            "nombre": nombre,
            "ambiente": ambiente,
            "cuit": cuit,
        },
    )
    return obtener_certificado(certificado_id)


def obtener_certificado(certificado_id: int) -> dict[str, object]:
    row = db.q(
        """
        SELECT id, nombre, ambiente, cuit, certificado_path, key_path, vencimiento, estado,
               activo, observaciones, created_at, updated_at
        FROM arca_certificados
        WHERE id = ?
        """,
        (int(certificado_id),),
        fetchone=True,
    )
    if not row:
        raise ValueError("No se encontró el certificado indicado.")
    return _row_to_dict(row)


def obtener_certificado_activo(ambiente: str) -> dict[str, object] | None:
    ambiente_normalizado = _validar_ambiente(ambiente)
    row = db.q(
        """
        SELECT id, nombre, ambiente, cuit, certificado_path, key_path, vencimiento, estado,
               activo, observaciones, created_at, updated_at
        FROM arca_certificados
        WHERE ambiente = ? AND activo = 1
        ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
        LIMIT 1
        """,
        (ambiente_normalizado,),
        fetchone=True,
    )
    return _row_to_dict(row) if row else None


def activar_certificado(certificado_id: int) -> dict[str, object]:
    certificado = obtener_certificado(certificado_id)
    if not certificado["certificado_existe"]:
        raise ValueError("No se puede activar: la ruta del certificado no existe.")
    if not certificado["key_existe"]:
        raise ValueError("No se puede activar: la ruta de la clave privada no existe.")

    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    db.q(
        "UPDATE arca_certificados SET activo = 0, estado = 'pendiente', updated_at = ? WHERE ambiente = ?",
        (now, certificado["ambiente"]),
        commit=True,
    )
    db.q(
        "UPDATE arca_certificados SET activo = 1, estado = 'activo', updated_at = ? WHERE id = ?",
        (now, int(certificado_id)),
        commit=True,
    )
    registrar_evento(
        nivel="info",
        mensaje="Certificado ARCA activado",
        detalle={
            "certificado_id": int(certificado_id),
            "nombre": certificado["nombre"],
            "ambiente": certificado["ambiente"],
            "cuit": certificado.get("cuit", ""),
        },
    )
    return obtener_certificado(certificado_id)
