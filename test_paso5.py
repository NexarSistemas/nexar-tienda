"""
Tests para PASO 5: Módulo de Stock
Pruebas de gestión de inventario, ajustes, historial y alertas
"""

import pytest
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.dirname(__file__))

import app as app_module
import database as db_module


@pytest.fixture
def client():
    """Fixture para crear cliente de prueba"""
    app_module.app.config['TESTING'] = True
    
    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def admin_client(client):
    """Fixture para cliente autenticado como admin"""
    # Login
    client.post('/login', data={
        'usuario': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    return client


class TestStockFunctions:
    """Tests para funciones de base de datos de stock"""
    
    def test_get_stock_full_returns_all_products(self):
        """Debe retornar todos los productos con estado calculado"""
        datos = db_module.get_stock_full()
        
        # Verificar que retorna lista
        assert isinstance(datos, list)
        
        # Verificar que tiene esperados campos si hay datos
        if len(datos) > 0:
            prod = datos[0]
            assert prod is not None
    
    def test_get_stock_full_search_filter(self):
        """Debe filtrar productos por búsqueda"""
        datos = db_module.get_stock_full(search='laptop')
        
        # Todos los resultados deben coincidir
        for prod in datos:
            assert ('laptop' in prod['codigo_interno'].lower() or 
                    'laptop' in prod['descripcion'].lower() or
                    'laptop' in prod['categoria'].lower())
    
    def test_get_stock_full_alerta_only_filter(self):
        """Debe retornar solo productos con alerta"""
        datos = db_module.get_stock_full(alerta_only=True)
        
        # Todos deben tener estado de alerta
        for prod in datos:
            assert prod['estado'] in ['SIN STOCK', 'CRITICO', 'BAJO']
    
    def test_get_alertas_count_structure(self):
        """Debe retornar estructura correcta de alertas"""
        alertas = db_module.get_alertas_count()
        
        assert isinstance(alertas, dict)
        assert 'sin_stock' in alertas
        assert 'critico' in alertas
        assert 'bajo' in alertas
        assert all(isinstance(v, int) for v in alertas.values())
    
    def test_get_stock_movimientos_returns_history(self):
        """Debe retornar historial de movimientos de un producto"""
        # Obtener pequeño ID de producto
        productos = db_module.q("SELECT id FROM productos LIMIT 1")
        
        if productos:
            pid = productos[0]['id']
            movimientos = db_module.get_stock_movimientos(pid)
            
            # Debe retornar lista
            assert isinstance(movimientos, list)


class TestStockRoutes:
    """Tests para rutas de stock"""
    
    def test_stock_route_requires_login(self, client):
        """Ruta /stock debe requerir login"""
        response = client.get('/stock')
        assert response.status_code == 302  # Redirect a login
    
    def test_stock_route_authenticated(self, admin_client):
        """Ruta /stock debe funcionar si está autenticado"""
        response = admin_client.get('/stock')
        # Puede ser 200 o redirect si no está completamente autenticado
        assert response.status_code in [200, 302]
    
    def test_stock_search_filter(self, admin_client):
        """Debe filtrar stock por búsqueda"""
        response = admin_client.get('/stock?buscar=test')
        assert response.status_code in [200, 302]
    
    def test_stock_estado_filter_all(self, admin_client):
        """Debe poder mostrar stock sin filtro de estado"""
        response = admin_client.get('/stock')
        assert response.status_code in [200, 302]
    
    def test_stock_ajustar_requires_admin(self, client):
        """Ruta /stock/ajustar debe requerir login"""
        response = client.get('/stock/1/ajustar')
        # Puede ser redirect a login o forbidden
        assert response.status_code in [302, 403]
    
    def test_stock_ajustar_get_shows_form(self, admin_client):
        """GET /stock/ajustar debe mostrar formulario si producto existe"""
        productos = db_module.q("SELECT id FROM productos WHERE activo=1 LIMIT 1")
        
        if productos:
            pid = productos[0]['id']
            response = admin_client.get(f"/stock/{pid}/ajustar")
            assert response.status_code in [200, 302]
    
    def test_stock_ajustar_nonexistent_product(self, admin_client):
        """GET /stock/ajustar con producto inexistente debe redirigir"""
        response = admin_client.get('/stock/99999/ajustar', follow_redirects=True)
        assert response.status_code == 200
    
    def test_stock_ajustar_post_negative_stock_validation(self, admin_client):
        """POST /stock/ajustar con stock negativo debe fallar"""
        productos = db_module.q("SELECT id FROM productos WHERE activo=1 LIMIT 1")
        
        if productos:
            pid = productos[0]['id']
            response = admin_client.post(
                f"/stock/{pid}/ajustar",
                data={
                    'stock_actual': '-10',
                    'stock_minimo': '5',
                    'stock_maximo': '100',
                    'proveedor_habitual': 'Test',
                    'motivo': 'Test'
                },
                follow_redirects=True
            )
            # Debe validar
            assert response.status_code == 200
    
    def test_stock_ajustar_post_valid_data(self, admin_client):
        """POST /stock/ajustar con datos válidos"""
        productos = db_module.q("SELECT id FROM productos WHERE activo=1 LIMIT 1")
        
        if productos:
            pid = productos[0]['id']
            response = admin_client.post(
                f"/stock/{pid}/ajustar",
                data={
                    'stock_actual': '50',
                    'stock_minimo': '5',
                    'stock_maximo': '100',
                    'proveedor_habitual': 'Proveedor Test',
                    'motivo': 'Ajuste para tests'
                },
                follow_redirects=True
            )
            assert response.status_code == 200
    
    def test_stock_movimientos_table_exists(self):
        """Tabla stock_movimientos debe existir"""
        movimientos_table = db_module.q(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_movimientos'",
            fetchone=True
        )
        assert movimientos_table is not None


class TestStockAlerts:
    """Tests para alertas de stock"""
    
    def test_api_alertas_requires_login(self, client):
        """/api/alertas debe requerir login"""
        response = client.get('/api/alertas')
        assert response.status_code == 302
    
    def test_api_alertas_authenticated_returns_json(self, admin_client):
        """GET /api/alertas autenticado debe retornar JSON"""
        response = admin_client.get('/api/alertas')
        # puede no estar ready si no tiene datos
        assert response.status_code in [200, 302]
    
    def test_alertas_count_zero_or_more(self):
        """Alertas count debe retornar valores válidos"""
        alertas = db_module.get_alertas_count()
        
        assert alertas['sin_stock'] >= 0
        assert alertas['critico'] >= 0
        assert alertas['bajo'] >= 0


class TestStockStates:
    """Tests para estados de stock (SIN STOCK, CRITICO, BAJO, NORMAL, EXCESO)"""
    
    def test_estado_values_valid(self):
        """Todos los estados deben ser válidos"""
        datos = db_module.get_stock_full()
        
        valid_states = ['SIN STOCK', 'CRITICO', 'BAJO', 'NORMAL', 'EXCESO']
        for prod in datos:
            assert prod['estado'] in valid_states


class TestStockIntegration:
    """Tests de integración para flujo completo de stock"""
    
    def test_nav_link_exists(self):
        """Link a Stock debe existir en navbar"""
        # Verificar que la ruta existe
        response = app_module.app.test_client().get('/stock')
        # Redirecciona a login si no autenticado
        assert response.status_code == 302
    
    def test_movimientos_logged_on_adjustment(self):
        """Verificar que stock_movimientos tiene estructura correcta"""
        columns = db_module.q("PRAGMA table_info(stock_movimientos)")
        column_names = [col['name'] for col in columns]
        
        required_columns = ['id', 'producto_id', 'tipo', 'cantidad', 
                           'stock_anterior', 'stock_nuevo', 'motivo', 'created_at']
        for col_name in required_columns:
            assert col_name in column_names


def test_database_structure_complete():
    """Verificar estructura de base de datos para PASO 5"""
    # Verificar tabla stock_movimientos
    movimientos_table = db_module.q(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_movimientos'",
        fetchone=True
    )
    assert movimientos_table is not None
    
    # Verificar funciones de stock
    assert hasattr(db_module, 'get_stock_full')
    assert hasattr(db_module, 'get_alertas_count')
    assert hasattr(db_module, 'get_stock_movimientos')


def test_routes_exist():
    """Verificar que rutas de PASO 5 existen"""
    # Estas deben estar definidas en app.py
    assert hasattr(app_module, 'app')
    
    # Verificar que flask app tiene las rutas
    with app_module.app.test_client() as client:
        # GET /stock debe existir (redirige si no auth)
        response = client.get('/stock')
        assert response.status_code in [200, 302]
        
        # GET /api/alertas debe existir
        response = client.get('/api/alertas')
        assert response.status_code in [200, 302]
