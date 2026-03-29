"""
Nexar Tienda — database.py
Conexión, tablas y consultas SQLite.

Basado en Nexar Almacén, adaptado para tienda de regalos:
  - Sin sistema de licencias ni OpenFoodFacts
  - Categorías propias de tienda (bijouterie, mates, etc.)
  - Módulo de temporadas (Día de la Madre, Navidad, etc.)
  - IVA dual: incluido o discriminado por cliente
"""

import sqlite3
import os
import hashlib
from datetime import datetime, date, timedelta

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
    """Ejecuta múltiples sentencias SQL en una sola transacción."""
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
    """
    Crea todas las tablas si no existen y carga datos iniciales.
    Se llama en cada request, pero solo inicializa la primera vez.
    """
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True

    conn = get_conn()
    c = conn.cursor()

    # ── TABLAS ────────────────────────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            username         TEXT UNIQUE NOT NULL,
            password_hash    TEXT NOT NULL,
            rol              TEXT DEFAULT 'usuario',
            nombre_completo  TEXT DEFAULT '',
            activo           INTEGER DEFAULT 1,
            created_at       TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categorias (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activa INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS productos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_interno  TEXT UNIQUE NOT NULL,
            codigo_barras   TEXT DEFAULT '',
            descripcion     TEXT NOT NULL,
            marca           TEXT DEFAULT '',
            categoria       TEXT DEFAULT '',
            unidad          TEXT DEFAULT 'Unidad',
            costo           REAL DEFAULT 0,
            precio_venta    REAL DEFAULT 0,
            iva_porcentaje  REAL DEFAULT 21.0,
            iva_tipo        TEXT DEFAULT 'incluido',
            tags            TEXT DEFAULT '',
            activo          INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stock (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id        INTEGER UNIQUE REFERENCES productos(id) ON DELETE CASCADE,
            stock_actual       REAL DEFAULT 0,
            stock_minimo       REAL DEFAULT 3,
            stock_maximo       REAL DEFAULT 30,
            ultimo_ingreso     TEXT DEFAULT '',
            proveedor_habitual TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo         TEXT UNIQUE,
            nombre         TEXT NOT NULL,
            dni_cuit       TEXT DEFAULT '',
            telefono       TEXT DEFAULT '',
            email          TEXT DEFAULT '',
            limite_credito REAL DEFAULT 0,
            iva_tipo       TEXT DEFAULT 'incluido',
            activo         INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS proveedores (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo       TEXT UNIQUE,
            nombre       TEXT NOT NULL,
            cuit         TEXT DEFAULT '',
            telefono     TEXT DEFAULT '',
            email        TEXT DEFAULT '',
            dias_credito INTEGER DEFAULT 30,
            activo       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ventas (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_ticket       INTEGER,
            fecha               TEXT,
            hora                TEXT,
            cliente_id          INTEGER DEFAULT 0,
            cliente_nombre      TEXT DEFAULT 'Mostrador',
            medio_pago          TEXT DEFAULT 'Efectivo',
            subtotal            REAL DEFAULT 0,
            descuento_adicional REAL DEFAULT 0,
            total               REAL DEFAULT 0,
            iva_discriminado    INTEGER DEFAULT 0,
            vendedor            TEXT DEFAULT '',
            temporada_id        INTEGER DEFAULT 0,
            temporada_nombre    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ventas_detalle (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id        INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
            producto_id     INTEGER DEFAULT 0,
            codigo_interno  TEXT DEFAULT '',
            descripcion     TEXT DEFAULT '',
            categoria       TEXT DEFAULT '',
            unidad          TEXT DEFAULT '',
            cantidad        REAL DEFAULT 1,
            precio_unitario REAL DEFAULT 0,
            descuento       REAL DEFAULT 0,
            subtotal        REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS compras (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha            TEXT,
            numero_remito    TEXT DEFAULT '',
            proveedor_id     INTEGER DEFAULT 0,
            proveedor_nombre TEXT DEFAULT '',
            producto_id      INTEGER DEFAULT 0,
            codigo_interno   TEXT DEFAULT '',
            descripcion      TEXT DEFAULT '',
            cantidad         REAL DEFAULT 1,
            costo_unitario   REAL DEFAULT 0,
            total            REAL DEFAULT 0,
            observaciones    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS caja_historial (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha                 TEXT UNIQUE,
            saldo_apertura        REAL DEFAULT 0,
            ventas_efectivo       REAL DEFAULT 0,
            ventas_debito         REAL DEFAULT 0,
            ventas_credito        REAL DEFAULT 0,
            ventas_qr             REAL DEFAULT 0,
            ventas_cta_cte        REAL DEFAULT 0,
            ventas_transferencia  REAL DEFAULT 0,
            total_ventas          REAL DEFAULT 0,
            gastos_dia            REAL DEFAULT 0,
            saldo_cierre_esperado REAL DEFAULT 0,
            saldo_cierre_real     REAL DEFAULT 0,
            diferencia            REAL DEFAULT 0,
            cerrada               INTEGER DEFAULT 0,
            responsable_apertura  TEXT DEFAULT '',
            responsable_cierre    TEXT DEFAULT '',
            hora_apertura         TEXT DEFAULT '',
            hora_cierre           TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS gastos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha         TEXT,
            categoria     TEXT DEFAULT '',
            descripcion   TEXT DEFAULT '',
            monto         REAL DEFAULT 0,
            medio_pago    TEXT DEFAULT 'Efectivo',
            proveedor     TEXT DEFAULT '',
            comprobante   TEXT DEFAULT '',
            observaciones TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS cc_clientes_mov (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id         INTEGER REFERENCES clientes(id),
            fecha              TEXT,
            tipo               TEXT DEFAULT 'Venta',
            numero_comprobante TEXT DEFAULT '',
            debe               REAL DEFAULT 0,
            haber              REAL DEFAULT 0,
            vencimiento        TEXT DEFAULT '',
            observaciones      TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS facturas_proveedores (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id      INTEGER REFERENCES proveedores(id),
            numero_factura    TEXT DEFAULT '',
            fecha             TEXT,
            fecha_vencimiento TEXT,
            importe           REAL DEFAULT 0,
            pagado            REAL DEFAULT 0,
            observaciones     TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS temporadas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin    TEXT NOT NULL,
            descripcion  TEXT DEFAULT '',
            color        TEXT DEFAULT '#3b82f6',
            activa       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS productos_temporada (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            temporada_id INTEGER REFERENCES temporadas(id) ON DELETE CASCADE,
            producto_id  INTEGER REFERENCES productos(id) ON DELETE CASCADE,
            UNIQUE(temporada_id, producto_id)
        );
    """)

    # ── CONFIG POR DEFECTO ────────────────────────────────────────────────────
    defaults = [
        ('nombre_negocio',         'Nexar Tienda'),
        ('direccion',              ''),
        ('telefono',               ''),
        ('cuit',                   ''),
        ('responsable',            ''),
        ('ticket_pie_texto',       'Gracias por su compra'),
        ('margen_minimo',          '0.30'),
        ('margen_objetivo',        '0.50'),
        ('dias_alerta_proveedor',  '30'),
        ('dias_alerta_cliente',    '15'),
        ('siguiente_ticket',       '1001'),
        ('siguiente_codigo',       '1'),
        ('iva_porcentaje_default', '21'),
        ('backup_intervalo_h',     '24'),
        ('backup_keep',            '10'),
        ('backup_ultimo',          ''),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO config VALUES (?,?)", (k, v))

    # ── USUARIOS POR DEFECTO ──────────────────────────────────────────────────
    def _hash(pw):
        return hashlib.sha256(pw.encode()).hexdigest()

    for uname, phash, rol, nombre in [
        ('admin',    _hash('admin123'),    'admin',   'Administrador'),
        ('vendedor', _hash('vendedor123'), 'usuario', 'Vendedor'),
    ]:
        c.execute(
            "INSERT OR IGNORE INTO usuarios (username,password_hash,rol,nombre_completo) VALUES (?,?,?,?)",
            (uname, phash, rol, nombre)
        )

    # ── CATEGORÍAS DE LA TIENDA ───────────────────────────────────────────────
    for cat in [
        'Bijouterie', 'Marroquinería', 'Mates y Termos',
        'Adornos y Decoración', 'Regalos Varios', 'Regalos de Temporada',
        'Papelería y Librería', 'Textil e Indumentaria',
        'Juguetería', 'Cotillón', 'Perfumería y Cosmética',
        'Artículos del Hogar', 'Otros',
    ]:
        c.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (cat,))

    # ── TEMPORADAS PREDEFINIDAS ───────────────────────────────────────────────
    yr = date.today().year
    for nombre, fi, ff, desc, color in [
        ('Día de la Madre',       f'{yr}-04-20', f'{yr}-05-25',       'Segunda quincena de mayo',     '#ec4899'),
        ('Día del Padre',         f'{yr}-06-01', f'{yr}-06-22',       'Tercer domingo de junio',      '#3b82f6'),
        ('Navidad',               f'{yr}-11-15', f'{yr}-12-25',       'Fin de año',                   '#dc2626'),
        ('Año Nuevo',             f'{yr}-12-26', f'{yr+1}-01-05',     'Primera semana del año',       '#f59e0b'),
        ('Día del Niño',          f'{yr}-07-20', f'{yr}-08-10',       'Segundo domingo de agosto',    '#10b981'),
        ('Día de los Enamorados', f'{yr}-02-01', f'{yr}-02-14',       '14 de febrero',                '#f43f5e'),
        ('Halloween',             f'{yr}-10-15', f'{yr}-10-31',       'Fin de octubre',               '#7c3aed'),
        ('Día del Maestro',       f'{yr}-09-01', f'{yr}-09-11',       '11 de septiembre',             '#0891b2'),
    ]:
        c.execute(
            "INSERT OR IGNORE INTO temporadas (nombre,fecha_inicio,fecha_fin,descripcion,color) VALUES (?,?,?,?,?)",
            (nombre, fi, ff, desc, color)
        )

    # ── REPARAR PRODUCTOS SIN STOCK ───────────────────────────────────────────
    c.execute("""
        INSERT OR IGNORE INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo)
        SELECT id, 0, 3, 30 FROM productos
        WHERE activo=1 AND id NOT IN (SELECT producto_id FROM stock)
    """)

    conn.commit()
    conn.close()


# ─── CONFIG ──────────────────────────────────────────────────────────────────

def get_config():
    rows = q("SELECT clave, valor FROM config")
    return {r['clave']: r['valor'] for r in rows}


def set_config(data: dict):
    conn = get_conn()
    c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO config VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()


# ─── CONTADORES ──────────────────────────────────────────────────────────────

def next_codigo():
    """Genera el próximo código de producto (PRD-0001, PRD-0002...)."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT MAX(CAST(SUBSTR(codigo_interno,5) AS INTEGER)) as mx "
        "FROM productos WHERE codigo_interno LIKE 'PRD-%'"
    ).fetchone()
    max_n = (row['mx'] or 0) + 1
    cfg_n = int(c.execute(
        "SELECT valor FROM config WHERE clave='siguiente_codigo'"
    ).fetchone()['valor'] or 1)
    n = max(max_n, cfg_n)
    new_code = f"PRD-{n:04d}"
    c.execute("INSERT OR REPLACE INTO config VALUES ('siguiente_codigo', ?)", (str(n + 1),))
    conn.commit()
    conn.close()
    return new_code


def next_ticket():
    cfg = get_config()
    n = int(cfg.get('siguiente_ticket', 1001))
    set_config({'siguiente_ticket': str(n + 1)})
    return n


# ─── AUTENTICACIÓN ───────────────────────────────────────────────────────────

def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def verificar_password(username: str, password: str):
    u = q("SELECT * FROM usuarios WHERE username=? AND activo=1", (username,), fetchone=True)
    if u and u['password_hash'] == _hash_pw(password):
        return dict(u)
    return None


def get_usuarios():
    return q("SELECT id,username,rol,nombre_completo,activo FROM usuarios ORDER BY rol,username")


def crear_usuario(username, password, rol, nombre):
    try:
        q("INSERT INTO usuarios (username,password_hash,rol,nombre_completo) VALUES (?,?,?,?)",
          (username.strip(), _hash_pw(password), rol, nombre.strip()),
          fetchall=False, commit=True)
        return True
    except Exception:
        return False


def editar_usuario(uid, nombre, rol):
    q("UPDATE usuarios SET nombre_completo=?, rol=? WHERE id=?",
      (nombre, rol, uid), fetchall=False, commit=True)


def cambiar_password(uid, nueva):
    q("UPDATE usuarios SET password_hash=? WHERE id=?",
      (_hash_pw(nueva), uid), fetchall=False, commit=True)


def toggle_usuario(uid):
    q("UPDATE usuarios SET activo=CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE id=?",
      (uid,), fetchall=False, commit=True)


def delete_usuario(uid):
    q("DELETE FROM usuarios WHERE id=? AND rol!='admin'",
      (uid,), fetchall=False, commit=True)


# ─── CATEGORÍAS ──────────────────────────────────────────────────────────────

def get_categorias():
    return [r['nombre'] for r in q(
        "SELECT nombre FROM categorias WHERE activa=1 ORDER BY nombre"
    )]


def add_categoria(nombre):
    q("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)",
      (nombre,), fetchall=False, commit=True)


def delete_categoria(nombre):
    conn = get_conn()
    conn.execute("DELETE FROM categorias WHERE nombre=?", (nombre,))
    conn.commit()
    conn.close()


# ─── PRODUCTOS ───────────────────────────────────────────────────────────────

def get_productos(activo_only=True, search='', categoria=''):
    sql = "SELECT * FROM productos"
    conds, params = [], []
    if activo_only:
        conds.append("activo=1")
    if search:
        conds.append("(descripcion LIKE ? OR codigo_interno LIKE ? OR marca LIKE ? OR tags LIKE ?)")
        params += [f'%{search}%'] * 4
    if categoria:
        conds.append("categoria=?")
        params.append(categoria)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY descripcion"
    return q(sql, params)


def get_producto(pid):
    return q("SELECT * FROM productos WHERE id=?", (pid,), fetchone=True)


def add_producto(data):
    codigo = next_codigo()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO productos
            (codigo_interno, codigo_barras, descripcion, marca, categoria,
             unidad, costo, precio_venta, iva_porcentaje, iva_tipo, tags, activo)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,1)
    """, (
        codigo,
        data.get('codigo_barras', ''),
        data['descripcion'],
        data.get('marca', ''),
        data.get('categoria', ''),
        data.get('unidad', 'Unidad'),
        float(data.get('costo', 0)),
        float(data.get('precio_venta', 0)),
        float(data.get('iva_porcentaje', 21)),
        data.get('iva_tipo', 'incluido'),
        data.get('tags', ''),
    ))
    pid = c.lastrowid
    c.execute(
        "INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo) VALUES (?,?,?,?)",
        (pid,
         float(data.get('stock_actual', 0)),
         float(data.get('stock_minimo', 3)),
         float(data.get('stock_maximo', 30)))
    )
    conn.commit()
    conn.close()
    return pid


def update_producto(pid, data):
    q("""
        UPDATE productos SET
            codigo_barras=?, descripcion=?, marca=?, categoria=?, unidad=?,
            costo=?, precio_venta=?, iva_porcentaje=?, iva_tipo=?, tags=?, activo=?
        WHERE id=?
    """, (
        data.get('codigo_barras', ''),
        data['descripcion'],
        data.get('marca', ''),
        data.get('categoria', ''),
        data.get('unidad', 'Unidad'),
        float(data.get('costo', 0)),
        float(data.get('precio_venta', 0)),
        float(data.get('iva_porcentaje', 21)),
        data.get('iva_tipo', 'incluido'),
        data.get('tags', ''),
        int(data.get('activo', 1)),
        pid,
    ), fetchall=False, commit=True)


def delete_producto(pid):
    """Baja lógica."""
    q("UPDATE productos SET activo=0 WHERE id=?", (pid,), fetchall=False, commit=True)


def buscar_productos_pos(term, limit=12):
    """Búsqueda instantánea para el POS (mín. 2 caracteres)."""
    if not term or len(term.strip()) < 2:
        return []
    t = f'%{term.strip()}%'
    return q("""
        SELECT p.id, p.codigo_interno, p.descripcion, p.categoria,
               p.unidad, p.precio_venta, p.iva_porcentaje, p.iva_tipo,
               COALESCE(s.stock_actual, 0) as stock_actual
        FROM productos p
        LEFT JOIN stock s ON s.producto_id = p.id
        WHERE p.activo=1
          AND (p.descripcion LIKE ? OR p.categoria LIKE ?
               OR p.codigo_interno LIKE ? OR p.tags LIKE ?)
        ORDER BY p.descripcion
        LIMIT ?
    """, (t, t, t, t, limit))


# ─── STOCK ───────────────────────────────────────────────────────────────────

def get_stock_full(search='', alerta_only=False):
    sql = """
        SELECT p.id, p.codigo_interno, p.descripcion, p.categoria,
               p.unidad, p.costo, p.precio_venta,
               s.stock_actual, s.stock_minimo, s.stock_maximo,
               s.ultimo_ingreso, s.proveedor_habitual,
               CASE
                   WHEN s.stock_actual <= 0                    THEN 'SIN STOCK'
                   WHEN s.stock_actual <= s.stock_minimo       THEN 'CRITICO'
                   WHEN s.stock_actual <= s.stock_minimo * 1.5 THEN 'BAJO'
                   WHEN s.stock_actual >= s.stock_maximo       THEN 'EXCESO'
                   ELSE 'NORMAL'
               END as estado,
               s.stock_actual * p.costo as valor_stock
        FROM productos p
        JOIN stock s ON s.producto_id = p.id
        WHERE p.activo=1
    """
    params = []
    if search:
        sql += " AND (p.descripcion LIKE ? OR p.categoria LIKE ? OR p.codigo_interno LIKE ?)"
        params += [f'%{search}%'] * 3
    if alerta_only:
        sql += " AND s.stock_actual <= s.stock_minimo * 1.5"
    sql += " ORDER BY p.descripcion"
    return q(sql, params)


def update_stock_item(pid, stock_actual=None, stock_minimo=None,
                      stock_maximo=None, proveedor=None):
    updates, params = [], []
    if stock_actual is not None:
        updates.append("stock_actual=?");      params.append(stock_actual)
    if stock_minimo is not None:
        updates.append("stock_minimo=?");      params.append(stock_minimo)
    if stock_maximo is not None:
        updates.append("stock_maximo=?");      params.append(stock_maximo)
    if proveedor is not None:
        updates.append("proveedor_habitual=?"); params.append(proveedor)
    if updates:
        params.append(pid)
        q(f"UPDATE stock SET {','.join(updates)} WHERE producto_id=?",
          params, fetchall=False, commit=True)


def get_alertas_count():
    r = q("""
        SELECT
            COALESCE(SUM(CASE WHEN s.stock_actual <= 0 THEN 1 ELSE 0 END), 0) as sin_stock,
            COALESCE(SUM(CASE WHEN s.stock_actual > 0 AND s.stock_actual <= s.stock_minimo THEN 1 ELSE 0 END), 0) as critico,
            COALESCE(SUM(CASE WHEN s.stock_actual > s.stock_minimo AND s.stock_actual <= s.stock_minimo*1.5 THEN 1 ELSE 0 END), 0) as bajo
        FROM stock s JOIN productos p ON p.id = s.producto_id WHERE p.activo=1
    """, fetchone=True)
    return {
        'sin_stock': r['sin_stock'] or 0,
        'critico':   r['critico']   or 0,
        'bajo':      r['bajo']      or 0,
    }


# ─── VENTAS ──────────────────────────────────────────────────────────────────

def get_ventas(search='', fecha_desde='', fecha_hasta='', limit=200):
    sql = """
        SELECT v.*, COUNT(d.id) as items
        FROM ventas v LEFT JOIN ventas_detalle d ON d.venta_id=v.id
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (v.cliente_nombre LIKE ? OR v.medio_pago LIKE ? OR CAST(v.numero_ticket AS TEXT) LIKE ?)"
        params += [f'%{search}%'] * 3
    if fecha_desde:
        sql += " AND v.fecha >= ?"; params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND v.fecha <= ?"; params.append(fecha_hasta)
    sql += " GROUP BY v.id ORDER BY v.fecha DESC, v.id DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def get_venta_detalle(vid):
    return q("SELECT * FROM ventas_detalle WHERE venta_id=? ORDER BY id", (vid,))


def crear_venta(items, cliente_nombre, medio_pago, descuento_adicional,
                vendedor, cliente_id=0, iva_discriminado=False):
    """
    Registra una venta completa.

    items: lista de dicts con producto_id, codigo_interno, descripcion,
           categoria, unidad, cantidad, precio_unitario, descuento
    """
    today     = date.today()
    ticket    = next_ticket()
    temporada = _get_temporada_activa(today)

    subtotal = sum(
        i['cantidad'] * i['precio_unitario'] * (1 - i.get('descuento', 0))
        for i in items
    )
    total = subtotal * (1 - descuento_adicional)

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO ventas
            (numero_ticket, fecha, hora, cliente_id, cliente_nombre, medio_pago,
             subtotal, descuento_adicional, total, iva_discriminado,
             vendedor, temporada_id, temporada_nombre)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        ticket,
        today.isoformat(),
        datetime.now().strftime('%H:%M'),
        cliente_id, cliente_nombre, medio_pago,
        subtotal, descuento_adicional, total,
        1 if iva_discriminado else 0,
        vendedor,
        temporada['id']     if temporada else 0,
        temporada['nombre'] if temporada else '',
    ))
    vid = c.lastrowid

    for item in items:
        item_sub = item['cantidad'] * item['precio_unitario'] * (1 - item.get('descuento', 0))
        c.execute("""
            INSERT INTO ventas_detalle
                (venta_id, producto_id, codigo_interno, descripcion,
                 categoria, unidad, cantidad, precio_unitario, descuento, subtotal)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (vid, item['producto_id'], item['codigo_interno'],
              item['descripcion'], item['categoria'], item['unidad'],
              item['cantidad'], item['precio_unitario'],
              item.get('descuento', 0), item_sub))
        c.execute(
            "UPDATE stock SET stock_actual=stock_actual-? WHERE producto_id=?",
            (item['cantidad'], item['producto_id'])
        )

    # Actualizar caja
    field = {
        'Efectivo': 'ventas_efectivo', 'Débito': 'ventas_debito',
        'Crédito': 'ventas_credito', 'QR / Billetera Virtual': 'ventas_qr',
        'Cuenta Corriente': 'ventas_cta_cte', 'Transferencia': 'ventas_transferencia',
    }.get(medio_pago, 'ventas_efectivo')
    c.execute(f"""
        INSERT INTO caja_historial (fecha, {field}, total_ventas) VALUES (?,?,?)
        ON CONFLICT(fecha) DO UPDATE SET
            {field}={field}+excluded.{field},
            total_ventas=total_ventas+excluded.total_ventas
    """, (today.isoformat(), total, total))

    # Cuenta corriente
    if medio_pago == 'Cuenta Corriente' and cliente_id:
        venc = (today + timedelta(days=15)).isoformat()
        c.execute("""
            INSERT INTO cc_clientes_mov
                (cliente_id, fecha, tipo, numero_comprobante, debe, vencimiento)
            VALUES (?,?,?,?,?,?)
        """, (cliente_id, today.isoformat(), 'Venta', str(ticket), total, venc))

    conn.commit()
    conn.close()
    return vid, ticket


# ─── COMPRAS ─────────────────────────────────────────────────────────────────

def get_compras(search='', limit=200):
    sql = """
        SELECT c.*, p.nombre as proveedor_obj FROM compras c
        LEFT JOIN proveedores p ON p.id=c.proveedor_id WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (c.descripcion LIKE ? OR c.proveedor_nombre LIKE ? OR c.numero_remito LIKE ?)"
        params += [f'%{search}%'] * 3
    sql += " ORDER BY c.fecha DESC, c.id DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def registrar_compra(data):
    conn = get_conn()
    c = conn.cursor()
    total = float(data.get('cantidad', 1)) * float(data.get('costo_unitario', 0))
    c.execute("""
        INSERT INTO compras
            (fecha, numero_remito, proveedor_id, proveedor_nombre, producto_id,
             codigo_interno, descripcion, cantidad, costo_unitario, total, observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get('fecha', date.today().isoformat()),
        data.get('numero_remito', ''),
        int(data.get('proveedor_id', 0)),
        data.get('proveedor_nombre', ''),
        int(data.get('producto_id', 0)),
        data.get('codigo_interno', ''),
        data.get('descripcion', ''),
        float(data.get('cantidad', 1)),
        float(data.get('costo_unitario', 0)),
        total,
        data.get('observaciones', ''),
    ))
    pid = int(data.get('producto_id', 0))
    if pid:
        c.execute(
            "UPDATE stock SET stock_actual=stock_actual+?, ultimo_ingreso=? WHERE producto_id=?",
            (float(data.get('cantidad', 1)), data.get('fecha', date.today().isoformat()), pid)
        )
        if float(data.get('costo_unitario', 0)) > 0:
            c.execute("UPDATE productos SET costo=? WHERE id=?",
                      (float(data.get('costo_unitario', 0)), pid))
    conn.commit()
    conn.close()


# ─── CAJA ────────────────────────────────────────────────────────────────────

def get_caja_hoy():
    row = q("SELECT * FROM caja_historial WHERE fecha=?",
            (date.today().isoformat(),), fetchone=True)
    return dict(row) if row else None


def abrir_caja(saldo_apertura, responsable):
    q("""
        INSERT OR IGNORE INTO caja_historial
            (fecha, saldo_apertura, responsable_apertura, hora_apertura, cerrada)
        VALUES (?,?,?,?,0)
    """, (date.today().isoformat(), saldo_apertura, responsable,
          datetime.now().strftime('%H:%M')),
    fetchall=False, commit=True)


def cerrar_caja(saldo_real, responsable):
    row = get_caja_hoy()
    if not row:
        return
    total_ventas = sum(row.get(f, 0) for f in [
        'ventas_efectivo', 'ventas_debito', 'ventas_credito',
        'ventas_qr', 'ventas_cta_cte', 'ventas_transferencia',
    ])
    esperado   = row['saldo_apertura'] + row.get('ventas_efectivo', 0) - row.get('gastos_dia', 0)
    diferencia = saldo_real - esperado
    q("""
        UPDATE caja_historial SET
            total_ventas=?, saldo_cierre_esperado=?, saldo_cierre_real=?,
            diferencia=?, cerrada=1, responsable_cierre=?, hora_cierre=?
        WHERE fecha=?
    """, (total_ventas, esperado, saldo_real, diferencia, responsable,
          datetime.now().strftime('%H:%M'), date.today().isoformat()),
    fetchall=False, commit=True)


def get_caja_historial(limit=60):
    return q("SELECT * FROM caja_historial ORDER BY fecha DESC LIMIT ?", (limit,))


def _add_gasto_a_caja(monto):
    q("""
        INSERT INTO caja_historial (fecha, gastos_dia) VALUES (?,?)
        ON CONFLICT(fecha) DO UPDATE SET gastos_dia=gastos_dia+excluded.gastos_dia
    """, (date.today().isoformat(), monto), fetchall=False, commit=True)


# ─── GASTOS ──────────────────────────────────────────────────────────────────

def get_gastos(search='', limit=500):
    sql = "SELECT * FROM gastos WHERE 1=1"
    params = []
    if search:
        sql += " AND (descripcion LIKE ? OR categoria LIKE ? OR proveedor LIKE ?)"
        params += [f'%{search}%'] * 3
    sql += " ORDER BY fecha DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def add_gasto(data):
    monto = float(data.get('monto', 0))
    q("""
        INSERT INTO gastos
            (fecha, categoria, descripcion, monto, medio_pago, proveedor, comprobante, observaciones)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        data.get('fecha', date.today().isoformat()),
        data.get('categoria', ''), data.get('descripcion', ''),
        monto, data.get('medio_pago', 'Efectivo'),
        data.get('proveedor', ''), data.get('comprobante', ''),
        data.get('observaciones', ''),
    ), fetchall=False, commit=True)
    _add_gasto_a_caja(monto)


def update_gasto(gid, data):
    q("""
        UPDATE gastos SET fecha=?, categoria=?, descripcion=?, monto=?,
            medio_pago=?, proveedor=?, comprobante=?, observaciones=?
        WHERE id=?
    """, (
        data.get('fecha'), data.get('categoria', ''), data.get('descripcion', ''),
        float(data.get('monto', 0)), data.get('medio_pago', 'Efectivo'),
        data.get('proveedor', ''), data.get('comprobante', ''),
        data.get('observaciones', ''), gid,
    ), fetchall=False, commit=True)


def delete_gasto(gid):
    q("DELETE FROM gastos WHERE id=?", (gid,), fetchall=False, commit=True)


# ─── CLIENTES ────────────────────────────────────────────────────────────────

def get_clientes(activo_only=True, search=''):
    sql = "SELECT * FROM clientes"
    conds, params = [], []
    if activo_only:
        conds.append("activo=1")
    if search:
        conds.append("(nombre LIKE ? OR codigo LIKE ? OR telefono LIKE ?)")
        params += [f'%{search}%'] * 3
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY nombre"
    return q(sql, params)


def get_cliente(cid):
    return q("SELECT * FROM clientes WHERE id=?", (cid,), fetchone=True)


def add_cliente(data):
    conn = get_conn()
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*)+1 as n FROM clientes").fetchone()['n']
    c.execute("""
        INSERT INTO clientes (codigo, nombre, dni_cuit, telefono, email, limite_credito, iva_tipo)
        VALUES (?,?,?,?,?,?,?)
    """, (f"CLI-{n:03d}", data['nombre'], data.get('dni_cuit', ''),
          data.get('telefono', ''), data.get('email', ''),
          float(data.get('limite_credito', 0)),
          data.get('iva_tipo', 'incluido')))
    conn.commit()
    conn.close()


def update_cliente(cid, data):
    q("""
        UPDATE clientes SET
            nombre=?, dni_cuit=?, telefono=?, email=?,
            limite_credito=?, iva_tipo=?, activo=?
        WHERE id=?
    """, (data['nombre'], data.get('dni_cuit', ''), data.get('telefono', ''),
          data.get('email', ''), float(data.get('limite_credito', 0) or 0),
          data.get('iva_tipo', 'incluido'), int(data.get('activo', 1)), cid),
    fetchall=False, commit=True)


def delete_cliente(cid):
    q("UPDATE clientes SET activo=0 WHERE id=?", (cid,), fetchall=False, commit=True)


def get_saldo_cliente(cid):
    r = q("SELECT COALESCE(SUM(debe),0)-COALESCE(SUM(haber),0) as saldo FROM cc_clientes_mov WHERE cliente_id=?",
          (cid,), fetchone=True)
    return r['saldo'] if r else 0


def get_cc_clientes_resumen():
    return q("""
        SELECT cl.*,
            COALESCE(SUM(m.debe),0)-COALESCE(SUM(m.haber),0) as saldo_actual,
            MAX(CASE WHEN m.debe>0 THEN m.vencimiento ELSE NULL END) as proximo_vto
        FROM clientes cl
        LEFT JOIN cc_clientes_mov m ON m.cliente_id=cl.id
        WHERE cl.activo=1
        GROUP BY cl.id ORDER BY cl.nombre
    """)


def get_cc_movimientos(cliente_id):
    return q("SELECT * FROM cc_clientes_mov WHERE cliente_id=? ORDER BY fecha DESC, id DESC",
             (cliente_id,))


def add_cc_mov(cliente_id, data):
    q("""
        INSERT INTO cc_clientes_mov
            (cliente_id, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones)
        VALUES (?,?,?,?,?,?,?,?)
    """, (cliente_id, data.get('fecha', date.today().isoformat()),
          data.get('tipo', 'Venta'), data.get('numero_comprobante', ''),
          float(data.get('debe', 0)), float(data.get('haber', 0)),
          data.get('vencimiento', ''), data.get('observaciones', '')),
    fetchall=False, commit=True)


def delete_cc_mov(mid):
    q("DELETE FROM cc_clientes_mov WHERE id=?", (mid,), fetchall=False, commit=True)


# ─── PROVEEDORES ─────────────────────────────────────────────────────────────

def get_proveedores(activo_only=True, search=''):
    sql = "SELECT * FROM proveedores"
    conds, params = [], []
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
    return q("SELECT * FROM proveedores WHERE id=?", (pid,), fetchone=True)


def add_proveedor(data):
    conn = get_conn()
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*)+1 as n FROM proveedores").fetchone()['n']
    c.execute("""
        INSERT INTO proveedores (codigo, nombre, cuit, telefono, email, dias_credito)
        VALUES (?,?,?,?,?,?)
    """, (f"PROV-{n:03d}", data['nombre'], data.get('cuit', ''),
          data.get('telefono', ''), data.get('email', ''),
          int(data.get('dias_credito', 30))))
    conn.commit()
    conn.close()


def update_proveedor(pid, data):
    q("""
        UPDATE proveedores SET nombre=?, cuit=?, telefono=?, email=?, dias_credito=?, activo=?
        WHERE id=?
    """, (data['nombre'], data.get('cuit', ''), data.get('telefono', ''),
          data.get('email', ''), int(data.get('dias_credito', 30) or 30),
          int(data.get('activo', 1)), pid),
    fetchall=False, commit=True)


def delete_proveedor(pid):
    q("UPDATE proveedores SET activo=0 WHERE id=?", (pid,), fetchall=False, commit=True)


def get_facturas_proveedores(search=''):
    sql = """
        SELECT fp.*, p.nombre as proveedor_nombre_obj,
               fp.importe - fp.pagado as saldo,
               CASE
                   WHEN fp.fecha_vencimiento < date('now') AND fp.importe > fp.pagado THEN 'VENCIDA'
                   WHEN fp.fecha_vencimiento <= date('now','+30 days') AND fp.importe > fp.pagado THEN 'POR VENCER'
                   WHEN fp.importe <= fp.pagado THEN 'PAGADA'
                   ELSE 'VIGENTE'
               END as estado
        FROM facturas_proveedores fp
        JOIN proveedores p ON p.id=fp.proveedor_id WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (p.nombre LIKE ? OR fp.numero_factura LIKE ?)"
        params += [f'%{search}%'] * 2
    sql += " ORDER BY fp.fecha_vencimiento ASC"
    return q(sql, params)


def add_factura_proveedor(data):
    q("""
        INSERT INTO facturas_proveedores
            (proveedor_id, numero_factura, fecha, fecha_vencimiento, importe, pagado, observaciones)
        VALUES (?,?,?,?,?,?,?)
    """, (int(data['proveedor_id']), data.get('numero_factura', ''),
          data.get('fecha', date.today().isoformat()), data['fecha_vencimiento'],
          float(data['importe']), float(data.get('pagado', 0)),
          data.get('observaciones', '')),
    fetchall=False, commit=True)


def pagar_factura(fid, monto):
    q("UPDATE facturas_proveedores SET pagado=pagado+? WHERE id=?",
      (monto, fid), fetchall=False, commit=True)


def delete_factura_proveedor(fid):
    q("DELETE FROM facturas_proveedores WHERE id=?", (fid,), fetchall=False, commit=True)


# ─── TEMPORADAS ★ ────────────────────────────────────────────────────────────

def get_temporadas(activa_only=False):
    sql = "SELECT * FROM temporadas"
    if activa_only:
        sql += " WHERE activa=1"
    sql += " ORDER BY fecha_inicio"
    return q(sql)


def get_temporada(tid):
    return q("SELECT * FROM temporadas WHERE id=?", (tid,), fetchone=True)


def add_temporada(data):
    return q("""
        INSERT INTO temporadas (nombre, fecha_inicio, fecha_fin, descripcion, color, activa)
        VALUES (?,?,?,?,?,1)
    """, (data['nombre'], data['fecha_inicio'], data['fecha_fin'],
          data.get('descripcion', ''), data.get('color', '#3b82f6')),
    fetchall=False, commit=True)


def update_temporada(tid, data):
    q("""
        UPDATE temporadas SET
            nombre=?, fecha_inicio=?, fecha_fin=?, descripcion=?, color=?, activa=?
        WHERE id=?
    """, (data['nombre'], data['fecha_inicio'], data['fecha_fin'],
          data.get('descripcion', ''), data.get('color', '#3b82f6'),
          int(data.get('activa', 1)), tid),
    fetchall=False, commit=True)


def delete_temporada(tid):
    q("DELETE FROM temporadas WHERE id=?", (tid,), fetchall=False, commit=True)


def _get_temporada_activa(hoy=None):
    """Devuelve la temporada activa hoy (la que termina antes si hay varias)."""
    hoy_str = (hoy or date.today()).isoformat()
    return q("""
        SELECT * FROM temporadas
        WHERE activa=1 AND fecha_inicio <= ? AND fecha_fin >= ?
        ORDER BY fecha_fin ASC LIMIT 1
    """, (hoy_str, hoy_str), fetchone=True)


def get_temporada_activa():
    return _get_temporada_activa()


def get_temporadas_proximas(dias=45):
    """Devuelve temporadas que empiezan en los próximos N días."""
    desde = date.today().isoformat()
    hasta = (date.today() + timedelta(days=dias)).isoformat()
    return q("""
        SELECT * FROM temporadas
        WHERE activa=1 AND fecha_inicio > ? AND fecha_inicio <= ?
        ORDER BY fecha_inicio ASC
    """, (desde, hasta))


def get_productos_temporada(tid):
    return q("""
        SELECT p.*, pt.id as pt_id FROM productos p
        JOIN productos_temporada pt ON pt.producto_id=p.id
        WHERE pt.temporada_id=? AND p.activo=1 ORDER BY p.descripcion
    """, (tid,))


def toggle_producto_temporada(tid, pid):
    """Agrega o quita un producto de una temporada. Devuelve True si fue agregado."""
    existing = q("SELECT id FROM productos_temporada WHERE temporada_id=? AND producto_id=?",
                 (tid, pid), fetchone=True)
    if existing:
        q("DELETE FROM productos_temporada WHERE temporada_id=? AND producto_id=?",
          (tid, pid), fetchall=False, commit=True)
        return False
    else:
        q("INSERT INTO productos_temporada (temporada_id, producto_id) VALUES (?,?)",
          (tid, pid), fetchall=False, commit=True)
        return True


# ─── ESTADÍSTICAS ────────────────────────────────────────────────────────────

def get_ventas_por_mes(year=None):
    if not year:
        year = date.today().year
    rows = q("""
        SELECT strftime('%m',fecha) as mes, ROUND(SUM(total),2) as total, COUNT(DISTINCT id) as tickets
        FROM ventas WHERE strftime('%Y',fecha)=? GROUP BY mes ORDER BY mes
    """, (str(year),))
    return {int(r['mes']): {'total': r['total'], 'tickets': r['tickets']} for r in rows}


def get_ventas_por_semana(weeks=8):
    rows = []
    today = date.today()
    for i in range(weeks - 1, -1, -1):
        start = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        end   = start + timedelta(days=6)
        r = q("SELECT ROUND(SUM(total),2) as total, COUNT(id) as tickets FROM ventas WHERE fecha>=? AND fecha<=?",
              (start.isoformat(), end.isoformat()), fetchone=True)
        rows.append({
            'label':   f'{start.strftime("%d/%m")}-{end.strftime("%d/%m")}',
            'total':   r['total']   or 0,
            'tickets': r['tickets'] or 0,
        })
    return rows


def get_ventas_por_medio_pago(year=None, month=None):
    if not year:  year  = date.today().year
    if not month: month = date.today().month
    return q("""
        SELECT medio_pago, ROUND(SUM(total),2) as total, COUNT(id) as ops
        FROM ventas WHERE strftime('%Y',fecha)=? AND strftime('%m',fecha)=?
        GROUP BY medio_pago ORDER BY total DESC
    """, (str(year), f'{month:02d}'))


def get_ventas_por_categoria(fecha_desde='', fecha_hasta=''):
    sql = """
        SELECT d.categoria, ROUND(SUM(d.subtotal),2) as total, ROUND(SUM(d.cantidad),2) as unidades
        FROM ventas_detalle d JOIN ventas v ON v.id=d.venta_id WHERE 1=1
    """
    params = []
    if fecha_desde:
        sql += " AND v.fecha>=?"; params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND v.fecha<=?"; params.append(fecha_hasta)
    sql += " GROUP BY d.categoria ORDER BY total DESC"
    return q(sql, params)


def get_ventas_por_temporada():
    return q("""
        SELECT temporada_nombre, ROUND(SUM(total),2) as total, COUNT(id) as tickets
        FROM ventas WHERE temporada_nombre != ''
        GROUP BY temporada_nombre ORDER BY total DESC
    """)


def get_top_productos(limit=10, fecha_desde='', fecha_hasta=''):
    sql = """
        SELECT d.descripcion, d.categoria,
               ROUND(SUM(d.cantidad),2) as total_unidades,
               ROUND(SUM(d.subtotal),2) as total_pesos,
               COUNT(DISTINCT d.venta_id) as num_ventas
        FROM ventas_detalle d JOIN ventas v ON v.id=d.venta_id WHERE 1=1
    """
    params = []
    if fecha_desde:
        sql += " AND v.fecha>=?"; params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND v.fecha<=?"; params.append(fecha_hasta)
    sql += " GROUP BY d.descripcion ORDER BY total_pesos DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def get_rentabilidad_mes(year=None, month=None):
    if not year:  year  = date.today().year
    if not month: month = date.today().month
    ym = f"{year}-{month:02d}"
    vr = q("SELECT ROUND(SUM(total),2) as v FROM ventas WHERE strftime('%Y-%m',fecha)=?", (ym,), fetchone=True)
    gr = q("SELECT ROUND(SUM(monto),2) as g FROM gastos WHERE strftime('%Y-%m',fecha)=?", (ym,), fetchone=True)
    ventas = vr['v'] or 0
    gastos = gr['g'] or 0
    return {
        'ventas': ventas, 'gastos': gastos,
        'utilidad': ventas - gastos,
        'rentabilidad': (ventas - gastos) / ventas * 100 if ventas else 0,
        'mes': month, 'anio': year,
    }


def get_dashboard_kpis():
    today = date.today().isoformat()
    month = date.today().strftime('%Y-%m')
    r_hoy = q("SELECT ROUND(SUM(total),2) as v, COUNT(id) as t FROM ventas WHERE fecha=?",
              (today,), fetchone=True)
    r_mes = q("SELECT ROUND(SUM(total),2) as v FROM ventas WHERE strftime('%Y-%m',fecha)=?",
              (month,), fetchone=True)
    g_mes = q("SELECT ROUND(SUM(monto),2) as g FROM gastos WHERE strftime('%Y-%m',fecha)=?",
              (month,), fetchone=True)
    alertas = get_alertas_count()
    fv = q("SELECT COUNT(*) as n FROM facturas_proveedores WHERE fecha_vencimiento <= date('now','+30 days') AND importe > pagado",
           fetchone=True)
    temporada_activa = get_temporada_activa()
    proximas = get_temporadas_proximas(45)
    return {
        'ventas_hoy':          r_hoy['v'] or 0,
        'tickets_hoy':         r_hoy['t'] or 0,
        'ventas_mes':          r_mes['v'] or 0,
        'gastos_mes':          g_mes['g'] or 0,
        'sin_stock':           alertas['sin_stock'],
        'stock_critico':       alertas['critico'],
        'facturas_por_vencer': fv['n'] or 0,
        'temporada_activa':    dict(temporada_activa) if temporada_activa else None,
        'temporadas_proximas': [dict(t) for t in proximas],
    }


# ─── EXPORTACIÓN ─────────────────────────────────────────────────────────────

def get_catalogo_export():
    return q("""
        SELECT p.codigo_interno, p.codigo_barras, p.descripcion, p.categoria,
               p.unidad, p.costo, p.precio_venta, p.iva_porcentaje, p.iva_tipo, p.tags,
               CASE WHEN p.costo>0
                    THEN ROUND((p.precio_venta-p.costo)/p.costo*100,2) ELSE 0
               END as margen_pct,
               COALESCE(s.stock_actual,0) as stock_actual,
               COALESCE(s.stock_minimo,0) as stock_minimo,
               COALESCE(s.stock_maximo,0) as stock_maximo,
               COALESCE(s.proveedor_habitual,'') as proveedor_habitual,
               CASE
                   WHEN COALESCE(s.stock_actual,0)<=0                              THEN 'SIN STOCK'
                   WHEN COALESCE(s.stock_actual,0)<=COALESCE(s.stock_minimo,0)     THEN 'CRITICO'
                   WHEN COALESCE(s.stock_actual,0)<=COALESCE(s.stock_minimo,0)*1.5 THEN 'BAJO'
                   WHEN COALESCE(s.stock_actual,0)>=COALESCE(s.stock_maximo,30)    THEN 'EXCESO'
                   ELSE 'NORMAL'
               END as estado_stock,
               COALESCE(s.stock_actual,0)*p.costo as valor_stock
        FROM productos p
        LEFT JOIN stock s ON s.producto_id=p.id
        WHERE p.activo=1
        ORDER BY p.categoria, p.descripcion
    """)
