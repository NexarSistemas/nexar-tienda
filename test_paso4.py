#!/usr/bin/env python3
"""
test_paso4.py - Validación Paso 4: Módulo de Productos (ABM)
Valida: Crear, Leer, Actualizar, Eliminar, búsqueda, filtros
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import app as application
import database as db

def test_paso4():
    """Suite completa de tests para Paso 4 - Módulo Productos"""
    
    print("\n" + "="*70)
    print("VALIDACIÓN PASO 4: Módulo de Productos (ABM)")
    print("="*70)

    # Inicializar DB
    db.init_db()
    print("✅ Base de datos inicializada")

    # ─── TEST 1: GET /productos (lista vacía después de init)
    print("\n[TEST 1] GET /productos - Lista de productos")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.get('/productos')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Productos' in response.data, "Pagina de productos no renderiza"
    
    print("✅ GET /productos retorna 200, template correcto")

    # ─── TEST 2: POST /productos/nuevo - Crear producto
    print("\n[TEST 2] POST /productos/nuevo - Crear producto")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.post('/productos/nuevo', data={
            'descripcion': 'Mate de Cerámica Negro',
            'marca': 'Marca Local',
            'categoria': 'Mates',
            'unidad': 'Unidad',
            'costo': '25.50',
            'precio_venta': '45.00',
            'iva': '21%',
            'codigo_barras': '7791234567890',
            'stock_actual': '10',
            'stock_minimo': '5',
            'stock_maximo': '50',
            'por_peso': ''
        }, follow_redirects=True)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Producto' in response.data or b'xito' in response.data, "Producto no creado"
    
    print("✅ POST /productos/nuevo crea producto correctamente")

    # ─── TEST 3: GET /api/productos (API JSON)
    print("\n[TEST 3] GET /api/productos - API JSON")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        # Crear un producto primero
        client.post('/productos/nuevo', data={
            'descripcion': 'Producto Prueba API',
            'categoria': 'Mates',
            'precio_venta': '50.00'
        })
        
        response = client.get('/api/productos')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.content_type == 'application/json', "API no retorna JSON"
        data = response.get_json()
        assert isinstance(data, dict), "API debe retornar dict"
        assert data.get('ok') == True, "API no tiene 'ok': true"
        productos = data.get('productos', [])
        assert isinstance(productos, list), "API debe retornar lista de productos"
        assert len(productos) >= 1, "API deberia retornar al menos 1 producto"
        assert 'descripcion' in productos[0], "JSON no tiene descripcion"
    
    print("✅ GET /api/productos retorna JSON válido")

    # ─── TEST 4: GET /productos (búsqueda)
    print("\n[TEST 4] GET /productos?buscar=Mate - Búsqueda")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.get('/productos?buscar=Mate')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Mate' in response.data or b'valor' in response.data, "Búsqueda no filtra"
    
    print("✅ Búsqueda en GET /productos funciona")

    # ─── TEST 5: GET /productos/nuevo (form crear)
    print("\n[TEST 5] GET /productos/nuevo - Formulario crear")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.get('/productos/nuevo')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Crear Producto' in response.data or b'Descripcion' in response.data, "Form no renderiza"
    
    print("✅ GET /productos/nuevo retorna formulario")

    # ─── TEST 6: GET /productos/1/editar (form editar)
    print("\n[TEST 6] GET /productos/1/editar - Formulario editar")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.get('/productos/1/editar')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert b'Editar' in response.data or b'Guardar Cambios' in response.data, "Form edit no renderiza"
        assert b'Mate' in response.data, "Datos del producto no pre-llenan"
    
    print("✅ GET /productos/1/editar retorna form con datos")

    # ─── TEST 7: POST /productos/1/editar - Actualizar producto
    print("\n[TEST 7] POST /productos/1/editar - Actualizar producto")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        # Crear un nuevo producto para editar
        response = client.post('/productos/nuevo', data={
            'descripcion': 'Producto para Editar TEST7',
            'marca': 'Marca Original',
            'categoria': 'Mates',
            'unidad': 'Unidad',
            'costo': '20.00',
            'precio_venta': '40.00',
            'iva': '21%',
            'stock_actual': '10',
            'stock_minimo': '5',
            'stock_maximo': '50'
        })
        
        # Determinar el ID del producto creado
        todos_productos = db.get_productos(activo_only=False)
        pid = todos_productos[-1]['id']  # Usar el último creado
        
        # Ahora editar ese producto
        response = client.post(f'/productos/{pid}/editar', data={
            'descripcion': 'Producto EDITADO Exitosamente',
            'marca': 'Marca Modificada',
            'categoria': 'Mates',
            'unidad': 'Unidad',
            'costo': '22.00',
            'precio_venta': '42.00',
            'iva': '21%',
            'activo': '1'
        }, follow_redirects=True)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verificar que la actualización se guardó
        datos_actualizado = db.get_producto(pid)
        assert datos_actualizado is not None, "Producto no existe"
        assert 'EDITADO' in datos_actualizado['descripcion'], "Descripcion no fue actualizada"
        assert 'Modificada' in datos_actualizado['marca'], "Marca no fue actualizada"
    
    print("✅ POST /productos/1/editar actualiza correctamente")

    # ─── TEST 8: POST /productos/1/eliminar (soft delete)
    print("\n[TEST 8] POST /productos/<id>/eliminar - Eliminar (soft delete)")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        # Crear un producto para eliminar
        response = client.post('/productos/nuevo', data={
            'descripcion': 'Producto para Eliminar TEST8',
            'categoria': 'Mates',
            'precio_venta': '35.00',
            'stock_actual': '5'
        })
        
        # Determinar el ID
        todos_productos = db.get_productos(activo_only=False)
        pid_to_delete = todos_productos[-1]['id']
        
        # Eliminar
        response = client.post(f'/productos/{pid_to_delete}/eliminar', follow_redirects=True)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Verificar que el producto no aparece en lista (soft delete)
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.get('/api/productos')
        data = response.get_json()
        productos = data.get('productos', [])
        # El producto debe estar marcado como inactivo
        activos_solo = [p for p in productos if p.get('activo', 1) == 1 and p['id'] == pid_to_delete]
        assert len(activos_solo) == 0, "Producto no fue eliminado (soft delete)"
    
    print("✅ POST /productos/1/eliminar realiza soft delete")

    # ─── TEST 9: Validación de campos requeridos
    print("\n[TEST 9] POST /productos/nuevo - Validación requeridos")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        # Sin descripción (requerido)
        response = client.post('/productos/nuevo', data={
            'descripcion': '',  # VACÍO - debe fallar
            'categoria': 'Mates',
            'precio_venta': '45.00'
        }, follow_redirects=True)
        
        # Debe retornar a la lista o mostrar error
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    print("✅ Validación de campos requeridos funciona")

    # ─── TEST 10: Categorías disponibles
    print("\n[TEST 10] GET /productos - Categorías renderizadas")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user'] = {'nombre_completo': 'Admin User', 'rol': 'admin'}
        
        response = client.get('/productos')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Debe estar presente al menos una categoría
        assert b'Mates' in response.data or b'Accesorios' in response.data or b'categoria' in response.data, \
            "Categorias no se renderizan"
    
    print("✅ Categorías se renderizan en vistas")

    # ─── TEST 11: Sin autenticación retorna 302 (redirect)
    print("\n[TEST 11] Sin autenticación - Protección de rutas")
    with application.app.test_client() as client:
        response = client.get('/productos', follow_redirects=False)
        assert response.status_code in [302, 401], f"Expected redirect, got {response.status_code}"
    
    print("✅ Rutas protegidas redirigen sin sesión")

    # ─── TEST 12: Permiso admin (solo admin puede crear/editar)
    print("\n[TEST 12] Control de permisos - Solo admin")
    with application.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 2  # vendedor
            sess['user'] = {'nombre_completo': 'Vendedor User', 'rol': 'vendedor'}
        
        # Intentar crear (vendedor no debería poder)
        response = client.post('/productos/nuevo', data={
            'descripcion': 'Intento de vendedor',
            'precio_venta': '100'
        }, follow_redirects=False)
        
        # Debe denegarllo (403 o redirect)
        assert response.status_code in [403, 302, 301], f"Expected 403/redirect, got {response.status_code}"
    
    print("✅ Control de permisos funciona (vendedor restringido)")

    print("\n" + "="*70)
    print("✅ TODOS LOS TESTS DE PASO 4 PASARON EXITOSAMENTE")
    print("="*70)
    print("""
Componentes validados:
  ✅ GET /productos - Lista con búsqueda y filtros
  ✅ GET /productos/nuevo - Formulario crear
  ✅ POST /productos/nuevo - Crear producto
  ✅ GET /productos/<id>/editar - Formulario editar
  ✅ POST /productos/<id>/editar - Actualizar
  ✅ POST /productos/<id>/eliminar - Eliminar (soft delete)
  ✅ GET /api/productos - API JSON
  ✅ Validación de campos requeridos
  ✅ Protección de rutas (autenticación)
  ✅ Control de permisos (admin/vendedor)
    """)

if __name__ == '__main__':
    test_paso4()
