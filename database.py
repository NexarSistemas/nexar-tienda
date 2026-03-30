"""
Nexar Tienda — database.py
Conexión, tablas y consultas SQLite.

Basado en Nexar Almacén, adaptado para tienda de regalos:
  - Sin sistema de licencias ni OpenFoodFacts
  - Categorías propias de tienda (bijouterie, mates, regalos, etc.)
  - Módulo de temporadas (Día de la Madre, Navidad, etc.)
  - Sistema de backups automáticos desde el inicio
"""

import sqlite3
import os
import hashlib
from datetime import datetime, date, timedelta

# ─── TIER LIMITS (SISTEMA DE LICENCIAS) ──────────────────────────────────────
# Define limites de productos, clientes y proveedores por tipo de licencia
TIER_LIMITS = {
    "DEMO": {
        "productos": None,      # ilimitado por 30 dias
        "clientes": None,
        "proveedores": None,
        "dias_prueba": 30,
        "descripcion": "Periodo de prueba (30 dias)"
    },
    "BASICA": {
        "productos": 200,       # max 200 productos
        "clientes": 100,        # max 100 clientes
        "proveedores": 50,      # max 50 proveedores
        "dias_prueba": None,
        "descripcion": "Licencia Basica"
    },
    "PRO": {
        "productos": None,      # ilimitado
        "clientes": None,
        "proveedores": None,
        "dias_prueba": None,
        "descripcion": "Licencia Profesional"
    },
}

# ─── RUTA DE LA BASE DE DATOS ────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tienda.db')


# ─── CONEXIÓN ─────────────────────────────────────────────────────────────────

