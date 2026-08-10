from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import requests

DEFAULT_REPO = "NexarSistemas/nexar-tienda"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT = 2.5

WINDOWS_INSTALLER = "Nexar_Comercio_Windows_Setup.exe"
LINUX_INSTALLER = "Nexar_Comercio_Linux_amd64.deb"


def normalize_release_version(version: str) -> str:
    match = re.fullmatch(r"[vV]?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    if not match:
        return ""
    return ".".join(str(int(part)) for part in match.groups())


def _parse_version(version: str) -> tuple[int, int, int]:
    raw = (version or "0.0.0").strip().lstrip("vV")
    parts = []
    for chunk in raw.split(".")[:3]:
        number = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(number or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _release_api_url() -> str:
    repo = os.getenv("NEXAR_UPDATE_REPOSITORY", DEFAULT_REPO).strip() or DEFAULT_REPO
    return f"https://api.github.com/repos/{repo}/releases/latest"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _asset_matches_platform(name: str) -> bool:
    if _is_windows():
        return name == WINDOWS_INSTALLER or bool(
            re.fullmatch(r"(?:NexarTienda|NexarComercio)_\d+(?:\.\d+){1,2}_Setup\.exe", name)
        )
    return name == LINUX_INSTALLER or bool(
        re.fullmatch(r"nexar-tienda_\d+(?:\.\d+){1,2}_amd64\.deb", name)
    )


def _stable_installer_for_current_platform() -> str:
    return WINDOWS_INSTALLER if _is_windows() else LINUX_INSTALLER


def _select_installer_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    stable_name = _stable_installer_for_current_platform()
    for asset in assets:
        if str(asset.get("name") or "") == stable_name:
            return asset
    return next(
        (asset for asset in assets if _asset_matches_platform(str(asset.get("name") or ""))),
        None,
    )


def _installer_kind(asset_name: str) -> str:
    if asset_name.lower().endswith(".exe"):
        return "windows"
    if asset_name.lower().endswith(".deb"):
        return "linux"
    return ""


def check_latest_release(current_version: str) -> dict[str, Any]:
    if os.getenv("NEXAR_DISABLE_UPDATE_CHECK", "").lower() in {"1", "true", "yes"}:
        return {"available": False}

    response = requests.get(
        _release_api_url(),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "NexarTienda"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    release = response.json()
    latest = normalize_release_version(str(release.get("tag_name") or ""))
    if not latest:
        return {"available": False}

    available = _parse_version(latest) > _parse_version(current_version)
    assets = release.get("assets") or []
    installer_asset = _select_installer_asset(assets)
    asset_name = installer_asset.get("name") if installer_asset else ""
    return {
        "available": available,
        "current": current_version,
        "latest": latest,
        "url": release.get("html_url") or f"https://github.com/{DEFAULT_REPO}/releases/latest",
        "name": release.get("name") or f"Nexar Tienda v{latest}",
        "asset_name": asset_name,
        "asset_url": installer_asset.get("browser_download_url") if installer_asset else "",
        "asset_kind": _installer_kind(asset_name),
    }


def get_cached_update_info(app, current_version: str) -> dict[str, Any]:
    now = time.time()
    cached = app.config.get("UPDATE_INFO_CACHE")
    if cached and now - cached.get("checked_at", 0) < CHECK_INTERVAL_SECONDS:
        return cached.get("data", {"available": False})

    try:
        data = check_latest_release(current_version)
    except Exception:
        data = {"available": False}

    app.config["UPDATE_INFO_CACHE"] = {"checked_at": now, "data": data}
    return data


def download_release_asset(asset_url: str, destination_dir: Path, version: str = "") -> Path:
    parsed_url = urlsplit(asset_url or "")
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("No hay un instalador descargable para esta version.")

    decoded_path = unquote(parsed_url.path)
    path_parts = decoded_path.split("/")
    filename = path_parts[-1] if path_parts else ""
    if (
        not filename
        or ".." in path_parts
        or "/" in filename
        or "\\" in filename
        or Path(filename).name != filename
        or not _asset_matches_platform(filename)
    ):
        raise ValueError("El instalador de actualizacion no es valido.")

    normalized_version = normalize_release_version(version)
    if version and not normalized_version:
        raise ValueError("La version de la actualizacion no es valida.")

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_root = destination_dir.resolve()
    target = (destination_root / filename).resolve()
    partial = (destination_root / f"{filename}.part").resolve()
    if target.parent != destination_root or partial.parent != destination_root:
        raise ValueError("El instalador de actualizacion no es valido.")

    with requests.get(asset_url, stream=True, timeout=30) as response:
        response.raise_for_status()
        with partial.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    partial.replace(target)
    version_file = destination_root / f"{filename}.version"
    if normalized_version:
        version_file.write_text(normalized_version, encoding="utf-8")
    elif version_file.exists():
        version_file.unlink()
    return target
