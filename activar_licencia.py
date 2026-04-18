from config.settings import settings
from license_manager import guardar_licencia
from services.license_sdk import load_public_key

from nexar_licencias import validar_licencia


def activar():
    key = input("Ingrese su licencia: ").strip()
    licencia = {"license_key": key}

    ok = validar_licencia(
        licencia,
        load_public_key(),
        settings.LICENSE_PRODUCT,
        debug=True,
    )

    if not ok:
        print("❌ Licencia inválida")
        return

    guardar_licencia(licencia)
    print("✔ Licencia activada correctamente")


if __name__ == "__main__":
    activar()