def get_conn():
    """Devuelve una conexión SQLite con Row factory y claves foráneas activas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def q(sql, params=(), fetchall=True, fetchone=False, commit=False):
    """
    Función única para ejecutar consultas SQL.

    Ejemplos:
        q("SELECT * FROM productos")
        q("SELECT * FROM productos WHERE id=?", (1,), fetchone=True)
        q("INSERT INTO ...", (...,), commit=True)  → devuelve lastrowid
    """
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        if commit:
            conn.commit()
            return c.lastrowid
        if fetchone:
            return c.fetchone()
        if fetchall:
            return c.fetchall()
    finally:
        conn.close()


def qm(statements):
    """Ejecuta múltiples statements en una transacción."""
    conn = get_conn()
    try:
        c = conn.cursor()
        for sql, params in statements:
            c.execute(sql, params)
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


# ─── INICIALIZACIÓN ──────────────────────────────────────────────────────────

_db_initialized = False


def init_db():
    """Inicializa la BD con todas las tablas necesarias para Nexar Tienda."""
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True

    conn = get_conn()
    c = conn.cursor()

    # Crear todas las tablas
    c.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT DEFAULT 'usuario',
            nombre_completo TEXT DEFAULT '',
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activa INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_interno TEXT UNIQUE NOT NULL,
            codigo_barras TEXT DEFAULT '',
            descripcion TEXT NOT NULL,
            marca TEXT DEFAULT '',
            categoria TEXT DEFAULT '',
            unidad TEXT DEFAULT 'Unidad',
            por_peso INTEGER DEFAULT 0,
            costo REAL DEFAULT 0,
            precio_venta REAL DEFAULT 0,
            iva TEXT DEFAULT '21%',
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER UNIQUE REFERENCES productos(id) ON DELETE CASCADE,
            stock_actual REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 5,
            stock_maximo REAL DEFAULT 50,
            ultimo_ingreso TEXT DEFAULT '',
            proveedor_habitual TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS stock_movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE,
            tipo TEXT DEFAULT 'AJUSTE',
            cantidad REAL DEFAULT 0,
            stock_anterior REAL DEFAULT 0,
            stock_nuevo REAL DEFAULT 0,
            motivo TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            nombre TEXT NOT NULL,
            dni_cuit TEXT DEFAULT '',
            telefono TEXT DEFAULT '',
            email TEXT DEFAULT '',
            limite_credito REAL DEFAULT 0,
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            nombre TEXT NOT NULL,
            cuit TEXT DEFAULT '',
            telefono TEXT DEFAULT '',
            email TEXT DEFAULT '',
            dias_credito INTEGER DEFAULT 30,
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_ticket INTEGER,
            fecha TEXT,
            hora TEXT,
            cliente_id INTEGER DEFAULT 0,
            cliente_nombre TEXT DEFAULT 'Mostrador',
            medio_pago TEXT DEFAULT 'Efectivo',
            subtotal REAL DEFAULT 0,
            descuento_adicional REAL DEFAULT 0,
            total REAL DEFAULT 0,
            vendedor TEXT DEFAULT '',
            temporada TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ventas_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
            producto_id INTEGER DEFAULT 0,
            codigo_interno TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            categoria TEXT DEFAULT '',
            unidad TEXT DEFAULT '',
            cantidad REAL DEFAULT 1,
            precio_unitario REAL DEFAULT 0,
            descuento REAL DEFAULT 0,
            subtotal REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            numero_remito TEXT DEFAULT '',
            proveedor_id INTEGER DEFAULT 0,
            proveedor_nombre TEXT DEFAULT '',
            producto_id INTEGER DEFAULT 0,
            codigo_interno TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            cantidad REAL DEFAULT 1,
            costo_unitario REAL DEFAULT 0,
            total REAL DEFAULT 0,
            observaciones TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS caja_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT UNIQUE,
            saldo_apertura REAL DEFAULT 0,
            ventas_efectivo REAL DEFAULT 0,
            ventas_debito REAL DEFAULT 0,
            ventas_credito REAL DEFAULT 0,
            ventas_qr REAL DEFAULT 0,
            ventas_cta_cte REAL DEFAULT 0,
            ventas_transferencia REAL DEFAULT 0,
            total_ventas REAL DEFAULT 0,
            gastos_dia REAL DEFAULT 0,
            saldo_cierre_esperado REAL DEFAULT 0,
            saldo_cierre_real REAL DEFAULT 0,
            diferencia REAL DEFAULT 0,
            cerrada INTEGER DEFAULT 0,
            responsable_apertura TEXT DEFAULT '',
            responsable_cierre TEXT DEFAULT '',
            hora_apertura TEXT DEFAULT '',
            hora_cierre TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo TEXT DEFAULT 'Gasto',
            categoria TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            monto REAL DEFAULT 0,
            iva_incluido INTEGER DEFAULT 1,
            medio_pago TEXT DEFAULT 'Efectivo',
            proveedor TEXT DEFAULT '',
            necesario TEXT DEFAULT 'SI (necesario)',
            comprobante TEXT DEFAULT '',
            observaciones TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS cc_clientes_mov (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER REFERENCES clientes(id),
            fecha TEXT,
            tipo TEXT DEFAULT 'Venta',
            numero_comprobante TEXT DEFAULT '',
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            vencimiento TEXT DEFAULT '',
            observaciones TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS cc_proveedores_mov (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER REFERENCES proveedores(id),
            fecha TEXT,
            tipo TEXT DEFAULT 'Compra',
            numero_comprobante TEXT DEFAULT '',
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            vencimiento TEXT DEFAULT '',
            observaciones TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS facturas_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER REFERENCES proveedores(id),
            numero_factura TEXT DEFAULT '',
            fecha TEXT,
            fecha_vencimiento TEXT,
            importe REAL DEFAULT 0,
            pagado REAL DEFAULT 0,
            observaciones TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS temporadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT DEFAULT '',
            fecha_inicio TEXT,
            fecha_fin TEXT,
            activa INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT DEFAULT 'Actualización',
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT ''
        );
    """)

    # ─── Configuración por defecto ────────────────────────────────────────────
    defaults = [
        ('nombre_negocio', 'Mi Tienda'),
        ('direccion', ''),
        ('telefono', ''),
        ('cuit', ''),
        ('responsable', ''),
        ('margen_minimo', '0.20'),
        ('margen_objetivo', '0.35'),
        ('dias_alerta_proveedor', '30'),
        ('dias_alerta_cliente', '15'),
        ('siguiente_ticket', '1001'),
        ('siguiente_codigo', '1'),
        ('backup_intervalo_h', '24'),
        ('backup_keep', '10'),
        ('backup_dir', ''),
        ('backup_ultimo', ''),
        # ─── SISTEMA DE LICENCIAS ─────────────────────────────────────────────
        ('license_type', 'MONO'),           # MONO / MULTI
        ('license_tier', 'DEMO'),           # DEMO / BASICA / PRO
        ('license_key', ''),                # Clave de licencia (vacio en DEMO)
        ('license_activated_at', ''),       # Fecha de activacion
        ('license_expires_at', ''),         # Fecha de expiracion (vacio = no vence)
        ('license_last_check', ''),         # Ultimo chequeo exitoso
        ('license_max_machines', '1'),      # Maquinas permitidas
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO config VALUES (?,?)", (k, v))

    # ─── Generar machine_id ──────────────────────────────────────────────────
    mid = c.execute("SELECT valor FROM config WHERE clave='machine_id'").fetchone()
    if not mid:
        import uuid
        machine_id = str(uuid.uuid4()).replace('-', '').upper()[:16]
        c.execute("INSERT INTO config VALUES ('machine_id',?)", (machine_id,))

    # ─── Usuarios por defecto ─────────────────────────────────────────────────
    def _hash(pw):
        return hashlib.sha256(pw.encode()).hexdigest()

    default_users = [
        ('admin', _hash('admin123'), 'admin', 'Administrador'),
        ('vendedor', _hash('vendedor123'), 'usuario', 'Vendedor'),
    ]
    for uname, phash, rol, nombre in default_users:
        c.execute(
            "INSERT OR IGNORE INTO usuarios (username,password_hash,rol,nombre_completo) VALUES (?,?,?,?)",
            (uname, phash, rol, nombre)
        )

    # ─── Categorías iniciales de tienda ──────────────────────────────────────
    cats = [
        'Bijouterie',
        'Mates y Termos',
        'Regalos Diversos',
        'Adornos',
        'Accesorios',
        'Productos de Temporada',
        'Navidad',
        'Día de la Madre',
        'Día del Padre',
        'Otros',
    ]
    for cat in cats:
        c.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (cat,))

    # ─── Temporadas iniciales ────────────────────────────────────────────────
    seasons = [
        ('Navidad', 'Adornos y regalos navideños', '2026-11-01', '2026-12-31'),
        ('Día de la Madre', 'Especiales para mamá', '2026-10-01', '2026-10-31'),
        ('Día del Padre', 'Especiales para papá', '2026-06-01', '2026-06-30'),
        ('Año Nuevo', 'Regalos y accesorios año nuevo', '2026-12-20', '2027-01-31'),
    ]
    for nombre, desc, inicio, fin in seasons:
        c.execute(
            "INSERT OR IGNORE INTO temporadas (nombre,descripcion,fecha_inicio,fecha_fin) VALUES (?,?,?,?)",
            (nombre, desc, inicio, fin)
        )

    _seed_changelog(c)

    # ─── Reparar stock ───────────────────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo)
        SELECT id, 0, 5, 50 FROM productos
        WHERE activo=1
        AND id NOT IN (SELECT producto_id FROM stock)
    """)

    conn.commit()
    conn.close()


def _seed_changelog(c):
    """Inserta el historial de versiones inicial."""
    existing = c.execute("SELECT COUNT(*) FROM changelog").fetchone()[0]
    if existing > 0:
        return

    entries = [
        ('0.1.0', '2026-03-29', 'Nueva función',
         'Estructura base de Nexar Tienda',
         'Proyecto inicial basado en Nexar Almacén adaptado para tienda de regalos.'),
        ('0.1.1', '2026-03-29', 'Nueva función',
         'Módulos completos y sistema de backups',
         'Se agregaron todas las tablas: Productos, Stock, Ventas, Clientes, Proveedores, Caja, Gastos, Temporadas. Sistema de backups automáticos.'),
    ]
    for ver, fecha, tipo, titulo, desc in entries:
        c.execute(
            "INSERT INTO changelog (version,fecha,tipo,titulo,descripcion) VALUES (?,?,?,?,?)",
            (ver, fecha, tipo, titulo, desc)
        )


# ─── CONFIG ──────────────────────────────────────────────────────────────────

def get_config():
    """Devuelve dict con toda la configuración."""
    rows = q("SELECT clave, valor FROM config")
    return {r['clave']: r['valor'] for r in rows}


def set_config(data: dict):
    """Actualiza multiples valores de configuracion."""
    conn = get_conn()
    c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO config VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()


# ─── LICENCIAS ──────────────────────────────────────────────────────────────

def get_license_info() -> dict:
    """Devuelve informacion completa de la licencia actual."""
    cfg = get_config()
    return {
        'type': cfg.get('license_type', 'MONO'),
        'tier': cfg.get('license_tier', 'DEMO'),
        'key': cfg.get('license_key', ''),
        'activated_at': cfg.get('license_activated_at', ''),
        'expires_at': cfg.get('license_expires_at', ''),
        'last_check': cfg.get('license_last_check', ''),
        'max_machines': int(cfg.get('license_max_machines', '1')),
        'limits': TIER_LIMITS.get(cfg.get('license_tier', 'DEMO'), {})
    }


def activate_license(tier: str, key: str = '', expires_at: str = ''):
    """Activa una nueva licencia."""
    if tier not in TIER_LIMITS:
        tier = 'DEMO'
    set_config({
        'license_tier': tier,
        'license_key': key,
        'license_activated_at': datetime.now().isoformat(),
        'license_expires_at': expires_at,
        'license_last_check': datetime.now().isoformat(),
    })


def check_license_limits(limit_key: str, current_count: int = None) -> dict:
    """Verifica si se excedio un limite de licencia.
    
    Retorna: {'ok': bool, 'current': int, 'limit': int, 'message': str}
    """
    lic = get_license_info()
    tier = lic['tier']
    limits = lic['limits']
    
    limit = limits.get(limit_key)
    
    # Si no hay limite (None), no hay restriccion
    if limit is None:
        return {'ok': True, 'current': current_count or 0, 'limit': None, 'message': 'Ilimitado'}
    
    # Si hay un limite, verificar
    if current_count is None:
        # Contar desde BD segun el tipo de limite
        if limit_key == 'productos':
            current_count = q("SELECT COUNT(*) FROM productos WHERE activo=1", fetchall=False)
        elif limit_key == 'clientes':
            current_count = q("SELECT COUNT(*) FROM clientes WHERE activo=1", fetchall=False)
        elif limit_key == 'proveedores':
            current_count = q("SELECT COUNT(*) FROM proveedores WHERE activo=1", fetchall=False)
        else:
            current_count = 0
    
    if current_count > limit:
        return {
            'ok': False,
            'current': current_count,
            'limit': limit,
            'message': f"Limite de {limit_key} ({limit}) excedido. Actual: {current_count}"
        }
    
    return {
        'ok': True,
        'current': current_count,
        'limit': limit,
        'message': f"{limit_key.capitalize()}: {current_count}/{limit}"
    }


# ─── CÓDIGOS AUTOMÁTICOS ─────────────────────────────────────────────────────

def next_codigo():
    """Genera next código de producto único."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT MAX(CAST(SUBSTR(codigo_interno,5) AS INTEGER)) as mx FROM productos WHERE codigo_interno LIKE 'PRD-%'"
    ).fetchone()
    max_n = (row['mx'] or 0) + 1
    cfg_n = int(c.execute("SELECT valor FROM config WHERE clave='siguiente_codigo'").fetchone()['valor'] or 1)
    n = max(max_n, cfg_n)
    new_code = f"PRD-{n:04d}"
    c.execute("INSERT OR REPLACE INTO config VALUES ('siguiente_codigo', ?)", (str(n + 1),))
    conn.commit()
    conn.close()
    return new_code


