from __future__ import annotations

import os
import time
from typing import Any

import requests

DEFAULT_REPO = "NexarSistemas/nexar-tienda"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT = 2.5


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
    latest = (release.get("tag_name") or "").strip().lstrip("vV")
    if not latest:
        return {"available": False}

    available = _parse_version(latest) > _parse_version(current_version)
    return {
        "available": available,
        "current": current_version,
        "latest": latest,
        "url": release.get("html_url") or f"https://github.com/{DEFAULT_REPO}/releases/latest",
        "name": release.get("name") or f"Nexar Tienda v{latest}",
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
