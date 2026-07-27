"""
Nexar Tienda â€” database.py
ConexiÃ³n, tablas y consultas SQLite.

Basado en Nexar AlmacÃ©n, adaptado para tienda de regalos:
  - Sistema de licencias RSA + Token Base64 (mismo esquema que AlmacÃ©n)
  - CategorÃ­as propias de tienda (bijouterie, mates, regalos, etc.)
  - MÃ³dulo de temporadas (DÃ­a de la Madre, Navidad, etc.)
  - Sistema de backups automÃ¡ticos desde el inicio
"""

import sqlite3
import os
import hashlib
import json
import unicodedata
from datetime import datetime, date, timedelta
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash

from licensing.planes import PLANES as TIER_MODULES_MAP, normalize_plan
from services.cuentas_corrientes import (
    calcular_estado_factura,
    calcular_deuda_proveedor_desde_facturas,
    calcular_saldo_factura,
    calcular_saldo_cliente_desde_movimientos,
)
from services.rubros import (
    convertir_cantidad_a_base,
    get_categorias_disponibles,
    get_categoria_default,
    get_rubro_actual,
    get_unidad_label,
    get_unidad_interna,
    get_rubros_disponibles,
    es_unidad_fraccionable,
    normalizar_rubro,
    normalizar_unidad,
)
from services.paths import get_database_path

# â”€â”€â”€ TIER LIMITS (SISTEMA DE LICENCIAS) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Define limites de productos, clientes y proveedores por tipo de licencia
TIER_LIMITS = {
    "DEMO": {
        "productos": None,      # ilimitado por 14 dias
        "clientes": None,
        "proveedores": None,
        "dias_prueba": 14,
        "support": False,
        "updates": False,
        "descripcion": "Periodo de prueba (14 dias)"
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
    "PRO": {
        "productos": None,      # ilimitado
        "clientes": None,
        "proveedores": None,
        "dias_prueba": None,
        "support": True,
        "updates": True,
        "descripcion": "Licencia Pro"
    },
    "FULL": {
        "productos": None,      # ilimitado
        "clientes": None,
        "proveedores": None,
        "dias_prueba": None,
        "support": True,
        "updates": True,
        "descripcion": "Licencia Full (actualizaciones y soporte)"
    },
}

DEMO_DEFAULT_DAYS = 14


def normalize_license_plan(plan: str = None) -> str:
    return normalize_plan(plan, default="BASICA")


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "si", "on"}


def _normalize_effective_plan(plan: str | None = None) -> str:
    raw = (plan or "").strip().upper().replace("-", "_").replace(" ", "_")
    if raw == "SIN_PLAN":
        return "SIN_PLAN"
    return normalize_license_plan(raw or "BASICA")


def _is_subscription_plan(plan: str) -> bool:
    return plan in {"PRO", "FULL"}


def _is_blocked_license_status(status: str | None) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {
        "revocada",
        "revocado",
        "suspendida",
        "suspendido",
        "bloqueada",
        "bloqueado",
        "anulada",
        "anulado",
        "cancelada",
        "cancelado",
    }


