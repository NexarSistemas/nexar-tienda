import json
import os
from pathlib import Path

# 📁 Guardar en directorio del proyecto (más seguro)
BASE_DIR = Path(__file__).resolve().parent.parent
LICENSE_FILE = BASE_DIR / "license.json"


def guardar_licencia(license_key):
    data = {
        "license_key": license_key
    }

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