def next_ticket():
    """Devuelve el próximo número de ticket."""
    cfg = get_config()
    n = int(cfg.get('siguiente_ticket', 1001))
    set_config({'siguiente_ticket': str(n + 1)})
    return n


# ─── CATEGORÍAS ──────────────────────────────────────────────────────────────

def get_categorias():
    """Devuelve lista de categorías activas."""
    return [r['nombre'] for r in q("SELECT nombre FROM categorias WHERE activa=1 ORDER BY nombre")]


def add_categoria(nombre):
    """Agrega una nueva categoría."""
    q("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (nombre,), fetchall=False, commit=True)


# ─── USUARIOS ────────────────────────────────────────────────────────────────

def get_usuario_by_username(username):
    """Obtiene usuario por username."""
    return q("SELECT * FROM usuarios WHERE username=?", (username,), fetchone=True)


def verify_password(password, password_hash):
    """Verifica contraseña contra hash."""
    return hashlib.sha256(password.encode()).hexdigest() == password_hash


def get_usuarios():
    """Devuelve todos los usuarios."""
    return q("SELECT id,username,rol,nombre_completo,activo FROM usuarios ORDER BY nombre_completo")


def add_usuario(username, password, rol, nombre_completo):
    """Agrega un nuevo usuario."""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    q(
        """INSERT INTO usuarios (username,password_hash,rol,nombre_completo)
        VALUES (?,?,?,?)""",
        (username, password_hash, rol, nombre_completo),
        fetchall=False, commit=True
    )


def update_usuario(uid, data):
    """Actualiza usuario."""
    updates = ["rol=?", "nombre_completo=?", "activo=?"]
    params = [data.get('rol', 'usuario'), data.get('nombre_completo', ''), int(data.get('activo', 1)), uid]
    q(f"UPDATE usuarios SET {','.join(updates)} WHERE id=?", params, fetchall=False, commit=True)


# ─── PRODUCTOS ───────────────────────────────────────────────────────────────

def get_productos(activo_only=True, search=''):
    """Devuelve productos filtrables."""
    sql = "SELECT * FROM productos"
    conds = []
    params = []
    if activo_only:
        conds.append("activo=1")
    if search:
        conds.append("(codigo_interno LIKE ? OR codigo_barras LIKE ? OR descripcion LIKE ? OR categoria LIKE ?)")
        params += [f'%{search}%'] * 4
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY descripcion"
    return q(sql, params)


def get_producto(pid):
    """Devuelve un producto por ID."""
    return q("SELECT * FROM productos WHERE id=?", (pid,), fetchone=True)


def get_producto_by_codigo(codigo):
    """Busca por código interno o barras."""
    r = q("SELECT * FROM productos WHERE codigo_interno=? AND activo=1", (codigo,), fetchone=True)
    if not r:
        r = q("SELECT * FROM productos WHERE codigo_barras=? AND activo=1", (codigo,), fetchone=True)
    return r


def add_producto(data):
    """Agrega un nuevo producto."""
    codigo = next_codigo()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO productos
        (codigo_interno,codigo_barras,descripcion,marca,categoria,unidad,por_peso,costo,precio_venta,iva,activo)
        VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
        (codigo, data.get('codigo_barras', ''), data['descripcion'], data.get('marca', ''),
         data.get('categoria', ''), data.get('unidad', 'Unidad'), int(data.get('por_peso', 0)),
         float(data.get('costo', 0)), float(data.get('precio_venta', 0)), data.get('iva', '21%'))
    )
    pid = c.lastrowid
    c.execute(
        "INSERT INTO stock (producto_id,stock_actual,stock_minimo,stock_maximo) VALUES (?,?,?,?)",
        (pid, float(data.get('stock_actual', 0)), float(data.get('stock_minimo', 5)), float(data.get('stock_maximo', 50)))
    )
    conn.commit()
    conn.close()
    return pid