def _parse_date(value, default: date | None = None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except Exception:
        return default


def _parse_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def calculate_demo_lifecycle(
    *,
    install_date: str | date | None,
    demo_days: str | int | None = DEMO_DEFAULT_DAYS,
    expires_at: str | date | None = None,
    today: str | date | None = None,
) -> dict:
    """
    Calcula el ciclo de DEMO con fechas locales inclusivas.

    Convencion: el dia de activacion cuenta como dia valido. Una DEMO de 14 dias
    iniciada el 2026-01-01 es utilizable hasta el 2026-01-14 inclusive y vence al
    comenzar el 2026-01-15. La fecha `expires_at` es exclusiva.
    """
    current_date = _parse_date(today, date.today()) or date.today()
    started_on = _parse_date(install_date)
    install_was_valid = started_on is not None
    if started_on is None:
        started_on = current_date

    configured_days = _parse_positive_int(demo_days, DEMO_DEFAULT_DAYS)
    configured_expires_on = _parse_date(expires_at)
    if configured_expires_on and configured_expires_on > started_on:
        expires_on = configured_expires_on
        granted_days = max((expires_on - started_on).days, 1)
        expires_was_valid = True
    else:
        expires_on = started_on + timedelta(days=configured_days)
        granted_days = configured_days
        expires_was_valid = False

    elapsed_days = max(0, (current_date - started_on).days)
    remaining_days = max(0, (expires_on - current_date).days)
    expired = current_date >= expires_on
    return {
        "install_date": started_on.isoformat(),
        "expires_at": expires_on.isoformat(),
        "dias_demo": granted_days,
        "dias_usados": elapsed_days,
        "dias_restantes": remaining_days,
        "vencido": expired,
        "aviso_proximo": not expired and remaining_days <= 7,
        "ventas_bloqueado": expired,
        "productos_bloqueado": expired,
        "ventas_pct": min(100, int(elapsed_days / max(granted_days, 1) * 100)),
        "install_date_valid": install_was_valid,
        "expires_at_valid": expires_was_valid,
    }


def _resolve_license_snapshot(cfg: dict | None = None) -> dict:
    cfg = cfg or get_config()
    original_plan = normalize_license_plan(
        cfg.get("license_plan_original")
        or cfg.get("license_plan")
        or cfg.get("license_tier")
        or "DEMO"
    )
    expires_at = cfg.get("license_expires_at", "") or ""
    plan_base_permanente = (
        original_plan == "BASICA"
        or _as_bool(cfg.get("license_plan_base_permanente"))
        or cfg.get("basica_activada", "0") == "1"
    )
    status = cfg.get("license_status", "").strip()
    blocked_status = _is_blocked_license_status(status)
    expired = False
    remaining_days = None
    if original_plan == "BASICA":
        expires_at = ""
    elif _is_subscription_plan(original_plan) and expires_at:
        try:
            expires_date = date.fromisoformat(expires_at)
            remaining_days = (expires_date - date.today()).days
            expired = remaining_days < 0
        except Exception:
            remaining_days = None
            expired = False

    fallback_aplicado = _as_bool(cfg.get("license_fallback_aplicado"))
    effective_plan = _normalize_effective_plan(
        cfg.get("license_effective_plan") or cfg.get("license_tier") or original_plan
    )

    if blocked_status:
        effective_plan = "SIN_PLAN"
        fallback_aplicado = False
        plan_base_permanente = False
    elif expired:
        effective_plan = "SIN_PLAN"
        status = f"{original_plan.lower()}_vencida"
        fallback_aplicado = False
    elif not status:
        status = "activa"

    return {
        "plan_original": original_plan,
        "plan_efectivo": effective_plan,
        "effective_plan": effective_plan,
        "estado": status,
        "fallback_aplicado": fallback_aplicado,
        "plan_base_permanente": plan_base_permanente,
        "expirada": expired,
        "expires_at": expires_at,
        "remaining_days": remaining_days,
    }

DEFAULT_GASTO_CATEGORIAS = [
    {'nombre': 'Servicios (Luz/Agua/Internet)', 'tipo': 'Necesario'},
    {'nombre': 'Alquiler', 'tipo': 'Necesario'},
    {'nombre': 'Sueldos', 'tipo': 'Necesario'},
    {'nombre': 'Limpieza', 'tipo': 'Necesario'},
    {'nombre': 'Impuestos', 'tipo': 'Necesario'},
    {'nombre': 'Mantenimiento', 'tipo': 'Necesario'},
    {'nombre': 'Otros', 'tipo': 'Prescindible'},
]

GASTO_CLASIFICACIONES = ("Operativo", "Impuesto", "Financiero", "Otro")
RUBRO_CONFIG_KEY = "rubro_negocio"
RUBRO_CONFIRMADO_CONFIG_KEY = "rubro_negocio_confirmado"

# â”€â”€â”€ RUTA DE LA BASE DE DATOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DB_PATH = str(get_database_path())


def _restrict_file(path):
    if os.name == "nt":
        return
    try:
        if os.path.exists(path):
            os.chmod(path, 0o600)
    except Exception:
        pass


# â”€â”€â”€ CONEXIÃ“N â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_conn():
    """Devuelve una conexiÃ³n SQLite con Row factory y claves forÃ¡neas activas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def q(sql, params=(), fetchall=True, fetchone=False, commit=False):
    """
    FunciÃ³n Ãºnica para ejecutar consultas SQL.

    Ejemplos:
        q("SELECT * FROM productos")
        q("SELECT * FROM productos WHERE id=?", (1,), fetchone=True)
        q("INSERT INTO ...", (...,), commit=True)  â†’ devuelve lastrowid
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
    """Ejecuta mÃºltiples statements en una transacciÃ³n."""
    conn = get_conn()
    try:
        c = conn.cursor()
        for sql, params in statements:
            c.execute(sql, params)
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


# â”€â”€â”€ INICIALIZACIÃ“N â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_db_initialized = False


def _ensure_table_columns(c, table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {
        row["name"] for row in c.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, definition in columns.items():
        if column_name not in existing_columns:
            c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_arca_directories() -> None:
    data_dir = Path(DB_PATH).resolve().parent
    arca_dir = data_dir / "arca"
    certificados_dir = arca_dir / "certificados"
    keys_dir = arca_dir / "keys"
    for directory in (arca_dir, certificados_dir, keys_dir):
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(directory, 0o700)
            except Exception:
                pass


def _init_arca_tables(c) -> None:
    c.executescript("""
        CREATE TABLE IF NOT EXISTS arca_configuracion (
            id INTEGER PRIMARY KEY,
            cuit TEXT,
            razon_social TEXT,
            nombre_fantasia TEXT DEFAULT '',
            condicion_fiscal TEXT,
            punto_venta INTEGER,
            ambiente TEXT DEFAULT 'homologacion',
            certificado_path TEXT DEFAULT '',
            key_path TEXT DEFAULT '',
            certificado_vencimiento TEXT DEFAULT NULL,
            activo INTEGER DEFAULT 0,
            email TEXT DEFAULT '',
            email_fiscal TEXT DEFAULT '',
            inicio_actividades TEXT DEFAULT '',
            domicilio_fiscal TEXT DEFAULT '',
            ingresos_brutos TEXT DEFAULT '',
            telefono_fiscal TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS arca_certificados (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            ambiente TEXT,
            certificado_path TEXT,
            key_path TEXT,
            activo INTEGER DEFAULT 0,
            cuit TEXT DEFAULT '',
            vencimiento TEXT DEFAULT NULL,
            estado TEXT DEFAULT 'pendiente',
            observaciones TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS arca_comprobantes (
            id INTEGER PRIMARY KEY,
            venta_id INTEGER NULL,
            tipo_comprobante TEXT,
            punto_venta INTEGER,
            numero INTEGER,
            numero_comprobante INTEGER,
            cae TEXT,
            cae_vencimiento TEXT,
            importe_total REAL,
            estado TEXT DEFAULT 'pendiente',
            fecha_emision TEXT DEFAULT '',
            respuesta_raw TEXT DEFAULT '',
            pdf_path TEXT DEFAULT NULL,
            modo TEXT DEFAULT 'wsfe',
            ambiente TEXT DEFAULT 'homologacion',
            total REAL,
            payload_json TEXT,
            respuesta_json TEXT,
            error_mensaje TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS arca_eventos (
            id INTEGER PRIMARY KEY,
            comprobante_id INTEGER NULL,
            nivel TEXT,
            mensaje TEXT,
            detalle_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS arca_wsaa_tickets (
            id INTEGER PRIMARY KEY,
            ambiente TEXT NOT NULL,
            service TEXT NOT NULL,
            token TEXT NOT NULL,
            sign TEXT NOT NULL,
            generation_time TEXT NOT NULL,
            expiration_time TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    _ensure_table_columns(
        c,
        "arca_configuracion",
        {
            "certificado_path": "TEXT DEFAULT ''",
            "key_path": "TEXT DEFAULT ''",
            "certificado_vencimiento": "TEXT DEFAULT NULL",
            "nombre_fantasia": "TEXT DEFAULT ''",
            "email": "TEXT DEFAULT ''",
            "email_fiscal": "TEXT DEFAULT ''",
            "inicio_actividades": "TEXT DEFAULT ''",
            "domicilio_fiscal": "TEXT DEFAULT ''",
            "ingresos_brutos": "TEXT DEFAULT ''",
            "telefono_fiscal": "TEXT DEFAULT ''",
            "updated_by": "TEXT DEFAULT ''",
        },
    )
    _ensure_table_columns(
        c,
        "arca_certificados",
        {
            "cuit": "TEXT DEFAULT ''",
            "vencimiento": "TEXT DEFAULT NULL",
            "estado": "TEXT DEFAULT 'pendiente'",
            "observaciones": "TEXT DEFAULT ''",
        },
    )
    _ensure_table_columns(
        c,
        "arca_comprobantes",
        {
            "numero_comprobante": "INTEGER",
            "importe_total": "REAL",
            "fecha_emision": "TEXT DEFAULT ''",
            "respuesta_raw": "TEXT DEFAULT ''",
            "pdf_path": "TEXT DEFAULT NULL",
            "modo": "TEXT DEFAULT 'wsfe'",
        },
    )
    c.execute(
        """
        UPDATE arca_comprobantes
        SET importe_total = total
        WHERE importe_total IS NULL AND total IS NOT NULL
        """
    )
    c.execute(
        """
        UPDATE arca_comprobantes
        SET numero_comprobante = numero
        WHERE numero_comprobante IS NULL AND numero IS NOT NULL
        """
    )
    c.execute(
        """
        UPDATE arca_comprobantes
        SET numero = numero_comprobante
        WHERE numero IS NULL AND numero_comprobante IS NOT NULL
        """
    )
    c.execute(
        """
        UPDATE arca_comprobantes
        SET modo = CASE
            WHEN LOWER(TRIM(COALESCE(ambiente, ''))) = 'simulacion' THEN 'simulacion'
            ELSE 'wsfe'
        END
        WHERE TRIM(COALESCE(modo, '')) = ''
        """
    )
    c.execute(
        """
        UPDATE arca_configuracion
        SET email_fiscal = COALESCE(NULLIF(TRIM(email_fiscal), ''), TRIM(email))
        WHERE COALESCE(TRIM(email), '') != ''
          AND COALESCE(TRIM(email_fiscal), '') = ''
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_arca_comprobantes_venta_id ON arca_comprobantes(venta_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_arca_comprobantes_estado ON arca_comprobantes(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_arca_comprobantes_numero ON arca_comprobantes(numero_comprobante)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_arca_eventos_comprobante_id ON arca_eventos(comprobante_id)")
    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_arca_wsaa_tickets_lookup
        ON arca_wsaa_tickets(ambiente, service, created_at DESC, id DESC)
        """
    )


def registrar_auditoria(accion, entidad, entidad_id=0, detalle='', motivo='', usuario='', rol=''):
    """Registra una accion critica en la bitacora de auditoria."""
    marca_tiempo = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    return q(
        """INSERT INTO auditoria
        (fecha, usuario, rol, accion, entidad, entidad_id, detalle, motivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            marca_tiempo,
            str(usuario or '').strip(),
            str(rol or '').strip(),
            str(accion or '').strip(),
            str(entidad or '').strip(),
            int(entidad_id or 0),
            str(detalle or '').strip(),
            str(motivo or '').strip(),
        ),
        commit=True,
    )


def get_auditoria(accion='', entidad='', fecha_desde='', fecha_hasta='', limit=300):
    """Devuelve registros de auditoria filtrables para vista de solo lectura."""
    sql = "SELECT * FROM auditoria WHERE 1=1"
    params = []
    if accion:
        sql += " AND accion = ?"
        params.append(str(accion).strip())
    if entidad:
        sql += " AND entidad = ?"
        params.append(str(entidad).strip())
    if fecha_desde:
        sql += " AND substr(fecha, 1, 10) >= ?"
        params.append(str(fecha_desde).strip())
    if fecha_hasta:
        sql += " AND substr(fecha, 1, 10) <= ?"
        params.append(str(fecha_hasta).strip())
    sql += " ORDER BY fecha DESC, id DESC LIMIT ?"
    params.append(int(limit or 300))
    return q(sql, tuple(params))


def get_auditoria_filtros():
    """Devuelve opciones simples para filtros de auditoria."""
    acciones = [row["accion"] for row in q("SELECT DISTINCT accion FROM auditoria WHERE TRIM(COALESCE(accion, '')) != '' ORDER BY accion")]
    entidades = [row["entidad"] for row in q("SELECT DISTINCT entidad FROM auditoria WHERE TRIM(COALESCE(entidad, '')) != '' ORDER BY entidad")]
    return {"acciones": acciones, "entidades": entidades}


def init_db():
    """Inicializa la BD con todas las tablas necesarias para Nexar Tienda."""
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True

    _ensure_arca_directories()
    conn = get_conn()
    c = conn.cursor()
    _init_arca_tables(c)

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
            email TEXT DEFAULT '',
            telefono TEXT DEFAULT '',
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
            imagen TEXT DEFAULT '',
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

        CREATE TABLE IF NOT EXISTS producto_atributos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nombre_normalizado TEXT NOT NULL UNIQUE,
            activo INTEGER DEFAULT 1,
            external_id TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS producto_atributo_valores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atributo_id INTEGER NOT NULL REFERENCES producto_atributos(id) ON DELETE CASCADE,
            valor TEXT NOT NULL,
            valor_normalizado TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            external_id TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (atributo_id, valor_normalizado)
        );

        CREATE TABLE IF NOT EXISTS producto_variantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            combination_key TEXT NOT NULL,
            nombre TEXT DEFAULT '',
            sku TEXT DEFAULT NULL,
            codigo_barras TEXT DEFAULT '',
            costo REAL DEFAULT NULL,
            precio REAL DEFAULT NULL,
            precio_promocional REAL DEFAULT NULL,
            activo INTEGER DEFAULT 1,
            external_id TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (producto_id, combination_key),
            UNIQUE (sku)
        );

        CREATE TABLE IF NOT EXISTS producto_variante_valores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variante_id INTEGER NOT NULL REFERENCES producto_variantes(id) ON DELETE CASCADE,
            atributo_id INTEGER NOT NULL REFERENCES producto_atributos(id) ON DELETE CASCADE,
            valor_id INTEGER NOT NULL REFERENCES producto_atributo_valores(id) ON DELETE RESTRICT,
            UNIQUE (variante_id, atributo_id)
        );

        CREATE TABLE IF NOT EXISTS stock_variantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variante_id INTEGER NOT NULL UNIQUE REFERENCES producto_variantes(id) ON DELETE CASCADE,
            stock_actual REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 5,
            stock_maximo REAL DEFAULT 50,
            ultimo_ingreso TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            temporada TEXT DEFAULT '',
            anulada INTEGER DEFAULT 0,
            anulada_at TEXT DEFAULT '',
            anulada_por TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT ''
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
            costo_unitario REAL,
            iva TEXT DEFAULT '',
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
            observaciones TEXT DEFAULT '',
            anulada INTEGER DEFAULT 0,
            anulada_at TEXT DEFAULT '',
            anulada_por TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT ''
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            gasto_id INTEGER,
            anulado INTEGER DEFAULT 0,
            anulada_at TEXT DEFAULT '',
            anulada_por TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT '',
            movimiento_origen_id INTEGER REFERENCES caja_movimientos(id)
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
            clasificacion TEXT DEFAULT 'Operativo',
            descripcion TEXT DEFAULT '',
            monto REAL DEFAULT 0,
            iva_incluido INTEGER DEFAULT 1,
            medio_pago TEXT DEFAULT 'Efectivo',
            proveedor TEXT DEFAULT '',
            necesario TEXT DEFAULT 'SI (necesario)',
            comprobante TEXT DEFAULT '',
            observaciones TEXT DEFAULT '',
            anulado INTEGER DEFAULT 0,
            anulada_at TEXT DEFAULT '',
            anulada_por TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT ''
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
            medio_pago TEXT DEFAULT '',
            vencimiento TEXT DEFAULT '',
            observaciones TEXT DEFAULT '',
            anulado INTEGER DEFAULT 0,
            anulada_at TEXT DEFAULT '',
            anulada_por TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT '',
            caja_movimiento_id INTEGER REFERENCES caja_movimientos(id) ON DELETE SET NULL,
            movimiento_origen_id INTEGER REFERENCES cc_clientes_mov(id) ON DELETE SET NULL
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
            compra_id INTEGER REFERENCES compras(id) ON DELETE SET NULL,
            numero_factura TEXT DEFAULT '',
            fecha TEXT,
            fecha_vencimiento TEXT,
            importe REAL DEFAULT 0,
            pagado REAL DEFAULT 0,
            observaciones TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            anulada INTEGER DEFAULT 0,
            anulada_at TEXT DEFAULT '',
            anulada_por TEXT DEFAULT '',
            motivo_anulacion TEXT DEFAULT ''
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
            tipo TEXT DEFAULT 'ActualizaciÃ³n',
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT DEFAULT '',
            rol TEXT DEFAULT '',
            accion TEXT DEFAULT '',
            entidad TEXT DEFAULT '',
            entidad_id INTEGER DEFAULT 0,
            detalle TEXT DEFAULT '',
            motivo TEXT DEFAULT ''
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

        CREATE TABLE IF NOT EXISTS license_module_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_tier TEXT UNIQUE NOT NULL,
            modules TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # â”€â”€â”€ MIGRACIONES MANUALES (Para bases de datos existentes) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Verificar y agregar columna 'venta_id' en 'cc_clientes_mov'
    columnas_cc = [r['name'] for r in c.execute("PRAGMA table_info(cc_clientes_mov)").fetchall()]
    if 'venta_id' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN venta_id INTEGER REFERENCES ventas(id) ON DELETE SET NULL")
    if 'medio_pago' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN medio_pago TEXT DEFAULT ''")
    if 'anulado' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN anulado INTEGER DEFAULT 0")
    if 'anulada_at' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN anulada_at TEXT DEFAULT ''")
    if 'anulada_por' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN anulada_por TEXT DEFAULT ''")
    if 'motivo_anulacion' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN motivo_anulacion TEXT DEFAULT ''")
    if 'caja_movimiento_id' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN caja_movimiento_id INTEGER REFERENCES caja_movimientos(id) ON DELETE SET NULL")
    if 'movimiento_origen_id' not in columnas_cc:
        c.execute("ALTER TABLE cc_clientes_mov ADD COLUMN movimiento_origen_id INTEGER REFERENCES cc_clientes_mov(id) ON DELETE SET NULL")

    columnas_facturas = [r['name'] for r in c.execute("PRAGMA table_info(facturas_proveedores)").fetchall()]
    if 'proveedor_id' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN proveedor_id INTEGER")
    if 'compra_id' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN compra_id INTEGER")
    if 'numero_factura' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN numero_factura TEXT DEFAULT ''")
    if 'fecha' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN fecha TEXT")
    if 'fecha_vencimiento' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN fecha_vencimiento TEXT")
    if 'importe' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN importe REAL DEFAULT 0")
    if 'pagado' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN pagado REAL DEFAULT 0")
    if 'observaciones' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN observaciones TEXT DEFAULT ''")
    if 'created_at' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN created_at TEXT DEFAULT ''")
    if 'anulada' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN anulada INTEGER DEFAULT 0")
    if 'anulada_at' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN anulada_at TEXT DEFAULT ''")
    if 'anulada_por' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN anulada_por TEXT DEFAULT ''")
    if 'motivo_anulacion' not in columnas_facturas:
        c.execute("ALTER TABLE facturas_proveedores ADD COLUMN motivo_anulacion TEXT DEFAULT ''")

    columnas_productos = [r['name'] for r in c.execute("PRAGMA table_info(productos)").fetchall()]
    if 'tipo_unidad' not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN tipo_unidad TEXT DEFAULT 'unidad'")
    if 'permite_fraccionado' not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN permite_fraccionado INTEGER DEFAULT 0")
    if 'rubro' not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN rubro TEXT DEFAULT NULL")
        c.execute(
            """UPDATE facturas_proveedores
            SET created_at = COALESCE(NULLIF(fecha, ''), DATE('now'))
            WHERE COALESCE(created_at, '') = ''"""
        )
    if 'imagen' not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen TEXT DEFAULT ''")
    c.execute("CREATE INDEX IF NOT EXISTS idx_facturas_proveedores_compra_id ON facturas_proveedores(compra_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_atributo_valores_atributo ON producto_atributo_valores(atributo_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_variantes_producto ON producto_variantes(producto_id)")
    duplicate_product_barcodes = c.execute(
        """
        SELECT TRIM(COALESCE(codigo_barras, '')) AS codigo, COUNT(*) AS total
        FROM productos
        WHERE TRIM(COALESCE(codigo_barras, '')) <> ''
        GROUP BY TRIM(COALESCE(codigo_barras, ''))
        HAVING COUNT(*) > 1
        ORDER BY codigo
        LIMIT 3
        """
    ).fetchall()
    if duplicate_product_barcodes:
        codigos = ", ".join(row["codigo"] for row in duplicate_product_barcodes)
        conn.close()
        raise RuntimeError(
            f"No se pudo aplicar la unicidad de codigo_barras en productos. Existen duplicados previos: {codigos}."
        )
    duplicate_variant_barcodes = c.execute(
        """
        SELECT TRIM(COALESCE(codigo_barras, '')) AS codigo, COUNT(*) AS total
        FROM producto_variantes
        WHERE TRIM(COALESCE(codigo_barras, '')) <> ''
        GROUP BY TRIM(COALESCE(codigo_barras, ''))
        HAVING COUNT(*) > 1
        ORDER BY codigo
        LIMIT 3
        """
    ).fetchall()
    if duplicate_variant_barcodes:
        codigos = ", ".join(row["codigo"] for row in duplicate_variant_barcodes)
        conn.close()
        raise RuntimeError(
            f"No se pudo aplicar la unicidad de codigo_barras en variantes. Existen duplicados previos: {codigos}."
        )
    duplicate_catalog_barcodes = c.execute(
        """
        SELECT p.codigo
        FROM (
            SELECT TRIM(COALESCE(codigo_barras, '')) AS codigo
            FROM productos
            WHERE TRIM(COALESCE(codigo_barras, '')) <> ''
        ) p
        INNER JOIN (
            SELECT TRIM(COALESCE(codigo_barras, '')) AS codigo
            FROM producto_variantes
            WHERE TRIM(COALESCE(codigo_barras, '')) <> ''
        ) v ON v.codigo = p.codigo
        ORDER BY p.codigo
        LIMIT 3
        """
    ).fetchall()
    if duplicate_catalog_barcodes:
        codigos = ", ".join(row["codigo"] for row in duplicate_catalog_barcodes)
        conn.close()
        raise RuntimeError(
            f"Se detectaron codigo_barras compartidos entre productos y variantes: {codigos}."
        )
    c.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_productos_codigo_barras_unique
        ON productos(codigo_barras)
        WHERE codigo_barras IS NOT NULL AND TRIM(codigo_barras) <> ''
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_variantes_codigo_barras ON producto_variantes(codigo_barras)")
    c.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_producto_variantes_codigo_barras_unique
        ON producto_variantes(codigo_barras)
        WHERE codigo_barras IS NOT NULL AND TRIM(codigo_barras) <> ''
        """
    )
    c.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_productos_codigo_barras_insert
        BEFORE INSERT ON productos
        FOR EACH ROW
        WHEN TRIM(COALESCE(NEW.codigo_barras, '')) <> ''
             AND EXISTS (
                 SELECT 1
                 FROM producto_variantes
                 WHERE TRIM(COALESCE(codigo_barras, '')) = TRIM(COALESCE(NEW.codigo_barras, ''))
             )
        BEGIN
            SELECT RAISE(ABORT, 'El codigo de barras ya existe en una variante.');
        END
        """
    )
    c.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_productos_codigo_barras_update
        BEFORE UPDATE OF codigo_barras ON productos
        FOR EACH ROW
        WHEN TRIM(COALESCE(NEW.codigo_barras, '')) <> ''
             AND EXISTS (
                 SELECT 1
                 FROM producto_variantes
                 WHERE TRIM(COALESCE(codigo_barras, '')) = TRIM(COALESCE(NEW.codigo_barras, ''))
             )
        BEGIN
            SELECT RAISE(ABORT, 'El codigo de barras ya existe en una variante.');
        END
        """
    )
    c.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_producto_variantes_codigo_barras_insert
        BEFORE INSERT ON producto_variantes
        FOR EACH ROW
        WHEN TRIM(COALESCE(NEW.codigo_barras, '')) <> ''
             AND EXISTS (
                 SELECT 1
                 FROM productos
                 WHERE TRIM(COALESCE(codigo_barras, '')) = TRIM(COALESCE(NEW.codigo_barras, ''))
             )
        BEGIN
            SELECT RAISE(ABORT, 'El codigo de barras ya existe en un producto.');
        END
        """
    )
    c.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_producto_variantes_codigo_barras_update
        BEFORE UPDATE OF codigo_barras ON producto_variantes
        FOR EACH ROW
        WHEN TRIM(COALESCE(NEW.codigo_barras, '')) <> ''
             AND EXISTS (
                 SELECT 1
                 FROM productos
                 WHERE TRIM(COALESCE(codigo_barras, '')) = TRIM(COALESCE(NEW.codigo_barras, ''))
             )
        BEGIN
            SELECT RAISE(ABORT, 'El codigo de barras ya existe en un producto.');
        END
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_variante_valores_variante ON producto_variante_valores(variante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_variante_valores_valor ON producto_variante_valores(valor_id)")

    # Verificar y agregar columna 'interes_financiacion' en 'ventas' (Paso 15)
    columnas_v = [r['name'] for r in c.execute("PRAGMA table_info(ventas)").fetchall()]
    if 'interes_financiacion' not in columnas_v:
        c.execute("ALTER TABLE ventas ADD COLUMN interes_financiacion REAL DEFAULT 0")
    if 'anulada' not in columnas_v:
        c.execute("ALTER TABLE ventas ADD COLUMN anulada INTEGER DEFAULT 0")
    if 'anulada_at' not in columnas_v:
        c.execute("ALTER TABLE ventas ADD COLUMN anulada_at TEXT DEFAULT ''")
    if 'anulada_por' not in columnas_v:
        c.execute("ALTER TABLE ventas ADD COLUMN anulada_por TEXT DEFAULT ''")
    if 'motivo_anulacion' not in columnas_v:
        c.execute("ALTER TABLE ventas ADD COLUMN motivo_anulacion TEXT DEFAULT ''")

    columnas_vd = [r['name'] for r in c.execute("PRAGMA table_info(ventas_detalle)").fetchall()]
    if 'costo_unitario' not in columnas_vd:
        c.execute("ALTER TABLE ventas_detalle ADD COLUMN costo_unitario REAL")
        c.execute(
            """UPDATE ventas_detalle
            SET costo_unitario = (
                SELECT p.costo FROM productos p WHERE p.id = ventas_detalle.producto_id
            )
            WHERE producto_id > 0"""
        )
    if 'iva' not in columnas_vd:
        c.execute("ALTER TABLE ventas_detalle ADD COLUMN iva TEXT DEFAULT ''")
        c.execute(
            """UPDATE ventas_detalle
            SET iva = COALESCE((
                SELECT p.iva FROM productos p WHERE p.id = ventas_detalle.producto_id
            ), '')
            WHERE producto_id > 0"""
        )

    columnas_compras = [r['name'] for r in c.execute("PRAGMA table_info(compras)").fetchall()]
    if 'anulada' not in columnas_compras:
        c.execute("ALTER TABLE compras ADD COLUMN anulada INTEGER DEFAULT 0")
    if 'anulada_at' not in columnas_compras:
        c.execute("ALTER TABLE compras ADD COLUMN anulada_at TEXT DEFAULT ''")
    if 'anulada_por' not in columnas_compras:
        c.execute("ALTER TABLE compras ADD COLUMN anulada_por TEXT DEFAULT ''")
    if 'motivo_anulacion' not in columnas_compras:
        c.execute("ALTER TABLE compras ADD COLUMN motivo_anulacion TEXT DEFAULT ''")

    # Verificar y agregar columnas de recuperaciÃ³n en usuarios
    columnas_u = [r['name'] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if 'security_question' not in columnas_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN security_question TEXT")
    if 'security_answer_hash' not in columnas_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN security_answer_hash TEXT")
    if 'email' not in columnas_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN email TEXT DEFAULT ''")
    if 'telefono' not in columnas_u:
        c.execute("ALTER TABLE usuarios ADD COLUMN telefono TEXT DEFAULT ''")
    columnas_cm = [r['name'] for r in c.execute("PRAGMA table_info(caja_movimientos)").fetchall()]
    if 'gasto_id' not in columnas_cm:
        c.execute("ALTER TABLE caja_movimientos ADD COLUMN gasto_id INTEGER")
    if 'anulado' not in columnas_cm:
        c.execute("ALTER TABLE caja_movimientos ADD COLUMN anulado INTEGER DEFAULT 0")
    if 'anulada_at' not in columnas_cm:
        c.execute("ALTER TABLE caja_movimientos ADD COLUMN anulada_at TEXT DEFAULT ''")
    if 'anulada_por' not in columnas_cm:
        c.execute("ALTER TABLE caja_movimientos ADD COLUMN anulada_por TEXT DEFAULT ''")
    if 'motivo_anulacion' not in columnas_cm:
        c.execute("ALTER TABLE caja_movimientos ADD COLUMN motivo_anulacion TEXT DEFAULT ''")
    if 'movimiento_origen_id' not in columnas_cm:
        c.execute("ALTER TABLE caja_movimientos ADD COLUMN movimiento_origen_id INTEGER REFERENCES caja_movimientos(id)")

    columnas_g = [r['name'] for r in c.execute("PRAGMA table_info(gastos)").fetchall()]
    if 'clasificacion' not in columnas_g:
        c.execute("ALTER TABLE gastos ADD COLUMN clasificacion TEXT DEFAULT 'Operativo'")
        c.execute(
            """UPDATE gastos
            SET clasificacion = CASE
                WHEN LOWER(categoria) LIKE '%impuesto%' OR LOWER(descripcion) LIKE '%impuesto%' THEN 'Impuesto'
                ELSE 'Operativo'
            END"""
        )
    if 'anulado' not in columnas_g:
        c.execute("ALTER TABLE gastos ADD COLUMN anulado INTEGER DEFAULT 0")
    if 'anulada_at' not in columnas_g:
        c.execute("ALTER TABLE gastos ADD COLUMN anulada_at TEXT DEFAULT ''")
    if 'anulada_por' not in columnas_g:
        c.execute("ALTER TABLE gastos ADD COLUMN anulada_por TEXT DEFAULT ''")
    if 'motivo_anulacion' not in columnas_g:
        c.execute("ALTER TABLE gastos ADD COLUMN motivo_anulacion TEXT DEFAULT ''")

    # â”€â”€â”€ ConfiguraciÃ³n por defecto â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    defaults = [
        ('nombre_negocio', 'Mi Tienda'),
        ('direccion', ''),
        ('localidad', ''),
        ('provincia', ''),
        ('telefono', ''),
        ('negocio_email', ''),
        ('cuit', ''),
        ('responsable', ''),
        ('margen_minimo', '0.20'),
        ('margen_objetivo', '0.35'),
        ('dias_alerta_proveedor', '30'),
        ('dias_alerta_cliente', '15'),
        ('siguiente_ticket', '1001'),
        ('siguiente_codigo', '1'),
        ('siguiente_codigo_barras_interno', '1'),
        ('backup_intervalo_h', '24'),
        ('backup_keep', '10'),
        ('backup_dir', ''),
        ('backup_ultimo', ''),
        (RUBRO_CONFIG_KEY, ''),
        (RUBRO_CONFIRMADO_CONFIG_KEY, '0'),
        ('gastos_categorias', json.dumps(DEFAULT_GASTO_CATEGORIAS, ensure_ascii=False)),
        # â”€â”€â”€ SISTEMA DE LICENCIAS RSA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        ('demo_mode', '1'),                 # 1=demo, 0=licencia activa
        ('demo_install_date', ''),          # Fecha de primer arranque (demo)
        ('demo_dias', '14'),                # Dias de prueba gratuita
        ('demo_expires_at', ''),            # Fecha exclusiva de vencimiento demo
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
        ('license_owner_phone', ''),        # Telefono titular
        ('license_vendor_code', ''),        # Codigo de vendedor opcional
        ('license_recovery_word', ''),      # Palabra de recuperacion local
        ('license_terms_accepted_at', ''),  # Aceptacion de terminos
        ('license_marketing_opt_in', '0'),  # Preferencia comercial opcional
        ('license_plan', 'DEMO'),           # Plan del token
        ('license_support', '0'),           # 1 = incluye soporte
        ('license_updates', '0'),           # 1 = incluye actualizaciones
        ('license_modules', '[]'),          # Modulos remotos sincronizados desde SDK
        ('activation_initial_completed', '1'),
        ('activation_initial_plan', ''),
        ('activation_checkout_status', ''),
        ('activation_checkout_plan', ''),
        ('activation_checkout_activation_id', ''),
        ('activation_checkout_started_at', ''),
        ('activation_checkout_checked_at', ''),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO config VALUES (?,?)", (k, v))

    # â”€â”€â”€ DEMO por defecto (sistema RSA) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    lic_tier = c.execute("SELECT valor FROM config WHERE clave='license_tier'").fetchone()
    if not lic_tier or not lic_tier['valor']:
        c.execute("INSERT OR REPLACE INTO config VALUES ('license_tier','DEMO')")

    demo_date = c.execute("SELECT valor FROM config WHERE clave='demo_install_date'").fetchone()
    if not demo_date or not demo_date['valor']:
        c.execute(
            "INSERT OR REPLACE INTO config VALUES ('demo_install_date',?)",
            (datetime.now().date().isoformat(),)
        )

    # â”€â”€â”€ Generar machine_id â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    mid = c.execute("SELECT valor FROM config WHERE clave='machine_id'").fetchone()
    if not mid:
        import uuid
        machine_id = str(uuid.uuid4()).replace('-', '').upper()[:16]
        c.execute("INSERT INTO config VALUES ('machine_id',?)", (machine_id,))

    # â”€â”€â”€ Roles y Permisos Iniciales (Paso 13) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    roles_data = [
        ('Administrador', 'Acceso total al sistema'),
        ('Encargado', 'GestiÃ³n de stock, compras y caja'),
        ('Vendedor', 'Acceso limitado a ventas y bÃºsqueda de productos'),
    ]
    for nombre, desc in roles_data:
        c.execute("INSERT OR IGNORE INTO roles (nombre, descripcion) VALUES (?,?)", (nombre, desc))

    permisos_data = [
        ('dashboard.ver', 'Visualizar el dashboard principal'),
        ('pos.acceso', 'Acceder al punto de venta'),
        ('stock.ver', 'Ver el inventario'),
        ('stock.ajustar', 'Realizar ajustes de stock (Admin/Encargado)'),
        ('reportes.ver', 'Ver reportes de rentabilidad y estadÃ­sticas'),
        ('caja.abrir_cerrar', 'Abrir y cerrar la caja diaria'),
        ('gastos.gestionar', 'Registrar y eliminar gastos operativos'),
        ('compras.gestionar', 'Registrar compras a proveedores'),
    ]
    for clave, desc in permisos_data:
        c.execute("INSERT OR IGNORE INTO permisos (clave, descripcion) VALUES (?,?)", (clave, desc))

    # AsignaciÃ³n bÃ¡sica de permisos a Vendedor (ejemplo)
    vendedor_rol = c.execute("SELECT id FROM roles WHERE nombre='Vendedor'").fetchone()
    if vendedor_rol:
        permisos_vendedor = ['pos.acceso', 'stock.ver', 'dashboard.ver']
        for p_clave in permisos_vendedor:
            p_id = c.execute("SELECT id FROM permisos WHERE clave=?", (p_clave,)).fetchone()
            if p_id:
                c.execute("INSERT OR IGNORE INTO roles_permisos (rol_id, permiso_id) VALUES (?,?)",
                          (vendedor_rol['id'], p_id['id']))

    # â”€â”€â”€ CategorÃ­as iniciales de tienda â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    cats = [
        'Bijouterie',
        'Mates y Termos',
        'Regalos Diversos',
        'Adornos',
        'Accesorios',
        'Productos de Temporada',
        'Navidad',
        'DÃ­a de la Madre',
        'DÃ­a del Padre',
        'Otros',
    ]
    for cat in cats:
        c.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (cat,))

    # â”€â”€â”€ Temporadas iniciales â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    seasons = [
        ('Navidad', 'Adornos y regalos navideÃ±os', '2026-11-01', '2026-12-31'),
        ('DÃ­a de la Madre', 'Especiales para mamÃ¡', '2026-10-01', '2026-10-31'),
        ('DÃ­a del Padre', 'Especiales para papÃ¡', '2026-06-01', '2026-06-30'),
        ('AÃ±o Nuevo', 'Regalos y accesorios aÃ±o nuevo', '2026-12-20', '2027-01-31'),
    ]
    for nombre, desc, inicio, fin in seasons:
        c.execute(
            "INSERT OR IGNORE INTO temporadas (nombre,descripcion,fecha_inicio,fecha_fin) VALUES (?,?,?,?)",
            (nombre, desc, inicio, fin)
        )

    # â”€â”€â”€ Mapeo de Tiers a MÃ³dulos (para integraciÃ³n modular) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tier_modules_map = [
        (tier, json.dumps(sorted(modules)))
        for tier, modules in TIER_MODULES_MAP.items()
    ]
    for tier, modules_json in tier_modules_map:
        c.execute(
            "INSERT OR IGNORE INTO license_module_map (license_tier, modules) VALUES (?,?)",
            (tier, modules_json)
        )

    _seed_changelog(c)

    # â”€â”€â”€ Reparar stock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    c.execute("""
        INSERT OR IGNORE INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo)
        SELECT id, 0, 5, 50 FROM productos
        WHERE activo=1
        AND id NOT IN (SELECT producto_id FROM stock)
    """)

    conn.commit()

    auditoria_columns = [row["name"] for row in c.execute("PRAGMA table_info(auditoria)").fetchall()]
    if "rol" not in auditoria_columns:
        c.execute("ALTER TABLE auditoria ADD COLUMN rol TEXT DEFAULT ''")
        conn.commit()
    conn.close()
    _restrict_file(DB_PATH)


def _seed_changelog(c):
    """Inserta el historial de versiones inicial."""
    existing = c.execute("SELECT COUNT(*) FROM changelog").fetchone()[0]
    if existing > 0:
        return

    entries = [
        ('0.1.0', '2026-03-29', 'Nueva funciÃ³n',
         'Estructura base de Nexar Tienda',
         'Proyecto inicial basado en Nexar AlmacÃ©n adaptado para tienda de regalos.'),
        ('0.1.1', '2026-03-29', 'Nueva funciÃ³n',
         'MÃ³dulos completos y sistema de backups',
         'Se agregaron todas las tablas: Productos, Stock, Ventas, Clientes, Proveedores, Caja, Gastos, Temporadas. Sistema de backups automÃ¡ticos.'),
        ('1.0.0', '2026-04-07', 'Lanzamiento Oficial',
         'Paso 10: Caja y LiquidaciÃ³n Diaria',
         'ImplementaciÃ³n completa de control de caja, movimientos de efectivo, arqueo diario e integraciÃ³n automÃ¡tica con POS.'),
        ('1.1.0', '2026-04-07', 'Nueva funciÃ³n',
         'Paso 11: Gastos Operativos',
         'Registro de gastos operativos con integraciÃ³n a caja diaria y categorizaciÃ³n de egresos.'),
        ('1.2.0', '2026-04-07', 'Nueva funciÃ³n',
         'Paso 12: Estadísticas Avanzadas',
         'Dashboard con grÃ¡ficos interactivos, anÃ¡lisis de rentabilidad y top de productos vendidos.'),
        ('1.3.0', '2026-04-08', 'Nueva funciÃ³n',
         'Paso 13: GestiÃ³n de Usuarios y Permisos',
         'ImplementaciÃ³n de sistema RBAC, control de accesos granulares y administraciÃ³n de usuarios.'),
        ('1.4.0', '2026-04-09', 'Nueva funciÃ³n',
         'Paso 14: GestiÃ³n de Temporadas',
         'CRUD completo de temporadas y vinculaciÃ³n de productos estacionales.'),
        ('1.5.0', '2026-04-10', 'Nueva funciÃ³n',
         'Paso 15: Temporadas - Rutas y CRUD',
         'ImplementaciÃ³n completa de las rutas para gestiÃ³n de temporadas, formularios de ediciÃ³n y filtrado dinÃ¡mico en el POS.'),
        ('1.6.0', '2026-04-11', 'Nueva funciÃ³n',
         'Paso 16: MÃ³dulo de Respaldo (UI)',
         'Panel de gestiÃ³n de copias de seguridad con opciones de descarga, restauraciÃ³n y configuraciÃ³n de frecuencia.'),
        ('1.7.0', '2026-04-12', 'Nueva funciÃ³n',
         'Paso 17: ConfiguraciÃ³n del Sistema',
         'Panel para personalizar datos del negocio, comportamiento de tickets y gestiÃ³n de categorÃ­as de productos.'),
        ('1.8.0', '2026-04-13', 'Nueva funciÃ³n',
         'Paso 18: Historial de Ventas',
         'Listado de todas las ventas con filtros de bÃºsqueda, fecha y medio de pago, y detalle para reimpresiÃ³n de tickets.'),
        ('1.8.1', '2026-04-13', 'Mejora',
         'Clientes: Interfaz y Límite de Crédito',
         'Mejoras en la interfaz de clientes con tarjetas interactivas y columna de lÃ­mite de crÃ©dito.'),
        ('1.9.0', '2026-04-14', 'Nueva funciÃ³n',
         'Paso 19: Estadísticas avanzadas y AnÃ¡lisis',
         'ImplementaciÃ³n de dashboard financiero anual, anÃ¡lisis de rentabilidad por producto/categorÃ­a y grÃ¡ficos interactivos.'),
        ('1.10.0', '2026-04-15', 'Nueva funciÃ³n',
         'Paso 20: ExportaciÃ³n de catÃ¡logo (Excel y PDF)',
         'GeneraciÃ³n de archivos Excel (.xlsx) y listas de precios en PDF para el catÃ¡logo de productos.'),
        ('1.11.0', '2026-04-16', 'Nueva funciÃ³n',
         'Paso 21: PÃ¡ginas Informativas',
         'ImplementaciÃ³n de secciones de Ayuda, Changelog y Acerca de para mejorar la experiencia del usuario.'),
        ('1.11.1', '2026-04-16', 'CorrecciÃ³n',
         'Fix: Atributo get_ventas_historial',
         'CorrecciÃ³n de error de atributo faltante en el mÃ³dulo de base de datos para el historial de ventas.'),
        ('1.12.0', '2026-04-17', 'Nueva funciÃ³n',
         'Paso 22: Apagado controlado',
         'ImplementaciÃ³n de cierre seguro del servidor Flask desde la interfaz administrativa.'),
        ('1.12.1', '2026-04-18', 'Mejora',
         'AutomatizaciÃ³n y Seguridad',
         'AdiciÃ³n de scripts de configuraciÃ³n y aplicaciÃ³n del estÃ¡ndar de seguridad para SECRET_KEY.'),
        ('1.22.0', '2026-04-15', 'Nueva funciÃ³n', 'GestiÃ³n Inteligente de SuscripciÃ³n PRO',
         'ImplementaciÃ³n de degradaciÃ³n automÃ¡tica a BÃSICA al vencer PRO y sistema de alertas preventivas (5 dÃ­as y 1 dÃ­a antes).'),
        ('1.23.0', '2026-04-15', 'Nueva funciÃ³n', 'Anti-ReinstalaciÃ³n de Demo',
         'ImplementaciÃ³n de un mecanismo que persiste la fecha de inicio del perÃ­odo de prueba en un archivo externo (`telemetry.bin`), evitando que el contador de la demo se reinicie al reinstalar la aplicaciÃ³n o eliminar la base de datos.'),
        ('1.24.0', '2026-04-18', 'Nueva funciÃ³n', 'Licencias Supabase y Build Distribuible',
         'IntegraciÃ³n del SDK nexar_licencias en builds PyInstaller, soporte de licencias Demo/BÃ¡sica/Mensual Full con multi-PC, recuperaciÃ³n obligatoria para usuarios nuevos e instalador Windows con aceptaciÃ³n de licencia.'),
        ('1.24.1', '2026-04-18', 'Seguridad', 'Hardening de Seguridad',
         'ProtecciÃ³n CSRF centralizada, hash seguro para respuestas de recuperaciÃ³n, permisos restrictivos para archivos locales y restauraciÃ³n de respaldos con validaciÃ³n SQLite y backup previo.'),
    ]
    for ver, fecha, tipo, titulo, desc in entries:
        c.execute(
            "INSERT INTO changelog (version,fecha,tipo,titulo,descripcion) VALUES (?,?,?,?,?)",
            (ver, fecha, tipo, titulo, desc)
        )


# â”€â”€â”€ CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_config():
    """Devuelve dict con toda la configuraciÃ³n."""
    rows = q("SELECT clave, valor FROM config")
    return {r['clave']: r['valor'] for r in rows}


def get_config_valor(clave: str, default=None):
    """Devuelve una configuraciÃ³n puntual con fallback."""
    row = q("SELECT valor FROM config WHERE clave=?", (clave,), fetchone=True)
    if not row:
        return default
    valor = row["valor"]
    return valor if valor not in (None, "") else default


def set_config_valor(clave: str, valor):
    """Persiste una configuraciÃ³n puntual."""
    q(
        "INSERT OR REPLACE INTO config VALUES (?,?)",
        (clave, "" if valor is None else str(valor)),
        commit=True,
    )


def set_config(data: dict):
    """Actualiza multiples valores de configuracion."""
    conn = get_conn()
    c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO config VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()


def get_rubro_configurado():
    """Devuelve el rubro confirmado por el usuario o None si hoy solo aplica fallback."""
    cfg = get_config()
    if not _as_bool(cfg.get(RUBRO_CONFIRMADO_CONFIG_KEY)):
        return None
    rubro = str(cfg.get(RUBRO_CONFIG_KEY, "") or "").strip().lower()
    return rubro if rubro in set(get_rubros_disponibles(include_future=True)) else None


def set_rubro_configurado(rubro: str):
    """Guarda el rubro operativo confirmado por el usuario."""
    rubro_raw = str(rubro or "").strip().lower()
    if rubro_raw not in set(get_rubros_disponibles()):
        raise ValueError("Rubro invalido.")
    set_config(
        {
            RUBRO_CONFIG_KEY: normalizar_rubro(rubro_raw),
            RUBRO_CONFIRMADO_CONFIG_KEY: "1",
        }
    )


def tiene_datos_operativos():
    """Indica si la instalacion ya tiene datos que vuelven riesgoso forzar el asistente."""
    counts = q(
        """
        SELECT
            (SELECT COUNT(*) FROM productos WHERE activo=1) AS productos,
            (SELECT COUNT(*) FROM ventas) AS ventas,
            (SELECT COUNT(*) FROM compras) AS compras
        """,
        fetchone=True,
    )
    return bool((counts["productos"] or 0) + (counts["ventas"] or 0) + (counts["compras"] or 0))


def necesita_configuracion_inicial_rubro():
    """Solo fuerza el asistente cuando el rubro no fue confirmado y la instalacion sigue vacia."""
    return get_rubro_configurado() is None and not tiene_datos_operativos()


def debe_mostrar_aviso_rubro_pendiente():
    """En instalaciones existentes muestra aviso en vez de bloquear la app."""
    return get_rubro_configurado() is None and tiene_datos_operativos()


def get_onboarding_context():
    """Resume si conviene mostrar la guÃ­a liviana de primeros pasos."""
    counts = q(
        """
        SELECT
            (SELECT COUNT(*) FROM productos WHERE activo=1) AS productos,
            (SELECT COUNT(*) FROM proveedores WHERE activo=1) AS proveedores,
            (SELECT COUNT(*) FROM ventas) AS ventas
        """,
        fetchone=True,
    )
    rubro_pendiente = get_rubro_configurado() is None
    onboarding_oculto = _as_bool(get_config_valor("onboarding_oculto", "0"))
    productos = int(counts["productos"] or 0)
    proveedores = int(counts["proveedores"] or 0)
    ventas = int(counts["ventas"] or 0)
    pendientes = {
        "rubro": rubro_pendiente,
        "proveedores": proveedores == 0,
        "productos": productos == 0,
        "movimientos": ventas == 0,
    }
    reportes_listos = productos > 0 or ventas > 0
    total_pasos = 5
    completados = sum(
        1
        for completo in (
            not pendientes["rubro"],
            not pendientes["proveedores"],
            not pendientes["productos"],
            ventas > 0,
            reportes_listos,
        )
        if completo
    )
    should_show = (not onboarding_oculto) and any(pendientes.values())
    return {
        "show": should_show,
        "hidden": onboarding_oculto,
        "rubro_pendiente": rubro_pendiente,
        "productos": productos,
        "proveedores": proveedores,
        "ventas": ventas,
        "compras_o_ventas": ventas,
        "reportes_listos": reportes_listos,
        "pendientes": pendientes,
        "steps_completed": completados,
        "steps_total": total_pasos,
        "is_new_install": productos == 0 and proveedores == 0 and ventas == 0,
    }


# â”€â”€â”€ LICENCIAS RSA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    # Lo dejamos propagar â€” no lo atrapamos aqui.
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


def get_demo_status(today: str | date | None = None) -> dict:
    """Devuelve el estado del periodo de prueba."""
    cfg  = get_config()
    demo = cfg.get('demo_mode', '1') == '1'
    if not demo:
        return {
            'demo': False, 'dias_restantes': 0, 'vencido': False,
            'aviso_proximo': False, 'install_date': '', 'expires_at': '',
            'dias_usados': 0, 'dias_demo': 0,
            'ventas_bloqueado': False, 'productos_bloqueado': False,
        }

    lifecycle = calculate_demo_lifecycle(
        install_date=cfg.get('demo_install_date', ''),
        demo_days=cfg.get('demo_dias', str(DEMO_DEFAULT_DAYS)),
        expires_at=cfg.get('demo_expires_at', ''),
        today=today,
    )
    updates = {}
    if cfg.get('demo_install_date', '') != lifecycle['install_date']:
        updates['demo_install_date'] = lifecycle['install_date']
    if not lifecycle['expires_at_valid'] and cfg.get('demo_expires_at', '') != lifecycle['expires_at']:
        updates['demo_expires_at'] = lifecycle['expires_at']
    if _parse_positive_int(cfg.get('demo_dias', ''), DEMO_DEFAULT_DAYS) != lifecycle['dias_demo']:
        updates['demo_dias'] = str(lifecycle['dias_demo'])
    if updates:
        set_config(updates)

    return {
        'demo':                demo,
        'install_date':        lifecycle['install_date'],
        'expires_at':          lifecycle['expires_at'],
        'dias_usados':         lifecycle['dias_usados'],
        'dias_restantes':      lifecycle['dias_restantes'],
        'dias_demo':           lifecycle['dias_demo'],
        'vencido':             lifecycle['vencido'],
        'aviso_proximo':       lifecycle['aviso_proximo'],
        'ventas_bloqueado':    lifecycle['ventas_bloqueado'],
        'productos_bloqueado': lifecycle['productos_bloqueado'],
        'ventas_pct':          lifecycle['ventas_pct'],
    }


def get_license_tier_from_db() -> str:
    """
    Obtiene el tier de licencia desde la tabla config.
    Normaliza aliases y retorna el tier canÃ³nico.
    """
    try:
        cfg = get_config()
        tier = cfg.get('license_tier', 'DEMO').strip().upper()
        return normalize_license_plan(tier)
    except Exception:
        return 'DEMO'


def get_modulos_from_tier(tier: str = None) -> set[str]:
    """
    Obtiene el conjunto de mÃ³dulos asociados a un tier de licencia.
    Si no encuentra el tier, devuelve mÃ³dulos para DEMO.
    """
    if not tier:
        tier = get_license_tier_from_db()

    tier = tier.strip().upper()
    tier = normalize_license_plan(tier)

    try:
        row = q(
            "SELECT modules FROM license_module_map WHERE license_tier=?",
            (tier,),
            fetchone=True
        )
        if row:
            modules_json = row['modules']
            if isinstance(modules_json, str):
                return set(json.loads(modules_json))
            return set(modules_json) if modules_json else {'core'}
    except Exception:
        pass

    return set(TIER_MODULES_MAP.get(tier, TIER_MODULES_MAP['DEMO']))


def _extract_license_modules(license_data: dict | None) -> list[str]:
    """Extrae mÃ³dulos remotos canÃ³nicos desde payloads del SDK."""
    if not isinstance(license_data, dict):
        return []

    raw_modules = (
        license_data.get('modules')
        or license_data.get('features')
        or license_data.get('modulos')
    )
    if not raw_modules:
        return []

    if isinstance(raw_modules, str):
        raw_modules = raw_modules.strip()
        if raw_modules.startswith('['):
            try:
                raw_modules = json.loads(raw_modules)
            except Exception:
                raw_modules = []
        else:
            raw_modules = [module.strip() for module in raw_modules.split(',') if module.strip()]

    if isinstance(raw_modules, str):
        modules = [raw_modules.strip().lower()] if raw_modules.strip() else []
    else:
        try:
            modules = [str(module).strip().lower() for module in raw_modules if str(module).strip()]
        except TypeError:
            return []

    return sorted(set(modules))


def get_license_info() -> dict:
    """Devuelve informacion completa de la licencia actual."""
    cfg = get_config()
    snapshot = _resolve_license_snapshot(cfg)
    tier = snapshot["plan_efectivo"]
    expires_at_str = snapshot["expires_at"]
    full_days = snapshot["remaining_days"] if snapshot["plan_original"] == "FULL" else None

    limits = TIER_LIMITS.get(tier, TIER_LIMITS["DEMO"])
    modules = _extract_license_modules({'modules': cfg.get('license_modules', '[]')})
    if tier == "SIN_PLAN":
        modules = []
    elif not modules:
        modules = sorted(TIER_MODULES_MAP.get(tier, TIER_MODULES_MAP["DEMO"]).copy())

    return {
        'type':        cfg.get('license_type', 'TDA_BASICA'),
        'tier':        tier,
        'key':         cfg.get('license_key', ''),
        'owner_name':  cfg.get('license_owner_name', ''),
        'owner_email': cfg.get('license_owner_email', ''),
        'owner_phone': cfg.get('license_owner_phone', ''),
        'vendor_code': cfg.get('license_vendor_code', ''),
        'recovery_word': cfg.get('license_recovery_word', ''),
        'plan':        snapshot["plan_original"],
        'plan_original': snapshot["plan_original"],
        'plan_efectivo': snapshot["plan_efectivo"],
        'effective_plan': snapshot["effective_plan"],
        'estado': snapshot["estado"],
        'fallback_aplicado': snapshot["fallback_aplicado"],
        'plan_base_permanente': snapshot["plan_base_permanente"],
        'expirada': snapshot["expirada"],
        'activated_at': cfg.get('license_activated_at', ''),
        'expires_at':  expires_at_str,
        'last_check':  cfg.get('license_last_check', ''),
        'max_machines': int(cfg.get('license_max_machines', '1')),
        'drive_index_id': cfg.get('license_drive_index_id', ''),
        'limits':      limits,
        'modules':     modules,
        'demo_mode':   cfg.get('demo_mode', '1'),
        'support':     bool(limits.get('support')) if tier != "SIN_PLAN" else False,
        'updates':     bool(limits.get('updates')) if tier != "SIN_PLAN" else False,
        # Campos de notificaciÃ³n de vencimiento
        'pro_days':    full_days,
        'pro_vencido': snapshot["plan_original"] == "PRO" and snapshot["expirada"],
        'pro_expires_soon':     full_days == 5,
        'pro_expires_tomorrow': full_days == 1,
        'full_days': full_days,
        'full_vencido': snapshot["plan_original"] == "FULL" and snapshot["expirada"],
    }


def sync_license_from_remote(license_data: dict):
    """Sincroniza una licencia Supabase/SDK al estado local de la app."""
    if not license_data:
        return

    original_plan = normalize_license_plan(
        license_data.get('plan_original') or license_data.get('plan') or license_data.get('tier') or license_data.get('license_plan')
    )
    effective_raw = license_data.get("plan_efectivo") or license_data.get("effective_plan") or original_plan
    effective_plan = _normalize_effective_plan(effective_raw)
    expira = license_data.get('expira') or license_data.get('expires_at') or ''
    if original_plan == 'BASICA':
        expira = ''
    status = str(license_data.get("estado", "") or "").strip()
    blocked_status = _is_blocked_license_status(status)
    plan_base_permanente = (
        not blocked_status
        and effective_plan != "SIN_PLAN"
        and (original_plan == "BASICA" or _as_bool(license_data.get("plan_base_permanente")))
    )
    vendor_code = str(
        license_data.get("codigo_vendedor")
        or license_data.get("vendor_code")
        or ""
    ).strip().upper()

    updates = {
        'demo_mode': '0' if original_plan != 'DEMO' else '1',
        'license_type': license_data.get('type', original_plan),
        'license_tier': effective_plan if effective_plan != "SIN_PLAN" else original_plan,
        'license_plan': original_plan,
        'license_plan_original': original_plan,
        'license_effective_plan': effective_plan,
        'license_status': status or "activa",
        'license_fallback_aplicado': '1' if _as_bool(license_data.get("fallback_aplicado")) else '0',
        'license_plan_base_permanente': '1' if plan_base_permanente else '0',
        'license_key': license_data.get('license_key', ''),
        'license_activated_at': datetime.now().isoformat(),
        'license_expires_at': expira,
        'license_last_check': datetime.now().date().isoformat(),
        'license_max_machines': str(license_data.get('max_devices') or license_data.get('max_machines') or 1),
        'license_support': '1' if effective_plan != "SIN_PLAN" and TIER_LIMITS.get(effective_plan, TIER_LIMITS["DEMO"]).get('support') else '0',
        'license_updates': '1' if effective_plan != "SIN_PLAN" and TIER_LIMITS.get(effective_plan, TIER_LIMITS["DEMO"]).get('updates') else '0',
    }
    if vendor_code:
        updates['license_vendor_code'] = vendor_code
    updates['basica_activada'] = '1' if plan_base_permanente else '0'
    if effective_plan == "SIN_PLAN":
        modules = []
    else:
        modules = _extract_license_modules({
            "modules": (
                license_data.get("modules_effective")
                or license_data.get("modulos_efectivos")
                or license_data.get("modules")
                or license_data.get("features_effective")
                or license_data.get("features")
                or license_data.get("modulos")
            )
        })
        if not modules:
            modules = sorted(TIER_MODULES_MAP.get(effective_plan, TIER_MODULES_MAP["DEMO"]).copy())
    updates['license_modules'] = json.dumps(modules)
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

        # â”€â”€ Reconstruir payload exactamente igual que el generador â”€â”€â”€â”€â”€â”€â”€â”€â”€
        #
        # CRÃTICO: estos campos, su orden (sort_keys=True) y los separadores
        # JSON deben coincidir byte a byte con lo que firma create_tienda_license()
        # en license_manager.py.
        #
        # Reglas del generador:
        #   - Usa json.dumps con separadores por defecto: (', ', ': ')
        #   - SIEMPRE incluye expires_at aunque sea None â†’ "expires_at": null
        #     (BASICA tiene None; PRO tiene "YYYY-MM-DD")
        #
        payload_dict = {
            "expires_at":  data.get("expires_at"),   # None â†’ null (BASICA) | "YYYY-MM-DD" (PRO)
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
            # La clave pÃºblica no se encontrÃ³ en ninguna ubicaciÃ³n esperada.
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
      - BASICA, PRO y FULL pueden activarse directamente como alta inicial.
      - `basica_activada` queda reservada para fallback permanente, no como
        requisito previo para activar PRO/FULL.

    Retorna: (ok: bool, mensaje: str)
    """
    ok, msg, data = validar_licencia_rsa(token_b64)
    if not ok:
        return False, msg

    tier = normalize_license_plan(data.get("tier", "BASICA"))

    expires_at = "" if tier == "BASICA" else (data.get("expires_at") or "")
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
        'license_support':        '1' if TIER_LIMITS[tier].get('support') else '0',
        'license_updates':        '1' if TIER_LIMITS[tier].get('updates') else '0',
    }

    # â”€â”€ Marcar BASICA como activada para fallback permanente â”€
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


