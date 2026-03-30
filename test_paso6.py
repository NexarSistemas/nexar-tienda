"""
Nexar Tienda — test_paso6.py
Tests para PASO 6: Módulo de Punto de Venta (POS)

Pruebas:
- Búsqueda de productos
- Gestión del carrito
- Creación de ventas
- Decremento de stock
- Generación de tickets
"""

import pytest
import json
from app import app, db
from datetime import datetime


class TestPOSFunctions:
    """Tests para funciones de POS en database.py"""

    def test_next_ticket(self):
        """Prueba generación de número de ticket."""
        with app.app_context():
            ticket1 = db.next_ticket()
            ticket2 = db.next_ticket()
            
            assert ticket1 == ticket2  # Debería ser determinista
            assert isinstance(ticket1, int)
            assert ticket1 > 0

    def test_buscar_productos_pos(self):
        """Prueba búsqueda de productos para POS."""
        with app.app_context():
            # Crear producto de prueba
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, categoria, costo, iva)
                VALUES (?, ?, ?, ?, ?, ?)""",
                ('SEARCH001_POS', 'Producto Búsqueda Test', 50.0, 'Test', 30.0, '21%'),
                commit=True
            )
            db.q(
                """INSERT INTO stock (producto_id, stock_actual)
                VALUES (?, ?)""",
                (pid, 10),
                commit=True
            )
            
            # Buscar todos
            productos = db.buscar_productos_pos('')
            assert isinstance(productos, list)
            assert len(productos) > 0

            # Buscar por nombre
            productos = db.buscar_productos_pos('búsqueda')
            assert isinstance(productos, list)
            assert len(productos) > 0

            # Verificar estructura
            p = productos[0]
            required_fields = ['id', 'codigo_interno', 'descripcion', 'categoria', 'unidad', 'precio_venta', 'stock_actual']
            for field in required_fields:
                assert p[field] is not None

    def test_crear_venta(self):
        """Prueba creación de venta."""
        with app.app_context():
            # Crear producto de prueba
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, costo, iva)
                VALUES (?, ?, ?, ?, ?)""",
                ('TEST001_POS', 'Producto Test', 100.0, 60.0, '21%'),
                commit=True
            )

            # Crear stock
            db.q(
                """INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo)
                VALUES (?, ?, ?, ?)""",
                (pid, 10, 5, 20),
                commit=True
            )

            # Items de venta
            items = [{
                'producto_id': pid,
                'codigo_interno': 'TEST001_POS',
                'descripcion': 'Producto Test',
                'categoria': 'Test',
                'unidad': 'Unidad',
                'cantidad': 2,
                'precio_unitario': 100.0,
                'subtotal': 200.0
            }]

            # Crear venta
            venta_id = db.crear_venta(
                items=items,
                cliente_nombre='Test Client',
                medio_pago='Efectivo',
                descuento_adicional=0,
                vendedor='Test User',
                temporada='Test Season'
            )

            assert venta_id > 0

            # Verificar venta creada
            venta = db.get_venta_ticket(venta_id)
            assert venta is not None
            assert venta['cliente_nombre'] == 'Test Client'
            assert venta['total'] == 200.0
            assert len(venta['detalle']) == 1

            # Verificar stock decrementado
            stock_actual = db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (pid,), fetchone=True)
            assert stock_actual['stock_actual'] == 8  # 10 - 2

            # Verificar movimiento de stock
            movimientos = db.q("SELECT * FROM stock_movimientos WHERE producto_id=? ORDER BY id DESC LIMIT 1", (pid,), fetchone=True)
            assert movimientos['tipo'] == 'VENTA'
            assert movimientos['cantidad'] == -2
            assert movimientos['stock_nuevo'] == 8

    def test_decrementar_stock_venta(self):
        """Prueba decremento de stock tras venta."""
        with app.app_context():
            # Crear producto
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, costo, iva)
                VALUES (?, ?, ?, ?, ?)""",
                ('TEST002_POS', 'Producto Test 2', 50.0, 25.0, '21%'),
                commit=True
            )

            db.q(
                """INSERT INTO stock (producto_id, stock_actual)
                VALUES (?, ?)""",
                (pid, 5),
                commit=True
            )

            # Crear venta manual
            vid = db.q(
                """INSERT INTO ventas (numero_ticket, fecha, hora, cliente_nombre, medio_pago, subtotal, total, vendedor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (db.next_ticket(), '2024-01-01', '12:00:00', 'Test', 'Efectivo', 100.0, 100.0, 'Test'),
                commit=True
            )

            # Agregar detalle
            db.q(
                """INSERT INTO ventas_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (vid, pid, 'Producto Test 2', 2, 50.0, 100.0),
                commit=True
            )

            # Decrementar stock
            db.decrementar_stock_venta(vid)

            # Verificar
            stock = db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (pid,), fetchone=True)
            assert stock['stock_actual'] == 3  # 5 - 2
    def setup_method(self):
        """Setup para cada test."""
        self.client = app.test_client()
        with app.app_context():
            # Login como admin
            with self.client.session_transaction() as sess:
                sess['username'] = 'admin'
                sess['user'] = {'id': 1, 'username': 'admin', 'rol': 'admin', 'nombre_completo': 'Admin User'}

    def test_punto_venta_get(self):
        """Prueba acceso a página de POS."""
        response = self.client.get('/punto_venta')
        assert response.status_code == 200
        assert b'Punto de Venta' in response.data

    def test_api_buscar_productos(self):
        """Prueba API de búsqueda de productos."""
        # Crear producto de prueba
        with app.app_context():
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, costo, iva)
                VALUES (?, ?, ?, ?, ?)""",
                ('SEARCH001_API', 'Producto Búsqueda', 75.0, 45.0, '21%'),
                commit=True
            )
            db.q(
                """INSERT INTO stock (producto_id, stock_actual)
                VALUES (?, ?)""",
                (pid, 10),
                commit=True
            )

        response = self.client.get('/api/buscar_productos?q=búsqueda')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['ok'] == True
        assert isinstance(data['productos'], list)

    def test_carrito_agregar(self):
        """Prueba agregar producto al carrito."""
        # Crear producto
        with app.app_context():
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, costo, iva)
                VALUES (?, ?, ?, ?, ?)""",
                ('CART001_API', 'Producto Carrito', 25.0, 15.0, '21%'),
                commit=True
            )
            db.q(
                """INSERT INTO stock (producto_id, stock_actual)
                VALUES (?, ?)""",
                (pid, 5),
                commit=True
            )

        # Agregar al carrito
        response = self.client.post('/api/carrito/agregar',
            data=json.dumps({'producto_id': pid, 'cantidad': 2}),
            content_type='application/json'
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['ok'] == True
        assert len(data['carrito']) == 1
        assert data['carrito'][0]['cantidad'] == 2

    def test_carrito_quitar(self):
        """Prueba quitar producto del carrito."""
        # Agregar producto primero
        with app.app_context():
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, costo, iva)
                VALUES (?, ?, ?, ?, ?)""",
                ('REMOVE001_API', 'Producto Remover', 30.0, 18.0, '21%'),
                commit=True
            )
            db.q(
                """INSERT INTO stock (producto_id, stock_actual)
                VALUES (?, ?)""",
                (pid, 3),
                commit=True
            )

        # Agregar
        self.client.post('/api/carrito/agregar',
            data=json.dumps({'producto_id': pid, 'cantidad': 1}),
            content_type='application/json'
        )

        # Quitar
        response = self.client.post(f'/api/carrito/quitar/{pid}')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['ok'] == True
        assert len(data['carrito']) == 0

    def test_venta_finalizar(self):
        """Prueba finalizar venta completa."""
        # Crear producto
        with app.app_context():
            pid = db.q(
                """INSERT INTO productos (codigo_interno, descripcion, precio_venta, costo, iva)
                VALUES (?, ?, ?, ?, ?)""",
                ('FINAL001_API', 'Producto Final', 40.0, 24.0, '21%'),
                commit=True
            )
            db.q(
                """INSERT INTO stock (producto_id, stock_actual)
                VALUES (?, ?)""",
                (pid, 4),
                commit=True
            )

        # Agregar al carrito
        self.client.post('/api/carrito/agregar',
            data=json.dumps({'producto_id': pid, 'cantidad': 2}),
            content_type='application/json'
        )

        # Finalizar venta
        response = self.client.post('/venta/finalizar', data={
            'cliente_id': 0,
            'cliente_nombre': 'Test Client',
            'medio_pago': 'Efectivo',
            'descuento_adicional': '0'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Venta' in response.data and b'realizada' in response.data

    def test_ticket_view(self):
        """Prueba vista de ticket."""
        # Crear venta de prueba
        with app.app_context():
            vid = db.q(
                """INSERT INTO ventas (numero_ticket, fecha, hora, cliente_nombre, medio_pago, subtotal, total, vendedor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (999, '2024-01-01', '12:00:00', 'Test', 'Efectivo', 100.0, 100.0, 'Test'),
                commit=True
            )

        response = self.client.get(f'/ticket/{vid}')
        assert response.status_code == 200
        assert b'TICKET DE VENTA' in response.data
        assert b'#999' in response.data


if __name__ == '__main__':
    pytest.main([__file__])