def update_producto(pid, data):
    """Actualiza un producto."""
    q(
        """UPDATE productos SET codigo_barras=?,descripcion=?,marca=?,categoria=?,unidad=?,por_peso=?,
        costo=?,precio_venta=?,iva=?,activo=? WHERE id=?""",
        (data.get('codigo_barras', ''), data['descripcion'], data.get('marca', ''),
         data.get('categoria', ''), data.get('unidad', 'Unidad'), int(data.get('por_peso', 0)),
         float(data.get('costo', 0)), float(data.get('precio_venta', 0)), data.get('iva', '21%'),
         int(data.get('activo', 1)), pid),
        fetchall=False, commit=True
    )


def delete_producto(pid):
    """Desactiva un producto."""
    q("UPDATE productos SET activo=0 WHERE id=?", (pid,), fetchall=False, commit=True)


# ─── STOCK ───────────────────────────────────────────────────────────────────

def get_stock_full(search='', alerta_only=False):
    """Devuelve stock completo con estados."""
    sql = """SELECT p.id, p.codigo_interno, p.descripcion, p.categoria, p.unidad,
                    p.costo, p.precio_venta,
                    s.stock_actual, s.stock_minimo, s.stock_maximo,
                    s.ultimo_ingreso, s.proveedor_habitual,
                    CASE
                        WHEN s.stock_actual <= 0 THEN 'SIN STOCK'
                        WHEN s.stock_actual <= s.stock_minimo THEN 'CRITICO'
                        WHEN s.stock_actual <= s.stock_minimo * 1.5 THEN 'BAJO'
                        WHEN s.stock_actual >= s.stock_maximo THEN 'EXCESO'
                        ELSE 'NORMAL'
                    END as estado,
                    s.stock_actual * p.costo as valor_stock
             FROM productos p
             JOIN stock s ON s.producto_id = p.id
             WHERE p.activo=1"""
    params = []
    if search:
        sql += " AND (p.descripcion LIKE ? OR p.categoria LIKE ? OR p.codigo_interno LIKE ?)"
        params += [f'%{search}%'] * 3
    if alerta_only:
        sql += " AND s.stock_actual <= s.stock_minimo * 1.5"
    sql += " ORDER BY p.descripcion"
    return q(sql, params)