# â”€â”€â”€ CÃ“DIGOS AUTOMÃTICOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def next_codigo():
    """Genera next cÃ³digo de producto Ãºnico."""
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


def _codigo_barras_flag_enabled(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "si"}


def normalize_codigo_barras(value) -> str:
    return str(value or "").strip()


def _codigo_barras_en_variantes(codigo_barras, *, exclude_variant_id=None) -> bool:
    codigo = normalize_codigo_barras(codigo_barras)
    if not codigo:
        return False
    sql = "SELECT id FROM producto_variantes WHERE TRIM(COALESCE(codigo_barras, '')) = ?"
    params = [codigo]
    if exclude_variant_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_variant_id))
    return q(sql, tuple(params), fetchone=True) is not None


def codigo_barras_exists(codigo_barras, exclude_id=None) -> bool:
    """Indica si el codigo de barras ya esta asignado a otro producto o variante."""
    codigo = normalize_codigo_barras(codigo_barras)
    if not codigo:
        return False
    sql = "SELECT id FROM productos WHERE TRIM(COALESCE(codigo_barras, '')) = ?"
    params = [codigo]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_id)
    if q(sql, tuple(params), fetchone=True) is not None:
        return True
    return _codigo_barras_en_variantes(codigo)


def next_codigo_barras_interno():
    """Genera el proximo codigo de barras interno disponible."""
    conn = get_conn()
    c = conn.cursor()
    try:
        row = c.execute(
            "SELECT valor FROM config WHERE clave='siguiente_codigo_barras_interno'"
        ).fetchone()
        siguiente = int((row["valor"] if row else "1") or 1)
        while True:
            codigo = f"NXR{siguiente:08d}"
            existe = c.execute(
                "SELECT 1 FROM productos WHERE TRIM(COALESCE(codigo_barras, '')) = ? LIMIT 1",
                (codigo,),
            ).fetchone()
            existe_variante = c.execute(
                "SELECT 1 FROM producto_variantes WHERE TRIM(COALESCE(codigo_barras, '')) = ? LIMIT 1",
                (codigo,),
            ).fetchone()
            if not existe and not existe_variante:
                c.execute(
                    "INSERT OR REPLACE INTO config VALUES ('siguiente_codigo_barras_interno', ?)",
                    (str(siguiente + 1),),
                )
                conn.commit()
                return codigo
            siguiente += 1
    finally:
        conn.close()


def _resolve_codigo_barras_for_save(data, *, exclude_id=None) -> str:
    codigo_barras = normalize_codigo_barras(data.get("codigo_barras"))
    generar_interno = _codigo_barras_flag_enabled(data.get("generar_codigo_barras")) or _codigo_barras_flag_enabled(data.get("generar_codigo_barras_interno"))
    if not codigo_barras and generar_interno:
        codigo_barras = next_codigo_barras_interno()
    if codigo_barras and codigo_barras_exists(codigo_barras, exclude_id=exclude_id):
        raise ValueError("Ya existe un producto o variante con ese codigo de barras.")
    return codigo_barras


def next_ticket():
    """Devuelve el prÃ³ximo nÃºmero de ticket y lo actualiza en la configuraciÃ³n.
    Asegura que el nÃºmero de ticket siempre sea mayor que el Ãºltimo registrado en ventas."""
    conn = get_conn()
    c = conn.cursor()

    # Obtener el Ãºltimo nÃºmero de ticket de la tabla de ventas
    last_sale_ticket = c.execute("SELECT MAX(numero_ticket) as max FROM ventas").fetchone()['max'] or 0

    # Obtener el siguiente nÃºmero de ticket de la configuraciÃ³n
    cfg_next_ticket = int(c.execute("SELECT valor FROM config WHERE clave='siguiente_ticket'").fetchone()['valor'] or 1001)

    # El prÃ³ximo ticket debe ser el mayor entre el Ãºltimo de ventas + 1 y el de la configuraciÃ³n
    next_num = max(last_sale_ticket + 1, cfg_next_ticket)

    # Actualizar la configuraciÃ³n para el siguiente ticket
    c.execute("INSERT OR REPLACE INTO config VALUES ('siguiente_ticket', ?)", (str(next_num + 1),))
    conn.commit()
    conn.close()
    return next_num


