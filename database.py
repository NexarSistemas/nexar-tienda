"""
Nexar Tienda — database.py
Conexión, tablas y consultas SQLite.

Basado en Nexar Almacén, adaptado para tienda de regalos:
  - Sistema de licencias RSA + Token Base64 (mismo esquema que Almacén)
  - Categorías propias de tienda (bijouterie, mates, regalos, etc.)
  - Módulo de temporadas (Día de la Madre, Navidad, etc.)
  - Sistema de backups automáticos desde el inicio
"""

import sqlite3
import os
import sys
import hashlib
import json
from datetime import datetime, date, timedelta
from werkzeug.security import check_password_hash, generate_password_hash

# ─── TIER LIMITS (SISTEMA DE LICENCIAS) ──────────────────────────────────────
# Define limites de productos, clientes y proveedores por tipo de licencia
TIER_LIMITS = {
    "DEMO": {
        "productos": None,      # ilimitado por 30 dias
        "clientes": None,
        "proveedores": None,
        "dias_prueba": 30,
        "support": False,
        "updates": False,
        "descripcion": "Periodo de prueba (30 dias)"
    },
    "BASICA": {
        "productos": 200,       # max 200 productos
        "clientes": 100,        # max 100 clientes
        "proveedores": 50,      # max 50 proveedores
        "dias_prueba": None,
        "support": False,
        "updates": False,
        "descripcion": "Licencia Basica permanente"
    },
    "MENSUAL_FULL": {
        "productos": None,      # ilimitado
        "clientes": None,
        "proveedores": None,
        "dias_prueba": None,
        "support": True,
        "updates": True,
        "descripcion": "Mensual Full (actualizaciones y soporte)"
    },
}
TIER_LIMITS["PRO"] = TIER_LIMITS["MENSUAL_FULL"]


def normalize_license_plan(plan: str = None) -> str:
    raw = (plan or "BASICA").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "BASIC": "BASICA",
        "BASICO": "BASICA",
        "TDA_BASICA": "BASICA",
        "FULL": "MENSUAL_FULL",
        "MENSUAL": "MENSUAL_FULL",
        "PRO": "MENSUAL_FULL",
        "TDA_PRO": "MENSUAL_FULL",
    }
    return aliases.get(raw, raw if raw in TIER_LIMITS else "BASICA")

DEFAULT_GASTO_CATEGORIAS = [
    {'nombre': 'Servicios (Luz/Agua/Internet)', 'tipo': 'Necesario'},
    {'nombre': 'Alquiler', 'tipo': 'Necesario'},
    {'nombre': 'Sueldos', 'tipo': 'Necesario'},
    {'nombre': 'Limpieza', 'tipo': 'Necesario'},
    {'nombre': 'Impuestos', 'tipo': 'Necesario'},
    {'nombre': 'Mantenimiento', 'tipo': 'Necesario'},
    {'nombre': 'Otros', 'tipo': 'Prescindible'},
]

# ─── RUTA DE LA BASE DE DATOS ────────────────────────────────────────────────

def _get_app_dir():
    """
    Retorna el directorio base para datos persistentes.
    - En modo congelado (PyInstaller): usa una carpeta de datos del usuario.
      Windows: %APPDATA%\\Nexar Tienda\\
      Linux: ~/.local/share/nexar-tienda/
    - En desarrollo normal: usa la carpeta de este archivo.
    """
    try:
        from services.runtime_config import app_data_dir

        return str(app_data_dir())
    except Exception:
        pass
    if getattr(sys, 'frozen', False):
        if os.name == "nt":
            return os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "Nexar Tienda")
        return os.path.join(os.path.expanduser("~"), ".local", "share", "nexar-tienda")
    return os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(_get_app_dir(), 'tienda.db')