def update_stock_item(pid, stock_actual=None, stock_minimo=None, stock_maximo=None, proveedor=None):
    """Actualiza valores de stock."""
    updates = []
    params = []
    if stock_actual is not None:
        updates.append("stock_actual=?")
        params.append(stock_actual)
    if stock_minimo is not None:
        updates.append("stock_minimo=?")
        params.append(stock_minimo)
    if stock_maximo is not None:
        updates.append("stock_maximo=?")
        params.append(stock_maximo)
    if proveedor is not None:
        updates.append("proveedor_habitual=?")
        params.append(proveedor)
    if updates:
        params.append(pid)
        q(f"UPDATE stock SET {','.join(updates)} WHERE producto_id=?", params, fetchall=False, commit=True)


def get_alertas_count():
    """Cuenta alertas de stock."""
    r = q(
        """SELECT
        COALESCE(SUM(CASE WHEN s.stock_actual<=0 THEN 1 ELSE 0 END),0) as sin_stock,
        COALESCE(SUM(CASE WHEN s.stock_actual>0 AND s.stock_actual<=s.stock_minimo THEN 1 ELSE 0 END),0) as critico,
        COALESCE(SUM(CASE WHEN s.stock_actual>s.stock_minimo AND s.stock_actual<=s.stock_minimo*1.5 THEN 1 ELSE 0 END),0) as bajo
        FROM stock s JOIN productos p ON p.id=s.producto_id WHERE p.activo=1""",
        fetchone=True
    )
    if r:
        return {'sin_stock': r['sin_stock'] or 0, 'critico': r['critico'] or 0, 'bajo': r['bajo'] or 0}
    return {'sin_stock': 0, 'critico': 0, 'bajo': 0}


def get_stock_movimientos(pid):
    """Obtiene historial de movimientos de un producto."""
    return q(
        """SELECT * FROM stock_movimientos WHERE producto_id=? 
           ORDER BY created_at DESC LIMIT 50""",
        (pid,)
    )


def get_stock_movimientos_all(start_date='', end_date=''):
    """Obtiene todos los movimientos con filtro opcional por fecha."""
    sql = "SELECT m.*, p.descripcion, p.codigo_interno FROM stock_movimientos m JOIN productos p ON p.id=m.producto_id"
    params = []
    
    if start_date:
        sql += " WHERE m.created_at >= ?"
        params.append(start_date)
    
    if end_date:
        if start_date:
            sql += " AND m.created_at <= ?"
        else:
            sql += " WHERE m.created_at <= ?"
        params.append(end_date)
    
    sql += " ORDER BY m.created_at DESC"
    return q(sql, params)


# ─── CLIENTES ────────────────────────────────────────────────────────────────

def get_clientes(activo_only=True, search=''):
    """Devuelve clientes filtrables."""
    sql = "SELECT * FROM clientes"
    conds = []
    params = []
    if activo_only:
        conds.append("activo=1")
    if search:
        conds.append("(nombre LIKE ? OR codigo LIKE ? OR dni_cuit LIKE ?)")
        params += [f'%{search}%'] * 3
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY nombre"
    return q(sql, params)


def get_cliente(cid):
    """Devuelve un cliente por ID."""
    return q("SELECT * FROM clientes WHERE id=?", (cid,), fetchone=True)


def add_cliente(data):
    """Agrega un nuevo cliente."""
    conn = get_conn()
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*)+1 as n FROM clientes").fetchone()['n']
    codigo = f"CLI-{n:03d}"
    c.execute(
        """INSERT INTO clientes (codigo,nombre,dni_cuit,telefono,email,limite_credito)
        VALUES (?,?,?,?,?,?)""",
        (codigo, data['nombre'], data.get('dni_cuit', ''), data.get('telefono', ''),
         data.get('email', ''), float(data.get('limite_credito', 0)))
    )
    cliente_id = c.lastrowid
    conn.commit()
    conn.close()
    return cliente_id


def update_cliente(cid, data):
    """Actualiza un cliente."""
    q(
        """UPDATE clientes SET nombre=?,dni_cuit=?,telefono=?,email=?,limite_credito=?,activo=? WHERE id=?""",
        (data['nombre'], data.get('dni_cuit', ''), data.get('telefono', ''), data.get('email', ''),
         float(data.get('limite_credito', 0)), int(data.get('activo', 1)), cid),
        fetchall=False, commit=True
    )


def get_saldo_cliente(cid):
    """Calcula saldo de cuenta corriente del cliente."""
    r = q(
        "SELECT COALESCE(SUM(debe),0)-COALESCE(SUM(haber),0) as saldo FROM cc_clientes_mov WHERE cliente_id=?",
        (cid,), fetchone=True
    )
    return r['saldo'] if r else 0


