from nexar_licencias import validar_licencia

def check_license():
    licencia = {
        "license_key": "ABC123"
    }

    ok = validar_licencia(
        licencia,
        public_key="public_key_fake",
        product_name="nexar-tienda",
        debug=True
    )

    if not ok:
        print("❌ LICENCIA INVALIDA - ACCESO DENEGADO")
        exit()

    print("✔ LICENCIA VALIDADA - ACCESO PERMITIDO")