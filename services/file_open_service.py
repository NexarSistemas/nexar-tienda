from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


def build_file_uri(path: str | Path) -> str:
    return Path(path).expanduser().resolve().as_uri()


def _is_external_url(target: str | Path) -> bool:
    parsed = urlparse(str(target).strip())
    return parsed.scheme in {"http", "https", "file"}


def _open_with_platform_handler(target: str, system_name: str) -> tuple[str, list[str] | None]:
    if system_name.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
        return "os.startfile", None
    if system_name == "darwin":
        command = ["open", target]
        subprocess.Popen(command)
        return "open", command

    command = ["xdg-open", target]
    subprocess.Popen(command)
    return "xdg-open", command


def open_external_target(target: str | Path) -> dict[str, object]:
    target_label = str(target).strip()
    if not target_label:
        logger.warning("No se pudo abrir destino externo vacio")
        return {
            "ok": False,
            "message": "No se recibió una URL o ruta válida para abrir.",
            "target": target_label,
        }

    system_name = platform.system().lower()
    try:
        method_name, command = _open_with_platform_handler(target_label, system_name)
        logger.info(
            "Apertura externa solicitada plataforma=%s metodo=%s target=%s comando=%s",
            system_name,
            method_name,
            target_label,
            command or "os.startfile",
        )
    except Exception as exc:
        logger.exception(
            "No se pudo abrir destino externo plataforma=%s target=%s",
            system_name,
            target_label,
        )
        return {
            "ok": False,
            "message": f"No se pudo abrir automáticamente. Abrilo manualmente desde: {target_label}",
            "target": target_label,
            "error": str(exc),
            "platform": system_name,
        }

    return {
        "ok": True,
        "message": f"Se abrió correctamente: {target_label}",
        "target": target_label,
        "platform": system_name,
        "method": method_name,
    }


def open_file_cross_platform(path: str | Path) -> dict[str, object]:
    if _is_external_url(path):
        return open_external_target(path)

    target_path = Path(path).expanduser().resolve()
    target_label = str(target_path)

    if not target_path.exists():
        logger.warning("No se pudo abrir destino inexistente path=%s", target_label)
        return {
            "ok": False,
            "message": f"No se encontró el archivo o carpeta: {target_label}",
            "path": target_label,
        }

    system_name = platform.system().lower()
    try:
        method_name, command = _open_with_platform_handler(str(target_path), system_name)
        logger.info(
            "Apertura de archivo solicitada plataforma=%s metodo=%s path=%s comando=%s",
            system_name,
            method_name,
            target_label,
            command or "os.startfile",
        )
    except Exception as exc:
        logger.exception("No se pudo abrir destino path=%s plataforma=%s", target_label, system_name)
        return {
            "ok": False,
            "message": f"No se pudo abrir automáticamente. Abrilo manualmente desde: {target_label}",
            "path": target_label,
            "error": str(exc),
        }

    return {
        "ok": True,
        "message": f"Se abrió correctamente: {target_label}",
        "path": target_label,
        "platform": system_name,
        "method": method_name,
    }