def get_movimientos_cliente(cid, limit=50):
    """Obtiene movimientos de cuenta corriente de un cliente."""
    return q(
        """SELECT * FROM cc_clientes_mov 
        WHERE cliente_id=? 
        ORDER BY fecha DESC, id DESC 
        LIMIT ?""",
        (cid, limit)
    )


def agregar_movimiento_cliente(cid, tipo, numero_comprobante, debe=0, haber=0, vencimiento='', observaciones=''):
    """Agrega un movimiento a la cuenta corriente del cliente."""
    fecha = datetime.now().strftime('%Y-%m-%d')
    q(
        """INSERT INTO cc_clientes_mov 
        (cliente_id, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones),
        commit=True
    )


def get_historial_ventas_cliente(cid, limit=20):
    """Obtiene historial de ventas de un cliente."""
    return q(
        """SELECT v.*, vd.producto_id, vd.descripcion, vd.cantidad, vd.precio_unitario, vd.subtotal
        FROM ventas v
        LEFT JOIN ventas_detalle vd ON v.id = vd.venta_id
        WHERE v.cliente_id = ?
        ORDER BY v.fecha DESC, v.id DESC
        LIMIT ?""",
        (cid, limit * 10)  # Multiplicar por 10 para incluir detalles
    )


def get_estadisticas_cliente(cid):
    """Obtiene estadísticas de un cliente."""
    # Total de compras
    total_compras = q(
        "SELECT COUNT(*) as total, COALESCE(SUM(total),0) as monto FROM ventas WHERE cliente_id=?",
        (cid,), fetchone=True
    )
    
    # Última compra
    ultima_compra = q(
        "SELECT fecha, total FROM ventas WHERE cliente_id=? ORDER BY fecha DESC LIMIT 1",
        (cid,), fetchone=True
    )
    
    return {
        'total_compras': total_compras['total'],
        'monto_total': total_compras['monto'],
        'ultima_compra': ultima_compra
    }


# ─── PROVEEDORES ─────────────────────────────────────────────────────────────

def get_proveedores(activo_only=True, search=''):
    """Devuelve proveedores filtrables."""
    sql = "SELECT * FROM proveedores"
    conds = []
    params = []
    if activo_only:
        conds.append("activo=1")
    if search:
        conds.append("(nombre LIKE ? OR codigo LIKE ?)")
        params += [f'%{search}%'] * 2
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY nombre"
    return q(sql, params)


def get_proveedor(pid):
    """Devuelve un proveedor por ID."""
    return q("SELECT * FROM proveedores WHERE id=?", (pid,), fetchone=True)


def add_proveedor(data):
    """Agrega un nuevo proveedor."""
    conn = get_conn()
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*)+1 as n FROM proveedores").fetchone()['n']
    codigo = f"PROV-{n:03d}"
    c.execute(
        """INSERT INTO proveedores (codigo,nombre,cuit,telefono,email,dias_credito)
        VALUES (?,?,?,?,?,?)""",
        (codigo, data['nombre'], data.get('cuit', ''), data.get('telefono', ''),
         data.get('email', ''), int(data.get('dias_credito', 30)))
    )
    conn.commit()
    conn.close()


def update_proveedor(pid, data):
    """Actualiza un proveedor."""
    q(
        """UPDATE proveedores SET nombre=?,cuit=?,telefono=?,email=?,dias_credito=?,activo=? WHERE id=?""",
        (data['nombre'], data.get('cuit', ''), data.get('telefono', ''), data.get('email', ''),
         int(data.get('dias_credito', 30)), int(data.get('activo', 1)), pid),
        fetchall=False, commit=True
    )


def get_saldo_proveedor(pid):
    """Calcula saldo de cuenta corriente del proveedor."""
    r = q(
        "SELECT COALESCE(SUM(debe),0)-COALESCE(SUM(haber),0) as saldo FROM cc_proveedores_mov WHERE proveedor_id=?",
        (pid,), fetchone=True
    )
    return r['saldo'] if r else 0


def get_movimientos_proveedor(pid, limit=50):
    """Obtiene movimientos de cuenta corriente del proveedor."""
    return q(
        """SELECT * FROM cc_proveedores_mov 
        WHERE proveedor_id=? 
        ORDER BY fecha DESC, id DESC 
        LIMIT ?""",
        (pid, limit)
    )


def agregar_movimiento_proveedor(pid, tipo, numero_comprobante, debe=0, haber=0, vencimiento='', observaciones=''):
    """Agrega un movimiento a la cuenta corriente del proveedor."""
    fecha = datetime.now().strftime('%Y-%m-%d')
    q(
        """INSERT INTO cc_proveedores_mov 
        (proveedor_id, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones),
        commit=True
    )


def get_historial_compras_proveedor(pid, limit=20):
    """Obtiene historial de compras del proveedor."""
    return q(
        """SELECT c.* FROM compras c 
        WHERE c.proveedor_id = ? 
        ORDER BY c.fecha DESC, c.id DESC 
        LIMIT ?""",
        (pid, limit)
    )


def get_estadisticas_proveedor(pid):
    """Obtiene estadísticas de un proveedor."""
    total_compras = q(
        "SELECT COUNT(*) as total, COALESCE(SUM(total),0) as monto FROM compras WHERE proveedor_id=?",
        (pid,), fetchone=True
    )

    ultima_compra = q(
        "SELECT fecha, total FROM compras WHERE proveedor_id=? ORDER BY fecha DESC LIMIT 1",
        (pid,), fetchone=True
    )

    return {
        'total_compras': total_compras['total'],
        'monto_total': total_compras['monto'],
        'ultima_compra': ultima_compra
    }


