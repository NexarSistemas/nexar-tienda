from nexar_licencias import validar_licencia
from config.settings import settings
from license_manager import cargar_licencia
from activar_licencia import activar


PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyxEOQihs10IR40mIkj2F
+IcoRzhCWkvryfcKABaZ6xXnGzvRCY7VE8LxtjetcjbXOIe8noPEhjPXBybIKzhG
pj4hE/jY79H60qhs6kwUMrzx650HIIxRR5vIfXvEXrFt5MbU3PdkKSo6UBF49Wu7
9A4MVWHEGCiB+VT8UdiI4X9e40Bxy4ySiCFdK7Yhqzju8WaJo3rYhcimzrcL9Coy
epd2RqrE294T3t2aC7Ltp6Zvtj21Qk3C+ki+LUcnTDgC0VbZdRXvVcgyHy27KFoB
uBkVZtixl498oc+HFKrJ4gRn0Axjdd/5TI2++bzxB98tMgoIT1i2DtwPYlDEiN/J
bQIDAQAB
-----END PUBLIC KEY-----
"""

def verificar_inicio_app():
    licencia = cargar_licencia()

    from activar_licencia import activar

def verificar_inicio_app():
    licencia = cargar_licencia()

    if not licencia:
        print("⚠️ No hay licencia. Activando...")

        activar()  # 👈 pide licencia al usuario

        licencia = cargar_licencia()

        if not licencia:
            print("❌ No se pudo activar la licencia")
            exit()

    ok = validar_licencia(
        licencia,
        PUBLIC_KEY,
        settings.LICENSE_PRODUCT,
        debug=settings.DEBUG
    )

    if not ok:
        print("❌ Licencia inválida o revocada")
        exit()

    print("✔ Licencia válida")