# â”€â”€â”€ CATEGORÃAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_categorias():
    """Devuelve lista de categorÃ­as activas."""
    return [r['nombre'] for r in q("SELECT nombre FROM categorias WHERE activa=1 ORDER BY nombre")]


def _normalize_categoria_nombre(nombre) -> str:
    return " ".join(str(nombre or "").strip().split())


def _normalize_name_key(nombre) -> str:
    texto = _normalize_categoria_nombre(nombre)
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return texto.lower()


def _categoria_nombre_key(nombre) -> str:
    return _normalize_name_key(nombre)


def _get_base_categorias_map():
    categorias_base = {}
    for rubro in get_rubros_disponibles(include_future=True):
        for categoria in get_categorias_disponibles(rubro):
            nombre = _normalize_categoria_nombre(categoria)
            key = _categoria_nombre_key(nombre)
            if key and key not in categorias_base:
                categorias_base[key] = nombre
    return categorias_base


def _get_categoria_rows():
    return q("SELECT id, nombre, activa FROM categorias ORDER BY id")


def _sync_productos_categoria_nombre(nombre_actual, nuevo_nombre):
    actual_key = _categoria_nombre_key(nombre_actual)
    nuevo = _normalize_categoria_nombre(nuevo_nombre)
    if not actual_key or not nuevo:
        return
    rows = q("SELECT id, TRIM(COALESCE(categoria, '')) AS categoria FROM productos")
    for row in rows:
        categoria = _normalize_categoria_nombre(row["categoria"])
        if categoria and _categoria_nombre_key(categoria) == actual_key and categoria != nuevo:
            q(
                "UPDATE productos SET categoria=? WHERE id=?",
                (nuevo, row["id"]),
                commit=True,
            )


def _get_productos_categoria_variantes():
    variantes = {}
    rows = q("SELECT id, TRIM(COALESCE(categoria, '')) AS categoria FROM productos")
    for row in rows:
        categoria = _normalize_categoria_nombre(row["categoria"])
        if not categoria:
            continue
        key = _categoria_nombre_key(categoria)
        if key:
            variantes.setdefault(key, []).append({"id": row["id"], "categoria": categoria})
    return variantes


def _find_categoria_row(nombre):
    key = _categoria_nombre_key(nombre)
    if not key:
        return None
    for row in _get_categoria_rows():
        if _categoria_nombre_key(row["nombre"]) == key:
            return row
    return None


def _find_categoria_row_by_id(categoria_id):
    if not str(categoria_id or "").strip():
        return None
    return q("SELECT id, nombre, activa FROM categorias WHERE id=?", (categoria_id,), fetchone=True)


def _categoria_base_existe(nombre) -> bool:
    return _categoria_nombre_key(nombre) in _get_base_categorias_map()


def _upsert_categoria_estado(nombre, activa):
    nombre_limpio = _normalize_categoria_nombre(nombre)
    if not nombre_limpio:
        return
    existente = _find_categoria_row(nombre_limpio)
    if existente:
        q(
            "UPDATE categorias SET nombre=?, activa=? WHERE id=?",
            (nombre_limpio, int(bool(activa)), existente["id"]),
            commit=True,
        )
    else:
        q(
            "INSERT INTO categorias (nombre, activa) VALUES (?, ?)",
            (nombre_limpio, int(bool(activa))),
            commit=True,
        )


def get_categorias_personalizadas(activo_only=True):
    """Devuelve categorÃ­as personalizadas de la tabla categorias."""
    sql = "SELECT id, nombre, activa FROM categorias"
    params = []
    if activo_only:
        sql += " WHERE activa=1"
    sql += " ORDER BY nombre"
    return q(sql, params)


def get_categorias_usadas(rubro_actual=None):
    """Devuelve categorÃ­as usadas actualmente en productos activos."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro_actual)
    return q(
        f"""
        SELECT DISTINCT TRIM(COALESCE(p.categoria, '')) AS nombre
        FROM productos p
        WHERE p.activo=1
          AND TRIM(COALESCE(p.categoria, '')) <> ''
          AND {rubro_cond}
        ORDER BY nombre
        """,
        rubro_params,
    )


def count_productos_por_categoria(nombre, rubro_actual=None):
    """Cuenta productos activos asociados a una categorÃ­a."""
    nombre_limpio = _normalize_categoria_nombre(nombre)
    if not nombre_limpio:
        return 0
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro_actual)
    row = q(
        f"""
        SELECT COUNT(*) AS total
        FROM productos p
        WHERE p.activo=1
          AND LOWER(TRIM(COALESCE(p.categoria, ''))) = LOWER(TRIM(?))
          AND {rubro_cond}
        """,
        (nombre_limpio, *rubro_params),
        fetchone=True,
    )
    return int(row["total"] or 0) if row else 0


def get_categorias_configuracion(rubro_actual):
    """Devuelve categorÃ­as configurables con estado, origen y cantidad de productos."""
    categorias_map = {}
    categorias_base = _get_base_categorias_map()

    def ensure_entry(nombre, *, activa=True, origen=None, categoria_id=None):
        nombre_limpio = _normalize_categoria_nombre(nombre)
        if not nombre_limpio:
            return None
        key = _categoria_nombre_key(nombre_limpio)
        existed = key in categorias_map
        entry = categorias_map.setdefault(
            key,
            {
                "nombre": nombre_limpio,
                "activa": bool(activa),
                "productos_count": 0,
                "es_base": False,
                "es_personalizada": False,
                "es_usada": False,
                "id": categoria_id,
            },
        )
        if origen == "base":
            entry["es_base"] = True
        elif origen == "personalizada":
            entry["es_personalizada"] = True
        elif origen == "usada":
            entry["es_usada"] = True
        if origen != "usada":
            entry["nombre"] = nombre_limpio
        if categoria_id and not entry.get("id"):
            entry["id"] = categoria_id
        if origen in {"base", "personalizada"} or not existed:
            entry["activa"] = bool(activa)
        return entry

    for categoria in get_categorias_disponibles(rubro_actual):
        ensure_entry(categoria, activa=True, origen="base")

    for row in get_categorias_personalizadas(activo_only=False):
        nombre_limpio = _normalize_categoria_nombre(row["nombre"])
        key = _categoria_nombre_key(nombre_limpio)
        es_base = key in categorias_base
        entry = ensure_entry(
            categorias_base.get(key, nombre_limpio),
            activa=bool(row["activa"]),
            origen=None if es_base else "personalizada",
            categoria_id=row["id"],
        )
        if entry:
            entry["activa"] = bool(row["activa"])
            entry["nombre"] = categorias_base.get(key, nombre_limpio)

    for row in get_categorias_usadas(rubro_actual):
        ensure_entry(row["nombre"], activa=True, origen="usada")

    resultado = []
    for key, entry in categorias_map.items():
        entry["productos_count"] = count_productos_por_categoria(entry["nombre"], rubro_actual)
        origenes = []
        if entry["es_base"]:
            origenes.append("base")
        if entry["es_personalizada"]:
            origenes.append("personalizada")
        if entry["es_usada"]:
            origenes.append("usada")
        entry["origen"] = "/".join(origenes) or "personalizada"
        resultado.append(entry)

    resultado.sort(key=lambda item: item["nombre"].lower())
    return resultado


def get_categorias_configurables(rubro_actual, categoria_actual=""):
    """Devuelve categorÃ­as visibles para formularios de productos."""
    categoria_actual_limpia = _normalize_categoria_nombre(categoria_actual)
    categoria_actual_key = categoria_actual_limpia.lower()
    resultado = []
    vistos = set()
    for item in get_categorias_configuracion(rubro_actual):
        key = item["nombre"].lower()
        if item["activa"] or (categoria_actual_limpia and key == categoria_actual_key):
            if key not in vistos:
                resultado.append(item["nombre"])
                vistos.add(key)
    return resultado


def _build_rubro_compatible_filter(rubro_actual: str | None):
    rubro = normalizar_rubro(rubro_actual or get_rubro_actual(get_config()))
    return "(COALESCE(TRIM(rubro), '') = '' OR LOWER(rubro) = ?)", [rubro]


def _build_rubro_compatible_filter_sql(alias: str = "p", rubro_actual: str | None = None):
    rubro = normalizar_rubro(rubro_actual or get_rubro_actual(get_config()))
    return f"(COALESCE(TRIM({alias}.rubro), '') = '' OR LOWER({alias}.rubro) = ?)", [rubro]


def _append_condition(base: str, condition: str) -> str:
    return f"{base} AND {condition}" if base else f"WHERE {condition}"


def add_categoria(nombre):
    """Agrega o reactiva una categorÃ­a."""
    cleanup_categorias_duplicadas()
    nombre_limpio = _normalize_categoria_nombre(nombre)
    if not nombre_limpio:
        raise ValueError("IngresÃ¡ un nombre de categorÃ­a.")
    existente = _find_categoria_row(nombre_limpio)
    if existente:
        if int(existente["activa"] or 0):
            raise ValueError("La categorÃ­a ya existe.")
        q(
            "UPDATE categorias SET nombre=?, activa=1 WHERE id=?",
            (nombre_limpio, existente["id"]),
            commit=True,
        )
        return
    if _categoria_base_existe(nombre_limpio):
        raise ValueError("La categorÃ­a ya existe.")
    q(
        "INSERT INTO categorias (nombre, activa) VALUES (?, 1)",
        (nombre_limpio,),
        fetchall=False,
        commit=True,
    )


def update_categoria(nombre_actual, nuevo_nombre, categoria_id=None):
    """Renombra una categorÃ­a y actualiza productos relacionados."""
    cleanup_categorias_duplicadas()
    nombre_actual_limpio = _normalize_categoria_nombre(nombre_actual)
    nuevo_nombre_limpio = _normalize_categoria_nombre(nuevo_nombre)
    if not nombre_actual_limpio:
        raise ValueError("La categorÃ­a actual es obligatoria.")
    if not nuevo_nombre_limpio:
        raise ValueError("IngresÃ¡ un nuevo nombre de categorÃ­a.")

    existente_actual = _find_categoria_row_by_id(categoria_id) or _find_categoria_row(nombre_actual_limpio)
    if not existente_actual:
        raise ValueError("No se encontrÃ³ la categorÃ­a a renombrar.")

    nombre_actual_limpio = _normalize_categoria_nombre(existente_actual["nombre"])
    existente_nuevo = _find_categoria_row(nuevo_nombre_limpio)
    if (
        existente_nuevo
        and int(existente_nuevo["id"]) != int(existente_actual["id"])
        and _categoria_nombre_key(nuevo_nombre_limpio) != _categoria_nombre_key(nombre_actual_limpio)
    ):
        raise ValueError("Ya existe otra categorÃ­a con ese nombre.")

    if _categoria_nombre_key(nombre_actual_limpio) == _categoria_nombre_key(nuevo_nombre_limpio):
        q(
            "UPDATE categorias SET nombre=? WHERE id=?",
            (nuevo_nombre_limpio, existente_actual["id"]),
            commit=True,
        )
        _sync_productos_categoria_nombre(nombre_actual_limpio, nuevo_nombre_limpio)
        return

    activa_actual = int(existente_actual["activa"] or 0)
    q(
        "UPDATE categorias SET nombre=?, activa=? WHERE id=?",
        (nuevo_nombre_limpio, activa_actual, existente_actual["id"]),
        commit=True,
    )
    _sync_productos_categoria_nombre(nombre_actual_limpio, nuevo_nombre_limpio)
    cleanup_categorias_duplicadas()


def set_categoria_activa(nombre, activa):
    """Activa o desactiva una categorÃ­a sin tocar productos existentes."""
    cleanup_categorias_duplicadas()
    nombre_limpio = _normalize_categoria_nombre(nombre)
    if not nombre_limpio:
        raise ValueError("La categorÃ­a es obligatoria.")
    _upsert_categoria_estado(nombre_limpio, bool(activa))


def delete_categoria(nombre):
    """Desactiva una categorÃ­a de forma segura."""
    set_categoria_activa(nombre, False)

def get_gasto_categorias():
    """Devuelve lista configurable de categorÃ­as de gastos con su tipo."""
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
            nombre = _normalize_categoria_nombre(cat.get('nombre', ''))
            tipo = normalizar_tipo_gasto(cat.get('tipo'))
        else:
            nombre = _normalize_categoria_nombre(cat)
            tipo = 'Necesario'
        if not nombre:
            continue
        key = _normalize_name_key(nombre)
        if key in keys:
            continue
        keys.add(key)
        normalizadas.append({'nombre': nombre, 'tipo': tipo})
    return normalizadas

def set_gasto_categorias(categorias):
    """Guarda la configuraciÃ³n completa de categorÃ­as de gastos."""
    limpias = []
    keys = set()
    for cat in categorias:
        if isinstance(cat, dict):
            nombre = _normalize_categoria_nombre(cat.get('nombre', ''))
            tipo = normalizar_tipo_gasto(cat.get('tipo'))
        else:
            nombre = _normalize_categoria_nombre(cat)
            tipo = 'Necesario'
        if not nombre:
            continue
        key = _normalize_name_key(nombre)
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


def normalizar_clasificacion_gasto(clasificacion, categoria=''):
    """Normaliza la clasificaciÃ³n contable del gasto."""
    txt = str(clasificacion or '').strip().lower()
    if not txt:
        cat = str(categoria or '').strip().lower()
        if 'impuesto' in cat:
            return 'Impuesto'
        return 'Operativo'
    if 'imp' in txt:
        return 'Impuesto'
    if 'fin' in txt or 'interes' in txt or 'interÃ©s' in txt:
        return 'Financiero'
    if 'otro' in txt:
        return 'Otro'
    return 'Operativo'


def get_gasto_clasificaciones():
    return list(GASTO_CLASIFICACIONES)


def get_tipo_gasto_categoria(nombre_categoria):
    """Obtiene el tipo asociado a una categorÃ­a de gasto."""
    nombre = (nombre_categoria or '').strip().lower()
    for cat in get_gasto_categorias():
        if cat['nombre'].strip().lower() == nombre:
            return cat['tipo']
    return 'Necesario'

def add_gasto_categoria(nombre, tipo='Necesario'):
    """Agrega una categorÃ­a de gastos al listado configurable."""
    cleanup_gasto_categorias_duplicadas()
    nombre_limpio = _normalize_categoria_nombre(nombre)
    if not nombre_limpio:
        raise ValueError("IngresÃ¡ un nombre de categorÃ­a de gasto.")
    categorias = get_gasto_categorias()
    if _normalize_name_key(nombre_limpio) in {_normalize_name_key(c['nombre']) for c in categorias}:
        raise ValueError("La categorÃ­a de gasto ya existe.")
    categorias.append({'nombre': nombre_limpio, 'tipo': normalizar_tipo_gasto(tipo)})
    set_gasto_categorias(categorias)

def delete_gasto_categoria(nombre):
    """Elimina una categorÃ­a de gastos del listado configurable."""
    clave = _normalize_name_key(nombre)
    categorias = [c for c in get_gasto_categorias() if _normalize_name_key(c['nombre']) != clave]
    set_gasto_categorias(categorias)

def update_gasto_categoria(nombre_actual, nuevo_nombre, tipo='Necesario'):
    """Renombra una categorÃ­a de gastos y actualiza registros relacionados."""
    cleanup_gasto_categorias_duplicadas()
    actual = _normalize_categoria_nombre(nombre_actual)
    nuevo = _normalize_categoria_nombre(nuevo_nombre)
    if not actual:
        raise ValueError("La categorÃ­a actual es obligatoria.")
    if not nuevo:
        raise ValueError("IngresÃ¡ un nuevo nombre para la categorÃ­a de gasto.")
    tipo_normalizado = normalizar_tipo_gasto(tipo)
    categorias = get_gasto_categorias()
    clave_actual = _normalize_name_key(actual)
    clave_nuevo = _normalize_name_key(nuevo)
    if clave_actual != clave_nuevo and clave_nuevo in {_normalize_name_key(c['nombre']) for c in categorias}:
        raise ValueError("Ya existe otra categorÃ­a de gasto con ese nombre.")
    if clave_actual not in {_normalize_name_key(c['nombre']) for c in categorias}:
        raise ValueError("No se encontrÃ³ la categorÃ­a de gasto a renombrar.")
    categorias = [
        {'nombre': nuevo, 'tipo': tipo_normalizado} if _normalize_name_key(c['nombre']) == clave_actual else c
        for c in categorias
    ]
    set_gasto_categorias(categorias)
    q("UPDATE gastos SET categoria=? WHERE LOWER(categoria)=LOWER(?)", (nuevo, actual), commit=True)
    q("UPDATE gastos SET necesario=? WHERE LOWER(categoria)=LOWER(?)", (tipo_normalizado, nuevo), commit=True)


def cleanup_categorias_duplicadas():
    """Consolida filas duplicadas de categorÃ­as y normaliza referencias de productos."""
    base_map = _get_base_categorias_map()
    rows = _get_categoria_rows()
    productos_variantes = _get_productos_categoria_variantes()
    grupos = {}
    for row in rows:
        key = _categoria_nombre_key(row["nombre"])
        if key:
            grupos.setdefault(key, []).append(row)

    cambios = 0
    conn = get_conn()
    try:
        c = conn.cursor()
        for key, group in grupos.items():
            canonical_name = base_map.get(key) or _normalize_categoria_nombre(group[0]["nombre"])
            keeper = min(group, key=lambda item: int(item["id"]))
            activa = 1 if any(int(item["activa"] or 0) for item in group) else 0
            if (
                _normalize_categoria_nombre(keeper["nombre"]) != canonical_name
                or int(keeper["activa"] or 0) != activa
            ):
                c.execute(
                    "UPDATE categorias SET nombre=?, activa=? WHERE id=?",
                    (canonical_name, activa, keeper["id"]),
                )
            for row in group:
                row_name = _normalize_categoria_nombre(row["nombre"])
                if row_name and row_name != canonical_name:
                    for producto in productos_variantes.get(key, []):
                        if producto["categoria"] != canonical_name:
                            c.execute(
                                "UPDATE productos SET categoria=? WHERE id=?",
                                (canonical_name, producto["id"]),
                            )
            duplicate_ids = [int(item["id"]) for item in group if int(item["id"]) != int(keeper["id"])]
            if duplicate_ids:
                placeholders = ",".join("?" for _ in duplicate_ids)
                c.execute(f"DELETE FROM categorias WHERE id IN ({placeholders})", tuple(duplicate_ids))
                cambios += len(duplicate_ids)
        conn.commit()
    finally:
        conn.close()

    cleanup_gasto_categorias_duplicadas()
    return cambios


def cleanup_gasto_categorias_duplicadas():
    """Consolida categorÃ­as de gasto duplicadas por nombre normalizado."""
    cfg = get_config()
    raw = cfg.get('gastos_categorias', '')
    try:
        categorias = json.loads(raw) if raw else []
    except Exception:
        categorias = []
    if not categorias:
        categorias = DEFAULT_GASTO_CATEGORIAS[:]

    canonicas = []
    cambios = 0
    vistos = {}
    for cat in categorias:
        if isinstance(cat, dict):
            nombre = _normalize_categoria_nombre(cat.get("nombre", ""))
            tipo = normalizar_tipo_gasto(cat.get("tipo"))
        else:
            nombre = _normalize_categoria_nombre(cat)
            tipo = 'Necesario'
        if not nombre:
            continue
        key = _normalize_name_key(nombre)
        if key in vistos:
            q(
                "UPDATE gastos SET categoria=? WHERE LOWER(TRIM(COALESCE(categoria, ''))) = LOWER(TRIM(?))",
                (vistos[key]["nombre"], nombre),
                commit=True,
            )
            cambios += 1
            continue
        item = {"nombre": nombre, "tipo": tipo}
        vistos[key] = item
        canonicas.append(item)
    if cambios or len(canonicas) != len(categorias):
        set_gasto_categorias(canonicas)
    return cambios


# â”€â”€â”€ USUARIOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_usuario_by_username(username):
    """Obtiene usuario por username."""
    return q("SELECT * FROM usuarios WHERE username=?", (username,), fetchone=True)


def get_usuario_by_id(uid):
    """Obtiene usuario por ID."""
    return q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)


def verify_password(password, password_hash):
    """Verifica contraseÃ±a contra hash."""
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


def add_usuario(
    username,
    password,
    rol,
    nombre_completo,
    security_question=None,
    security_answer=None,
    *,
    email="",
    telefono="",
):
    """Agrega un nuevo usuario."""
    password_hash = generate_password_hash(password)
    ans_hash = None
    if security_answer:
        ans_hash = hash_security_answer(security_answer)
    q(
        """INSERT INTO usuarios (username,password_hash,rol,nombre_completo,email,telefono,security_question,security_answer_hash)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            username,
            password_hash,
            rol,
            nombre_completo,
            email,
            telefono,
            security_question,
            ans_hash,
        ),
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
    """Actualiza la contraseÃ±a de un usuario por username."""
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

    if 'email' in data:
        sets.append("email=?")
        params.append(data.get('email', ''))

    if 'telefono' in data:
        sets.append("telefono=?")
        params.append(data.get('telefono', ''))

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
    """Verifica si un rol tiene un permiso especÃ­fico."""
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


# â”€â”€â”€ PRODUCTOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_productos(activo_only=True, search='', rubro=None, proveedor=''):
    """Devuelve productos filtrables."""
    sql = (
        "SELECT productos.*, COALESCE(s.proveedor_habitual, '') AS proveedor_habitual "
        "FROM productos "
        "LEFT JOIN stock s ON s.producto_id = productos.id"
    )
    conds = []
    params = []
    if activo_only:
        conds.append("productos.activo=1")
    if rubro is not None:
        rubro_cond, rubro_params = _build_rubro_compatible_filter(rubro)
        conds.append(rubro_cond)
        params += rubro_params
    if search:
        conds.append(
            "("
            "productos.codigo_interno LIKE ? "
            "OR productos.codigo_barras LIKE ? "
            "OR productos.descripcion LIKE ? "
            "OR productos.categoria LIKE ? "
            "OR COALESCE(s.proveedor_habitual, '') LIKE ?"
            ")"
        )
        params += [f'%{search}%'] * 5
    if proveedor:
        conds.append("LOWER(COALESCE(s.proveedor_habitual, '')) = ?")
        params.append(str(proveedor).strip().lower())
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY productos.descripcion"
    return q(sql, params)


