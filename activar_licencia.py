from services.license_sdk import validate_license_key
from services.license_storage import guardar_licencia


def activar():
    key = input("Ingrese su licencia: ").strip()

    ok, msg = validate_license_key(key, debug=False)

    if not ok:
        print(f"❌ {msg}")
        return

    guardar_licencia(key)
    print("✔ Licencia activada correctamente")


if __name__ == "__main__":
    activar()
