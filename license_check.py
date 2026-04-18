from activar_licencia import activar
from services.license_sdk import validate_saved_license
from services.license_storage import cargar_licencia


def verificar_inicio_app():
    licencia = cargar_licencia()

    if not licencia:
        print("⚠️ No hay licencia. Activando...")
        activar()
        licencia = cargar_licencia()

        if not licencia:
            print("❌ No se pudo activar la licencia")
            raise SystemExit(1)

    ok, msg = validate_saved_license(debug=False)

    if not ok:
        print(f"❌ {msg}")
        raise SystemExit(1)

    print("✔ Licencia válida")
