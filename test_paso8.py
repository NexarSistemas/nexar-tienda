#!/usr/bin/env python3
"""Tests para PASO 8: Gestión de Proveedores y Cuentas Corrientes."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import app as application
import database as db


def test_paso8():
    """Suite completa de tests para Paso 8 - Gestión de Proveedores"""

    print("\n" + "="*70)
    print("VALIDACIÓN PASO 8: Gestión de Proveedores y Cuentas Corrientes")
    print("="*70)

    # ─── TEST 1: GET /proveedores - Lista de proveedores
    print("\n[TEST 1] GET /proveedores - Lista de proveedores")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/proveedores')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'proveedores' in response.data.lower(), "Página de proveedores no renderiza"

    print("✅ GET /proveedores retorna 200, template correcto")

    # ─── TEST 2: GET /proveedores/nuevo - Formulario crear proveedor
    print("\n[TEST 2] GET /proveedores/nuevo - Formulario crear proveedor")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/proveedores/nuevo')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Crear Proveedor' in response.data, "Form no renderiza"

    print("✅ GET /proveedores/nuevo retorna formulario")

    # ─── TEST 3: POST /proveedores/nuevo - Crear proveedor
    print("\n[TEST 3] POST /proveedores/nuevo - Crear proveedor")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/proveedores/nuevo', data={
            'nombre': 'Proveedor Test PASO8',
            'cuit': '30-12345678-9',
            'telefono': '123456789',
            'email': 'test@proveedor.com',
            'dias_credito': '45'
        }, follow_redirects=True)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Proveedor creado exitosamente' in response.data, "Proveedor no creado"

    print("✅ POST /proveedores/nuevo crea proveedor correctamente")

    # ─── TEST 4: GET /proveedores/1/editar - Formulario editar proveedor
    print("\n[TEST 4] GET /proveedores/1/editar - Formulario editar proveedor")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/proveedores/1/editar')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Editar Proveedor' in response.data, "Form editar no renderiza"

    print("✅ GET /proveedores/1/editar retorna formulario")

    # ─── TEST 5: POST /proveedores/1/editar - Actualizar proveedor
    print("\n[TEST 5] POST /proveedores/1/editar - Actualizar proveedor")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/proveedores/1/editar', data={
            'nombre': 'Proveedor Editado PASO8',
            'cuit': '30-87654321-0',
            'telefono': '987654321',
            'email': 'editado@proveedor.com',
            'dias_credito': '60',
            'activo': '1'
        }, follow_redirects=True)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Proveedor actualizado exitosamente' in response.data, "Proveedor no actualizado"

    print("✅ POST /proveedores/1/editar actualiza proveedor correctamente")

    # ─── TEST 6: GET /proveedores/1 - Detalle de proveedor
    print("\n[TEST 6] GET /proveedores/1 - Detalle de proveedor")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/proveedores/1')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Proveedor Editado PASO8' in response.data, "Detalle no muestra proveedor"

    print("✅ GET /proveedores/1 muestra detalle correctamente")

    # ─── TEST 7: POST /proveedores/1/movimiento - Agregar movimiento
    print("\n[TEST 7] POST /proveedores/1/movimiento - Agregar movimiento")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/proveedores/1/movimiento', data={
            'tipo': 'Compra',
            'numero_comprobante': 'COMP001',
            'debe': '500.00',
            'haber': '0',
            'observaciones': 'Movimiento test'
        }, follow_redirects=True)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Movimiento agregado exitosamente' in response.data, "Movimiento no agregado"

    print("✅ POST /proveedores/1/movimiento agrega movimiento correctamente")

    # ─── TEST 8: POST /proveedores/1/eliminar - Desactivar proveedor
    print("\n[TEST 8] POST /proveedores/1/eliminar - Desactivar proveedor")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/proveedores/1/eliminar', follow_redirects=True)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'desactivado' in response.data, "Proveedor no desactivado"

    print("✅ POST /proveedores/1/eliminar desactiva proveedor correctamente")

    print("\n" + "="*70)
    print("✅ TODOS LOS TESTS DE RUTAS PASARON")
    print("="*70)


if __name__ == '__main__':
    print("═" * 60)
    print("  TEST PASO 8: GESTIÓN DE PROVEEDORES")
    print("═" * 60)

    print("\n✅ Inicializando base de datos...")
    db.init_db()

    print("✅ Ejecutando tests...")
    test_paso8()

    print("\n" + "═" * 60)
    print("✅ TESTS COMPLETADOS")
    print("═" * 60)