def _restrict_file(path):
    if os.name == "nt":
        return
    try:
        if os.path.exists(path):
            os.chmod(path, 0o600)
    except Exception:
        pass


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
            interes_financiacion REAL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            fecha_apertura TIMESTAMP,
            fecha_cierre TIMESTAMP,
            saldo_inicial REAL,
            saldo_final_real REAL,
            estado INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS caja_movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caja_id INTEGER REFERENCES caja(id) ON DELETE CASCADE,
            tipo TEXT,
            monto REAL,
            motivo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            venta_id INTEGER REFERENCES ventas(id) ON DELETE SET NULL,
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

        CREATE TABLE IF NOT EXISTS productos_temporadas (
            producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE,
            temporada_id INTEGER REFERENCES temporadas(id) ON DELETE CASCADE,
            destacado INTEGER DEFAULT 0,
            PRIMARY KEY (producto_id, temporada_id)
        );

        CREATE TABLE IF NOT EXISTS changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT DEFAULT 'Actualización',
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT
        );

        CREATE TABLE IF NOT EXISTS permisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE NOT NULL,
            descripcion TEXT
        );

        CREATE TABLE IF NOT EXISTS roles_permisos (
            rol_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
            permiso_id INTEGER REFERENCES permisos(id) ON DELETE CASCADE,
            PRIMARY KEY (rol_id, permiso_id)
        );
    """)

    # ─── MIGRACIONES MANUALES (Para bases de datos existentes) ───────────────
    # Verificar y agregar columna 'venta_id' en 'cc_clientes_mov'
    columnas_cc = [r['name'] for r in c.execute("PRAGMA table_info(cc_clientes_mov)").fetchall()]
    if 'venta_id' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN venta_id INTEGER REFERENCES ventas(id) ON DELETE SET NULL")

    # Verificar y agregar columna 'interes_financiacion' en 'ventas' (Paso 15)
    columnas_v = [r['name'] for r in c.execute("PRAGMA table_info(ventas)").fetchall()]
    if 'interes_financiacion' not in columnas_v:
        c.execute("ALTER TABLE ventas ADD COLUMN interes_financiacion REAL DEFAULT 0")

    # Verificar y agregar columnas de recuperación en usuarios
    columnas_u = [r['name'] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if 'security_question' not in columnas_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN security_question TEXT")
    if 'security_answer_hash' not in columnas_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN security_answer_hash TEXT")

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
        ('gastos_categorias', json.dumps(DEFAULT_GASTO_CATEGORIAS, ensure_ascii=False)),
        # ─── SISTEMA DE LICENCIAS RSA ─────────────────────────────────────────
        ('demo_mode', '1'),                 # 1=demo, 0=licencia activa
        ('demo_install_date', ''),          # Fecha de primer arranque (demo)
        ('demo_dias', '30'),                # Dias de prueba gratuita
        ('license_type', 'MONO'),           # Tipo de licencia (TDA_BASICA / TDA_PRO)
        ('license_tier', 'DEMO'),           # Tier: DEMO / BASICA / PRO
        ('license_key', ''),                # Clave de licencia (vacio en DEMO)
        ('license_activated_at', ''),       # Fecha de activacion
        ('license_expires_at', ''),         # Fecha de expiracion (vacio = no vence)
        ('license_last_check', ''),         # Ultimo chequeo exitoso contra Drive
        ('license_max_machines', '1'),      # Maquinas permitidas (siempre 1 en Tienda)
        ('license_drive_index_id', ''),     # ID del index_tienda.json en Google Drive
        ('license_owner_name', ''),         # Nombre titular
        ('license_owner_email', ''),        # Email titular
        ('license_plan', 'DEMO'),           # Plan del token
        ('license_support', '0'),           # 1 = incluye soporte
        ('license_updates', '0'),           # 1 = incluye actualizaciones
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO config VALUES (?,?)", (k, v))

    # ─── DEMO por defecto (sistema RSA) ──────────────────────────────────────
    lic_tier = c.execute("SELECT valor FROM config WHERE clave='license_tier'").fetchone()
    if not lic_tier or not lic_tier['valor']:
        c.execute("INSERT OR REPLACE INTO config VALUES ('license_tier','DEMO')")

    demo_date = c.execute("SELECT valor FROM config WHERE clave='demo_install_date'").fetchone()
    if not demo_date or not demo_date['valor']:
        c.execute(
            "INSERT OR REPLACE INTO config VALUES ('demo_install_date',?)",
            (datetime.now().date().isoformat(),)
        )

    # ─── Generar machine_id ──────────────────────────────────────────────────
    mid = c.execute("SELECT valor FROM config WHERE clave='machine_id'").fetchone()
    if not mid:
        import uuid
        machine_id = str(uuid.uuid4()).replace('-', '').upper()[:16]
        c.execute("INSERT INTO config VALUES ('machine_id',?)", (machine_id,))

    # ─── Roles y Permisos Iniciales (Paso 13) ────────────────────────────────
    roles_data = [
        ('Administrador', 'Acceso total al sistema'),
        ('Encargado', 'Gestión de stock, compras y caja'),
        ('Vendedor', 'Acceso limitado a ventas y búsqueda de productos'),
    ]
    for nombre, desc in roles_data:
        c.execute("INSERT OR IGNORE INTO roles (nombre, descripcion) VALUES (?,?)", (nombre, desc))

    permisos_data = [
        ('dashboard.ver', 'Visualizar el dashboard principal'),
        ('pos.acceso', 'Acceder al punto de venta'),
        ('stock.ver', 'Ver el inventario'),
        ('stock.ajustar', 'Realizar ajustes de stock (Admin/Encargado)'),
        ('reportes.ver', 'Ver reportes de rentabilidad y estadísticas'),
        ('caja.abrir_cerrar', 'Abrir y cerrar la caja diaria'),
        ('gastos.gestionar', 'Registrar y eliminar gastos operativos'),
        ('compras.gestionar', 'Registrar compras a proveedores'),
    ]
    for clave, desc in permisos_data:
        c.execute("INSERT OR IGNORE INTO permisos (clave, descripcion) VALUES (?,?)", (clave, desc))

    # Asignación básica de permisos a Vendedor (ejemplo)
    vendedor_rol = c.execute("SELECT id FROM roles WHERE nombre='Vendedor'").fetchone()
    if vendedor_rol:
        permisos_vendedor = ['pos.acceso', 'stock.ver', 'dashboard.ver']
        for p_clave in permisos_vendedor:
            p_id = c.execute("SELECT id FROM permisos WHERE clave=?", (p_clave,)).fetchone()
            if p_id:
                c.execute("INSERT OR IGNORE INTO roles_permisos (rol_id, permiso_id) VALUES (?,?)", 
                          (vendedor_rol['id'], p_id['id']))

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
    _restrict_file(DB_PATH)


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
        ('1.0.0', '2026-04-07', 'Lanzamiento Oficial',
         'Paso 10: Caja y Liquidación Diaria',
         'Implementación completa de control de caja, movimientos de efectivo, arqueo diario e integración automática con POS.'),
        ('1.1.0', '2026-04-07', 'Nueva función',
         'Paso 11: Gastos Operativos',
         'Registro de gastos operativos con integración a caja diaria y categorización de egresos.'),
        ('1.2.0', '2026-04-07', 'Nueva función',
         'Paso 12: Estadísticas Avanzadas',
         'Dashboard con gráficos interactivos, análisis de rentabilidad y top de productos vendidos.'),
        ('1.3.0', '2026-04-08', 'Nueva función',
         'Paso 13: Gestión de Usuarios y Permisos',
         'Implementación de sistema RBAC, control de accesos granulares y administración de usuarios.'),
        ('1.4.0', '2026-04-09', 'Nueva función',
         'Paso 14: Gestión de Temporadas',
         'CRUD completo de temporadas y vinculación de productos estacionales.'),
        ('1.5.0', '2026-04-10', 'Nueva función',
         'Paso 15: Temporadas - Rutas y CRUD',
         'Implementación completa de las rutas para gestión de temporadas, formularios de edición y filtrado dinámico en el POS.'),
        ('1.6.0', '2026-04-11', 'Nueva función',
         'Paso 16: Módulo de Respaldo (UI)',
         'Panel de gestión de copias de seguridad con opciones de descarga, restauración y configuración de frecuencia.'),
        ('1.7.0', '2026-04-12', 'Nueva función',
         'Paso 17: Configuración del Sistema',
         'Panel para personalizar datos del negocio, comportamiento de tickets y gestión de categorías de productos.'),
        ('1.8.0', '2026-04-13', 'Nueva función',
         'Paso 18: Historial de Ventas',
         'Listado de todas las ventas con filtros de búsqueda, fecha y medio de pago, y detalle para reimpresión de tickets.'),
        ('1.8.1', '2026-04-13', 'Mejora',
         'Clientes: Interfaz y Límite de Crédito',
         'Mejoras en la interfaz de clientes con tarjetas interactivas y columna de límite de crédito.'),
        ('1.9.0', '2026-04-14', 'Nueva función',
         'Paso 19: Estadísticas avanzadas y Análisis',
         'Implementación de dashboard financiero anual, análisis de rentabilidad por producto/categoría y gráficos interactivos.'),
        ('1.10.0', '2026-04-15', 'Nueva función',
         'Paso 20: Exportación de catálogo (Excel y PDF)',
         'Generación de archivos Excel (.xlsx) y listas de precios en PDF para el catálogo de productos.'),
        ('1.11.0', '2026-04-16', 'Nueva función',
         'Paso 21: Páginas Informativas',
         'Implementación de secciones de Ayuda, Changelog y Acerca de para mejorar la experiencia del usuario.'),
        ('1.11.1', '2026-04-16', 'Corrección',
         'Fix: Atributo get_ventas_historial',
         'Corrección de error de atributo faltante en el módulo de base de datos para el historial de ventas.'),
        ('1.12.0', '2026-04-17', 'Nueva función',
         'Paso 22: Apagado controlado',
         'Implementación de cierre seguro del servidor Flask desde la interfaz administrativa.'),
        ('1.12.1', '2026-04-18', 'Mejora',
         'Automatización y Seguridad',
         'Adición de scripts de configuración y aplicación del estándar de seguridad para SECRET_KEY.'),
        ('1.22.0', '2026-04-15', 'Nueva función', 'Gestión Inteligente de Suscripción PRO',
         'Implementación de degradación automática a BÁSICA al vencer PRO y sistema de alertas preventivas (5 días y 1 día antes).'),
        ('1.23.0', '2026-04-15', 'Nueva función', 'Anti-Reinstalación de Demo',
         'Implementación de un mecanismo que persiste la fecha de inicio del período de prueba en un archivo externo (`telemetry.bin`), evitando que el contador de la demo se reinicie al reinstalar la aplicación o eliminar la base de datos.'),
        ('1.24.0', '2026-04-18', 'Nueva función', 'Licencias Supabase y Build Distribuible',
         'Integración del SDK nexar_licencias en builds PyInstaller, soporte de licencias Demo/Básica/Mensual Full con multi-PC, recuperación obligatoria para usuarios nuevos e instalador Windows con aceptación de licencia.'),
        ('1.24.1', '2026-04-18', 'Seguridad', 'Hardening de Seguridad',
         'Protección CSRF centralizada, hash seguro para respuestas de recuperación, permisos restrictivos para archivos locales y restauración de respaldos con validación SQLite y backup previo.'),
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


# ─── LICENCIAS RSA ───────────────────────────────────────────────────────────
#
# Verificacion RSA usando SOLO stdlib Python (base64, hashlib).
# Sin cryptography, sin rsa, sin pyasn1.
# Funciona en cualquier exe PyInstaller sin instalar nada extra.
#
# El token Base64 generado por licensias_fh contiene:
#   { hardware_id, license_key, product:"tienda", tier, type,
#     expires_at, max_machines, public_signature }

import base64 as _base64
import hashlib as _hashlib_rsa


def _get_tienda_pubkey_pem() -> bytes:
    """
    Obtiene la clave publica RSA desde:
      1. Variable de entorno PUBLIC_KEY
      2. keys/public_key.pem  (copiado desde licensias_fh/keys/)
      3. keys/public_key.asc  (nombre alternativo)
      4. public_key.pem / public_key.asc en la raiz del proyecto
    """
    key_str = (os.getenv("PUBLIC_KEY") or "").strip()
    if not key_str:
        base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        possible = [
            os.path.join(base, 'keys', 'public_key.pem'),
            os.path.join(base, 'keys', 'public_key.asc'),
            os.path.join(base, 'public_key.pem'),
            os.path.join(base, 'public_key.asc'),
        ]
        for p in possible:
            if os.path.isfile(p):
                with open(p, 'r', encoding='utf-8') as f:
                    key_str = f.read().strip()
                break
    if not key_str:
        raise RuntimeError(
            "Clave publica no encontrada. "
            "Copia licensias_fh/keys/public_key.pem a nexar-tienda/keys/public_key.pem"
        )
    return key_str.encode('utf-8')


# SHA256 DigestInfo header (RFC 3447 / PKCS1v15)
_TDA_SHA256_HEADER = bytes([
    0x30,0x31,0x30,0x0d,0x06,0x09,0x60,0x86,0x48,0x01,
    0x65,0x03,0x04,0x02,0x01,0x05,0x00,0x04,0x20
])


def _parse_asn1_len(data, pos):
    b = data[pos]; pos += 1
    if b < 0x80:
        return b, pos
    n = b & 0x7f
    return int.from_bytes(data[pos:pos+n], 'big'), pos + n


def _parse_asn1_int(data, pos):
    assert data[pos] == 0x02; pos += 1
    length, pos = _parse_asn1_len(data, pos)
    return int.from_bytes(data[pos:pos+length], 'big'), pos + length


def _load_tda_pubkey():
    """Extrae (n, e) de la clave publica PEM usando solo stdlib."""
    pem   = _get_tienda_pubkey_pem()
    lines = pem.strip().split(b'\n')
    der   = _base64.b64decode(b''.join(l for l in lines if not l.startswith(b'-----')))
    pos = 0
    assert der[pos] == 0x30; pos += 1
    _, pos = _parse_asn1_len(der, pos)
    assert der[pos] == 0x30; pos += 1
    alg_len, pos = _parse_asn1_len(der, pos)
    pos += alg_len
    assert der[pos] == 0x03; pos += 1
    _, pos = _parse_asn1_len(der, pos)
    pos += 1
    assert der[pos] == 0x30; pos += 1
    _, pos = _parse_asn1_len(der, pos)
    n, pos = _parse_asn1_int(der, pos)
    e, _   = _parse_asn1_int(der, pos)
    return n, e


def _tda_rsa_verify(message: bytes, signature: bytes) -> bool:
    """
    Verifica firma PKCS1v15 SHA256 usando solo aritmetica entera.

    Propaga RuntimeError si la clave publica no se encuentra, para que
    validar_licencia_rsa pueda mostrar un mensaje claro en lugar de
    "firma invalida" cuando el problema real es la clave ausente.
    """
    # _load_tda_pubkey() lanza RuntimeError si no encuentra el archivo.
    # Lo dejamos propagar — no lo atrapamos aqui.
    n, e = _load_tda_pubkey()

    try:
        k = (n.bit_length() + 7) // 8
        if len(signature) != k:
            return False
        m = pow(int.from_bytes(signature, 'big'), e, n).to_bytes(k, 'big')
        if m[0] != 0x00 or m[1] != 0x01:
            return False
        sep = m.find(b'\x00', 2)
        if sep < 0 or any(b != 0xFF for b in m[2:sep]):
            return False
        return m[sep+1:] == _TDA_SHA256_HEADER + _hashlib_rsa.sha256(message).digest()
    except Exception:
        return False


def get_machine_id() -> str:
    """Devuelve el machine_id unico de esta instalacion."""
    r = q("SELECT valor FROM config WHERE clave='machine_id'", fetchone=True)
    return r['valor'] if r else 'UNKNOWN'


def is_demo_mode() -> bool:
    """True si la app esta en modo demo."""
    cfg = get_config()
    return cfg.get('demo_mode', '1') == '1'


def get_demo_status() -> dict:
    """Devuelve el estado del periodo de prueba."""
    cfg  = get_config()
    demo = cfg.get('demo_mode', '1') == '1'
    if not demo:
        return {
            'demo': False, 'dias_restantes': 0, 'vencido': False,
            'aviso_proximo': False, 'install_date': '', 'dias_usados': 0,
            'ventas_bloqueado': False, 'productos_bloqueado': False,
        }

    dias_demo   = int(cfg.get('demo_dias', '30'))
    install_str = cfg.get('demo_install_date', '')
    try:
        install_dt = date.fromisoformat(install_str)
    except Exception:
        install_dt = date.today()
        set_config({'demo_install_date': install_dt.isoformat()})

    dias_usados    = (date.today() - install_dt).days
    dias_restantes = max(0, dias_demo - dias_usados)
    vencido        = dias_restantes == 0
    aviso_proximo  = not vencido and dias_restantes <= 7

    return {
        'demo':                demo,
        'install_date':        install_str,
        'dias_usados':         dias_usados,
        'dias_restantes':      dias_restantes,
        'dias_demo':           dias_demo,
        'vencido':             vencido,
        'aviso_proximo':       aviso_proximo,
        'ventas_bloqueado':    vencido,
        'productos_bloqueado': vencido,
        'ventas_pct':          min(100, int(dias_usados / dias_demo * 100)),
    }


def get_license_info() -> dict:
    """Devuelve informacion completa de la licencia actual."""
    cfg = get_config()
    tier = normalize_license_plan(cfg.get('license_tier', 'DEMO'))
    expires_at_str = cfg.get('license_expires_at', '')
    
    # ── Calcular días restantes y alertas para el Plan Mensual Full ──────────
    full_days = None
    if tier == 'MENSUAL_FULL' and expires_at_str:
        try:
            expires_date = date.fromisoformat(expires_at_str)
            full_days = (expires_date - date.today()).days
            
            if full_days < 0:
                tier = 'BASICA' if cfg.get('basica_activada', '0') == '1' else 'DEMO'
        except Exception:
            pass

    limits = TIER_LIMITS.get(tier, TIER_LIMITS["DEMO"])

    return {
        'type':        cfg.get('license_type', 'TDA_BASICA'),
        'tier':        tier,
        'key':         cfg.get('license_key', ''),
        'owner_name':  cfg.get('license_owner_name', ''),
        'owner_email': cfg.get('license_owner_email', ''),
        'plan':        normalize_license_plan(cfg.get('license_plan', tier)),
        'activated_at': cfg.get('license_activated_at', ''),
        'expires_at':  expires_at_str,
        'last_check':  cfg.get('license_last_check', ''),
        'max_machines': int(cfg.get('license_max_machines', '1')),
        'drive_index_id': cfg.get('license_drive_index_id', ''),
        'limits':      limits,
        'demo_mode':   cfg.get('demo_mode', '1'),
        'support':     cfg.get('license_support', '0') == '1' or bool(limits.get('support')),
        'updates':     cfg.get('license_updates', '0') == '1' or bool(limits.get('updates')),
        # Campos de notificación de vencimiento
        'pro_days':    full_days,
        'pro_vencido': full_days is not None and full_days < 0,
        'pro_expires_soon':     full_days == 5,
        'pro_expires_tomorrow': full_days == 1,
        'full_days': full_days,
        'full_vencido': full_days is not None and full_days < 0,
    }


def sync_license_from_remote(license_data: dict):
    """Sincroniza una licencia Supabase/SDK al estado local de la app."""
    if not license_data:
        return

    plan = normalize_license_plan(
        license_data.get('plan') or license_data.get('tier') or license_data.get('license_plan')
    )
    expira = license_data.get('expira') or license_data.get('expires_at') or ''
    if plan == 'BASICA':
        expira = ''

    updates = {
        'demo_mode': '0' if plan != 'DEMO' else '1',
        'license_type': license_data.get('type', plan),
        'license_tier': plan,
        'license_plan': plan,
        'license_key': license_data.get('license_key', ''),
        'license_activated_at': datetime.now().isoformat(),
        'license_expires_at': expira,
        'license_last_check': datetime.now().date().isoformat(),
        'license_max_machines': str(license_data.get('max_devices') or license_data.get('max_machines') or 1),
        'license_support': '1' if license_data.get('support') or TIER_LIMITS[plan].get('support') else '0',
        'license_updates': '1' if license_data.get('updates') or TIER_LIMITS[plan].get('updates') else '0',
    }
    if plan == 'BASICA':
        updates['basica_activada'] = '1'
    set_config(updates)


def validar_licencia_rsa(token_b64: str) -> tuple:
    """
    Valida un token Base64 generado por licensias_fh para Nexar Tienda.

    Retorna: (ok: bool, mensaje: str, data: dict | None)

    El token debe tener:
      product = "tienda"
      hardware_id = machine_id de esta PC
      public_signature = firma RSA hex del payload publico
    """
    try:
        import json as _json
        try:
            data = _json.loads(_base64.b64decode(token_b64.strip()).decode())
        except Exception:
            return False, "El token no es valido. Verifica que lo hayas copiado completo.", None

        if data.get("product") != "tienda":
            return False, "Este token no es una licencia de Nexar Tienda.", None

        sig_hex = data.get("public_signature", "")
        if not sig_hex:
            return False, "El token no contiene firma digital.", None

        try:
            signature = bytes.fromhex(sig_hex)
        except ValueError:
            return False, "La firma digital del token esta corrupta.", None

        # ── Reconstruir payload exactamente igual que el generador ─────────
        #
        # CRÍTICO: estos campos, su orden (sort_keys=True) y los separadores
        # JSON deben coincidir byte a byte con lo que firma create_tienda_license()
        # en license_manager.py.
        #
        # Reglas del generador:
        #   - Usa json.dumps con separadores por defecto: (', ', ': ')
        #   - SIEMPRE incluye expires_at aunque sea None → "expires_at": null
        #     (BASICA tiene None; PRO tiene "YYYY-MM-DD")
        #
        payload_dict = {
            "expires_at":  data.get("expires_at"),   # None → null (BASICA) | "YYYY-MM-DD" (PRO)
            "hardware_id": data["hardware_id"],
            "license_key": data["license_key"],
            "max_machines": data["max_machines"],
            "product":     "tienda",
            "tier":        data.get("tier", "BASICA"),
            "type":        data["type"],
        }

        try:
            payload_bytes = _json.dumps(payload_dict, sort_keys=True).encode()
            verificado = _tda_rsa_verify(payload_bytes, signature)
        except RuntimeError as key_err:
            # La clave pública no se encontró en ninguna ubicación esperada.
            return (
                False,
                f"Clave publica RSA no encontrada.\n"
                f"Detalle: {key_err}\n"
                "Asegurate de que 'keys/public_key.pem' este en la carpeta de la aplicacion.",
                None,
            )

        if not verificado:
            return (
                False,
                "La firma digital es invalida. "
                "El token fue alterado o no corresponde a este sistema.",
                None,
            )

        machine_id = get_machine_id()
        if machine_id != data.get("hardware_id"):
            mid_fmt = f"{machine_id[:4]}-{machine_id[4:8]}-{machine_id[8:12]}-{machine_id[12:]}"
            return (
                False,
                f"Esta licencia no esta autorizada para esta computadora.\n"
                f"Tu ID es: {mid_fmt}\nContacta al desarrollador.",
                None
            )

        return True, "OK", data

    except Exception as ex:
        return False, f"Error al validar la licencia: {ex}", None


def activar_licencia(token_b64: str) -> tuple:
    """
    Valida el token RSA y, si es correcto, activa la licencia en la DB.

    Regla de negocio:
      - TDA_BASICA: activa directamente y marca 'basica_activada' = '1'.
      - TDA_PRO: solo se puede activar si antes se activó BASICA.
        Si BASICA nunca fue activada, devuelve error explicativo.

    Retorna: (ok: bool, mensaje: str)
    """
    ok, msg, data = validar_licencia_rsa(token_b64)
    if not ok:
        return False, msg

    tier = normalize_license_plan(data.get("tier", "BASICA"))

    # ── Regla: Mensual Full requiere BASICA previa en el flujo legacy RSA ────
    if tier == "MENSUAL_FULL":
        cfg = get_config()
        if cfg.get("basica_activada", "0") != "1":
            return (
                False,
                "Para activar la licencia Mensual Full primero debés activar la licencia BÁSICA.\n"
                "Contactá al desarrollador para obtener tu token BÁSICA.",
            )

    expires_at = data.get("expires_at") or ""
    updates = {
        'demo_mode':              '0',
        'license_type':           data.get('type', 'TDA_BASICA'),
        'license_tier':           tier,
        'license_plan':           tier,
        'license_max_machines':   str(data.get('max_machines', 1)),
        'license_key':            data.get('license_key', ''),
        'license_activated_at':   datetime.now().isoformat(),
        'license_expires_at':     expires_at,
        'license_last_check':     datetime.now().date().isoformat(),
    }

    # ── Marcar BASICA como activada (necesario para poder activar PRO luego) ─
    if tier == "BASICA":
        updates['basica_activada'] = '1'

    set_config(updates)
    return True, "Licencia activada correctamente."


def activate_license(tier: str, key: str = '', expires_at: str = ''):
    """Activa una licencia directamente por tier (uso interno/admin)."""
    tier = normalize_license_plan(tier)
    demo_val = '0' if tier != 'DEMO' else '1'
    set_config({
        'demo_mode':            demo_val,
        'license_tier':         tier,
        'license_plan':         tier,
        'license_key':          key,
        'license_activated_at': datetime.now().isoformat(),
        'license_expires_at':   expires_at,
        'license_last_check':   datetime.now().date().isoformat(),
        'license_support':      '1' if TIER_LIMITS[tier].get('support') else '0',
        'license_updates':      '1' if TIER_LIMITS[tier].get('updates') else '0',
    })


def activate_license_token(payload: dict, token: str):
    """Activa licencia usando token RSA Base64 (wrapper para compatibilidad)."""
    # Si viene el token_b64 directamente, usar el flujo RSA
    ok, msg = activar_licencia(token)
    return ok, msg


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
            current_count = q("SELECT COUNT(*) FROM productos WHERE activo=1", fetchone=True)[0]
        elif limit_key == 'clientes':
            current_count = q("SELECT COUNT(*) FROM clientes WHERE activo=1", fetchone=True)[0]
        elif limit_key == 'proveedores':
            current_count = q("SELECT COUNT(*) FROM proveedores WHERE activo=1", fetchone=True)[0]
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


# ─── TICKET AUTOMÁTICO ───────────────────────────────────────────────────────

def next_ticket():
    """Devuelve el próximo número de ticket y lo actualiza en la configuración.
    Asegura que el número de ticket siempre sea mayor que el último registrado en ventas."""
    conn = get_conn()
    c = conn.cursor()

    # Obtener el último número de ticket de la tabla de ventas
    last_sale_ticket = c.execute("SELECT MAX(numero_ticket) as max FROM ventas").fetchone()['max'] or 0

    # Obtener el siguiente número de ticket de la configuración
    cfg_next_ticket = int(c.execute("SELECT valor FROM config WHERE clave='siguiente_ticket'").fetchone()['valor'] or 1001)

    # El próximo ticket debe ser el mayor entre el último de ventas + 1 y el de la configuración
    next_num = max(last_sale_ticket + 1, cfg_next_ticket)

    # Actualizar la configuración para el siguiente ticket
    c.execute("INSERT OR REPLACE INTO config VALUES ('siguiente_ticket', ?)", (str(next_num + 1),))
    conn.commit()
    conn.close()
    return next_num


# ─── CATEGORÍAS ──────────────────────────────────────────────────────────────

def get_categorias():
    """Devuelve lista de categorías activas."""
    return [r['nombre'] for r in q("SELECT nombre FROM categorias WHERE activa=1 ORDER BY nombre")]


def add_categoria(nombre):
    """Agrega una nueva categoría."""
    q("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (nombre,), fetchall=False, commit=True)

def delete_categoria(nombre):
    """Elimina una categoría por nombre."""
    q("DELETE FROM categorias WHERE nombre=?", (nombre,), commit=True)

def get_gasto_categorias():
    """Devuelve lista configurable de categorías de gastos con su tipo."""
    cfg = get_config()
    raw = cfg.get('gastos_categorias', '')
    try:
        categorias = json.loads(raw) if raw else []
    except Exception:
        categorias = []
    if not categorias:
        categorias = DEFAULT_GASTO_CATEGORIAS[:]

    # Normalizar: soporta formato antiguo (lista de strings) y nuevo (lista de dicts)
    normalizadas = []
    keys = set()
    for cat in categorias:
        if isinstance(cat, dict):
            nombre = str(cat.get('nombre', '')).strip()
            tipo = normalizar_tipo_gasto(cat.get('tipo'))
        else:
            nombre = str(cat).strip()
            tipo = 'Necesario'
        if not nombre:
            continue
        key = nombre.lower()
        if key in keys:
            continue
        keys.add(key)
        normalizadas.append({'nombre': nombre, 'tipo': tipo})
    return normalizadas

def set_gasto_categorias(categorias):
    """Guarda la configuración completa de categorías de gastos."""
    limpias = []
    keys = set()
    for cat in categorias:
        if isinstance(cat, dict):
            nombre = str(cat.get('nombre', '')).strip()
            tipo = normalizar_tipo_gasto(cat.get('tipo'))
        else:
            nombre = str(cat).strip()
            tipo = 'Necesario'
        if not nombre:
            continue
        key = nombre.lower()
        if key in keys:
            continue
        keys.add(key)
        limpias.append({'nombre': nombre, 'tipo': tipo})
    if not limpias:
        limpias = DEFAULT_GASTO_CATEGORIAS[:]
    set_config({'gastos_categorias': json.dumps(limpias, ensure_ascii=False)})

def normalizar_tipo_gasto(tipo):
    """Normaliza tipo de gasto a Necesario/Prescindible."""
    txt = str(tipo or '').strip().lower()
    return 'Prescindible' if 'prescind' in txt else 'Necesario'

def get_tipo_gasto_categoria(nombre_categoria):
    """Obtiene el tipo asociado a una categoría de gasto."""
    nombre = (nombre_categoria or '').strip().lower()
    for cat in get_gasto_categorias():
        if cat['nombre'].strip().lower() == nombre:
            return cat['tipo']
    return 'Necesario'

def add_gasto_categoria(nombre, tipo='Necesario'):
    """Agrega una categoría de gastos al listado configurable."""
    categorias = get_gasto_categorias()
    if nombre.strip().lower() not in [c['nombre'].lower() for c in categorias]:
        categorias.append({'nombre': nombre.strip(), 'tipo': normalizar_tipo_gasto(tipo)})
        set_gasto_categorias(categorias)

def delete_gasto_categoria(nombre):
    """Elimina una categoría de gastos del listado configurable."""
    categorias = [c for c in get_gasto_categorias() if c['nombre'].lower() != nombre.strip().lower()]
    set_gasto_categorias(categorias)

def update_gasto_categoria(nombre_actual, nuevo_nombre, tipo='Necesario'):
    """Renombra una categoría de gastos y actualiza registros relacionados."""
    actual = nombre_actual.strip()
    nuevo = nuevo_nombre.strip()
    tipo_normalizado = normalizar_tipo_gasto(tipo)
    categorias = get_gasto_categorias()
    categorias = [
        {'nombre': nuevo, 'tipo': tipo_normalizado} if c['nombre'].lower() == actual.lower() else c
        for c in categorias
    ]
    set_gasto_categorias(categorias)
    q("UPDATE gastos SET categoria=? WHERE LOWER(categoria)=LOWER(?)", (nuevo, actual), commit=True)
    q("UPDATE gastos SET necesario=? WHERE LOWER(categoria)=LOWER(?)", (tipo_normalizado, nuevo), commit=True)


# ─── USUARIOS ────────────────────────────────────────────────────────────────

def get_usuario_by_username(username):
    """Obtiene usuario por username."""
    return q("SELECT * FROM usuarios WHERE username=?", (username,), fetchone=True)


def verify_password(password, password_hash):
    """Verifica contraseña contra hash."""
    if not password_hash:
        return False
    try:
        if password_hash.startswith(("pbkdf2:", "scrypt:")):
            return check_password_hash(password_hash, password)
    except Exception:
        pass
    return hashlib.sha256(password.encode()).hexdigest() == password_hash


def _normalize_security_answer(answer: str) -> str:
    return (answer or "").strip().lower()


def hash_security_answer(answer: str) -> str:
    return generate_password_hash(_normalize_security_answer(answer))


def verify_security_answer(answer: str, answer_hash: str) -> bool:
    if not answer_hash:
        return False
    normalized = _normalize_security_answer(answer)
    try:
        if answer_hash.startswith(("pbkdf2:", "scrypt:")):
            return check_password_hash(answer_hash, normalized)
    except Exception:
        return False
    return hashlib.sha256(normalized.encode()).hexdigest() == answer_hash


def needs_security_answer_rehash(answer_hash: str) -> bool:
    return bool(answer_hash and not answer_hash.startswith(("pbkdf2:", "scrypt:")))


def set_security_answer_hash(uid, answer):
    q(
        "UPDATE usuarios SET security_answer_hash=? WHERE id=?",
        (hash_security_answer(answer), uid),
        commit=True,
    )


def get_usuarios():
    """Devuelve todos los usuarios."""
    return q(
        """SELECT id,username,rol,nombre_completo,activo,security_question,security_answer_hash
        FROM usuarios ORDER BY nombre_completo"""
    )


def add_usuario(username, password, rol, nombre_completo, security_question=None, security_answer=None):
    """Agrega un nuevo usuario."""
    password_hash = generate_password_hash(password)
    ans_hash = None
    if security_answer:
        ans_hash = hash_security_answer(security_answer)
    q(
        """INSERT INTO usuarios (username,password_hash,rol,nombre_completo, security_question, security_answer_hash)
        VALUES (?,?,?,?,?,?)""",
        (username, password_hash, rol, nombre_completo, security_question, ans_hash),
        fetchall=False, commit=True
    )


def count_usuarios():
    """Devuelve la cantidad de usuarios creados."""
    row = q("SELECT COUNT(*) as total FROM usuarios", fetchone=True)
    return int(row["total"] if row else 0)


def count_admins_activos(exclude_uid=None):
    """Cuenta administradores activos, opcionalmente excluyendo un usuario."""
    params = []
    where = "WHERE activo=1 AND rol IN ('Administrador','admin')"
    if exclude_uid is not None:
        where += " AND id<>?"
        params.append(exclude_uid)
    row = q(f"SELECT COUNT(*) as total FROM usuarios {where}", params, fetchone=True)
    return int(row["total"] if row else 0)


def set_password_for_username(username, password):
    """Actualiza la contraseña de un usuario por username."""
    q(
        "UPDATE usuarios SET password_hash=? WHERE username=?",
        (generate_password_hash(password), username),
        commit=True,
    )


def update_usuario(uid, data):
    """Actualiza usuario."""
    updates = ["rol=?", "nombre_completo=?", "activo=?"]
    params = [data.get('rol', 'usuario'), data.get('nombre_completo', ''), int(data.get('activo', 1)), uid]
    q(f"UPDATE usuarios SET {','.join(updates)} WHERE id=?", params, fetchall=False, commit=True)


def set_usuario_activo(uid, activo):
    """Activa o desactiva un usuario."""
    q("UPDATE usuarios SET activo=? WHERE id=?", (1 if activo else 0, uid), commit=True)


def delete_usuario(uid):
    """Elimina definitivamente un usuario."""
    q("DELETE FROM usuarios WHERE id=?", (uid,), commit=True)


def update_perfil(uid, data):
    """Actualiza datos del perfil del propio usuario."""
    sets = ["nombre_completo=?"]
    params = [data.get('nombre_completo', '')]
    
    if data.get('password'):
        sets.append("password_hash=?")
        params.append(generate_password_hash(data['password']))
        
    if data.get('security_question'):
        sets.append("security_question=?")
        params.append(data['security_question'])
        
    if data.get('security_answer'):
        sets.append("security_answer_hash=?")
        params.append(hash_security_answer(data['security_answer']))
        
    params.append(uid)
    q(f"UPDATE usuarios SET {','.join(sets)} WHERE id=?", params, commit=True)


def delete_cliente(cid):
    """Desactiva un cliente sin borrar historial."""
    q("UPDATE clientes SET activo=0 WHERE id=?", (cid,), commit=True)


def delete_proveedor(pid):
    """Desactiva un proveedor sin borrar historial."""
    q("UPDATE proveedores SET activo=0 WHERE id=?", (pid,), commit=True)


def has_permission(role_name, perm_key):
    """Verifica si un rol tiene un permiso específico."""
    # El Administrador (en cualquiera de sus nombres) tiene acceso total
    if role_name in ['Administrador', 'admin']:
        return True
    
    res = q("""
        SELECT 1 FROM roles_permisos rp
        JOIN roles r ON r.id = rp.rol_id
        JOIN permisos p ON p.id = rp.permiso_id
        WHERE r.nombre = ? AND p.clave = ?
    """, (role_name, perm_key), fetchone=True)
    return res is not None


def get_roles():
    """Devuelve todos los roles disponibles."""
    return q("SELECT * FROM roles ORDER BY nombre")


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

def get_clientes(search='', with_debt_only=False, activo_only=True):
    """Devuelve clientes filtrables con soporte para búsqueda y deuda."""
    # 1. Base de la consulta: Incluimos un subquery para calcular el saldo al vuelo
    sql = """
        SELECT *, 
        (SELECT COALESCE(SUM(debe),0) - COALESCE(SUM(haber),0) 
         FROM cc_clientes_mov WHERE cliente_id = clientes.id) as saldo 
        FROM clientes
    """
    conds = []
    params = []

    # 2. Filtro de Activos
    if activo_only:
        conds.append("activo = 1")

    # 3. Filtro de Búsqueda
    if search:
        conds.append("(nombre LIKE ? OR codigo LIKE ? OR dni_cuit LIKE ?)")
        params += [f'%{search}%'] * 3

    # 4. Filtro de Deuda (Solo si el saldo > 0)
    if with_debt_only:
        # Usamos comillas triples para que Python permita varias líneas
        query_saldo = """
            (SELECT COALESCE(SUM(debe),0) - COALESCE(SUM(haber),0) 
             FROM cc_clientes_mov WHERE cliente_id = clientes.id)
        """
        conds.append(f"{query_saldo} > 0")

    # 5. Construcción final
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


def agregar_movimiento_cliente(cid, tipo, numero_comprobante, debe=0, haber=0, vencimiento='', observaciones='', fecha=None, venta_id=None):
    """Agrega un movimiento a la cuenta corriente del cliente."""
    if not fecha:
        fecha = datetime.now().strftime('%Y-%m-%d')
    q(
        """INSERT INTO cc_clientes_mov 
        (cliente_id, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones, venta_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones, venta_id),
        commit=True
    )


