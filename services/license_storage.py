import json

from services.runtime_config import app_data_dir

LICENSE_FILE = app_data_dir() / "license.json"


def guardar_licencia(license_key, license_data=None):
    data = dict(license_data or {})
    data["license_key"] = license_key

    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        print("💾 Licencia guardada correctamente")

    except Exception as e:
        print("❌ Error guardando licencia:", e)


def cargar_licencia():
    if not LICENSE_FILE.exists():
        return None

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            # 🔎 validación mínima
            if "license_key" not in data:
                print("⚠️ license.json inválido")
                return None

            return data

    except json.JSONDecodeError:
        print("❌ JSON corrupto en license.json")
        return None

    except Exception as e:
        print("❌ Error leyendo licencia:", e)
        return None