def get_productos_por_proveedor_categoria(proveedor, categoria="", rubro=None):
    """Devuelve productos activos filtrados por proveedor habitual y categorÃ­a opcional."""
    proveedor_normalizado = str(proveedor or "").strip()
    if not proveedor_normalizado:
        return []

    sql = (
        "SELECT p.id, p.codigo_interno, p.descripcion, p.categoria, p.costo, p.precio_venta, "
        "COALESCE(s.proveedor_habitual, '') AS proveedor_habitual "
        "FROM productos p "
        "LEFT JOIN stock s ON s.producto_id = p.id"
    )
    conds = [
        "p.activo = 1",
        "LOWER(TRIM(COALESCE(s.proveedor_habitual, ''))) = LOWER(TRIM(?))",
    ]
    params = [proveedor_normalizado]
    if rubro is not None:
        rubro_cond, rubro_params = _build_rubro_compatible_filter(rubro)
        conds.append(rubro_cond.replace("productos.", "p."))
        params += rubro_params
    if str(categoria or "").strip():
        conds.append("LOWER(TRIM(COALESCE(p.categoria, ''))) = LOWER(TRIM(?))")
        params.append(str(categoria).strip())
    sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY p.descripcion"
    return q(sql, params)


def aplicar_aumento_precios(productos_ids, porcentaje):
    """Aplica aumento porcentual a costo y precio_venta de productos especÃ­ficos."""
    try:
        porcentaje_num = float(porcentaje)
    except (TypeError, ValueError) as exc:
        raise ValueError("El porcentaje debe ser un nÃºmero vÃ¡lido.") from exc
    if porcentaje_num <= 0:
        raise ValueError("El porcentaje debe ser mayor a 0.")

    ids_limpios = []
    vistos = set()
    for raw_id in productos_ids or []:
        try:
            pid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if pid > 0 and pid not in vistos:
            ids_limpios.append(pid)
            vistos.add(pid)
    if not ids_limpios:
        return 0

    conn = get_conn()
    try:
        c = conn.cursor()
        placeholders = ",".join("?" for _ in ids_limpios)
        rows = c.execute(
            f"SELECT id, costo, precio_venta FROM productos WHERE activo=1 AND id IN ({placeholders})",
            ids_limpios,
        ).fetchall()
        factor = 1 + (porcentaje_num / 100.0)
        afectados = 0
        for row in rows:
            nuevo_costo = round(float(row["costo"] or 0) * factor, 2)
            nuevo_precio = round(float(row["precio_venta"] or 0) * factor, 2)
            c.execute(
                "UPDATE productos SET costo=?, precio_venta=? WHERE id=?",
                (nuevo_costo, nuevo_precio, row["id"]),
            )
            afectados += 1
        conn.commit()
        return afectados
    finally:
        conn.close()


def get_producto(pid):
    """Devuelve un producto por ID."""
    return q("SELECT * FROM productos WHERE id=?", (pid,), fetchone=True)


def get_producto_by_codigo(codigo):
    """Busca por cÃ³digo interno o barras."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter(None)
    r = q(
        f"SELECT * FROM productos WHERE codigo_interno=? AND activo=1 AND {rubro_cond}",
        (codigo, *rubro_params),
        fetchone=True,
    )
    if not r:
        r = q(
            f"SELECT * FROM productos WHERE codigo_barras=? AND activo=1 AND {rubro_cond}",
            (codigo, *rubro_params),
            fetchone=True,
        )
    return r


def producto_permite_fraccionado(producto) -> bool:
    """Fraccionado por override explicito, unidad fraccionable o productos legacy."""
    if not producto:
        return False
    try:
        tipo_unidad = normalizar_unidad(producto["tipo_unidad"] or "")
        unidad_visual = normalizar_unidad(producto["unidad"] or "")
        return bool(
            int(producto["permite_fraccionado"] or 0)
            or es_unidad_fraccionable(tipo_unidad)
            or es_unidad_fraccionable(unidad_visual)
            or int(producto["por_peso"] or 0)
        )
    except Exception:
        return False


def validar_cantidad_producto(producto, cantidad, *, campo="cantidad") -> float:
    """Restringe decimales a productos fraccionados y exige cantidad positiva."""
    try:
        cantidad_num = float(cantidad or 0)
    except (TypeError, ValueError):
        raise ValueError(f"La {campo} es invalida.")
    if cantidad_num <= 0:
        raise ValueError(f"La {campo} debe ser mayor a 0.")
    if not producto_permite_fraccionado(producto):
        if not cantidad_num.is_integer():
            raise ValueError(f"El producto {producto['descripcion']} solo permite cantidades enteras.")
        return float(int(cantidad_num))
    return round(cantidad_num, 3)


def add_producto(data):
    """Agrega un nuevo producto."""
    codigo = next_codigo()
    rubro_actual = get_rubro_actual(get_config())
    proveedor_habitual = str(data.get('proveedor_habitual') or '').strip()
    imagen = str(data.get('imagen') or '').strip()
    codigo_barras = _resolve_codigo_barras_for_save(data)
    unidad_seleccionada = normalizar_unidad(data.get('tipo_unidad') or data.get('unidad'), rubro=rubro_actual)
    tipo_unidad = get_unidad_interna(unidad_seleccionada)
    unidad = get_unidad_label(unidad_seleccionada)
    permite_fraccionado = int(data.get('permite_fraccionado', 0) or 0)
    es_fraccionable = producto_permite_fraccionado({"tipo_unidad": tipo_unidad, "unidad": unidad_seleccionada, "permite_fraccionado": permite_fraccionado, "por_peso": data.get("por_peso", 0)})
    stock_actual = convertir_cantidad_a_base(data.get('stock_actual', 0), unidad_seleccionada)
    stock_minimo = convertir_cantidad_a_base(data.get('stock_minimo', 5), unidad_seleccionada)
    stock_maximo = convertir_cantidad_a_base(data.get('stock_maximo', 50), unidad_seleccionada)
    if not es_fraccionable and not stock_actual.is_integer():
        raise ValueError("El stock inicial solo puede tener decimales para productos fraccionados.")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO productos
        (codigo_interno,codigo_barras,descripcion,marca,imagen,categoria,unidad,tipo_unidad,permite_fraccionado,rubro,por_peso,costo,precio_venta,iva,activo)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (codigo, codigo_barras, data['descripcion'], data.get('marca', ''), imagen,
         data.get('categoria') or get_categoria_default(rubro_actual), unidad, tipo_unidad, permite_fraccionado,
         data.get('rubro') or rubro_actual, 1 if es_fraccionable else int(data.get('por_peso', 0)),
         float(data.get('costo', 0)), float(data.get('precio_venta', 0)), data.get('iva', '21%'))
    )
    pid = c.lastrowid
    c.execute(
        "INSERT INTO stock (producto_id,stock_actual,stock_minimo,stock_maximo,proveedor_habitual) VALUES (?,?,?,?,?)",
        (pid, stock_actual, stock_minimo, stock_maximo, proveedor_habitual)
    )
    conn.commit()
    conn.close()
    return pid


def update_producto(pid, data):
    """Actualiza un producto."""
    producto_actual = get_producto(pid)
    rubro_actual = get_rubro_actual(get_config())
    codigo_barras = _resolve_codigo_barras_for_save(data, exclude_id=pid)
    imagen_guardada = (
        str(data.get('imagen') or '').strip()
        if 'imagen' in data
        else str((producto_actual['imagen'] if producto_actual else '') or '').strip()
    )
    unidad_seleccionada = normalizar_unidad(data.get('tipo_unidad') or data.get('unidad'), rubro=rubro_actual)
    tipo_unidad = get_unidad_interna(unidad_seleccionada)
    unidad = get_unidad_label(unidad_seleccionada)
    permite_fraccionado = int(data.get('permite_fraccionado', 0) or 0)
    es_fraccionable = producto_permite_fraccionado({"tipo_unidad": tipo_unidad, "unidad": unidad_seleccionada, "permite_fraccionado": permite_fraccionado, "por_peso": data.get("por_peso", 0)})
    rubro_guardado = (
        str(data.get('rubro', '') or '').strip().lower()
        or str((producto_actual['rubro'] if producto_actual else '') or '').strip().lower()
    )
    q(
        """UPDATE productos SET codigo_barras=?,descripcion=?,marca=?,imagen=?,categoria=?,unidad=?,tipo_unidad=?,
        permite_fraccionado=?,rubro=?,por_peso=?,costo=?,precio_venta=?,iva=?,activo=? WHERE id=?""",
        (codigo_barras, data['descripcion'], data.get('marca', ''), imagen_guardada,
         data.get('categoria') or get_categoria_default(rubro_actual), unidad, tipo_unidad, permite_fraccionado,
         rubro_guardado or None, 1 if es_fraccionable else int(data.get('por_peso', 0)),
         float(data.get('costo', 0)), float(data.get('precio_venta', 0)), data.get('iva', '21%'),
         int(data.get('activo', 1)), pid),
        fetchall=False, commit=True
    )


def delete_producto(pid):
    """Desactiva un producto."""
    q("UPDATE productos SET activo=0 WHERE id=?", (pid,), fetchall=False, commit=True)


# â”€â”€â”€ STOCK â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€â”€ CLIENTES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_clientes(search='', with_debt_only=False, activo_only=True):
    """Devuelve clientes filtrables con soporte para bÃºsqueda y deuda."""
    # 1. Base de la consulta: Incluimos un subquery para calcular el saldo al vuelo
    sql = """
        SELECT *,
        (SELECT COALESCE(SUM(debe),0) - COALESCE(SUM(haber),0)
         FROM cc_clientes_mov
         WHERE cliente_id = clientes.id AND COALESCE(anulado, 0)=0) as saldo
        FROM clientes
    """
    conds = []
    params = []

    # 2. Filtro de Activos
    if activo_only:
        conds.append("activo = 1")

    # 3. Filtro de BÃºsqueda
    if search:
        conds.append("(nombre LIKE ? OR codigo LIKE ? OR dni_cuit LIKE ?)")
        params += [f'%{search}%'] * 3

    # 4. Filtro de Deuda (Solo si el saldo > 0)
    if with_debt_only:
        # Usamos comillas triples para que Python permita varias lÃ­neas
        query_saldo = """
            (SELECT COALESCE(SUM(debe),0) - COALESCE(SUM(haber),0)
             FROM cc_clientes_mov
             WHERE cliente_id = clientes.id AND COALESCE(anulado, 0)=0)
        """
        conds.append(f"{query_saldo} > 0")

    # 5. ConstrucciÃ³n final
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
    movimientos = q(
        "SELECT debe, haber FROM cc_clientes_mov WHERE cliente_id=? AND COALESCE(anulado, 0)=0",
        (cid,),
    )
    return calcular_saldo_cliente_desde_movimientos(movimientos)


def get_movimientos_cliente(cid, limit=50):
    """Obtiene movimientos de cuenta corriente de un cliente."""
    return q(
        """SELECT * FROM cc_clientes_mov
        WHERE cliente_id=?
        ORDER BY fecha DESC, id DESC
        LIMIT ?""",
        (cid, limit)
    )


def get_movimiento_cliente(mid):
    """Obtiene un movimiento puntual de cuenta corriente cliente."""
    return q("SELECT * FROM cc_clientes_mov WHERE id=?", (mid,), fetchone=True)


def agregar_movimiento_cliente(
    cid,
    tipo,
    numero_comprobante,
    debe=0,
    haber=0,
    vencimiento='',
    observaciones='',
    fecha=None,
    venta_id=None,
    medio_pago='',
    caja_movimiento_id=None,
    movimiento_origen_id=None,
):
    """Agrega un movimiento a la cuenta corriente del cliente."""
    if not fecha:
        fecha = datetime.now().strftime('%Y-%m-%d')
    return q(
        """INSERT INTO cc_clientes_mov
        (cliente_id, fecha, tipo, numero_comprobante, debe, haber, medio_pago, vencimiento, observaciones, venta_id, caja_movimiento_id, movimiento_origen_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cid,
            fecha,
            tipo,
            numero_comprobante,
            float(debe or 0),
            float(haber or 0),
            str(medio_pago or '').strip(),
            vencimiento,
            observaciones,
            venta_id,
            caja_movimiento_id,
            movimiento_origen_id,
        ),
        fetchall=False,
        commit=True
    )


def registrar_movimiento_cliente_manual(
    cid,
    tipo,
    numero_comprobante='',
    debe=0,
    haber=0,
    vencimiento='',
    observaciones='',
    fecha=None,
    medio_pago='',
):
    """Registra un movimiento manual no destructivo para cuenta corriente cliente."""
    cliente = get_cliente(cid)
    if not cliente:
        raise ValueError("El cliente indicado no existe.")

    tipo_limpio = str(tipo or '').strip()
    if not tipo_limpio:
        raise ValueError("El tipo de movimiento es obligatorio.")
    if tipo_limpio.lower() == 'venta':
        raise ValueError("Las ventas fiadas deben generarse desde el Punto de Venta.")

    debe_valor = float(debe or 0)
    haber_valor = float(haber or 0)
    if debe_valor < 0 or haber_valor < 0:
        raise ValueError("Los importes no pueden ser negativos.")
    if debe_valor > 0 and haber_valor > 0:
        raise ValueError("Registrá un movimiento deudor o acreedor, no ambos a la vez.")
    if debe_valor <= 0 and haber_valor <= 0:
        raise ValueError("Ingresá un importe válido para el movimiento.")

    return agregar_movimiento_cliente(
        cid,
        tipo_limpio,
        numero_comprobante,
        debe=debe_valor,
        haber=haber_valor,
        vencimiento=vencimiento,
        observaciones=observaciones,
        fecha=fecha,
        medio_pago=medio_pago,
    )


def registrar_pago_cliente(
    cid,
    monto,
    numero_comprobante='',
    observaciones='',
    fecha=None,
    medio_pago='Efectivo',
):
    """Registra un pago de cliente y sincroniza caja si corresponde."""
    cliente = get_cliente(cid)
    if not cliente:
        raise ValueError("El cliente indicado no existe.")

    monto_valor = float(monto or 0)
    if monto_valor <= 0:
        raise ValueError("El monto del pago debe ser mayor a 0.")

    fecha_pago = fecha or datetime.now().strftime('%Y-%m-%d')
    medio_pago_limpio = str(medio_pago or '').strip() or 'Efectivo'
    caja_movimiento_id = None

    if medio_pago_limpio.lower() == 'efectivo':
        caja = get_caja_abierta()
        if not caja:
            raise ValueError("No hay una caja abierta para registrar pagos en efectivo.")
        fecha_caja = str(caja['fecha_apertura'] or '')[:10]
        if fecha_pago != fecha_caja:
            raise ValueError("No podés registrar pagos en efectivo fuera de la caja abierta actual.")
        motivo_caja = f"Pago CC cliente #{cid}: {cliente['nombre']}"
        if str(numero_comprobante or '').strip():
            motivo_caja += f" ({str(numero_comprobante).strip()})"
        caja_movimiento_id = registrar_movimiento_caja_abierta(
            "INGRESO",
            monto_valor,
            motivo_caja,
        )

    return agregar_movimiento_cliente(
        cid,
        "Pago",
        numero_comprobante,
        debe=0,
        haber=monto_valor,
        observaciones=observaciones,
        fecha=fecha_pago,
        medio_pago=medio_pago_limpio,
        caja_movimiento_id=caja_movimiento_id,
    )


def anular_movimiento_cliente(mid, motivo, usuario='', rol=''):
    """Anula un movimiento de cuenta corriente cliente sin borrar historial."""
    movimiento = get_movimiento_cliente(mid)
    if not movimiento:
        raise ValueError("El movimiento indicado no existe.")
    if int(movimiento['anulado'] or 0):
        raise ValueError("El movimiento ya está anulado.")

    tipo_limpio = str(movimiento['tipo'] or '').strip().lower()
    if int(movimiento['venta_id'] or 0) > 0 or tipo_limpio in {'venta', 'anulación venta', 'anulacion venta'}:
        raise ValueError("Este movimiento proviene de una venta. Anulá la venta desde Historial para conservar coherencia.")

    motivo_limpio = str(motivo or '').strip()
    if not motivo_limpio:
        raise ValueError("El motivo de anulación es obligatorio.")

    caja_movimiento_id = int(movimiento['caja_movimiento_id'] or 0)
    if caja_movimiento_id > 0:
        anular_caja_movimiento(
            caja_movimiento_id,
            f"Anulación de pago en cuenta corriente cliente: {motivo_limpio}",
            usuario=usuario,
        )

    marca_tiempo = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    q(
        """UPDATE cc_clientes_mov
        SET anulado=1, anulada_at=?, anulada_por=?, motivo_anulacion=?
        WHERE id=?""",
        (marca_tiempo, str(usuario or '').strip(), motivo_limpio, mid),
        commit=True,
    )
    registrar_auditoria(
        "ANULACION_CC_CLIENTE",
        "cc_cliente",
        mid,
        detalle=f"{movimiento['tipo'] or 'Movimiento'} · Cliente #{int(movimiento['cliente_id'] or 0)} · Comprobante: {movimiento['numero_comprobante'] or 'Sin comprobante'}",
        motivo=motivo_limpio,
        usuario=usuario,
        rol=rol,
    )
    return get_movimiento_cliente(mid)


