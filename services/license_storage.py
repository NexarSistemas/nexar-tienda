import json

from services.runtime_config import app_data_dir, restrict_permissions

LICENSE_FILE = app_data_dir() / "license.json"


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(str(message).encode("ascii", "ignore").decode("ascii"))


def guardar_licencia(license_key, license_data=None):
    data = dict(license_data or {})
    data["license_key"] = license_key

    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        restrict_permissions(LICENSE_FILE)

        _safe_print("Licencia guardada correctamente")

    except Exception as e:
        _safe_print(f"Error guardando licencia: {e}")


def cargar_licencia():
    if not LICENSE_FILE.exists():
        return None

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            if "license_key" not in data:
                _safe_print("license.json invalido")
                return None

            return data

    except json.JSONDecodeError:
        _safe_print("JSON corrupto en license.json")
        return None

    except Exception as e:
        _safe_print(f"Error leyendo licencia: {e}")
        return None
