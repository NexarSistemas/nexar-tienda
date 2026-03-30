#!/usr/bin/env python3
"""Tests para PASO 9: Gestión de Compras y actualización de Stock."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import app as application
import database as db


def test_paso9():
    """Suite completa de tests para Paso 9 - Compras."""

    print("\n" + "="*70)
    print("VALIDACIÓN PASO 9: Gestión de Compras")
    print("="*70)

    db.init_db()

    # Crear proveedor y producto base
    pid = db.add_proveedor({'nombre': 'Proveedor Test PASO9', 'cuit': '30-11111111-1', 'telefono': '1111111', 'email': 'paso9@proveedor.com', 'dias_credito': 30})
    prod_id = db.add_producto({'codigo_interno': 'P9-001', 'descripcion': 'Producto test PASO9', 'costo': 100, 'precio_venta': 150})

    # Verificar GET /compras
    print("\n[TEST 1] GET /compras")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/compras')
        assert response.status_code == 200
        assert b'Compras' in response.data

    print("✅ GET /compras OK")

    # GET nuevo formulario
    print("\n[TEST 2] GET /compras/nuevo")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get('/compras/nuevo')
        assert response.status_code == 200
        assert b'Crear Compra' in response.data or b'Nueva Compra' in response.data

    print("✅ GET /compras/nuevo OK")

    # POST crear compra
    print("\n[TEST 3] POST /compras/nuevo")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post('/compras/nuevo', data={
            'fecha': '2026-03-30',
            'numero_remito': 'R-0001',
            'proveedor_id': str(pid),
            'producto_id': str(prod_id),
            'cantidad': '5',
            'costo_unitario': '10.00',
            'observaciones': 'Compra de prueba PASO9'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Compra registrada exitosamente' in response.data

    print("✅ POST /compras/nuevo crea compra")

    compra = db.q('SELECT * FROM compras ORDER BY id DESC LIMIT 1', fetchone=True)
    assert compra is not None

    # Revisión de stock incrementado
    stock_row = db.q('SELECT stock_actual FROM stock WHERE producto_id=?', (prod_id,), fetchone=True)
    assert stock_row is not None and float(stock_row['stock_actual']) >= 5.0

    # GET detalle compra
    print("\n[TEST 4] GET /compras/<id>")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.get(f"/compras/{compra['id']}")
        assert response.status_code == 200
        assert f"Compra #{compra['id']}".encode() in response.data

    print("✅ GET /compras/<id> OK")

    # POST eliminar compra
    print("\n[TEST 5] POST /compras/<id>/eliminar")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}

        response = client.post(f"/compras/{compra['id']}/eliminar", follow_redirects=True)
        assert response.status_code == 200
        assert b'Compra #' in response.data and b'eliminada' in response.data

    print("✅ POST /compras/<id>/eliminar OK")

    # Verifica que la compra fue eliminada
    compra_deleted = db.get_compra(compra['id'])
    assert compra_deleted is None

    print("\n" + "="*70)
    print("✅ TODOS LOS TESTS DE RUTAS PASARON")
    print("="*70)


if __name__ == '__main__':
    print("═" * 60)
    print("  TEST PASO 9: GESTIÓN DE COMPRAS")
    print("═" * 60)

    print("\n✅ Inicializando base de datos...")
    db.init_db()

    print("✅ Ejecutando tests...")
    test_paso9()

    print("\n" + "═" * 60)
    print("✅ TESTS COMPLETADOS")
    print("═" * 60)