def reconciliar_cc_clientes_desde_ventas():
    """Crea movimientos faltantes para ventas en cuenta corriente ya registradas."""
    ventas_pendientes = q(
        """
        SELECT v.id, v.cliente_id, v.fecha, v.numero_ticket, v.total
        FROM ventas v
        LEFT JOIN cc_clientes_mov m
               ON m.venta_id = v.id
              AND COALESCE(m.anulado, 0)=0
              AND LOWER(m.tipo)=LOWER('Venta')
        WHERE v.cliente_id > 0
          AND COALESCE(v.anulada, 0) = 0
          AND LOWER(v.medio_pago) = LOWER('Cuenta Corriente')
          AND m.id IS NULL
        ORDER BY v.id
        """
    )
    for venta in ventas_pendientes:
        agregar_movimiento_cliente(
            venta["cliente_id"],
            "Venta",
            f"TCK-{venta['numero_ticket']}",
            debe=float(venta["total"] or 0),
            haber=0,
            observaciones="Movimiento generado automaticamente desde venta en cuenta corriente.",
            fecha=venta["fecha"],
            venta_id=venta["id"],
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
    """Obtiene estadÃ­sticas de un cliente."""
    # Total de compras
    total_compras = q(
        "SELECT COUNT(*) as total, COALESCE(SUM(total),0) as monto FROM ventas WHERE cliente_id=? AND COALESCE(anulada, 0)=0",
        (cid,), fetchone=True
    )

    # Última compra
    ultima_compra = q(
        "SELECT fecha, total FROM ventas WHERE cliente_id=? AND COALESCE(anulada, 0)=0 ORDER BY fecha DESC LIMIT 1",
        (cid,), fetchone=True
    )

    return {
        'total_compras': total_compras['total'],
        'monto_total': total_compras['monto'],
        'ultima_compra': ultima_compra
    }


# â”€â”€â”€ PROVEEDORES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    """Saldo legado/auxiliar del proveedor basado en cc_proveedores_mov."""
    r = q(
        "SELECT COALESCE(SUM(debe),0)-COALESCE(SUM(haber),0) as saldo FROM cc_proveedores_mov WHERE proveedor_id=?",
        (pid,), fetchone=True
    )
    return r['saldo'] if r else 0


def get_facturas_proveedor(proveedor_id):
    """Obtiene facturas del proveedor para deuda comercial desde facturas_proveedores."""
    return q(
        """SELECT * FROM facturas_proveedores
        WHERE proveedor_id=?
        ORDER BY COALESCE(fecha, '') DESC, COALESCE(fecha_vencimiento, '') DESC, id DESC""",
        (proveedor_id,),
    )


def get_factura_proveedor(factura_id):
    """Devuelve una factura de proveedor por ID."""
    return q(
        "SELECT * FROM facturas_proveedores WHERE id=?",
        (factura_id,),
        fetchone=True,
    )


def get_factura_por_compra(compra_id):
    """Busca la factura comercial asociada a una compra."""
    return q(
        "SELECT * FROM facturas_proveedores WHERE compra_id=? AND COALESCE(anulada, 0)=0 ORDER BY id DESC LIMIT 1",
        (compra_id,),
        fetchone=True,
    )


def compra_tiene_factura(compra_id):
    """Indica si una compra ya genero factura comercial."""
    return get_factura_por_compra(compra_id) is not None


def crear_factura_proveedor(proveedor_id, numero_factura, fecha, fecha_vencimiento, importe, observaciones, compra_id=None, conn=None):
    """Crea una factura de proveedor para deuda comercial."""
    importe = float(importe or 0)
    if importe <= 0:
        raise ValueError("El importe de la factura debe ser mayor a cero.")
    if compra_id and compra_tiene_factura(compra_id):
        raise ValueError("La compra indicada ya tiene una factura comercial asociada.")

    params = (
        proveedor_id,
        compra_id,
        str(numero_factura or "").strip(),
        str(fecha or "").strip(),
        str(fecha_vencimiento or "").strip(),
        importe,
        str(observaciones or "").strip(),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    sql = """INSERT INTO facturas_proveedores
        (proveedor_id, compra_id, numero_factura, fecha, fecha_vencimiento, importe, pagado, observaciones, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)"""
    if conn is not None:
        c = conn.cursor()
        c.execute(sql, params)
        return c.lastrowid
    return q(sql, params, commit=True)


def actualizar_factura_proveedor(factura_id, numero_factura, fecha, fecha_vencimiento, importe, observaciones):
    """Actualiza una factura de proveedor sin perder trazabilidad de pagos."""
    factura = get_factura_proveedor(factura_id)
    if not factura:
        raise ValueError("La factura indicada no existe.")
    if int(factura["anulada"] or 0):
        raise ValueError("No se puede editar una factura anulada.")
    importe = float(importe or 0)
    pagado_actual = float(factura["pagado"] or 0)
    if importe <= 0:
        raise ValueError("El importe de la factura debe ser mayor a cero.")
    if pagado_actual > importe:
        raise ValueError("El importe no puede ser menor al total ya pagado.")
    q(
        """UPDATE facturas_proveedores
        SET numero_factura=?, fecha=?, fecha_vencimiento=?, importe=?, observaciones=?
        WHERE id=?""",
        (
            str(numero_factura or "").strip(),
            str(fecha or "").strip(),
            str(fecha_vencimiento or "").strip(),
            importe,
            str(observaciones or "").strip(),
            factura_id,
        ),
        commit=True,
    )


def registrar_pago_factura_proveedor(factura_id, monto):
    """Registra un pago parcial o total sobre una factura de proveedor."""
    factura = get_factura_proveedor(factura_id)
    if not factura:
        raise ValueError("La factura indicada no existe.")
    if int(factura["anulada"] or 0):
        raise ValueError("No se puede registrar un pago sobre una factura anulada.")
    monto = float(monto or 0)
    if monto <= 0:
        raise ValueError("El monto del pago debe ser mayor a cero.")
    importe = float(factura["importe"] or 0)
    pagado_actual = float(factura["pagado"] or 0)
    nuevo_pagado = pagado_actual + monto
    if nuevo_pagado > importe:
        raise ValueError("El pago no puede superar el importe pendiente de la factura.")
    q(
        "UPDATE facturas_proveedores SET pagado=? WHERE id=?",
        (nuevo_pagado, factura_id),
        commit=True,
    )


def eliminar_factura_proveedor(factura_id):
    """Compatibilidad: la eliminación física fue reemplazada por anulación segura."""
    return anular_factura_proveedor(factura_id)


def anular_factura_proveedor(factura_id, motivo='', usuario='', rol=''):
    """Marca una factura como anulada sin borrar historial ni pagos."""
    factura = get_factura_proveedor(factura_id)
    if not factura:
        raise ValueError("La factura indicada no existe.")
    if int(factura["anulada"] or 0):
        raise ValueError("La factura ya estÃ¡ anulada.")
    if float(factura["pagado"] or 0) > 0:
        raise ValueError("No se puede anular una factura con pagos registrados.")
    motivo_limpio = str(motivo or "").strip()
    if not motivo_limpio:
        raise ValueError("DebÃ©s indicar un motivo para anular la factura.")
    q(
        """UPDATE facturas_proveedores
        SET anulada=1, anulada_at=?, anulada_por=?, motivo_anulacion=?
        WHERE id=?""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(usuario or "").strip(), motivo_limpio, factura_id),
        commit=True,
    )
    registrar_auditoria(
        "ANULACION_FACTURA_PROVEEDOR",
        "factura_proveedor",
        factura_id,
        detalle=f"Proveedor #{int(factura['proveedor_id'] or 0)} · Factura: {factura['numero_factura'] or f'#{factura_id}'} · Importe: {float(factura['importe'] or 0):.2f}",
        motivo=motivo_limpio,
        usuario=usuario,
        rol=rol,
    )


def crear_factura_desde_compra(compra_id, proveedor_id, total, numero_factura=None, fecha=None, fecha_vencimiento=None, observaciones=None, conn=None):
    """Crea una factura comercial asociada a una compra, evitando duplicados."""
    if not proveedor_id or int(proveedor_id) <= 0:
        raise ValueError("La compra a cuenta corriente requiere un proveedor valido.")
    if compra_tiene_factura(compra_id):
        return get_factura_por_compra(compra_id)

    fecha_factura = str(fecha or "").strip()
    if not fecha_factura:
        compra = get_compra(compra_id)
        fecha_factura = str((compra["fecha"] if compra else "") or datetime.now().strftime("%Y-%m-%d")).strip()

    numero = str(numero_factura or "").strip() or f"COMPRA-{compra_id}"
    factura_id = crear_factura_proveedor(
        proveedor_id,
        numero,
        fecha_factura,
        fecha_vencimiento,
        total,
        observaciones,
        compra_id=compra_id,
        conn=conn,
    )
    if conn is not None:
        c = conn.cursor()
        return c.execute("SELECT * FROM facturas_proveedores WHERE id=?", (factura_id,)).fetchone()
    return get_factura_proveedor(factura_id)


def get_deuda_proveedor_desde_facturas(proveedor_id):
    """Calcula deuda comercial del proveedor desde facturas_proveedores."""
    facturas = get_facturas_proveedor(proveedor_id)
    return calcular_deuda_proveedor_desde_facturas(facturas)


def get_resumen_facturas_proveedor(proveedor_id):
    """Resume deuda, saldos y estados calculados de facturas del proveedor."""
    facturas = get_facturas_proveedor(proveedor_id)
    resumen = {
        "total_facturas": 0,
        "total_facturado": 0.0,
        "total_pagado": 0.0,
        "deuda_total": 0.0,
        "facturas_pendientes": 0,
        "facturas_pagadas": 0,
        "facturas_vencidas": 0,
        "facturas_por_vencer": 0,
    }
    for factura in facturas:
        saldo = calcular_saldo_factura(factura)
        estado = calcular_estado_factura(factura)
        resumen["total_facturas"] += 1
        resumen["total_facturado"] += float(factura["importe"] or 0)
        resumen["total_pagado"] += float(factura["pagado"] or 0)
        if saldo > 0:
            resumen["deuda_total"] += saldo
            resumen["facturas_pendientes"] += 1
        else:
            resumen["facturas_pagadas"] += 1
        if estado == "VENCIDA":
            resumen["facturas_vencidas"] += 1
        elif estado == "POR VENCER":
            resumen["facturas_por_vencer"] += 1
    return resumen


def get_facturas_proveedores_vencidas():
    """Devuelve facturas vencidas pendientes de pago con nombre de proveedor."""
    rows = q(
        """SELECT fp.*, p.nombre as proveedor_nombre
        FROM facturas_proveedores fp
        JOIN proveedores p ON p.id = fp.proveedor_id
        WHERE COALESCE(fp.anulada, 0)=0
        ORDER BY COALESCE(fp.fecha_vencimiento, '') ASC, fp.id DESC"""
    )
    return [row for row in rows if calcular_estado_factura(row) == "VENCIDA"]


def get_facturas_proveedores_por_vencer(dias=7):
    """Devuelve facturas pendientes cuyo vencimiento cae dentro de los proximos N dias."""
    dias = int(dias or 0)
    if dias <= 0:
        dias = 7
    hoy = date.today()
    rows = q(
        """SELECT fp.*, p.nombre as proveedor_nombre
        FROM facturas_proveedores fp
        JOIN proveedores p ON p.id = fp.proveedor_id
        WHERE COALESCE(fp.anulada, 0)=0
        ORDER BY COALESCE(fp.fecha_vencimiento, '') ASC, fp.id DESC"""
    )
    resultado = []
    for row in rows:
        estado = calcular_estado_factura(row)
        if estado == "PAGADA":
            continue
        fecha_vencimiento = str(row["fecha_vencimiento"] or "").strip()
        if not fecha_vencimiento:
            continue
        try:
            vencimiento = date.fromisoformat(fecha_vencimiento)
        except ValueError:
            continue
        delta = (vencimiento - hoy).days
        if 0 <= delta <= dias:
            resultado.append(row)
    return resultado


def get_total_deuda_proveedores():
    """Suma la deuda comercial pendiente de todos los proveedores."""
    rows = q("SELECT importe, pagado, anulada FROM facturas_proveedores WHERE COALESCE(anulada, 0)=0")
    return calcular_deuda_proveedor_desde_facturas(rows)


def get_cantidad_facturas_proveedores_pendientes():
    """Cuenta facturas de proveedores con saldo pendiente."""
    rows = q("SELECT importe, pagado, anulada FROM facturas_proveedores WHERE COALESCE(anulada, 0)=0")
    return sum(1 for row in rows if calcular_saldo_factura(row) > 0)


def get_cantidad_facturas_proveedores_vencidas():
    return len(get_facturas_proveedores_vencidas())


def get_cantidad_facturas_proveedores_por_vencer(dias=7):
    return len(get_facturas_proveedores_por_vencer(dias=dias))


def get_total_deuda_clientes():
    """Suma la deuda actual de clientes desde cc_clientes_mov."""
    row = q(
        """SELECT COALESCE(SUM(saldo), 0) as total
        FROM (
            SELECT COALESCE(SUM(debe),0) - COALESCE(SUM(haber),0) as saldo
            FROM cc_clientes_mov
            WHERE COALESCE(anulado, 0)=0
            GROUP BY cliente_id
            HAVING saldo > 0
        )""",
        fetchone=True,
    )
    return float(row["total"] or 0) if row else 0.0


def get_cantidad_clientes_con_deuda():
    """Cuenta clientes con saldo deudor."""
    row = q(
        """SELECT COUNT(*) as total
        FROM (
            SELECT cliente_id
            FROM cc_clientes_mov
            WHERE COALESCE(anulado, 0)=0
            GROUP BY cliente_id
            HAVING COALESCE(SUM(debe),0) - COALESCE(SUM(haber),0) > 0
        )""",
        fetchone=True,
    )
    return int(row["total"] or 0) if row else 0


def get_clientes_con_deuda(limit=5):
    """Devuelve una lista corta de clientes con deuda ordenados por saldo."""
    rows = q(
        """SELECT clientes.id, clientes.nombre, clientes.codigo,
                  COALESCE(SUM(cc_clientes_mov.debe),0) - COALESCE(SUM(cc_clientes_mov.haber),0) as saldo
           FROM clientes
           JOIN cc_clientes_mov ON cc_clientes_mov.cliente_id = clientes.id
           WHERE clientes.activo = 1
             AND COALESCE(cc_clientes_mov.anulado, 0)=0
           GROUP BY clientes.id, clientes.nombre, clientes.codigo
           HAVING saldo > 0
           ORDER BY saldo DESC, clientes.nombre ASC
           LIMIT ?""",
        (limit,),
    )
    return rows or []


def get_facturas_proveedores_vencidas_resumen(limit=5):
    """Lista corta de facturas vencidas con saldo calculado."""
    rows = get_facturas_proveedores_vencidas()
    resultado = []
    for row in rows[:limit]:
        resultado.append({
            **dict(row),
            "saldo": calcular_saldo_factura(row),
            "estado": calcular_estado_factura(row),
        })
    return resultado


def get_facturas_proveedores_por_vencer_resumen(dias=7, limit=5):
    """Lista corta de facturas por vencer con saldo calculado."""
    rows = get_facturas_proveedores_por_vencer(dias=dias)
    resultado = []
    for row in rows[:limit]:
        resultado.append({
            **dict(row),
            "saldo": calcular_saldo_factura(row),
            "estado": calcular_estado_factura(row),
        })
    return resultado


def get_resumen_dashboard_financiero(dias_por_vencer=7):
    """Agrupa KPIs financieros seguros para el dashboard."""
    return {
        "deuda_proveedores": get_total_deuda_proveedores(),
        "facturas_pendientes": get_cantidad_facturas_proveedores_pendientes(),
        "facturas_vencidas": get_cantidad_facturas_proveedores_vencidas(),
        "facturas_por_vencer": get_cantidad_facturas_proveedores_por_vencer(dias=dias_por_vencer),
        "deuda_clientes": get_total_deuda_clientes(),
        "clientes_con_deuda": get_cantidad_clientes_con_deuda(),
    }


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
    """Obtiene estadÃ­sticas de un proveedor."""
    total_compras = q(
        "SELECT COUNT(*) as total, COALESCE(SUM(total),0) as monto FROM compras WHERE proveedor_id=? AND COALESCE(anulada, 0)=0",
        (pid,), fetchone=True
    )

    ultima_compra = q(
        "SELECT fecha, total FROM compras WHERE proveedor_id=? AND COALESCE(anulada, 0)=0 ORDER BY fecha DESC LIMIT 1",
        (pid,), fetchone=True
    )

    return {
        'total_compras': total_compras['total'],
        'monto_total': total_compras['monto'],
        'ultima_compra': ultima_compra
    }


# â”€â”€â”€ VENTAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    """Retorna ventas filtradas por bÃºsqueda, fecha y medio de pago (Paso 18)."""
    params = []
    condiciones = []

    if search:
        # Buscamos por nombre de cliente, nÃºmero de ticket o ID interno
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


def get_medios_pago_ventas():
    """Devuelve los medios de pago usados en ventas."""
    return q(
        """SELECT DISTINCT medio_pago
        FROM ventas
        WHERE medio_pago IS NOT NULL AND TRIM(medio_pago) <> ''
        ORDER BY medio_pago"""
    )


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
            (venta_id,producto_id,codigo_interno,descripcion,categoria,unidad,cantidad,precio_unitario,costo_unitario,iva,descuento,subtotal)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (venta_id, item.get('producto_id', 0), item.get('codigo_interno', ''), item.get('descripcion', ''),
             item.get('categoria', ''), item.get('unidad', ''), item.get('cantidad', 1),
             item.get('precio_unitario', 0), item.get('costo_unitario', 0), item.get('iva', ''),
             item.get('descuento', 0), item.get('subtotal', 0))
        )

    conn.commit()
    conn.close()
    return venta_id


def delete_venta(venta_id):
    """Compatibilidad: la eliminación física fue reemplazada por anulación segura."""
    return anular_venta(venta_id)


def anular_venta(venta_id, motivo='', usuario='', rol=''):
    """Marca una venta como anulada y restaura stock una sola vez."""
    conn = get_conn()
    try:
        c = conn.cursor()
        venta = c.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
        if not venta:
            raise ValueError("La venta indicada no existe.")
        if int(venta["anulada"] or 0):
            raise ValueError("La venta ya estÃ¡ anulada.")

        items = c.execute("SELECT * FROM ventas_detalle WHERE venta_id=?", (venta_id,)).fetchall()
        motivo_movimiento = f"Anulación venta #{venta_id}"
        for item in items:
            producto_id = int(item["producto_id"] or 0)
            cantidad = float(item["cantidad"] or 0)
            if producto_id <= 0 or cantidad <= 0:
                continue

            stock = c.execute("SELECT stock_actual, stock_minimo, stock_maximo, proveedor_habitual FROM stock WHERE producto_id=?", (producto_id,)).fetchone()
            if stock:
                stock_anterior = float(stock["stock_actual"] or 0)
                stock_nuevo = stock_anterior + cantidad
                c.execute("UPDATE stock SET stock_actual=? WHERE producto_id=?", (stock_nuevo, producto_id))
            else:
                stock_anterior = 0.0
                stock_nuevo = cantidad
                c.execute(
                    "INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo, proveedor_habitual) VALUES (?,?,?,?,?)",
                    (producto_id, stock_nuevo, 5, 50, ""),
                )

            c.execute(
                """INSERT INTO stock_movimientos
                (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo)
                VALUES (?,?,?,?,?,?)""",
                (producto_id, 'ANULACION_VENTA', cantidad, stock_anterior, stock_nuevo, motivo_movimiento),
            )

        if (
            int(venta["cliente_id"] or 0) > 0
            and str(venta["medio_pago"] or "").strip().lower() == "cuenta corriente"
        ):
            movimiento_original = c.execute(
                "SELECT id FROM cc_clientes_mov WHERE venta_id=? AND COALESCE(anulado, 0)=0 AND LOWER(tipo)=LOWER('Venta') LIMIT 1",
                (venta_id,),
            ).fetchone()
            movimiento_compensacion = c.execute(
                "SELECT id FROM cc_clientes_mov WHERE venta_id=? AND LOWER(tipo)=LOWER('Anulación venta') LIMIT 1",
                (venta_id,),
            ).fetchone()
            if movimiento_original and not movimiento_compensacion:
                c.execute(
                    """INSERT INTO cc_clientes_mov
                    (cliente_id, fecha, tipo, numero_comprobante, debe, haber, vencimiento, observaciones, venta_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        int(venta["cliente_id"] or 0),
                        venta["fecha"] or datetime.now().strftime('%Y-%m-%d'),
                        "Anulación venta",
                        f"TCK-{venta['numero_ticket']}",
                        0,
                        float(venta["total"] or 0),
                        '',
                        str(motivo or "Compensación automática por anulación de venta.").strip(),
                        venta_id,
                    ),
                )

        marca_tiempo = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            """UPDATE ventas
            SET anulada=1, anulada_at=?, anulada_por=?, motivo_anulacion=?
            WHERE id=?""",
            (marca_tiempo, str(usuario or '').strip(), str(motivo or '').strip(), venta_id),
        )
        conn.commit()
        registrar_auditoria(
            "ANULACION_VENTA",
            "venta",
            venta_id,
            detalle=f"Ticket #{venta['numero_ticket'] or venta_id} · Cliente: {venta['cliente_nombre'] or 'Mostrador'} · Total: {float(venta['total'] or 0):.2f}",
            motivo=motivo,
            usuario=usuario,
            rol=rol,
        )
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# â”€â”€â”€ COMPRAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_compras(search='', fecha_desde='', fecha_hasta='', limit=200):
    """Devuelve compras filtrables."""
    sql = """
        SELECT compras.*,
               (
                   SELECT fp.id
                   FROM facturas_proveedores fp
                   WHERE fp.compra_id = compras.id
                   ORDER BY fp.id DESC
                   LIMIT 1
               ) as factura_proveedor_id,
               (
                   SELECT fp.numero_factura
                   FROM facturas_proveedores fp
                   WHERE fp.compra_id = compras.id
                   ORDER BY fp.id DESC
                   LIMIT 1
               ) as factura_proveedor_numero
        FROM compras
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (compras.descripcion LIKE ? OR compras.numero_remito LIKE ? OR compras.proveedor_nombre LIKE ?)"
        params += [f'%{search}%'] * 3
    if fecha_desde:
        sql += " AND compras.fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        sql += " AND compras.fecha <= ?"
        params.append(fecha_hasta)
    sql += " ORDER BY compras.fecha DESC, compras.id DESC LIMIT ?"
    params.append(limit)
    return q(sql, params)


def get_compra(cid):
    """Devuelve una compra por ID."""
    return q(
        """SELECT compras.*,
               (
                   SELECT fp.id
                   FROM facturas_proveedores fp
                   WHERE fp.compra_id = compras.id
                   ORDER BY fp.id DESC
                   LIMIT 1
               ) as factura_proveedor_id,
               (
                   SELECT fp.numero_factura
                   FROM facturas_proveedores fp
                   WHERE fp.compra_id = compras.id
                   ORDER BY fp.id DESC
                   LIMIT 1
               ) as factura_proveedor_numero
        FROM compras
        WHERE compras.id=?""",
        (cid,),
        fetchone=True,
    )


def get_detalle_compra(compra_id):
    """Alias seguro para obtener el detalle actual de una compra."""
    return get_compra(compra_id)


def actualizar_compra_basica(compra_id, proveedor_id, fecha, observaciones, condicion_pago=None, numero_remito=None, proveedor_nombre=None):
    """Actualiza solo metadatos seguros de la compra, sin tocar stock ni detalle."""
    compra = get_compra(compra_id)
    if not compra:
        raise ValueError("La compra indicada no existe.")

    proveedor_id = int(proveedor_id or 0)
    if proveedor_nombre is None:
        proveedor = get_proveedor(proveedor_id) if proveedor_id > 0 else None
        proveedor_nombre = proveedor["nombre"] if proveedor else ""

    q(
        """UPDATE compras
        SET fecha=?, numero_remito=?, proveedor_id=?, proveedor_nombre=?, observaciones=?
        WHERE id=?""",
        (
            str(fecha or compra["fecha"] or "").strip(),
            str(compra["numero_remito"] if numero_remito is None else numero_remito or "").strip(),
            proveedor_id,
            str(proveedor_nombre or "").strip(),
            str(observaciones or "").strip(),
            compra_id,
        ),
        commit=True,
    )


def actualizar_factura_compra_basica(factura_id, numero_factura, fecha, fecha_vencimiento, observaciones, proveedor_id=None):
    """Actualiza metadatos seguros de la factura asociada a una compra, sin tocar importe ni pagos."""
    factura = get_factura_proveedor(factura_id)
    if not factura:
        raise ValueError("La factura indicada no existe.")

    proveedor_final = int(proveedor_id or factura["proveedor_id"] or 0)
    q(
        """UPDATE facturas_proveedores
        SET proveedor_id=?, numero_factura=?, fecha=?, fecha_vencimiento=?, observaciones=?
        WHERE id=?""",
        (
            proveedor_final,
            str(numero_factura or "").strip(),
            str(fecha or "").strip(),
            str(fecha_vencimiento or "").strip(),
            str(observaciones or "").strip(),
            factura_id,
        ),
        commit=True,
    )


def update_compra(cid, data):
    """Actualiza una compra."""
    compra_actual = get_compra(cid)
    if not compra_actual:
        return

    conn = get_conn()
    c = conn.cursor()

    producto_anterior = int(compra_actual['producto_id'] or 0)
    cantidad_anterior = float(compra_actual['cantidad'] or 0)
    proveedor_nuevo = int(data.get('proveedor_id', 0) or 0)
    producto_nuevo = int(data.get('producto_id', 0) or 0)
    cantidad_nueva = float(data.get('cantidad', 1) or 0)
    costo_nuevo = float(data.get('costo_unitario', 0) or 0)
    total_nuevo = float(data.get('total', 0) or 0)
    fecha_nueva = data.get('fecha', datetime.now().strftime('%Y-%m-%d'))

    if producto_anterior > 0 and cantidad_anterior > 0:
        stock = c.execute("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_anterior,)).fetchone()
        if stock:
            c.execute(
                "UPDATE stock SET stock_actual=? WHERE producto_id=?",
                (float(stock['stock_actual'] or 0) - cantidad_anterior, producto_anterior)
            )

    if producto_nuevo > 0 and cantidad_nueva > 0:
        stock = c.execute("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_nuevo,)).fetchone()
        if stock:
            c.execute(
                "UPDATE stock SET stock_actual=?, ultimo_ingreso=? WHERE producto_id=?",
                (float(stock['stock_actual'] or 0) + cantidad_nueva, fecha_nueva, producto_nuevo)
            )
        if costo_nuevo > 0:
            c.execute("UPDATE productos SET costo=? WHERE id=?", (costo_nuevo, producto_nuevo))

    c.execute(
        """UPDATE compras SET fecha=?,numero_remito=?,proveedor_id=?,proveedor_nombre=?,producto_id=?,codigo_interno=?,descripcion=?,cantidad=?,costo_unitario=?,total=?,observaciones=? WHERE id=?""",
        (fecha_nueva, data.get('numero_remito', ''),
         proveedor_nuevo, data.get('proveedor_nombre', ''), producto_nuevo,
         data.get('codigo_interno', ''), data.get('descripcion', ''), cantidad_nueva,
         costo_nuevo, total_nuevo, data.get('observaciones', ''), cid)
    )
    conn.commit()
    conn.close()


def delete_compra(cid):
    """Compatibilidad: la eliminación física fue reemplazada por anulación segura."""
    return anular_compra(cid)


def anular_compra(compra_id, motivo='', usuario='', rol=''):
    """Marca una compra como anulada y revierte stock una sola vez."""
    compra_actual = get_compra(compra_id)
    if not compra_actual:
        raise ValueError("La compra indicada no existe.")
    if int(compra_actual["anulada"] or 0):
        raise ValueError("La compra ya estÃ¡ anulada.")

    factura_asociada = get_factura_por_compra(compra_id)
    if factura_asociada:
        raise ValueError("No se puede anular automÃ¡ticamente una compra asociada a cuenta corriente proveedor. AnulÃ¡ o ajustÃ¡ primero la factura/proveedor.")

    conn = get_conn()
    try:
        c = conn.cursor()
        producto_id = int(compra_actual['producto_id'] or 0)
        cantidad = float(compra_actual['cantidad'] or 0)
        if producto_id > 0 and cantidad > 0:
            stock = c.execute("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,)).fetchone()
            stock_actual = float(stock['stock_actual'] or 0) if stock else 0.0
            if stock_actual < cantidad:
                raise ValueError("No se puede anular porque el stock actual es menor a la cantidad ingresada. AjustÃ¡ stock o revisÃ¡ movimientos.")
            stock_nuevo = stock_actual - cantidad
            c.execute(
                "UPDATE stock SET stock_actual=? WHERE producto_id=?",
                (stock_nuevo, producto_id)
            )
            c.execute(
                """INSERT INTO stock_movimientos
                (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo)
                VALUES (?,?,?,?,?,?)""",
                (producto_id, 'ANULACION_COMPRA', -cantidad, stock_actual, stock_nuevo, f'AnulaciÃ³n compra #{compra_id}'),
            )

        marca_tiempo = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            """UPDATE compras
            SET anulada=1, anulada_at=?, anulada_por=?, motivo_anulacion=?
            WHERE id=?""",
            (marca_tiempo, str(usuario or '').strip(), str(motivo or '').strip(), compra_id),
        )
        conn.commit()
        registrar_auditoria(
            "ANULACION_COMPRA",
            "compra",
            compra_id,
            detalle=f"Remito: {compra_actual['numero_remito'] or f'#{compra_id}'} · Proveedor: {compra_actual['proveedor_nombre'] or 'Sin proveedor'} · Total: {float(compra_actual['total'] or 0):.2f}",
            motivo=motivo,
            usuario=usuario,
            rol=rol,
        )
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def add_compra(data, conn=None):
    """Agrega una compra."""
    params = (
        data.get('fecha', datetime.now().strftime('%Y-%m-%d')),
        data.get('numero_remito', ''),
        data.get('proveedor_id', 0),
        data.get('proveedor_nombre', ''),
        data.get('producto_id', 0),
        data.get('codigo_interno', ''),
        data.get('descripcion', ''),
        float(data.get('cantidad', 1)),
        float(data.get('costo_unitario', 0)),
        float(data.get('total', 0)),
        data.get('observaciones', ''),
    )

    if conn is not None:
        c = conn.cursor()
        c.execute(
            """INSERT INTO compras
            (fecha,numero_remito,proveedor_id,proveedor_nombre,producto_id,codigo_interno,descripcion,cantidad,costo_unitario,total,observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            params,
        )
        compra_id = c.lastrowid
        if data.get('producto_id') and float(data.get('cantidad', 1)) > 0:
            _incrementar_stock_compra_tx(conn, int(data.get('producto_id')), float(data.get('cantidad', 1)), compra_id)
        return compra_id

    compra_id = q(
        """INSERT INTO compras
        (fecha,numero_remito,proveedor_id,proveedor_nombre,producto_id,codigo_interno,descripcion,cantidad,costo_unitario,total,observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        params,
        fetchall=False,
        commit=True
    )

    if data.get('producto_id') and float(data.get('cantidad', 1)) > 0:
        incrementar_stock_compra(int(data.get('producto_id')), float(data.get('cantidad', 1)), compra_id)

    return compra_id


def _incrementar_stock_compra_tx(conn, producto_id, cantidad, compra_id=None):
    """Version transaccional de incremento de stock para compras."""
    if cantidad <= 0:
        return

    c = conn.cursor()
    stock_actual = c.execute("SELECT * FROM stock WHERE producto_id=?", (producto_id,)).fetchone()
    if stock_actual:
        nuevo = float(stock_actual['stock_actual'] or 0) + cantidad
        c.execute("UPDATE stock SET stock_actual=? WHERE producto_id=?", (nuevo, producto_id))
        stock_anterior = float(stock_actual['stock_actual'] or 0)
    else:
        c.execute(
            "INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo, ultimo_ingreso, proveedor_habitual) VALUES (?,?,?,?,?,?)",
            (producto_id, cantidad, 5, 50, datetime.now().strftime('%Y-%m-%d'), ''),
        )
        stock_anterior = 0.0
        nuevo = cantidad

    c.execute(
        """INSERT INTO stock_movimientos
        (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo)
        VALUES (?,?,?,?,?,?)""",
        (
            producto_id,
            'COMPRA',
            cantidad,
            stock_anterior,
            nuevo,
            f'Compra #{compra_id}' if compra_id else 'Compra',
        ),
    )


def add_compra_con_factura(data, factura_data=None):
    """Registra compra y factura comercial en una sola transaccion si corresponde."""
    conn = get_conn()
    try:
        compra_id = add_compra(data, conn=conn)
        if factura_data and str(factura_data.get("condicion_pago", "")).strip().lower() == "cuenta_corriente":
            crear_factura_desde_compra(
                compra_id=compra_id,
                proveedor_id=int(data.get("proveedor_id", 0) or 0),
                total=float(data.get("total", 0) or 0),
                numero_factura=factura_data.get("numero_factura"),
                fecha=factura_data.get("fecha_factura") or data.get("fecha"),
                fecha_vencimiento=factura_data.get("fecha_vencimiento"),
                observaciones=factura_data.get("observaciones_factura") or data.get("observaciones"),
                conn=conn,
            )
        conn.commit()
        return compra_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# â”€â”€â”€ CAJA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_caja_dia(fecha):
    """Devuelve caja del dÃ­a."""
    return q("SELECT * FROM caja_historial WHERE fecha=?", (fecha,), fetchone=True)


def get_caja_abierta():
    """Devuelve la caja actualmente abierta o None."""
    return q("SELECT * FROM caja WHERE estado=1 ORDER BY id DESC LIMIT 1", fetchone=True)


def get_caja_movimiento(mid):
    """Obtiene un movimiento de caja con estado de su caja."""
    return q(
        """SELECT cm.*, c.estado as caja_estado, c.fecha_apertura, c.fecha_cierre
        FROM caja_movimientos cm
        LEFT JOIN caja c ON c.id = cm.caja_id
        WHERE cm.id=?""",
        (mid,),
        fetchone=True,
    )


def get_caja_movimiento_activo_por_gasto(gasto_id):
    """Devuelve el ultimo movimiento activo asociado a un gasto."""
    return q(
        """SELECT cm.*, c.estado as caja_estado, c.fecha_apertura, c.fecha_cierre
        FROM caja_movimientos cm
        LEFT JOIN caja c ON c.id = cm.caja_id
        WHERE cm.gasto_id=? AND COALESCE(cm.anulado, 0)=0
        ORDER BY cm.id DESC LIMIT 1""",
        (gasto_id,),
        fetchone=True,
    )


def crear_movimiento_caja(caja_id, tipo, monto, motivo, gasto_id=None, movimiento_origen_id=None):
    """Crea un movimiento de caja inmutable."""
    return q(
        """INSERT INTO caja_movimientos
        (caja_id,tipo,monto,motivo,gasto_id,movimiento_origen_id)
        VALUES (?,?,?,?,?,?)""",
        (caja_id, tipo, float(monto or 0), motivo, gasto_id, movimiento_origen_id),
        fetchall=False,
        commit=True,
    )


def registrar_movimiento_caja_abierta(tipo, monto, motivo, gasto_id=None, movimiento_origen_id=None):
    """Registra un movimiento solo si hay una caja abierta."""
    caja = get_caja_abierta()
    if not caja:
        raise ValueError("No hay una caja abierta para registrar movimientos.")
    return crear_movimiento_caja(
        caja["id"],
        tipo,
        monto,
        motivo,
        gasto_id=gasto_id,
        movimiento_origen_id=movimiento_origen_id,
    )


def anular_caja_movimiento(mid, motivo, usuario="", permitir_vinculado_gasto=False):
    """Marca un movimiento de caja como anulado sin borrarlo."""
    movimiento = get_caja_movimiento(mid)
    if not movimiento:
        raise ValueError("El movimiento de caja indicado no existe.")
    if int(movimiento["anulado"] or 0):
        raise ValueError("El movimiento seleccionado ya estÃ¡ anulado.")
    if int(movimiento["gasto_id"] or 0) > 0 and not permitir_vinculado_gasto:
        raise ValueError("Este movimiento estÃ¡ vinculado a un gasto. Modificalo desde Gastos para conservar coherencia.")
    if int(movimiento["caja_estado"] or 0) != 1:
        raise ValueError("No se pueden anular movimientos de una caja cerrada.")
    motivo_limpio = str(motivo or "").strip()
    if not motivo_limpio:
        raise ValueError("El motivo de anulación es obligatorio.")
    marca_tiempo = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    q(
        """UPDATE caja_movimientos
        SET anulado=1, anulada_at=?, anulada_por=?, motivo_anulacion=?
        WHERE id=?""",
        (marca_tiempo, str(usuario or "").strip(), motivo_limpio, mid),
        commit=True,
    )
    return get_caja_movimiento(mid)


def validar_operacion_gasto_caja(gid, nuevo_data=None, deleting=False):
    """Bloquea cambios destructivos de gastos que impactan cajas cerradas."""
    movimiento = get_caja_movimiento_activo_por_gasto(gid)
    if not movimiento:
        return
    if int(movimiento["caja_estado"] or 0) == 1:
        return
    gasto = q("SELECT * FROM gastos WHERE id=?", (gid,), fetchone=True)
    if not gasto:
        return
    if deleting:
        raise ValueError("No podÃ©s eliminar este gasto porque impacta una caja cerrada.")
    if not nuevo_data:
        return
    campos_sensibles = ("fecha", "medio_pago", "monto", "descripcion", "categoria")
    for campo in campos_sensibles:
        actual = str(gasto[campo] if gasto[campo] is not None else "").strip()
        nuevo = str(nuevo_data.get(campo, "") if nuevo_data.get(campo) is not None else "").strip()
        if campo == "monto":
            try:
                if float(actual or 0) != float(nuevo or 0):
                    raise ValueError("No podÃ©s modificar este gasto porque impacta una caja cerrada.")
            except ValueError:
                raise ValueError("No podÃ©s modificar este gasto porque impacta una caja cerrada.")
            continue
        if actual != nuevo:
            raise ValueError("No podÃ©s modificar este gasto porque impacta una caja cerrada.")


def sync_gasto_caja_movimiento(gasto_id):
    """Sincroniza el gasto con caja si fue pagado en efectivo durante la caja abierta."""
    gasto = q("SELECT * FROM gastos WHERE id=?", (gasto_id,), fetchone=True)
    movimiento = get_caja_movimiento_activo_por_gasto(gasto_id)

    if not gasto:
        if movimiento:
            anular_caja_movimiento(
                movimiento["id"],
                "AnulaciÃ³n automÃ¡tica por eliminaciÃ³n del gasto asociado.",
                usuario="sistema",
                permitir_vinculado_gasto=True,
            )
        return

    if int(gasto["anulado"] or 0):
        if movimiento:
            anular_caja_movimiento(
                movimiento["id"],
                "Anulación automática por anulación del gasto asociado.",
                usuario="sistema",
                permitir_vinculado_gasto=True,
            )
        return

    caja = get_caja_abierta()
    fecha_caja = str(caja["fecha_apertura"])[:10] if caja else ""
    medio_pago = str(gasto["medio_pago"] or "").strip().lower()
    aplica_caja = bool(caja and medio_pago == "efectivo" and str(gasto["fecha"] or "") == fecha_caja)
    motivo = f"Gasto #{gasto_id}: {gasto['descripcion'] or gasto['categoria'] or 'Gasto operativo'}"
    monto = float(gasto["monto"] or 0)
    movimiento_original_id = None

    if aplica_caja:
        reemplazar = bool(
            movimiento
            and (
                int(movimiento["caja_id"] or 0) != int(caja["id"] or 0)
                or str(movimiento["tipo"] or "").strip().upper() != "EGRESO"
                or float(movimiento["monto"] or 0) != monto
                or str(movimiento["motivo"] or "").strip() != motivo
            )
        )
        if reemplazar:
            movimiento_original_id = int(movimiento["id"] or 0)
            anular_caja_movimiento(
                movimiento["id"],
                "AnulaciÃ³n automÃ¡tica por actualizaciÃ³n del gasto asociado.",
                usuario="sistema",
                permitir_vinculado_gasto=True,
            )
            movimiento = None
        if not movimiento:
            crear_movimiento_caja(
                caja["id"],
                "EGRESO",
                monto,
                motivo,
                gasto_id=gasto_id,
                movimiento_origen_id=movimiento_original_id,
            )
    elif movimiento:
        anular_caja_movimiento(
            movimiento["id"],
            "AnulaciÃ³n automÃ¡tica porque el gasto dejÃ³ de impactar caja.",
            usuario="sistema",
            permitir_vinculado_gasto=True,
        )


def init_caja_dia(fecha):
    """Inicializa caja del dÃ­a."""
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
    """Cierra la caja del dÃ­a."""
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


# â”€â”€â”€ GASTOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


def get_gasto(gid):
    """Obtiene un gasto por ID."""
    return q("SELECT * FROM gastos WHERE id=?", (gid,), fetchone=True)


def _gastos_activos_cond(alias=''):
    prefijo = f"{alias}." if alias else ""
    return f"COALESCE({prefijo}anulado, 0)=0"


def validar_gasto_efectivo_contra_caja(data):
    """Bloquea gastos en efectivo fuera de una caja abierta valida."""
    medio_pago = str(data.get('medio_pago', '') or '').strip().lower()
    if medio_pago != 'efectivo':
        return
    caja = get_caja_abierta()
    if not caja:
        raise ValueError("No podÃ©s registrar gastos con efectivo porque no hay una caja abierta.")
    fecha_gasto = str(data.get('fecha', '') or '').strip()
    fecha_caja = str(caja['fecha_apertura'] or '')[:10]
    if fecha_gasto != fecha_caja:
        raise ValueError("No podÃ©s registrar gastos con efectivo fuera de la caja abierta actual.")


def add_gasto(data):
    """Agrega un gasto."""
    validar_gasto_efectivo_contra_caja(data)
    categoria = data.get('categoria', '')
    necesario = normalizar_tipo_gasto(data.get('necesario'))
    if 'necesario' not in data:
        necesario = get_tipo_gasto_categoria(categoria)
    clasificacion = normalizar_clasificacion_gasto(data.get('clasificacion'), categoria)
    gasto_id = q(
        """INSERT INTO gastos
        (fecha,tipo,categoria,clasificacion,descripcion,monto,iva_incluido,medio_pago,proveedor,necesario,comprobante,observaciones)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (data.get('fecha', datetime.now().strftime('%Y-%m-%d')), data.get('tipo', 'Gasto'),
         categoria, clasificacion, data.get('descripcion', ''), float(data.get('monto', 0)),
         int(data.get('iva_incluido', 1)), data.get('medio_pago', 'Efectivo'), data.get('proveedor', ''),
         necesario, data.get('comprobante', ''), data.get('observaciones', '')),
        fetchall=False, commit=True
    )
    sync_gasto_caja_movimiento(gasto_id)
    return gasto_id


def update_gasto(gid, data):
    """Actualiza un gasto."""
    gasto_actual = get_gasto(gid)
    if not gasto_actual:
        raise ValueError("El gasto indicado no existe.")
    if int(gasto_actual["anulado"] or 0):
        raise ValueError("El gasto seleccionado ya está anulado.")
    raise ValueError("Los gastos registrados no se editan para conservar caja y reportes. Anulalo y cargalo nuevamente.")


def anular_gasto(gid, motivo='', usuario='', rol=''):
    """Anula un gasto sin borrarlo para conservar historial y coherencia."""
    gasto = get_gasto(gid)
    if not gasto:
        raise ValueError("El gasto indicado no existe.")
    if int(gasto["anulado"] or 0):
        raise ValueError("El gasto seleccionado ya está anulado.")

    motivo_limpio = str(motivo or "").strip()
    if not motivo_limpio:
        raise ValueError("El motivo de anulación es obligatorio.")

    movimiento = get_caja_movimiento_activo_por_gasto(gid)
    if movimiento and int(movimiento["caja_estado"] or 0) != 1:
        raise ValueError("No podés anular este gasto porque impacta una caja cerrada.")

    if movimiento:
        anular_caja_movimiento(
            int(movimiento["id"]),
            f"Anulación de gasto #{gid}: {motivo_limpio}",
            usuario=str(usuario or "").strip(),
            permitir_vinculado_gasto=True,
        )

    marca_tiempo = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    q(
        """UPDATE gastos
        SET anulado=1, anulada_at=?, anulada_por=?, motivo_anulacion=?
        WHERE id=?""",
        (marca_tiempo, str(usuario or "").strip(), motivo_limpio, gid),
        commit=True,
    )
    registrar_auditoria(
        "ANULACION_GASTO",
        "gasto",
        gid,
        detalle=f"{gasto['categoria'] or 'Sin categoria'} · {gasto['descripcion'] or 'Sin descripcion'} · {float(gasto['monto'] or 0):.2f}",
        motivo=motivo_limpio,
        usuario=usuario,
        rol=rol,
    )
    return get_gasto(gid)


def delete_gasto(gid):
    """Compatibilidad: los gastos ya no se eliminan físicamente."""
    raise ValueError("Los gastos ya no se eliminan. Usá anulación responsable para conservar historial.")


# â”€â”€â”€ TEMPORADAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_temporada_actual():
    """Devuelve la temporada actual o None."""
    hoy = date.today().isoformat()
    return q(
        """SELECT * FROM temporadas
        WHERE activa=1 AND fecha_inicio <= ? AND fecha_fin >= ? LIMIT 1""",
        (hoy, hoy), fetchone=True
    )

def get_proxima_temporada():
    """Retorna la prÃ³xima temporada programada."""
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


# â”€â”€â”€ UTILIDADES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def fmt_ars(valor):
    """Formatea valor en ARS."""
    return f"${valor:,.2f}"


def _ventas_activas_cond(alias="v"):
    """Condicion SQL reusable para excluir ventas anuladas."""
    return f"COALESCE({alias}.anulada, 0) = 0"


def get_dashboard_stats():
    """Calcula estadÃ­sticas para dashboard."""
    hoy = date.today().isoformat()

    # Ventas del dÃ­a
    ventas_hoy = q(
        f"SELECT COUNT(*) as total, COALESCE(SUM(total),0) as monto FROM ventas WHERE fecha=? AND {_ventas_activas_cond('ventas')}",
        (hoy,), fetchone=True
    )

    # Stock en alerta
    alertas = get_alertas_count()

    # Ãšltimas ventas
    ultimas_ventas = q(f"SELECT * FROM ventas WHERE {_ventas_activas_cond('ventas')} ORDER BY fecha DESC, id DESC LIMIT 5")

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
    """Busca productos para POS por nombre/cÃ³digo/categorÃ­a."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter(None)
    sql = """SELECT p.id, p.codigo_interno, p.codigo_barras, p.descripcion, p.categoria, p.unidad,
                    p.tipo_unidad, p.permite_fraccionado, p.por_peso, p.precio_venta, s.stock_actual
             FROM productos p
             JOIN stock s ON s.producto_id = p.id
             WHERE p.activo=1"""
    params = []
    sql += f" AND {rubro_cond}"
    params += rubro_params
    if search:
        sql += " AND (p.descripcion LIKE ? OR p.categoria LIKE ? OR p.codigo_interno LIKE ? OR p.codigo_barras LIKE ?)"
        params += [f'%{search}%'] * 4
    sql += " ORDER BY p.descripcion LIMIT 50"

    # DEBUG: Descomenta las siguientes lÃ­neas para ver la consulta SQL y los parÃ¡metros
    # import os
    # if os.environ.get('FLASK_DEBUG') == '1': # Solo imprime si Flask estÃ¡ en modo debug
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

# â”€â”€â”€ REPORTES Y ESTADÃSTICAS (PASO 12) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_stats_rentabilidad(mes_actual=None, rubro=None):
    """Calcula ganancia bruta y operativa simple del mes."""
    if not mes_actual:
        mes_actual = datetime.now().strftime('%Y-%m')

    # Total ventas.
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    ventas = q(
        f"""
        SELECT COALESCE(SUM(v.total), 0) as total
        FROM ventas v
        WHERE v.fecha LIKE ?
          AND {_ventas_activas_cond('v')}
          AND EXISTS (
              SELECT 1
              FROM ventas_detalle vd
              LEFT JOIN productos p ON p.id = vd.producto_id
              WHERE vd.venta_id = v.id AND {rubro_cond}
          )
        """,
        (f"{mes_actual}%", *rubro_params),
        fetchone=True,
    )['total']

    # Costo de lo vendido: usa el costo guardado al vender y cae al costo actual en ventas viejas.
    costo_ventas = q(f"""
        SELECT COALESCE(SUM(vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0)), 0) as total_costo
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        LEFT JOIN productos p ON p.id = vd.producto_id
        WHERE v.fecha LIKE ? AND {_ventas_activas_cond('v')} AND {rubro_cond}
    """, (f"{mes_actual}%", *rubro_params), fetchone=True)['total_costo']

    gastos_rows = q(
        """SELECT COALESCE(clasificacion, 'Operativo') as clasificacion,
                  COALESCE(SUM(monto), 0) as total
        FROM gastos
        WHERE fecha LIKE ? AND COALESCE(anulado, 0)=0
        GROUP BY COALESCE(clasificacion, 'Operativo')""",
        (f"{mes_actual}%",),
    )
    gastos_por_clasificacion = {
        normalizar_clasificacion_gasto(r["clasificacion"]): float(r["total"] or 0)
        for r in gastos_rows
    }
    gastos_operativos = gastos_por_clasificacion.get("Operativo", 0) + gastos_por_clasificacion.get("Otro", 0)
    impuestos = gastos_por_clasificacion.get("Impuesto", 0)
    gastos_financieros = gastos_por_clasificacion.get("Financiero", 0)
    total_gastos = gastos_operativos + impuestos + gastos_financieros

    ganancia_bruta = ventas - costo_ventas
    ganancia_operativa = ganancia_bruta - gastos_operativos
    ganancia_neta_estimada = ganancia_operativa - impuestos - gastos_financieros
    margen_bruto = round((ganancia_bruta / ventas) * 100, 1) if ventas else 0

    return {
        'ingresos': ventas,
        'costo_mercaderia': costo_ventas,
        'ganancia_bruta': ganancia_bruta,
        'margen_bruto': margen_bruto,
        'gastos_operativos': gastos_operativos,
        'impuestos': impuestos,
        'gastos_financieros': gastos_financieros,
        'total_gastos': total_gastos,
        'ganancia_operativa': ganancia_operativa,
        'ganancia_neta_estimada': ganancia_neta_estimada,
        'utilidad_neta': ganancia_neta_estimada
    }

def get_top_productos_vendidos(limit=5, rubro=None):
    """Obtiene los productos mÃ¡s vendidos por cantidad."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    return q(f"""
        SELECT COALESCE(NULLIF(vd.descripcion, ''), p.descripcion, 'Producto sin nombre') as descripcion,
               COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria') as categoria,
               COALESCE(NULLIF(vd.unidad, ''), NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad') as unidad,
               SUM(vd.cantidad) as total_vendido,
               SUM(vd.subtotal) as recaudado
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        LEFT JOIN productos p ON p.id = vd.producto_id
        WHERE {_ventas_activas_cond('v')} AND {rubro_cond}
        GROUP BY
            vd.producto_id,
            COALESCE(NULLIF(vd.descripcion, ''), p.descripcion, 'Producto sin nombre'),
            COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria'),
            COALESCE(NULLIF(vd.unidad, ''), NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad')
        ORDER BY total_vendido DESC
        LIMIT ?
    """, (*rubro_params, limit))

def get_ventas_por_mes(year, rubro=None):
    """Retorna total de ventas y cantidad de tickets por mes para un aÃ±o dado."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    rows = q(f"""
        SELECT strftime('%m', v.fecha) as mes,
               COUNT(*) as tickets,
               ROUND(SUM(v.total), 2) as total
        FROM ventas v
        WHERE strftime('%Y', v.fecha) = ?
          AND {_ventas_activas_cond('v')}
          AND EXISTS (
              SELECT 1
              FROM ventas_detalle vd
              LEFT JOIN productos p ON p.id = vd.producto_id
              WHERE vd.venta_id = v.id AND {rubro_cond}
          )
        GROUP BY mes
    """, (str(year), *rubro_params))
    return {int(r['mes']): dict(r) for r in rows}

def get_ventas_por_semana(semanas=8, rubro=None):
    """Retorna ventas agrupadas por semana para las Ãºltimas N semanas."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    rows = q(f"""
        SELECT strftime('%W/%Y', v.fecha) as label,
               ROUND(SUM(v.total), 2) as total,
               COUNT(*) as tickets
        FROM ventas v
        WHERE v.fecha >= date('now', '-{semanas * 7} days')
          AND {_ventas_activas_cond('v')}
          AND EXISTS (
              SELECT 1
              FROM ventas_detalle vd
              LEFT JOIN productos p ON p.id = vd.producto_id
              WHERE vd.venta_id = v.id AND {rubro_cond}
          )
        GROUP BY label ORDER BY label
    """, tuple(rubro_params))
    return [dict(r) for r in rows]

def get_ventas_por_medio_pago(year, mes, rubro=None):
    """Retorna ventas agrupadas por medio de pago para un aÃ±o y mes."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    return q(f"""
        SELECT v.medio_pago,
               COUNT(*) as cant,
               ROUND(SUM(v.total), 2) as total
        FROM ventas v
        WHERE strftime('%Y', v.fecha) = ? AND strftime('%m', v.fecha) = ?
          AND {_ventas_activas_cond('v')}
          AND EXISTS (
              SELECT 1
              FROM ventas_detalle vd
              LEFT JOIN productos p ON p.id = vd.producto_id
              WHERE vd.venta_id = v.id AND {rubro_cond}
          )
        GROUP BY v.medio_pago
    """, (str(year), str(mes).zfill(2), *rubro_params))

def get_ventas_por_temporada(rubro=None):
    """Retorna ventas agrupadas por temporada."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    return q(f"""
        SELECT v.temporada as nombre, COUNT(v.id) as cant, ROUND(SUM(v.total), 2) as total
        FROM ventas v
        WHERE v.temporada != ''
          AND {_ventas_activas_cond('v')}
          AND EXISTS (
              SELECT 1
              FROM ventas_detalle vd
              LEFT JOIN productos p ON p.id = vd.producto_id
              WHERE vd.venta_id = v.id AND {rubro_cond}
          )
        GROUP BY v.temporada ORDER BY total DESC
    """, tuple(rubro_params))

def get_ventas_por_categoria(rubro=None):
    """Retorna ventas agrupadas por categorÃ­a de producto."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    return q(f"""
        SELECT COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria') as categoria,
               ROUND(SUM(vd.subtotal), 2) as total
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        LEFT JOIN productos p ON vd.producto_id = p.id
        WHERE {_ventas_activas_cond('v')} AND {rubro_cond}
        GROUP BY COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria')
        ORDER BY total DESC
    """, tuple(rubro_params))

def get_top_productos_analisis(limit=15, desde='', hasta='', rubro=None):
    """Retorna los productos mÃ¡s vendidos en un rango de fechas con rentabilidad."""
    params = []
    condicion = ""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    if desde and hasta:
        condicion = "WHERE v.fecha BETWEEN ? AND ?"
        params = [desde, hasta]
    condicion = _append_condition(condicion, _ventas_activas_cond("v"))
    condicion = _append_condition(condicion, rubro_cond)
    return q(f"""
        SELECT COALESCE(NULLIF(vd.descripcion, ''), p.descripcion, 'Producto sin nombre') as descripcion,
               COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria') as categoria,
               COALESCE(NULLIF(vd.unidad, ''), NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad') as unidad,
               SUM(vd.cantidad) as unidades,
               ROUND(SUM(vd.subtotal), 2) as total_pesos,
               ROUND(SUM(vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0)), 2) as costo_mercaderia,
               ROUND(SUM(vd.subtotal - (vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0))), 2) as utilidad,
               ROUND(
                   CASE
                       WHEN SUM(vd.subtotal) > 0 THEN
                           (SUM(vd.subtotal - (vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0))) / SUM(vd.subtotal)) * 100
                       ELSE 0
                   END,
                   1
               ) as margen_bruto
        FROM ventas_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        LEFT JOIN productos p ON vd.producto_id = p.id
        {condicion}
        GROUP BY
            vd.producto_id,
            COALESCE(NULLIF(vd.descripcion, ''), p.descripcion, 'Producto sin nombre'),
            COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria'),
            COALESCE(NULLIF(vd.unidad, ''), NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad')
        ORDER BY total_pesos DESC LIMIT ?
    """, params + rubro_params + [limit])


def get_resumen_rentabilidad_periodo(desde='', hasta='', rubro=None):
    """Resume ingresos, costo historico y ganancia bruta de un periodo."""
    params = []
    condicion = ""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    if desde and hasta:
        condicion = "WHERE v.fecha BETWEEN ? AND ?"
        params = [desde, hasta]
    condicion = _append_condition(condicion, _ventas_activas_cond("v"))
    condicion = _append_condition(condicion, rubro_cond)
    row = q(f"""
        SELECT ROUND(COALESCE(SUM(vd.subtotal), 0), 2) as ingresos,
               ROUND(COALESCE(SUM(vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0)), 0), 2) as costo,
               ROUND(COALESCE(SUM(vd.subtotal - (vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0))), 0), 2) as ganancia
        FROM ventas_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        LEFT JOIN productos p ON vd.producto_id = p.id
        {condicion}
    """, params + rubro_params, fetchone=True)
    ingresos = float(row["ingresos"] or 0) if row else 0
    ganancia = float(row["ganancia"] or 0) if row else 0
    return {
        "ingresos": ingresos,
        "costo": float(row["costo"] or 0) if row else 0,
        "ganancia": ganancia,
        "margen": round((ganancia / ingresos) * 100, 1) if ingresos else 0,
    }


def _periodo_ventas_expr(granularidad):
    if granularidad == "mensual":
        return "strftime('%Y-%m', v.fecha)"
    if granularidad == "anual":
        return "strftime('%Y', v.fecha)"
    if granularidad == "semanal":
        return "strftime('%Y-W%W', v.fecha)"
    return "v.fecha"


def _periodo_gastos_expr(granularidad):
    if granularidad == "mensual":
        return "strftime('%Y-%m', fecha)"
    if granularidad == "anual":
        return "strftime('%Y', fecha)"
    if granularidad == "semanal":
        return "strftime('%Y-W%W', fecha)"
    return "fecha"


def _resumen_gastos_periodo(desde='', hasta=''):
    params = []
    condicion = ""
    if desde and hasta:
        condicion = f"WHERE fecha BETWEEN ? AND ? AND {_gastos_activos_cond()}"
        params = [desde, hasta]
    else:
        condicion = f"WHERE {_gastos_activos_cond()}"
    rows = q(f"""
        SELECT COALESCE(clasificacion, 'Operativo') as clasificacion,
               ROUND(COALESCE(SUM(monto), 0), 2) as total
        FROM gastos
        {condicion}
        GROUP BY COALESCE(clasificacion, 'Operativo')
    """, params)
    resumen = {"Operativo": 0.0, "Impuesto": 0.0, "Financiero": 0.0, "Otro": 0.0}
    for row in rows:
        resumen[normalizar_clasificacion_gasto(row["clasificacion"])] += float(row["total"] or 0)
    return {
        "gastos_operativos": resumen["Operativo"] + resumen["Otro"],
        "impuestos": resumen["Impuesto"],
        "gastos_financieros": resumen["Financiero"],
    }


def get_rentabilidad_detallada_articulos(desde='', hasta='', rubro=None):
    """Rentabilidad estimada por articulo, con gastos prorrateados por ingresos."""
    params = []
    condicion = ""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    if desde and hasta:
        condicion = "WHERE v.fecha BETWEEN ? AND ?"
        params = [desde, hasta]
    condicion = _append_condition(condicion, _ventas_activas_cond("v"))
    condicion = _append_condition(condicion, rubro_cond)

    rows = q(f"""
        SELECT COALESCE(NULLIF(vd.descripcion, ''), p.descripcion, 'Producto sin nombre') as descripcion,
               COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria') as categoria,
               COALESCE(NULLIF(vd.unidad, ''), NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad') as unidad,
               SUM(vd.cantidad) as unidades,
               ROUND(SUM(vd.subtotal), 2) as ingresos,
               ROUND(SUM(vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0)), 2) as costo,
               ROUND(SUM(vd.subtotal - (vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0))), 2) as ganancia_bruta
        FROM ventas_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        LEFT JOIN productos p ON vd.producto_id = p.id
        {condicion}
        GROUP BY
            vd.producto_id,
            COALESCE(NULLIF(vd.descripcion, ''), p.descripcion, 'Producto sin nombre'),
            COALESCE(NULLIF(vd.categoria, ''), p.categoria, 'Sin categoria'),
            COALESCE(NULLIF(vd.unidad, ''), NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad')
        ORDER BY ingresos DESC
    """, params + rubro_params)

    total_ingresos = sum(float(row["ingresos"] or 0) for row in rows)
    gastos = _resumen_gastos_periodo(desde, hasta)
    resultado = []
    for row in rows:
        ingresos = float(row["ingresos"] or 0)
        ganancia_bruta = float(row["ganancia_bruta"] or 0)
        proporcion = (ingresos / total_ingresos) if total_ingresos else 0
        gastos_operativos = round(gastos["gastos_operativos"] * proporcion, 2)
        impuestos = round(gastos["impuestos"] * proporcion, 2)
        gastos_financieros = round(gastos["gastos_financieros"] * proporcion, 2)
        ganancia_operativa = ganancia_bruta - gastos_operativos
        ganancia_neta = ganancia_operativa - impuestos - gastos_financieros
        resultado.append({
            "descripcion": row["descripcion"],
            "categoria": row["categoria"],
            "unidad": row["unidad"] or "unidad",
            "unidades": float(row["unidades"] or 0),
            "ingresos": ingresos,
            "costo": float(row["costo"] or 0),
            "ganancia_bruta": ganancia_bruta,
            "gastos_operativos": gastos_operativos,
            "impuestos_financieros": impuestos + gastos_financieros,
            "ganancia_operativa": ganancia_operativa,
            "ganancia_neta_estimada": ganancia_neta,
            "margen_bruto": round((ganancia_bruta / ingresos) * 100, 1) if ingresos else 0,
            "margen_neto": round((ganancia_neta / ingresos) * 100, 1) if ingresos else 0,
        })
    return resultado


def get_rentabilidad_detallada_periodos(granularidad='diario', desde='', hasta='', rubro=None):
    """Rentabilidad agrupada por dia, mes o anio."""
    ventas_expr = _periodo_ventas_expr(granularidad)
    gastos_expr = _periodo_gastos_expr(granularidad)
    params = []
    condicion_ventas = ""
    condicion_gastos = ""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    if desde and hasta:
        condicion_ventas = "WHERE v.fecha BETWEEN ? AND ?"
        condicion_gastos = f"WHERE fecha BETWEEN ? AND ? AND {_gastos_activos_cond()}"
        params = [desde, hasta]
    else:
        condicion_gastos = f"WHERE {_gastos_activos_cond()}"
    condicion_ventas = _append_condition(condicion_ventas, _ventas_activas_cond("v"))
    condicion_ventas = _append_condition(condicion_ventas, rubro_cond)

    ventas_rows = q(f"""
        SELECT {ventas_expr} as periodo,
               ROUND(COALESCE(SUM(vd.subtotal), 0), 2) as ingresos,
               ROUND(COALESCE(SUM(vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0)), 0), 2) as costo
        FROM ventas_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        LEFT JOIN productos p ON vd.producto_id = p.id
        {condicion_ventas}
        GROUP BY {ventas_expr}
    """, params + rubro_params)

    gastos_rows = q(f"""
        SELECT {gastos_expr} as periodo,
               COALESCE(clasificacion, 'Operativo') as clasificacion,
               ROUND(COALESCE(SUM(monto), 0), 2) as total
        FROM gastos
        {condicion_gastos}
        GROUP BY {gastos_expr}, COALESCE(clasificacion, 'Operativo')
    """, params)

    periodos = {}
    for row in ventas_rows:
        key = row["periodo"] or ""
        periodos[key] = {
            "periodo": key,
            "ingresos": float(row["ingresos"] or 0),
            "costo": float(row["costo"] or 0),
            "gastos_operativos": 0.0,
            "impuestos": 0.0,
            "gastos_financieros": 0.0,
        }

    for row in gastos_rows:
        key = row["periodo"] or ""
        item = periodos.setdefault(key, {
            "periodo": key,
            "ingresos": 0.0,
            "costo": 0.0,
            "gastos_operativos": 0.0,
            "impuestos": 0.0,
            "gastos_financieros": 0.0,
        })
        clasificacion = normalizar_clasificacion_gasto(row["clasificacion"])
        monto = float(row["total"] or 0)
        if clasificacion in {"Operativo", "Otro"}:
            item["gastos_operativos"] += monto
        elif clasificacion == "Impuesto":
            item["impuestos"] += monto
        elif clasificacion == "Financiero":
            item["gastos_financieros"] += monto

    resultado = []
    for key in sorted(periodos.keys(), reverse=True):
        item = periodos[key]
        ganancia_bruta = item["ingresos"] - item["costo"]
        ganancia_operativa = ganancia_bruta - item["gastos_operativos"]
        ganancia_neta = ganancia_operativa - item["impuestos"] - item["gastos_financieros"]
        item.update({
            "total_gastos": item["gastos_operativos"] + item["impuestos"] + item["gastos_financieros"],
            "ganancia_bruta": ganancia_bruta,
            "ganancia_operativa": ganancia_operativa,
            "ganancia_neta_estimada": ganancia_neta,
            "margen_bruto": round((ganancia_bruta / item["ingresos"]) * 100, 1) if item["ingresos"] else 0,
            "margen_neto": round((ganancia_neta / item["ingresos"]) * 100, 1) if item["ingresos"] else 0,
        })
        resultado.append(item)
    return resultado


def get_composicion_gastos_rentabilidad(granularidad='mensual', desde='', hasta='', rubro=None):
    """Muestra ingresos y gastos reales agrupados por categoria para explicar el margen."""
    ventas_expr = _periodo_ventas_expr(granularidad)
    gastos_expr = _periodo_gastos_expr(granularidad)
    params = []
    condicion_ventas = ""
    condicion_gastos = ""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    if desde and hasta:
        condicion_ventas = "WHERE v.fecha BETWEEN ? AND ?"
        condicion_gastos = f"WHERE fecha BETWEEN ? AND ? AND {_gastos_activos_cond()}"
        params = [desde, hasta]
    else:
        condicion_gastos = f"WHERE {_gastos_activos_cond()}"
    condicion_ventas = _append_condition(condicion_ventas, _ventas_activas_cond("v"))
    condicion_ventas = _append_condition(condicion_ventas, f"EXISTS (SELECT 1 FROM ventas_detalle vd LEFT JOIN productos p ON p.id = vd.producto_id WHERE vd.venta_id = v.id AND {rubro_cond})")

    ventas_rows = q(f"""
        SELECT {ventas_expr} as periodo,
               ROUND(COALESCE(SUM(v.total), 0), 2) as ingresos
        FROM ventas v
        {condicion_ventas}
        GROUP BY {ventas_expr}
    """, params + rubro_params)

    gastos_rows = q(f"""
        SELECT {gastos_expr} as periodo,
               COALESCE(clasificacion, 'Operativo') as clasificacion,
               COALESCE(NULLIF(categoria, ''), 'Sin categoria') as categoria,
               ROUND(COALESCE(SUM(monto), 0), 2) as total,
               COUNT(*) as movimientos
        FROM gastos
        {condicion_gastos}
        GROUP BY {gastos_expr}, COALESCE(clasificacion, 'Operativo'), COALESCE(NULLIF(categoria, ''), 'Sin categoria')
        ORDER BY periodo DESC, total DESC
    """, params)

    periodos = {}
    for row in ventas_rows:
        key = row["periodo"] or ""
        periodos[key] = {
            "periodo": key,
            "ingresos": float(row["ingresos"] or 0),
            "gastos": [],
            "total_gastos": 0.0,
        }

    for row in gastos_rows:
        key = row["periodo"] or ""
        item = periodos.setdefault(key, {
            "periodo": key,
            "ingresos": 0.0,
            "gastos": [],
            "total_gastos": 0.0,
        })
        total = float(row["total"] or 0)
        item["gastos"].append({
            "clasificacion": normalizar_clasificacion_gasto(row["clasificacion"]),
            "categoria": row["categoria"],
            "total": total,
            "movimientos": int(row["movimientos"] or 0),
        })
        item["total_gastos"] += total

    resultado = []
    for key in sorted(periodos.keys(), reverse=True):
        item = periodos[key]
        item["resultado_despues_gastos"] = item["ingresos"] - item["total_gastos"]
        resultado.append(item)
    return resultado


def get_resumen_rentabilidad_simple(desde='', hasta='', rubro=None):
    """Resumen simple de rentabilidad para vista ejecutiva."""
    bruto = get_resumen_rentabilidad_periodo(desde, hasta, rubro=rubro)
    gastos = _resumen_gastos_periodo(desde, hasta)
    ganancia_bruta = float(bruto["ganancia"] or 0)
    gastos_operativos = float(gastos["gastos_operativos"] or 0)
    impuestos = float(gastos["impuestos"] or 0)
    gastos_financieros = float(gastos["gastos_financieros"] or 0)
    ganancia_operativa = ganancia_bruta - gastos_operativos
    ganancia_neta = ganancia_operativa - impuestos - gastos_financieros
    ingresos = float(bruto["ingresos"] or 0)
    return {
        "ingresos": ingresos,
        "costo": float(bruto["costo"] or 0),
        "ganancia_bruta": ganancia_bruta,
        "margen_bruto": bruto["margen"],
        "gastos_operativos": gastos_operativos,
        "impuestos": impuestos,
        "gastos_financieros": gastos_financieros,
        "total_gastos": gastos_operativos + impuestos + gastos_financieros,
        "ganancia_operativa": ganancia_operativa,
        "ganancia_neta_estimada": ganancia_neta,
        "margen_neto": round((ganancia_neta / ingresos) * 100, 1) if ingresos else 0,
    }


def get_gastos_por_categoria_periodo(desde='', hasta=''):
    """Gastos reales agrupados por categoria para graficos y cierre."""
    params = []
    condicion = ""
    if desde and hasta:
        condicion = f"WHERE fecha BETWEEN ? AND ? AND {_gastos_activos_cond()}"
        params = [desde, hasta]
    else:
        condicion = f"WHERE {_gastos_activos_cond()}"
    return q(f"""
        SELECT COALESCE(NULLIF(categoria, ''), 'Sin categoria') as categoria,
               COALESCE(clasificacion, 'Operativo') as clasificacion,
               ROUND(COALESCE(SUM(monto), 0), 2) as total,
               COUNT(*) as movimientos
        FROM gastos
        {condicion}
        GROUP BY COALESCE(NULLIF(categoria, ''), 'Sin categoria'), COALESCE(clasificacion, 'Operativo')
        ORDER BY total DESC
    """, params)


def get_evolucion_rentabilidad_simple(granularidad='mensual', desde='', hasta='', rubro=None):
    """Evolucion de ingresos, gastos y neta estimada por periodo."""
    periodos = get_rentabilidad_detallada_periodos(granularidad, desde, hasta, rubro=rubro)
    return list(reversed(periodos))


def get_bottom_productos(limit=10, rubro=None):
    """Retorna los productos con menor movimiento (activos)."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    return q(f"""
        SELECT p.descripcion, p.categoria,
               COALESCE(NULLIF(p.unidad, ''), NULLIF(p.tipo_unidad, ''), 'unidad') as unidad,
               COALESCE(SUM(CASE WHEN COALESCE(v.anulada, 0) = 0 THEN vd.cantidad ELSE 0 END), 0) as unidades
        FROM productos p
        LEFT JOIN ventas_detalle vd ON p.id = vd.producto_id
        LEFT JOIN ventas v ON v.id = vd.venta_id
        WHERE p.activo = 1 AND {rubro_cond}
        GROUP BY p.id ORDER BY unidades ASC LIMIT ?
    """, (*rubro_params, limit))

def get_rentabilidad_historica(rubro=None):
    """Retorna rentabilidad de los Ãºltimos 6 meses."""
    rubro_cond, rubro_params = _build_rubro_compatible_filter_sql("p", rubro)
    return q(f"""
        SELECT strftime('%Y-%m', v.fecha) as mes,
               ROUND(SUM(v.total), 2) as ingresos,
               ROUND(SUM(vd.cantidad * COALESCE(vd.costo_unitario, p.costo, 0)), 2) as costo
        FROM ventas v
        JOIN ventas_detalle vd ON v.id = vd.venta_id
        LEFT JOIN productos p ON vd.producto_id = p.id
        WHERE v.fecha >= date('now', '-6 months') AND {_ventas_activas_cond('v')} AND {rubro_cond}
        GROUP BY mes ORDER BY mes
    """, tuple(rubro_params))

def get_catalogo_export():
    """Retorna todos los productos activos para exportaciÃ³n."""
    return q("""
        SELECT p.codigo_interno as codigo, p.descripcion, p.categoria, p.precio_venta,
               s.stock_actual, p.activo
        FROM productos p
        JOIN stock s ON p.id = s.producto_id
        ORDER BY p.categoria, p.descripcion
    """)