def get_historial_ventas_cliente(cid, limit=20):
    """Obtiene historial de ventas de un cliente (una fila por venta con resumen)."""
    return q("""
        SELECT v.*, 
               (SELECT GROUP_CONCAT(descripcion || ' (x' || CAST(cantidad AS INTEGER) || ')', ', ') 
                FROM ventas_detalle WHERE venta_id = v.id) as resumen_articulos
        FROM ventas v
        WHERE v.cliente_id = ?
        ORDER BY v.fecha DESC, v.id DESC
        LIMIT ?
    """, (cid, limit))


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
    proveedor_id = c.lastrowid
    conn.commit()
    conn.close()
    return proveedor_id


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


def get_ventas_historial(search='', fecha_desde='', fecha_hasta='', medio_pago=''):
    """Retorna ventas filtradas por búsqueda, fecha y medio de pago (Paso 18)."""
    params = []
    condiciones = []

    if search:
        # Buscamos por nombre de cliente, número de ticket o ID interno
        condiciones.append("(v.cliente_nombre LIKE ? OR CAST(v.numero_ticket AS TEXT) LIKE ? OR CAST(v.id AS TEXT) LIKE ?)")
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if fecha_desde:
        condiciones.append("v.fecha >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        condiciones.append("v.fecha <= ?")
        params.append(fecha_hasta)
    if medio_pago:
        condiciones.append("v.medio_pago = ?")
        params.append(medio_pago)

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    return q(f"""
        SELECT v.*
        FROM ventas v
        {where}
        ORDER BY v.fecha DESC, v.id DESC
        LIMIT 500
    """, params)


def get_venta_detalle(vid):
    """Devuelve items de una venta."""
    return q("SELECT * FROM ventas_detalle WHERE venta_id=? ORDER BY id", (vid,))


def crear_venta(items, cliente_nombre, medio_pago, descuento_adicional, vendedor, cliente_id=0, temporada='', interes_financiacion=0):
    """Crea una venta con detalle."""
    conn = get_conn()
    c = conn.cursor()

    numero_ticket = next_ticket()
    ahora = datetime.now()
    fecha = ahora.strftime('%Y-%m-%d')
    hora = ahora.strftime('%H:%M:%S')

    subtotal = sum(item.get('subtotal', 0) for item in items)
    total = subtotal - descuento_adicional + interes_financiacion

    c.execute(
        """INSERT INTO ventas
        (numero_ticket,fecha,hora,cliente_id,cliente_nombre,medio_pago,subtotal,descuento_adicional,total,vendedor,temporada,interes_financiacion)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (numero_ticket, fecha, hora, cliente_id, cliente_nombre, medio_pago, subtotal, descuento_adicional, total, vendedor, temporada, interes_financiacion)
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


def get_compra(cid):
    """Devuelve una compra por ID."""
    return q("SELECT * FROM compras WHERE id=?", (cid,), fetchone=True)


def update_compra(cid, data):
    """Actualiza una compra."""
    q(
        """UPDATE compras SET fecha=?,numero_remito=?,proveedor_id=?,proveedor_nombre=?,producto_id=?,codigo_interno=?,descripcion=?,cantidad=?,costo_unitario=?,total=?,observaciones=? WHERE id=?""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('numero_remito', ''),
         data.get('proveedor_id', 0), data.get('proveedor_nombre', ''), data.get('producto_id', 0),
         data.get('codigo_interno', ''), data.get('descripcion', ''), float(data.get('cantidad', 1)),
         float(data.get('costo_unitario', 0)), float(data.get('total', 0)), data.get('observaciones', ''), cid),
        fetchall=False, commit=True
    )