# ─── VENTAS ──────────────────────────────────────────────────────────────────

def get_ventas(search='', fecha_desde='', fecha_hasta='', limit=200):
    """Devuelve ventas filtrables."""
    sql = """SELECT v.*, COUNT(d.id) as items
             FROM ventas v LEFT JOIN ventas_detalle d ON d.venta_id=v.id
             WHERE 1=1"""
    params = []
    if search:
        sql += " AND (v.cliente_nombre LIKE ? OR v.medio_pago LIKE ? OR CAST(v.numero_ticket AS TEXT) LIKE ?)"
        params += [f'%{search}%'] * 3
    if fecha_desde:
        sql += " AND v.fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND v.fecha <= ?"
        params.append(fecha_hasta)
    sql += " GROUP BY v.id ORDER BY v.fecha DESC, v.id DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def get_venta_detalle(vid):
    """Devuelve items de una venta."""
    return q("SELECT * FROM ventas_detalle WHERE venta_id=? ORDER BY id", (vid,))


def crear_venta(items, cliente_nombre, medio_pago, descuento_adicional, vendedor, cliente_id=0, temporada=''):
    """Crea una venta con detalle."""
    conn = get_conn()
    c = conn.cursor()

    numero_ticket = next_ticket()
    ahora = datetime.now()
    fecha = ahora.strftime('%Y-%m-%d')
    hora = ahora.strftime('%H:%M:%S')

    subtotal = sum(item.get('subtotal', 0) for item in items)
    total = subtotal - descuento_adicional

    c.execute(
        """INSERT INTO ventas
        (numero_ticket,fecha,hora,cliente_id,cliente_nombre,medio_pago,subtotal,descuento_adicional,total,vendedor,temporada)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (numero_ticket, fecha, hora, cliente_id, cliente_nombre, medio_pago, subtotal, descuento_adicional, total, vendedor, temporada)
    )
    venta_id = c.lastrowid

    for item in items:
        c.execute(
            """INSERT INTO ventas_detalle
            (venta_id,producto_id,codigo_interno,descripcion,categoria,unidad,cantidad,precio_unitario,descuento,subtotal)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (venta_id, item.get('producto_id', 0), item.get('codigo_interno', ''), item.get('descripcion', ''),
             item.get('categoria', ''), item.get('unidad', ''), item.get('cantidad', 1),
             item.get('precio_unitario', 0), item.get('descuento', 0), item.get('subtotal', 0))
        )

    conn.commit()
    conn.close()
    return venta_id


# ─── COMPRAS ─────────────────────────────────────────────────────────────────

def get_compras(search='', fecha_desde='', fecha_hasta='', limit=200):
    """Devuelve compras filtrables."""
    sql = "SELECT * FROM compras WHERE 1=1"
    params = []
    if search:
        sql += " AND (descripcion LIKE ? OR numero_remito LIKE ? OR proveedor_nombre LIKE ?)"
        params += [f'%{search}%'] * 3
    if fecha_desde:
        sql += " AND fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND fecha <= ?"
        params.append(fecha_hasta)
    sql += " ORDER BY fecha DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def add_compra(data):
    """Agrega una compra."""
    q(
        """INSERT INTO compras
        (fecha,numero_remito,proveedor_id,proveedor_nombre,producto_id,codigo_interno,descripcion,cantidad,costo_unitario,total,observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('numero_remito', ''),
         data.get('proveedor_id', 0), data.get('proveedor_nombre', ''), data.get('producto_id', 0),
         data.get('codigo_interno', ''), data.get('descripcion', ''), float(data.get('cantidad', 1)),
         float(data.get('costo_unitario', 0)), float(data.get('total', 0)), data.get('observaciones', '')),
        fetchall=False, commit=True
    )


# ─── CAJA ────────────────────────────────────────────────────────────────────

def get_caja_dia(fecha):
    """Devuelve caja del día."""
    return q("SELECT * FROM caja_historial WHERE fecha=?", (fecha,), fetchone=True)


def init_caja_dia(fecha):
    """Inicializa caja del día."""
    ahora = datetime.now()
    hora = ahora.strftime('%H:%M:%S')
    q(
        """INSERT OR REPLACE INTO caja_historial
        (fecha,saldo_apertura,responsable_apertura,hora_apertura)
        VALUES (?,?,?,?)""",
        (fecha, 0, 'Sistema', hora),
        fetchall=False, commit=True
    )


def cerrar_caja_dia(fecha, saldo_real):
    """Cierra la caja del día."""
    ahora = datetime.now()
    hora = ahora.strftime('%H:%M:%S')
    caja = get_caja_dia(fecha)
    if not caja:
        return False
    saldo_esperado = caja['saldo_apertura'] + caja['total_ventas'] - caja['gastos_dia']
    diferencia = saldo_real - saldo_esperado
    q(
        """UPDATE caja_historial SET saldo_cierre_real=?,saldo_cierre_esperado=?,diferencia=?,
        cerrada=1,responsable_cierre=?,hora_cierre=? WHERE fecha=?""",
        (saldo_real, saldo_esperado, diferencia, 'Sistema', hora, fecha),
        fetchall=False, commit=True
    )
    return True


# ─── GASTOS ──────────────────────────────────────────────────────────────────

def get_gastos(search='', fecha_desde='', fecha_hasta='', limit=200):
    """Devuelve gastos filtrables."""
    sql = "SELECT * FROM gastos WHERE 1=1"
    params = []
    if search:
        sql += " AND (descripcion LIKE ? OR categoria LIKE ? OR proveedor LIKE ?)"
        params += [f'%{search}%'] * 3
    if fecha_desde:
        sql += " AND fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND fecha <= ?"
        params.append(fecha_hasta)
    sql += " ORDER BY fecha DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def add_gasto(data):
    """Agrega un gasto."""
    q(
        """INSERT INTO gastos
        (fecha,tipo,categoria,descripcion,monto,iva_incluido,medio_pago,proveedor,necesario,comprobante,observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('tipo', 'Gasto'),
         data.get('categoria', ''), data.get('descripcion', ''), float(data.get('monto', 0)),
         int(data.get('iva_incluido', 1)), data.get('medio_pago', 'Efectivo'), data.get('proveedor', ''),
         data.get('necesario', 'SI (necesario)'), data.get('comprobante', ''), data.get('observaciones', '')),
        fetchall=False, commit=True
    )


