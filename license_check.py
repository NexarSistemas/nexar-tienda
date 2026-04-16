from nexar_licencias import validar_licencia

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

def check_license():
    licencia = {
        "license_key": "ABC123",
        "producto": "nexar-tienda",
        "signature": "7e966d55fca6a4faf2d35fdb6f491451b0ecb900b8402bd3f3af684b308543f48ac9fb079b8976e6d497c2cfa418e84fc231f891d052da0806429f9da7a51bb9f8f65f56a03c23fe3d2d552530d700b2a66738e6cd376f4c18b08c9111cedaa327bce43889c5f6a37fc9ce964aa553891d91bbf8077ec94b95bfab4a9be5ea0137be7341afefc6b150c01eeff25338dcc689b81268b8325d64a0bdc12aab466638eef97b024cb3a4992dc82f32a904f55d52756c023926fb90627357f3902b6a69852bba0ebdd13137fe4b1d4f299ca2076331671f77745e7db65c7be75d315205e3c8c76d22fe6d5ee1e4188f1712bab17eee5df7b118858d6ddfeb312bbee7"
    }

    ok = validar_licencia(
        licencia,
        PUBLIC_KEY,
        "nexar-tienda",
        debug=True
    )

    if not ok:
        print("❌ LICENCIA INVALIDA")
        exit()

    print("✔ LICENCIA OK")