#!/usr/bin/env python3
"""Tests para PASO 7: Gestión de Clientes y Cuentas Corrientes."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import app as application
import database as db

def test_paso7():
    """Suite completa de tests para Paso 7 - Gestión de Clientes"""

    print("\n" + "="*70)
    print("VALIDACIÓN PASO 7: Gestión de Clientes y Cuentas Corrientes")
    print("="*70)

    # ─── TEST 1: GET /clientes - Lista de clientes
    print("\n[TEST 1] GET /clientes - Lista de clientes")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/clientes')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'clientes' in response.data.lower(), "Página de clientes no renderiza"

    print("✅ GET /clientes retorna 200, template correcto")

    # ─── TEST 2: GET /clientes/nuevo - Formulario crear
    print("\n[TEST 2] GET /clientes/nuevo - Formulario crear cliente")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/clientes/nuevo')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Crear Cliente' in response.data, "Form no renderiza"

    print("✅ GET /clientes/nuevo retorna formulario")

    # ─── TEST 3: POST /clientes/nuevo - Crear cliente
    print("\n[TEST 3] POST /clientes/nuevo - Crear cliente")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/clientes/nuevo', data={
            'nombre': 'Cliente Test PASO7',
            'dni_cuit': '12345678',
            'telefono': '123456789',
            'email': 'test@cliente.com',
            'limite_credito': '1000.00'
        }, follow_redirects=True)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Cliente creado exitosamente' in response.data, "Cliente no creado"

    print("✅ POST /clientes/nuevo crea cliente correctamente")

    # ─── TEST 4: GET /clientes/1/editar - Formulario editar
    print("\n[TEST 4] GET /clientes/1/editar - Formulario editar cliente")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/clientes/1/editar')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Editar Cliente' in response.data, "Form editar no renderiza"

    print("✅ GET /clientes/1/editar retorna formulario")

    # ─── TEST 5: POST /clientes/1/editar - Actualizar cliente
    print("\n[TEST 5] POST /clientes/1/editar - Actualizar cliente")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/clientes/1/editar', data={
            'nombre': 'Cliente Editado PASO7',
            'dni_cuit': '87654321',
            'telefono': '987654321',
            'email': 'editado@test.com',
            'limite_credito': '1500.00',
            'activo': '1'
        }, follow_redirects=True)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Cliente actualizado exitosamente' in response.data, "Cliente no actualizado"

    print("✅ POST /clientes/1/editar actualiza cliente correctamente")

    # ─── TEST 6: GET /clientes/1 - Detalle de cliente
    print("\n[TEST 6] GET /clientes/1 - Detalle de cliente")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/clientes/1')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Cliente Editado PASO7' in response.data, "Detalle no muestra cliente"

    print("✅ GET /clientes/1 muestra detalle correctamente")

    # ─── TEST 7: POST /clientes/1/movimiento - Agregar movimiento
    print("\n[TEST 7] POST /clientes/1/movimiento - Agregar movimiento")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/clientes/1/movimiento', data={
            'tipo': 'Venta',
            'numero_comprobante': 'TEST001',
            'debe': '200.00',
            'haber': '0',
            'observaciones': 'Movimiento de test'
        }, follow_redirects=True)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Movimiento agregado exitosamente' in response.data, "Movimiento no agregado"

    print("✅ POST /clientes/1/movimiento agrega movimiento correctamente")

    # ─── TEST 8: POST /clientes/1/eliminar - Eliminar cliente
    print("\n[TEST 8] POST /clientes/1/eliminar - Desactivar cliente")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/clientes/1/eliminar', follow_redirects=True)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'desactivado' in response.data, "Cliente no desactivado"

    print("✅ POST /clientes/1/eliminar desactiva cliente correctamente")

    print("\n" + "="*70)
    print("✅ TODOS LOS TESTS DE RUTAS PASARON")
    print("="*70)


# ─── EJECUCIÓN PRINCIPAL ─────────────────────────────────────────────────────

if __name__ == '__main__':
    print("═" * 60)
    print("  TEST PASO 7: GESTIÓN DE CLIENTES")
    print("═" * 60)

    # Inicializar BD
    print("\n✅ Inicializando base de datos...")
    db.init_db()

    # Ejecutar tests
    print("✅ Ejecutando tests...")
    test_paso7()

    print("\n" + "═" * 60)
    print("✅ TESTS COMPLETADOS")
    print("═" * 60)