# ─── TEMPORADAS ──────────────────────────────────────────────────────────────

def get_temporadas(activa_only=False):
    """Devuelve temporadas."""
    sql = "SELECT * FROM temporadas"
    if activa_only:
        sql += " WHERE activa=1"
    sql += " ORDER BY fecha_inicio"
    return q(sql)


def get_temporada_actual():
    """Devuelve la temporada actual o None."""
    hoy = date.today().isoformat()
    return q(
        """SELECT * FROM temporadas
        WHERE activa=1 AND fecha_inicio <= ? AND fecha_fin >= ? LIMIT 1""",
        (hoy, hoy), fetchone=True
    )


def add_temporada(data):
    """Agrega una temporada."""
    q(
        """INSERT INTO temporadas
        (nombre,descripcion,fecha_inicio,fecha_fin)
        VALUES (?,?,?,?)""",
        (data['nombre'], data.get('descripcion', ''), data.get('fecha_inicio', ''), data.get('fecha_fin', '')),
        fetchall=False, commit=True
    )


# ─── UTILIDADES ──────────────────────────────────────────────────────────────

def fmt_ars(valor):
    """Formatea valor en ARS."""
    return f"${valor:,.2f}"


def get_dashboard_stats():
    """Calcula estadísticas para dashboard."""
    hoy = date.today().isoformat()

    # Ventas del día
    ventas_hoy = q(
        "SELECT COUNT(*) as total, COALESCE(SUM(total),0) as monto FROM ventas WHERE fecha=?",
        (hoy,), fetchone=True
    )

    # Stock en alerta
    alertas = get_alertas_count()

    # Últimas ventas
    ultimas_ventas = q("SELECT * FROM ventas ORDER BY fecha DESC, id DESC LIMIT 5")

    # Temporada actual
    temporada = get_temporada_actual()

    return {
        'ventas_hoy': ventas_hoy['total'] or 0,
        'monto_hoy': ventas_hoy['monto'] or 0,
        'alertas': alertas,
        'ultimas_ventas': ultimas_ventas,
        'temporada': temporada['nombre'] if temporada else 'Ninguna',
    }


# ─── PUNTO DE VENTA ──────────────────────────────────────────────────────────

def next_ticket():
    """Devuelve el próximo número de ticket."""
    ultimo = q("SELECT MAX(numero_ticket) as max FROM ventas", fetchone=True)
    return (ultimo['max'] or 0) + 1


def buscar_productos_pos(search):
    """Busca productos para POS por nombre/código/categoría."""
    sql = """SELECT p.id, p.codigo_interno, p.descripcion, p.categoria, p.unidad,
                    p.precio_venta, s.stock_actual
             FROM productos p
             JOIN stock s ON s.producto_id = p.id
             WHERE p.activo=1 AND s.stock_actual > 0"""
    params = []
    if search:
        sql += " AND (p.descripcion LIKE ? OR p.categoria LIKE ? OR p.codigo_interno LIKE ?)"
        params += [f'%{search}%'] * 3
    sql += " ORDER BY p.descripcion LIMIT 50"
    return q(sql, params)


def decrementar_stock_venta(venta_id):
    """Decrementa stock de productos vendidos."""
    items = get_venta_detalle(venta_id)
    for item in items:
        pid = item['producto_id']
        cantidad = item['cantidad']
        # Obtener stock actual
        stock_actual = q("SELECT stock_actual FROM stock WHERE producto_id=?", (pid,), fetchone=True)
        if stock_actual:
            nuevo_stock = stock_actual['stock_actual'] - cantidad
            q("UPDATE stock SET stock_actual=? WHERE producto_id=?", (nuevo_stock, pid), fetchall=False, commit=True)
            # Registrar movimiento
            q(
                """INSERT INTO stock_movimientos
                (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo)
                VALUES (?,?,?,?,?,?)""",
                (pid, 'VENTA', -cantidad, stock_actual['stock_actual'], nuevo_stock, f'Venta #{venta_id}'),
                fetchall=False, commit=True
            )


def get_venta_ticket(vid):
    """Devuelve venta completa para ticket."""
    venta = q("SELECT * FROM ventas WHERE id=?", (vid,), fetchone=True)
    if venta:
        venta = dict(venta)
        venta['detalle'] = get_venta_detalle(vid)
    return venta
