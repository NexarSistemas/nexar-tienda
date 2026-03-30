"""
Nexar Tienda — app.py
Rutas y lógica principal de Flask.

Paso 3: Login, logout, dashboard básico + sistema de backups automáticos
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from datetime import date, datetime, timedelta
from functools import wraps
import json
import os
import sys
import signal
import shutil
import glob
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

# ─── VERSIÓN ─────────────────────────────────────────────────────────────────
def _read_version():
    try:
        v = open(os.path.join(os.path.dirname(__file__), 'VERSION')).read().strip()
        return v if v else "0.1.0"
    except Exception:
        return "0.1.0"

APP_VERSION = _read_version()

# ─── FLASK SETUP ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'nexar-tienda-dev-key-cambiar-en-produccion'
app.jinja_env.add_extension('jinja2.ext.loopcontrols')


@app.route('/favicon.ico')
def favicon():
    return send_file(
        os.path.join(app.root_path, 'static/icons/nexar_tienda.ico'),
        mimetype='image/vnd.microsoft.icon'
    )


# ─── SISTEMA DE BACKUPS AUTOMÁTICOS ──────────────────────────────────────────

_backup_timer = None


def get_backup_dir():
    """Devuelve el directorio de backups."""
    cfg = db.get_config()
    custom = cfg.get('backup_dir', '').strip()
    if custom and os.path.isabs(custom):
        return custom
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'respaldo')


def hacer_backup(manual=False):
    """Copia tienda.db → respaldo/tienda_YYYY-MM-DD_HH-MM.db"""
    try:
        db_path = db.DB_PATH
        if not os.path.exists(db_path):
            return False, 'No se encontró la base de datos.'

        backup_dir = get_backup_dir()
        os.makedirs(backup_dir, exist_ok=True)

        ts = datetime.now().strftime('%Y-%m-%d_%H-%M')
        dest = os.path.join(backup_dir, f'tienda_{ts}.db')
        shutil.copy2(db_path, dest)

        # Mantener solo los últimos N backups
        cfg = db.get_config()
        keep = int(cfg.get('backup_keep', '10'))
        all_bkp = sorted(glob.glob(os.path.join(backup_dir, 'tienda_*.db')))
        for old in all_bkp[:-keep]:
            try:
                os.remove(old)
            except Exception:
                pass

        db.set_config({'backup_ultimo': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        return True, dest
    except Exception as e:
        return False, str(e)


def _schedule_backup():
    """Programa el siguiente backup automático."""
    global _backup_timer
    try:
        cfg = db.get_config()
        interval_h = float(cfg.get('backup_intervalo_h', '24'))
        if interval_h <= 0:
            return

        hacer_backup()
        interval_s = interval_h * 3600
        _backup_timer = threading.Timer(interval_s, _schedule_backup)
        _backup_timer.daemon = True
        _backup_timer.start()
    except Exception:
        pass


def iniciar_backup_scheduler():
    """Inicia el planificador de backups."""
    global _backup_timer
    if _backup_timer:
        _backup_timer.cancel()
    _backup_timer = threading.Timer(5, _schedule_backup)  # first run after 5s
    _backup_timer.daemon = True
    _backup_timer.start()


# ─── DECORADORES DE AUTENTICACIÓN ────────────────────────────────────────────

def login_required(f):
    """Requiere que el usuario esté autenticado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            flash('⚠️ Debés iniciar sesión para acceder.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Requiere que el usuario sea administrador."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session['user'].get('rol') != 'admin':
            flash('⛔ Acceso restringido: se requieren permisos de Administrador.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── INICIALIZACIÓN ──────────────────────────────────────────────────────────

_scheduler_started = False


@app.before_request
def before():
    """Se ejecuta antes de cada request."""
    global _scheduler_started
    db.init_db()
    if not _scheduler_started:
        _scheduler_started = True
        iniciar_backup_scheduler()

    # Rutas públicas (sin login requerido)
    public_routes = {'/login', '/static', '/favicon.ico'}
    if request.path in public_routes or request.path.startswith('/static'):
        return

    # Forzar login en el resto
    if 'user' not in session and request.path != '/login':
        flash('⚠️ Sesión expirada. Volvé a iniciar sesión.', 'warning')
        return redirect(url_for('login', next=request.path))


# ─── RUTAS ───────────────────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    """Redirecciona a dashboard si está autenticado, a login si no."""
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login del usuario."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('❌ Usuario y contraseña requeridos.', 'danger')
            return render_template('login.html', app_version=APP_VERSION)

        usuario = db.get_usuario_by_username(username)
        if not usuario or not db.verify_password(password, usuario['password_hash']):
            flash('❌ Usuario o contraseña incorrectos.', 'danger')
            return render_template('login.html', app_version=APP_VERSION)

        if not usuario['activo']:
            flash('⛔ Usuario desactivado.', 'danger')
            return render_template('login.html', app_version=APP_VERSION)

        # Login exitoso
        session['user'] = {
            'id': usuario['id'],
            'username': usuario['username'],
            'nombre_completo': usuario['nombre_completo'],
            'rol': usuario['rol']
        }

        flash(f"✅ ¡Hola, {usuario['nombre_completo']}!", 'success')

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(url_for('dashboard'))

    return render_template('login.html', app_version=APP_VERSION)


@app.route('/logout')
def logout():
    """Cierra la sesión."""
    usuario = session.get('user', {})
    session.clear()
    flash(f"✅ Hasta luego, {usuario.get('nombre_completo', 'Usuario')}!", 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal."""
    cfg = db.get_config()
    stats = db.get_dashboard_stats()
    usuario = session['user']
    license_info = db.get_license_info()

    return render_template(
        'dashboard.html',
        app_version=APP_VERSION,
        usuario=usuario,
        nombre_negocio=cfg.get('nombre_negocio', 'Mi Tienda'),
        stats=stats,
        license_info=license_info
    )


@app.route('/api/backups', methods=['GET'])
@admin_required
def api_backups():
    """API: devuelve lista de backups."""
    try:
        backup_dir = get_backup_dir()
        backups = sorted(glob.glob(os.path.join(backup_dir, 'tienda_*.db')), reverse=True)
        return jsonify({
            'ok': True,
            'backups': [
                {
                    'nombre': os.path.basename(b),
                    'fecha': os.path.getctime(b),
                    'tamanio': os.path.getsize(b),
                    'ruta': b
                }
                for b in backups
            ]
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/backup-ahora', methods=['POST'])
@admin_required
def api_backup_ahora():
    """API: crea un backup inmediato."""
    ok, msg = hacer_backup(manual=True)
    if ok:
        flash('✅ Respaldo creado exitosamente.', 'success')
        return jsonify({'ok': True, 'msg': msg})
    else:
        flash(f'❌ Error en respaldo: {msg}', 'danger')
        return jsonify({'ok': False, 'error': msg})


# ─── PRODUCTOS (PASO 4) ──────────────────────────────────────────────────────

@app.route('/productos')
@login_required
def productos():
    """Lista de productos con búsqueda."""
    buscar = request.args.get('q', '').strip()
    categoria = request.args.get('cat', '').strip()

    productos_list = db.get_productos(search=buscar)

    # Filtrar por categoría si se especifica
    if categoria:
        productos_list = [p for p in productos_list if p['categoria'] == categoria]

    categorias = db.get_categorias()

    return render_template(
        'productos.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        productos=productos_list,
        categorias=categorias,
        buscar=buscar,
        categoria_filtro=categoria
    )


@app.route('/productos/nuevo', methods=['GET', 'POST'])
@login_required
def producto_nuevo():
    """Crear nuevo producto."""
    if request.method == 'POST':
        try:
            data = request.form.to_dict()

            # Validación
            if not data.get('descripcion', '').strip():
                flash('❌ La descripción del producto es requerida.', 'danger')
                return redirect(url_for('producto_nuevo'))

            if not data.get('precio_venta'):
                flash('❌ El precio de venta es requerido.', 'danger')
                return redirect(url_for('producto_nuevo'))

            try:
                float(data.get('precio_venta'))
                float(data.get('costo', 0))
            except ValueError:
                flash('❌ Los precios deben ser números válidos.', 'danger')
                return redirect(url_for('producto_nuevo'))

            # Verificar límite de productos (según tier de licencia)
            limite_check = db.check_license_limits('productos')
            if not limite_check['ok']:
                flash(f"❌ {limite_check['message']}", 'danger')
                return redirect(url_for('productos'))

            # Crear producto
            pid = db.add_producto(data)
            flash(f"✅ Producto creado exitosamente (código: {db.get_producto(pid)['codigo_interno']})", 'success')
            return redirect(url_for('productos'))

        except Exception as e:
            flash(f'❌ Error al crear producto: {str(e)}', 'danger')
            return redirect(url_for('producto_nuevo'))

    categorias = db.get_categorias()
    return render_template(
        'producto_form.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        categorias=categorias,
        producto=None,
        accion='Crear'
    )


@app.route('/productos/<int:pid>/editar', methods=['GET', 'POST'])
@login_required
def producto_editar(pid):
    """Editar producto existente."""
    producto = db.get_producto(pid)
    if not producto:
        flash('❌ Producto no encontrado.', 'danger')
        return redirect(url_for('productos'))

    if request.method == 'POST':
        try:
            data = request.form.to_dict()

            # Validación
            if not data.get('descripcion', '').strip():
                flash('❌ La descripción del producto es requerida.', 'danger')
                return redirect(url_for('producto_editar', pid=pid))

            try:
                float(data.get('precio_venta', 0))
                float(data.get('costo', 0))
            except ValueError:
                flash('❌ Los precios deben ser números válidos.', 'danger')
                return redirect(url_for('producto_editar', pid=pid))

            # Actualizar producto
            db.update_producto(pid, data)
            flash(f"✅ Producto actualizado exitosamente.", 'success')
            return redirect(url_for('productos'))

        except Exception as e:
            flash(f'❌ Error al actualizar producto: {str(e)}', 'danger')
            return redirect(url_for('producto_editar', pid=pid))

    categorias = db.get_categorias()
    return render_template(
        'producto_form.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        categorias=categorias,
        producto=producto,
        accion='Editar'
    )


@app.route('/productos/<int:pid>/eliminar', methods=['POST'])
@login_required
def producto_eliminar(pid):
    """Eliminar (desactivar) producto."""
    producto = db.get_producto(pid)
    if not producto:
        flash('❌ Producto no encontrado.', 'danger')
        return redirect(url_for('productos'))

    try:
        db.delete_producto(pid)
        flash(f"✅ Producto '{producto['descripcion']}' desactivado.", 'success')
    except Exception as e:
        flash(f'❌ Error al desactivar producto: {str(e)}', 'danger')

    return redirect(url_for('productos'))


@app.route('/api/productos', methods=['GET'])
@login_required
def api_productos():
    """API: devuelve productos en JSON (para búsqueda AJAX)."""
    q = request.args.get('q', '').strip()
    productos_list = db.get_productos(search=q)
    return jsonify({
        'ok': True,
        'productos': [
            {
                'id': p['id'],
                'codigo': p['codigo_interno'],
                'descripcion': p['descripcion'],
                'categoria': p['categoria'],
                'precio': p['precio_venta'],
                'stock': db.q(
                    "SELECT stock_actual FROM stock WHERE producto_id=?",
                    (p['id'],), fetchone=True
                )['stock_actual'] if db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (p['id'],), fetchone=True) else 0
            }
            for p in productos_list
        ]
    })


# ─── LICENCIAS ──────────────────────────────────────────────────────────────

# ─── CLIENTES (PASO 7) ──────────────────────────────────────────────────────

@app.route('/clientes')
@login_required
def clientes():
    """Lista de clientes con búsqueda."""
    buscar = request.args.get('q', '').strip()

    clientes_list = db.get_clientes(search=buscar)

    return render_template(
        'clientes.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        clientes=clientes_list,
        buscar=buscar
    )


@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
def cliente_nuevo():
    """Crear nuevo cliente."""
    if request.method == 'POST':
        try:
            data = request.form.to_dict()

            # Validación
            if not data.get('nombre', '').strip():
                flash('❌ El nombre del cliente es requerido.', 'danger')
                return redirect(url_for('cliente_nuevo'))

            # Verificar límite de clientes (según tier de licencia)
            limite_check = db.check_license_limits('clientes')
            if not limite_check['ok']:
                flash(f"❌ {limite_check['message']}", 'danger')
                return redirect(url_for('clientes'))

            # Crear cliente
            db.add_cliente(data)
            flash("✅ Cliente creado exitosamente.", 'success')
            return redirect(url_for('clientes'))

        except Exception as e:
            flash(f'❌ Error al crear cliente: {str(e)}', 'danger')
            return redirect(url_for('cliente_nuevo'))

    return render_template(
        'cliente_form.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        cliente=None,
        accion='Crear'
    )


@app.route('/clientes/<int:cid>/editar', methods=['GET', 'POST'])
@login_required
def cliente_editar(cid):
    """Editar cliente existente."""
    cliente = db.get_cliente(cid)
    if not cliente:
        flash('❌ Cliente no encontrado.', 'danger')
        return redirect(url_for('clientes'))

    if request.method == 'POST':
        try:
            data = request.form.to_dict()

            # Validación
            if not data.get('nombre', '').strip():
                flash('❌ El nombre del cliente es requerido.', 'danger')
                return redirect(url_for('cliente_editar', cid=cid))

            # Actualizar cliente
            db.update_cliente(cid, data)
            flash("✅ Cliente actualizado exitosamente.", 'success')
            return redirect(url_for('clientes'))

        except Exception as e:
            flash(f'❌ Error al actualizar cliente: {str(e)}', 'danger')
            return redirect(url_for('cliente_editar', cid=cid))

    return render_template(
        'cliente_form.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        cliente=cliente,
        accion='Editar'
    )


@app.route('/clientes/<int:cid>')
@login_required
def cliente_detalle(cid):
    """Detalle de cliente con cuenta corriente."""
    cliente = db.get_cliente(cid)
    if not cliente:
        flash('❌ Cliente no encontrado.', 'danger')
        return redirect(url_for('clientes'))

    # Obtener datos adicionales
    saldo = db.get_saldo_cliente(cid)
    movimientos = db.get_movimientos_cliente(cid)
    estadisticas = db.get_estadisticas_cliente(cid)
    historial_ventas = db.get_historial_ventas_cliente(cid, limit=10)

    return render_template(
        'cliente_detalle.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        cliente=cliente,
        saldo=saldo,
        movimientos=movimientos,
        estadisticas=estadisticas,
        historial_ventas=historial_ventas
    )


@app.route('/clientes/<int:cid>/movimiento', methods=['POST'])
@login_required
def cliente_agregar_movimiento(cid):
    """Agregar movimiento a cuenta corriente."""
    cliente = db.get_cliente(cid)
    if not cliente:
        flash('❌ Cliente no encontrado.', 'danger')
        return redirect(url_for('clientes'))

    try:
        tipo = request.form.get('tipo')
        numero_comprobante = request.form.get('numero_comprobante', '').strip()
        debe = float(request.form.get('debe', 0))
        haber = float(request.form.get('haber', 0))
        vencimiento = request.form.get('vencimiento', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        if not tipo:
            flash('❌ El tipo de movimiento es requerido.', 'danger')
            return redirect(url_for('cliente_detalle', cid=cid))

        db.agregar_movimiento_cliente(cid, tipo, numero_comprobante, debe, haber, vencimiento, observaciones)
        flash("✅ Movimiento agregado exitosamente.", 'success')

    except Exception as e:
        flash(f'❌ Error al agregar movimiento: {str(e)}', 'danger')

    return redirect(url_for('cliente_detalle', cid=cid))


@app.route('/clientes/<int:cid>/eliminar', methods=['POST'])
@login_required
def cliente_eliminar(cid):
    """Eliminar (desactivar) cliente."""
    cliente = db.get_cliente(cid)
    if not cliente:
        flash('❌ Cliente no encontrado.', 'danger')
        return redirect(url_for('clientes'))

    try:
        # Soft delete - marcar como inactivo
        db.update_cliente(cid, {**cliente, 'activo': 0})
        flash(f"✅ Cliente '{cliente['nombre']}' desactivado.", 'success')
    except Exception as e:
        flash(f'❌ Error al desactivar cliente: {str(e)}', 'danger')

    return redirect(url_for('clientes'))

@app.route('/stock', methods=['GET'])
@login_required
def stock():
    """Gestión de stock."""
    search = request.args.get('buscar', '').strip()
    estado_filter = request.args.get('estado', '').strip()
    
    datos = db.get_stock_full(search=search)
    
    # Aplicar filtro de estado
    if estado_filter:
        datos = [d for d in datos if d['estado'] == estado_filter]
    
    # Estadísticas
    alertas = db.get_alertas_count()
    total_stock_value = sum(d['valor_stock'] for d in datos)
    
    return render_template(
        'stock.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        productos=datos,
        alertas=alertas,
        total_stock_value=total_stock_value,
        buscar=search,
        estado_filter=estado_filter
    )


@app.route('/stock/<int:pid>/ajustar', methods=['GET', 'POST'])
@login_required
@admin_required
def stock_ajustar(pid):
    """Ajustar stock de un producto."""
    producto = db.get_producto(pid)
    if not producto:
        flash('❌ Producto no encontrado.', 'danger')
        return redirect(url_for('stock'))
    
    # Obtener datos actuales de stock
    stock_actual = db.q(
        "SELECT * FROM stock WHERE producto_id=?",
        (pid,), fetchone=True
    )
    
    if request.method == 'POST':
        try:
            stock_nuevo = float(request.form.get('stock_actual', 0))
            stock_minimo = float(request.form.get('stock_minimo', stock_actual['stock_minimo']))
            stock_maximo = float(request.form.get('stock_maximo', stock_actual['stock_maximo']))
            proveedor = request.form.get('proveedor_habitual', stock_actual['proveedor_habitual'] or '')
            
            # Validación
            if stock_nuevo < 0:
                flash('❌ El stock no puede ser negativo.', 'danger')
                return redirect(url_for('stock_ajustar', pid=pid))
            
            if stock_minimo >= stock_maximo:
                flash('❌ Stock mínimo debe ser menor que máximo.', 'danger')
                return redirect(url_for('stock_ajustar', pid=pid))
            
            # Registrar movimiento antes de actualizar
            diferencia = stock_nuevo - stock_actual['stock_actual']
            db.q(
                """INSERT INTO stock_movimientos 
                (producto_id, tipo, cantidad, stock_anterior, stock_nuevo, motivo)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (pid, 'AJUSTE', diferencia, stock_actual['stock_actual'], stock_nuevo, 
                 request.form.get('motivo', 'Ajuste manual')),
                fetchall=False, commit=True
            )
            
            # Actualizar stock
            db.update_stock_item(
                pid,
                stock_actual=stock_nuevo,
                stock_minimo=stock_minimo,
                stock_maximo=stock_maximo,
                proveedor=proveedor
            )
            
            flash(f"✅ Stock actualizado (antes: {stock_actual['stock_actual']}, ahora: {stock_nuevo})", 'success')
            return redirect(url_for('stock'))
        
        except ValueError:
            flash('❌ Valores inválidos. Verifique los números.', 'danger')
            return redirect(url_for('stock_ajustar', pid=pid))
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'danger')
            return redirect(url_for('stock_ajustar', pid=pid))
    
    # Obtener historial de movimientos
    movimientos = db.get_stock_movimientos(pid)
    
    return render_template(
        'stock_ajustar.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        producto=producto,
        stock=stock_actual,
        movimientos=movimientos
    )


@app.route('/api/alertas', methods=['GET'])
@login_required
def api_alertas():
    """API: devuelve alertas de stock."""
    alertas = db.get_alertas_count()
    datos = db.get_stock_full(alerta_only=True)
    
    return jsonify({
        'ok': True,
        'alertas': alertas,
        'productos_alerta': [
            {
                'id': d['id'],
                'descripcion': d['descripcion'],
                'estado': d['estado'],
                'stock_actual': d['stock_actual'],
                'stock_minimo': d['stock_minimo']
            }
            for d in datos
        ]
    })


# ─── PUNTO DE VENTA ──────────────────────────────────────────────────────────

@app.route('/punto_venta')
@login_required
def punto_venta():
    """Página principal del punto de venta."""
    # Inicializar carrito si no existe
    if 'carrito' not in session:
        session['carrito'] = []
    
    clientes = db.get_clientes()
    temporada = db.get_temporada_actual()
    
    return render_template('punto_venta.html', 
                         app_version=APP_VERSION,
                         clientes=clientes,
                         temporada=temporada)


@app.route('/api/buscar_productos', methods=['GET'])
@login_required
def api_buscar_productos():
    """API: busca productos para POS."""
    search = request.args.get('q', '').strip()
    productos = db.buscar_productos_pos(search)
    
    return jsonify({
        'ok': True,
        'productos': [
            {
                'id': p['id'],
                'codigo_interno': p['codigo_interno'],
                'descripcion': p['descripcion'],
                'categoria': p['categoria'],
                'unidad': p['unidad'],
                'precio_venta': p['precio_venta'],
                'stock_actual': p['stock_actual']
            }
            for p in productos
        ]
    })


@app.route('/api/carrito/agregar', methods=['POST'])
@login_required
def api_carrito_agregar():
    """API: agrega producto al carrito."""
    data = request.get_json()
    pid = data.get('producto_id')
    cantidad = float(data.get('cantidad', 1))
    
    if not pid or cantidad <= 0:
        return jsonify({'ok': False, 'error': 'Datos inválidos'})
    
    # Obtener producto
    producto = db.get_producto(pid)
    if not producto:
        return jsonify({'ok': False, 'error': 'Producto no encontrado'})
    
    # Verificar stock
    stock = db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if not stock or stock['stock_actual'] < cantidad:
        return jsonify({'ok': False, 'error': 'Stock insuficiente'})
    
    # Inicializar carrito
    if 'carrito' not in session:
        session['carrito'] = []
    
    carrito = session['carrito']
    
    # Buscar si ya existe en carrito
    encontrado = False
    for item in carrito:
        if item['producto_id'] == pid:
            item['cantidad'] += cantidad
            item['subtotal'] = item['cantidad'] * item['precio_unitario']
            encontrado = True
            break
    
    if not encontrado:
        carrito.append({
            'producto_id': pid,
            'codigo_interno': producto['codigo_interno'],
            'descripcion': producto['descripcion'],
            'categoria': producto['categoria'],
            'unidad': producto['unidad'],
            'cantidad': cantidad,
            'precio_unitario': producto['precio_venta'],
            'subtotal': cantidad * producto['precio_venta']
        })
    
    session['carrito'] = carrito
    session.modified = True
    
    return jsonify({'ok': True, 'carrito': carrito})


@app.route('/api/carrito/quitar/<int:pid>', methods=['POST'])
@login_required
def api_carrito_quitar(pid):
    """API: quita producto del carrito."""
    if 'carrito' not in session:
        return jsonify({'ok': False, 'error': 'Carrito vacío'})
    
    carrito = session['carrito']
    carrito = [item for item in carrito if item['producto_id'] != pid]
    session['carrito'] = carrito
    session.modified = True
    
    return jsonify({'ok': True, 'carrito': carrito})


@app.route('/api/carrito/vaciar', methods=['POST'])
@login_required
def api_carrito_vaciar():
    """API: vacía el carrito."""
    session['carrito'] = []
    session.modified = True
    return jsonify({'ok': True})


@app.route('/venta/finalizar', methods=['POST'])
@login_required
def venta_finalizar():
    """Finaliza la venta."""
    if 'carrito' not in session or not session['carrito']:
        flash('❌ Carrito vacío', 'error')
        return redirect(url_for('punto_venta'))
    
    cliente_id = int(request.form.get('cliente_id', 0))
    cliente_nombre = request.form.get('cliente_nombre', 'Mostrador')
    medio_pago = request.form.get('medio_pago', 'Efectivo')
    descuento_adicional = float(request.form.get('descuento_adicional', 0))
    
    # Obtener temporada actual
    temporada = db.get_temporada_actual()
    temporada_nombre = temporada['nombre'] if temporada else ''
    
    # Usuario actual
    usuario = db.get_usuario_by_username(session['username'])
    vendedor = usuario['nombre_completo'] or usuario['username']
    
    try:
        # Crear venta
        venta_id = db.crear_venta(
            items=session['carrito'],
            cliente_nombre=cliente_nombre,
            medio_pago=medio_pago,
            descuento_adicional=descuento_adicional,
            vendedor=vendedor,
            cliente_id=cliente_id,
            temporada=temporada_nombre
        )
        
        # Decrementar stock
        db.decrementar_stock_venta(venta_id)
        
        # Limpiar carrito
        session['carrito'] = []
        session.modified = True
        
        flash(f'✅ Venta #{venta_id} realizada exitosamente', 'success')
        return redirect(url_for('ticket', vid=venta_id))
        
    except Exception as e:
        flash(f'❌ Error al procesar venta: {str(e)}', 'error')
        return redirect(url_for('punto_venta'))


@app.route('/ticket/<int:vid>')
@login_required
def ticket(vid):
    """Muestra ticket de venta."""
    venta = db.get_venta_ticket(vid)
    if not venta:
        flash('❌ Ticket no encontrado', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('ticket.html', venta=venta, app_version=APP_VERSION)




@app.errorhandler(404)
def not_found(e):
    """Página no encontrada."""
    return render_template('404.html', app_version=APP_VERSION), 404


@app.errorhandler(500)
def server_error(e):
    """Error interno del servidor."""
    return render_template('500.html', error=str(e), app_version=APP_VERSION), 500


@app.template_filter('fmt_ars')
def jinja_fmt_ars(valor):
    """Filtro Jinja para formatear ARS."""
    return db.fmt_ars(valor)


@app.template_filter('date')
def jinja_date(fecha_str):
    """Filtro Jinja para formatear fechas."""
    if not fecha_str:
        return '—'
    try:
        return datetime.strptime(fecha_str, '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        return fecha_str


# ─── INÍCIO ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"╔═══════════════════════════════════════════════╗")
    print(f"║        Nexar Tienda v{APP_VERSION}                    ║")
    print(f"║   🌐 http://localhost:5000                   ║")
    print(f"║   👤 usuario: admin / contraseña: admin123   ║")
    print(f"║   👤 usuario: vendedor / contraseña: vendedor123 ║")
    print(f"╚═══════════════════════════════════════════════╝")

    app.run(debug=True, host='0.0.0.0', port=5000)
