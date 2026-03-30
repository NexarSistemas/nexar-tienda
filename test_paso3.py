#!/usr/bin/env python3
"""Script de prueba rápida de Nexar Tienda."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import init_db, get_usuarios, verify_password, get_usuario_by_username

print("═" * 50)
print("  TEST RÁPIDO NEXAR TIENDA - Paso 3")
print("═" * 50)

# 1. Inicializar BD
print("\n✅ Inicializando BD...", end=" ")
init_db()
print("OK")

# 2. Verificar usuarios
print("✅ Verificando usuarios...", end=" ")
usuarios = get_usuarios()
assert len(usuarios) == 2, f"Se esperaban 2 usuarios, se encontraron {len(usuarios)}"
print(f"OK ({len(usuarios)} usuarios)")

# 3. Verificar login admin
print("✅ Verificando login admin...", end=" ")
admin = get_usuario_by_username('admin')
assert admin is not None, "Usuario admin no encontrado"
assert verify_password('admin123', admin['password_hash']), "Contraseña admin incorrecta"
print("OK")

# 4. Verificar Flask
print("✅ Verificando Flask...", end=" ")
assert app is not None, "Flask app no inicializado"
print("OK")

# 5. Testear cliente Flask
print("✅ Testeando rutas...", end=" ")
client = app.test_client()

# Sin autenticación
resp = client.get('/')
assert resp.status_code in [302, 200], f"GET / falló con {resp.status_code}"

# Login page
resp = client.get('/login')
assert resp.status_code == 200, f"GET /login falló con {resp.status_code}"
print("OK")

# 6. Test login correcto
print("✅ Test login...", end=" ")
resp = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
assert b'Dashboard' in resp.data or b'dashboard' in resp.data, "Login falló"
print("OK")

print("\n" + "═" * 50)
print("✅ TODOS LOS TESTS PASARON CORRECTAMENTE")
print("═" * 50)
print("\n📝 Próximas etapas:")
print("  Paso 4: Módulo de Productos (ABM)")
print("  Paso 5: Módulo de Stock")
print("  Paso 6: Punto de Venta (POS)")
print("\n🚀 Para iniciar la app: python3 app.py")
print("   Login: admin / admin123")
print("          vendedor / vendedor123")
