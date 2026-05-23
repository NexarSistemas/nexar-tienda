from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

from services.paths import (
    bundle_dir,
    get_app_data_dir,
    get_cache_dir,
    get_config_dir,
    project_dir,
    restrict_permissions,
)


def _should_load_dotenv() -> bool:
    if os.getenv("NEXAR_SKIP_DOTENV", "").strip() == "1":
        return False
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    return True


def app_data_dir() -> Path:
    return get_app_data_dir()


def _load_json_config() -> dict:
    candidates = [
        Path(os.getenv("NEXAR_RUNTIME_CONFIG", "")),
        get_config_dir() / "license_runtime_config.json",
        bundle_dir() / "license_runtime_config.json",
        Path.cwd() / "license_runtime_config.json",
        project_dir() / "license_runtime_config.json",
    ]
    for path in candidates:
        if not path or not str(path):
            continue
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _ensure_secret_key(data_dir: Path) -> None:
    if os.getenv("SECRET_KEY", "").strip():
        return

    secret_path = get_config_dir() / "secret.key"
    try:
        if secret_path.exists():
            secret = secret_path.read_text(encoding="utf-8").strip()
        else:
            secret = secrets.token_hex(32)
            secret_path.write_text(secret, encoding="utf-8")
        restrict_permissions(secret_path)
        os.environ["SECRET_KEY"] = secret
    except Exception:
        os.environ["SECRET_KEY"] = secrets.token_hex(32)


def load_runtime_env() -> None:
    if _should_load_dotenv():
        load_dotenv()
    data_dir = app_data_dir()
    cache_dir = get_cache_dir()

    config = _load_json_config()
    for key, value in config.items():
        if value is not None and not os.getenv(key):
            os.environ[key] = str(value)

    if os.getenv("SUPABASE_ANON_KEY") and not os.getenv("SUPABASE_KEY"):
        os.environ["SUPABASE_KEY"] = os.getenv("SUPABASE_ANON_KEY", "")

    if not os.getenv("NEXAR_CACHE_FILE"):
        os.environ["NEXAR_CACHE_FILE"] = str(cache_dir / "license_cache.json")
    if not os.getenv("CACHE_FILE"):
        os.environ["CACHE_FILE"] = os.environ["NEXAR_CACHE_FILE"]

    _ensure_secret_key(data_dir)