def delete_compra(cid):
    """Elimina una compra."""
    q("DELETE FROM compras WHERE id=?", (cid,), fetchall=False, commit=True)


def incrementar_stock_compra(producto_id, cantidad, compra_id=None):
    """Incrementa stock al registrar una compra."""
    if cantidad <= 0:
        return

    stock_actual = q("SELECT * FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
    if stock_actual:
        nuevo = stock_actual['stock_actual'] + cantidad
        q("UPDATE stock SET stock_actual=? WHERE producto_id=?", (nuevo, producto_id), fetchall=False, commit=True)
    else:
        q(
            "INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo, ultimo_ingreso, proveedor_habitual) VALUES (?,?,?,?,?,?)",
            (producto_id, cantidad, 5, 50, datetime.now().strftime('%Y-%m-%d'), ''),
            fetchall=False, commit=True
        )

    q(
        """INSERT INTO stock_movimientos
        (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo)
        VALUES (?,?,?,?,?,?)""",
        (producto_id, 'COMPRA', cantidad,
         stock_actual['stock_actual'] if stock_actual else 0,
         stock_actual['stock_actual'] + cantidad if stock_actual else cantidad,
         f'Compra #{compra_id}' if compra_id else 'Compra'),
        fetchall=False, commit=True
    )


def add_compra(data):
    """Agrega una compra."""
    compra_id = q(
        """INSERT INTO compras
        (fecha,numero_remito,proveedor_id,proveedor_nombre,producto_id,codigo_interno,descripcion,cantidad,costo_unitario,total,observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('numero_remito', ''),
         data.get('proveedor_id', 0), data.get('proveedor_nombre', ''), data.get('producto_id', 0),
         data.get('codigo_interno', ''), data.get('descripcion', ''), float(data.get('cantidad', 1)),
         float(data.get('costo_unitario', 0)), float(data.get('total', 0)), data.get('observaciones', '')),
        fetchall=False, commit=True
    )

    # Actualizar stock y registrar movimiento de compra
    if data.get('producto_id') and float(data.get('cantidad', 1)) > 0:
        incrementar_stock_compra(int(data.get('producto_id')), float(data.get('cantidad', 1)), compra_id)

    return compra_id


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
    categoria = data.get('categoria', '')
    necesario = normalizar_tipo_gasto(data.get('necesario'))
    if 'necesario' not in data:
        necesario = get_tipo_gasto_categoria(categoria)
    q(
        """INSERT INTO gastos
        (fecha,tipo,categoria,descripcion,monto,iva_incluido,medio_pago,proveedor,necesario,comprobante,observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('tipo', 'Gasto'),
         categoria, data.get('descripcion', ''), float(data.get('monto', 0)),
         int(data.get('iva_incluido', 1)), data.get('medio_pago', 'Efectivo'), data.get('proveedor', ''),
         necesario, data.get('comprobante', ''), data.get('observaciones', '')),
        fetchall=False, commit=True
    )


def update_gasto(gid, data):
    """Actualiza un gasto."""
    categoria = data.get('categoria', '')
    necesario = normalizar_tipo_gasto(data.get('necesario'))
    if 'necesario' not in data:
        necesario = get_tipo_gasto_categoria(categoria)
    q(
        """UPDATE gastos SET fecha=?,tipo=?,categoria=?,descripcion=?,monto=?,iva_incluido=?,
        medio_pago=?,proveedor=?,necesario=?,comprobante=?,observaciones=? WHERE id=?""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('tipo', 'Gasto'),
         categoria, data.get('descripcion', ''), float(data.get('monto', 0)),
         int(data.get('iva_incluido', 1)), data.get('medio_pago', 'Efectivo'), data.get('proveedor', ''),
         necesario, data.get('comprobante', ''), data.get('observaciones', ''), gid),
        commit=True
    )


def delete_gasto(gid):
    """Elimina un gasto."""
    q("DELETE FROM gastos WHERE id=?", (gid,), commit=True)


# ─── TEMPORADAS ──────────────────────────────────────────────────────────────

def get_temporada_actual():
    """Devuelve la temporada actual o None."""
    hoy = date.today().isoformat()
    return q(
        """SELECT * FROM temporadas
        WHERE activa=1 AND fecha_inicio <= ? AND fecha_fin >= ? LIMIT 1""",
        (hoy, hoy), fetchone=True
    )

def get_proxima_temporada():
    """Retorna la próxima temporada programada."""
    hoy = date.today().isoformat()
    return q(
        """SELECT * FROM temporadas 
        WHERE activa=1 AND fecha_inicio > ? 
        ORDER BY fecha_inicio LIMIT 1""",
        (hoy,), fetchone=True
    )

def get_productos_por_temporada(tid):
    """Retorna productos vinculados a una temporada."""
    return q("""
        SELECT p.* FROM productos p
        JOIN productos_temporadas pt ON p.id = pt.producto_id
        WHERE pt.temporada_id = ? AND p.activo = 1
    """, (tid,))

def get_temporadas():
    """Retorna todas las temporadas ordenadas por fecha de inicio."""
    return q("SELECT * FROM temporadas ORDER BY fecha_inicio")

def get_temporada(tid):
    """Retorna una temporada por ID."""
    return q("SELECT * FROM temporadas WHERE id=?", (tid,), fetchone=True)

def add_temporada(data):
    """Crea una temporada."""
    return q("""
        INSERT INTO temporadas (nombre, descripcion, fecha_inicio, fecha_fin, activa)
        VALUES (?, ?, ?, ?, ?)
    """, (data['nombre'], data.get('descripcion', ''), data.get('fecha_inicio'), 
          data.get('fecha_fin'), int(data.get('activa', 1))), commit=True)

def update_temporada(tid, data):
    """Actualiza una temporada."""
    q("""UPDATE temporadas SET nombre=?, descripcion=?, fecha_inicio=?, fecha_fin=?, activa=?
         WHERE id=?""",
      (data['nombre'], data.get('descripcion', ''), data.get('fecha_inicio'), 
       data.get('fecha_fin'), int(data.get('activa', 1)), tid), commit=True)

def delete_temporada(tid):
    """Elimina temporada y relaciones."""
    q("DELETE FROM productos_temporadas WHERE temporada_id=?", (tid,), commit=True)
    q("DELETE FROM temporadas WHERE id=?", (tid,), commit=True)


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


def buscar_productos_pos(search):
    """Busca productos para POS por nombre/código/categoría."""
    sql = """SELECT p.id, p.codigo_interno, p.descripcion, p.categoria, p.unidad,
                    p.precio_venta, s.stock_actual
             FROM productos p
             JOIN stock s ON s.producto_id = p.id
             WHERE p.activo=1""" 
    params = []
    if search:
        sql += " AND (p.descripcion LIKE ? OR p.categoria LIKE ? OR p.codigo_interno LIKE ?)"
        params += [f'%{search}%'] * 3
    sql += " ORDER BY p.descripcion LIMIT 50"
    
    # DEBUG: Descomenta las siguientes líneas para ver la consulta SQL y los parámetros
    # import os
    # if os.environ.get('FLASK_DEBUG') == '1': # Solo imprime si Flask está en modo debug
    #     print(f"DEBUG SQL (buscar_productos_pos): {sql}")
    #     print(f"DEBUG Params (buscar_productos_pos): {params}")
    
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

# ─── REPORTES Y ESTADÍSTICAS (PASO 12) ───────────────────────────────────────

def get_stats_rentabilidad(mes_actual=None):
    """Calcula la rentabilidad: Ingresos - Costos - Gastos."""
    if not mes_actual:
        mes_actual = datetime.now().strftime('%Y-%m')
    
    # Total ventas (bruto)
    ventas = q("SELECT COALESCE(SUM(total), 0) as total FROM ventas WHERE fecha LIKE ?", (f"{mes_actual}%",), fetchone=True)['total']
    
    # Costo de lo vendido (para calcular utilidad bruta)
    # Necesitamos un join con productos para obtener el costo al momento de la venta o el actual
    costo_ventas = q("""
        SELECT COALESCE(SUM(vd.cantidad * p.costo), 0) as total_costo
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        JOIN productos p ON p.id = vd.producto_id
        WHERE v.fecha LIKE ?
    """, (f"{mes_actual}%",), fetchone=True)['total_costo']
    
    # Gastos operativos
    gastos = q("SELECT COALESCE(SUM(monto), 0) as total FROM gastos WHERE fecha LIKE ?", (f"{mes_actual}%",), fetchone=True)['total']
    
    utilidad_neta = ventas - costo_ventas - gastos
    
    return {
        'ingresos': ventas,
        'costo_mercaderia': costo_ventas,
        'gastos_operativos': gastos,
        'utilidad_neta': utilidad_neta
    }

def get_top_productos_vendidos(limit=5):
    """Obtiene los productos más vendidos por cantidad."""
    return q("""
        SELECT descripcion, SUM(cantidad) as total_vendido, SUM(subtotal) as recaudado
        FROM ventas_detalle
        GROUP BY producto_id
        ORDER BY total_vendido DESC
        LIMIT ?
    """, (limit,))

def get_ventas_por_mes(year):
    """Retorna total de ventas y cantidad de tickets por mes para un año dado."""
    rows = q("""
        SELECT strftime('%m', fecha) as mes,
               COUNT(*) as tickets,
               ROUND(SUM(total), 2) as total
        FROM ventas
        WHERE strftime('%Y', fecha) = ?
        GROUP BY mes
    """, (str(year),))
    return {int(r['mes']): dict(r) for r in rows}

def get_ventas_por_semana(semanas=8):
    """Retorna ventas agrupadas por semana para las últimas N semanas."""
    rows = q(f"""
        SELECT strftime('%W/%Y', fecha) as label,
               ROUND(SUM(total), 2) as total,
               COUNT(*) as tickets
        FROM ventas
        WHERE fecha >= date('now', '-{semanas * 7} days')
        GROUP BY label ORDER BY label
    """)
    return [dict(r) for r in rows]

def get_ventas_por_medio_pago(year, mes):
    """Retorna ventas agrupadas por medio de pago para un año y mes."""
    return q("""
        SELECT medio_pago,
               COUNT(*) as cant,
               ROUND(SUM(total), 2) as total
        FROM ventas
        WHERE strftime('%Y', fecha) = ? AND strftime('%m', fecha) = ?
        GROUP BY medio_pago
    """, (str(year), str(mes).zfill(2)))

def get_ventas_por_temporada():
    """Retorna ventas agrupadas por temporada."""
    return q("""
        SELECT temporada as nombre, COUNT(id) as cant, ROUND(SUM(total), 2) as total
        FROM ventas
        WHERE temporada != ''
        GROUP BY temporada ORDER BY total DESC
    """)

def get_ventas_por_categoria():
    """Retorna ventas agrupadas por categoría de producto."""
    return q("""
        SELECT p.categoria, ROUND(SUM(vd.subtotal), 2) as total
        FROM ventas_detalle vd
        JOIN productos p ON vd.producto_id = p.id
        GROUP BY p.categoria ORDER BY total DESC
    """)

def get_top_productos_analisis(limit=15, desde='', hasta=''):
    """Retorna los productos más vendidos en un rango de fechas con rentabilidad."""
    params = []
    condicion = ""
    if desde and hasta:
        condicion = "WHERE v.fecha BETWEEN ? AND ?"
        params = [desde, hasta]
    return q(f"""
        SELECT p.descripcion, p.categoria,
               SUM(vd.cantidad) as unidades,
               ROUND(SUM(vd.subtotal), 2) as total_pesos,
               ROUND(SUM(vd.subtotal - (vd.cantidad * p.costo)), 2) as utilidad
        FROM ventas_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        JOIN productos p ON vd.producto_id = p.id
        {condicion}
        GROUP BY p.id ORDER BY total_pesos DESC LIMIT ?
    """, params + [limit])

def get_bottom_productos(limit=10):
    """Retorna los productos con menor movimiento (activos)."""
    return q("""
        SELECT p.descripcion, p.categoria,
               COALESCE(SUM(vd.cantidad), 0) as unidades
        FROM productos p
        LEFT JOIN ventas_detalle vd ON p.id = vd.producto_id
        WHERE p.activo = 1
        GROUP BY p.id ORDER BY unidades ASC LIMIT ?
    """, (limit,))

def get_rentabilidad_historica():
    """Retorna rentabilidad de los últimos 6 meses."""
    return q("""
        SELECT strftime('%Y-%m', v.fecha) as mes,
               ROUND(SUM(v.total), 2) as ingresos,
               ROUND(SUM(vd.cantidad * p.costo), 2) as costo
        FROM ventas v
        JOIN ventas_detalle vd ON v.id = vd.venta_id
        JOIN productos p ON vd.producto_id = p.id
        WHERE v.fecha >= date('now', '-6 months')
        GROUP BY mes ORDER BY mes
    """)

def get_catalogo_export():
    """Retorna todos los productos activos para exportación."""
    return q("""
        SELECT p.codigo_interno as codigo, p.descripcion, p.categoria, p.precio_venta,
               s.stock_actual, p.activo
        FROM productos p
        JOIN stock s ON p.id = s.producto_id
        ORDER BY p.categoria, p.descripcion
    """)
