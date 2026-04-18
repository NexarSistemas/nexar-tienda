import json

from services.runtime_config import app_data_dir, restrict_permissions


LICENSE_FILE = app_data_dir() / "license.json"

def guardar_licencia(data: dict):
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    restrict_permissions(LICENSE_FILE)

def cargar_licencia():
    if not LICENSE_FILE.exists():
        return None

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def borrar_licencia():
    if LICENSE_FILE.exists():
        LICENSE_FILE.unlink()
