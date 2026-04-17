import json
import os

LICENSE_FILE = "license.json"


def guardar_licencia(license_key):
    data = {
        "license_key": license_key
    }

    with open(LICENSE_FILE, "w") as f:
        json.dump(data, f)


def cargar_licencia():
    if not os.path.exists(LICENSE_FILE):
        return None

    try:
        with open(LICENSE_FILE, "r") as f:
            return json.load(f)
    except:
        return None