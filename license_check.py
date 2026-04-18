from config.settings import settings
from license_manager import cargar_licencia
from activar_licencia import activar
from services.license_sdk import load_public_key

from nexar_licencias import validar_licencia


def verificar_inicio_app():
    licencia = cargar_licencia()

    if not licencia:
        print("⚠️ No hay licencia. Activando...")
        activar()
        licencia = cargar_licencia()

        if not licencia:
            print("❌ No se pudo activar la licencia")
            raise SystemExit(1)

    ok = validar_licencia(
        licencia,
        load_public_key(),
        settings.LICENSE_PRODUCT,
        debug=settings.DEBUG,
    )

    if not ok:
        print("❌ Licencia inválida o revocada")
        raise SystemExit(1)

    print("✔ Licencia válida")
