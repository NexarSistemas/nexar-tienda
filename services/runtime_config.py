from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv


APP_DIR_NAME = "Nexar Tienda"
LINUX_DIR_NAME = "nexar-tienda"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_dir()


def app_data_dir() -> Path:
    if not is_frozen() and os.getenv("NEXAR_USE_USER_DATA", "").lower() not in {"1", "true", "yes"}:
        return project_dir()

    if os.name == "nt":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
        path = base / APP_DIR_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        path = base / LINUX_DIR_NAME

    path.mkdir(parents=True, exist_ok=True)
    restrict_permissions(path, directory=True)
    return path


def restrict_permissions(path: Path, *, directory: bool = False) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o700 if directory else 0o600)
    except Exception:
        pass


def _load_json_config() -> dict:
    candidates = [
        Path(os.getenv("NEXAR_RUNTIME_CONFIG", "")),
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

    secret_path = data_dir / "secret.key"
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
    load_dotenv()
    data_dir = app_data_dir()

    config = _load_json_config()
    for key, value in config.items():
        if value is not None and not os.getenv(key):
            os.environ[key] = str(value)

    if os.getenv("SUPABASE_ANON_KEY") and not os.getenv("SUPABASE_KEY"):
        os.environ["SUPABASE_KEY"] = os.getenv("SUPABASE_ANON_KEY", "")

    if not os.getenv("NEXAR_CACHE_FILE"):
        os.environ["NEXAR_CACHE_FILE"] = str(data_dir / "license_cache.json")
    if not os.getenv("CACHE_FILE"):
        os.environ["CACHE_FILE"] = os.environ["NEXAR_CACHE_FILE"]

    _ensure_secret_key(data_dir)
