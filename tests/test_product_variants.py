import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_env():
    for key in ("FLASK_ENV", "NEXAR_LICENSE_MODE", "NEXAR_EXTRA_MODULES", "SECRET_KEY"):
        os.environ.pop(key, None)


class ProductVariantsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"

        import app as app_module
        import database
        from routes import main as routes_main
        from services import product_variants

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.product_variants = importlib.reload(product_variants)
        self.routes_main = importlib.reload(routes_main)
        self.routes_main.db = self.database
        self.routes_main.product_variants = self.product_variants

        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.database
        self.app = self.app_module.create_app()

        self.database.add_usuario(
            "admin",
            "1234",
            "Administrador",
            "Administrador Test",
            security_question="color",
            security_answer="azul",
        )
        self.database.set_rubro_configurado("tienda")

    def tearDown(self):
        _reset_env()

    def _crear_producto(self, descripcion="Producto base", stock=12, costo=100, precio=150, codigo_barras=""):
        return int(
            self.database.add_producto(
                {
                    "descripcion": descripcion,
                    "marca": "",
                    "categoria": "General",
                    "tipo_unidad": "unidad",
                    "unidad": "unidad",
                    "stock_actual": stock,
                    "stock_minimo": 2,
                    "stock_maximo": 20,
                    "costo": costo,
                    "precio_venta": precio,
                    "iva": "21%",
                    "codigo_barras": codigo_barras,
                }
            )
        )

    def _login_admin(self, client):
        with client.session_transaction() as session:
            session["_csrf_token"] = "test-token"
        response = client.post(
            "/login",
            data={"username": "admin", "password": "1234", "csrf_token": "test-token"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def _assert_variant_tables_empty(self):
        for tabla in ("producto_variantes", "producto_variante_valores", "stock_variantes"):
            row = self.database.q(f"SELECT COUNT(*) AS total FROM {tabla}", fetchone=True)
            self.assertEqual(int(row["total"] or 0), 0, f"La tabla {tabla} quedo con filas parciales")

    def _direct_conn(self):
        conn = sqlite3.connect(self.database.DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def test_creacion_producto_comun_permanece_compatible(self):
        producto_id = self._crear_producto(descripcion="Producto comun", stock=8, costo=50, precio=90)

        producto = self.database.get_producto(producto_id)
        stock_row = self.database.q("SELECT * FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        variantes = self.product_variants.list_product_variants(producto_id)

        self.assertEqual(producto["descripcion"], "Producto comun")
        self.assertEqual(float(producto["precio_venta"] or 0), 90.0)
        self.assertEqual(float(stock_row["stock_actual"] or 0), 8.0)
        self.assertEqual(variantes, [])

    def test_creacion_de_atributos_y_opciones_reutilizables(self):
        color_negro = self.product_variants.ensure_attribute_value("Color", "Negro")
        color_blanco = self.product_variants.ensure_attribute_value("Color", "Blanco")
        talle_m = self.product_variants.ensure_attribute_value("Talle", "M")
        catalogo = self.product_variants.list_attributes_catalog()

        self.assertEqual(color_negro["attribute_id"], color_blanco["attribute_id"])
        self.assertNotEqual(color_negro["value_id"], color_blanco["value_id"])
        self.assertNotEqual(color_negro["attribute_id"], talle_m["attribute_id"])
        self.assertTrue(any(item["nombre"] == "Color" for item in catalogo))

    def test_crea_variantes_combinadas(self):
        producto_id = self._crear_producto(descripcion="Remera")

        variante_id = self.product_variants.create_variant(
            producto_id,
            attributes=[
                {"attribute_name": "Color", "value_name": "Negro"},
                {"attribute_name": "Talle", "value_name": "M"},
            ],
            sku="REM-NEG-M",
            codigo_barras="779000000001",
            costo=120,
            precio=210,
            stock_actual=4,
            stock_minimo=1,
            stock_maximo=8,
        )

        variantes = self.product_variants.list_product_variants(producto_id)

        self.assertEqual(variante_id, variantes[0]["id"])
        self.assertEqual(variantes[0]["resumen_atributos"], "Color: Negro, Talle: M")
        self.assertEqual(float(variantes[0]["stock_actual"]), 4.0)

    def test_rechaza_combinaciones_duplicadas(self):
        producto_id = self._crear_producto(descripcion="Zapatilla")
        payload = [
            {"attribute_name": "Numero", "value_name": "40"},
            {"attribute_name": "Color", "value_name": "Negro"},
        ]
        self.product_variants.create_variant(producto_id, attributes=payload, sku="ZAP-40-NEG")

        with self.assertRaisesRegex(ValueError, "combinacion de atributos ya existe"):
            self.product_variants.create_variant(producto_id, attributes=list(reversed(payload)), sku="ZAP-NEG-40")

    def test_guarda_sku_y_codigo_barras_por_variante(self):
        producto_id = self._crear_producto(descripcion="Martillo")

        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Medida", "value_name": "16 oz"}],
            sku="MAR-16",
            codigo_barras="779000000016",
            precio=180,
            stock_actual=3,
        )

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["sku"], "MAR-16")
        self.assertEqual(variante["codigo_barras"], "779000000016")

    def test_post_variantes_exige_csrf_y_acepta_token_valido(self):
        producto_id = self._crear_producto(descripcion="Campera")
        with self.app.test_client() as client:
            self._login_admin(client)

            respuesta_sin_token = client.post(
                f"/productos/{producto_id}/variantes",
                data={
                    "attribute_name[]": ["Color"],
                    "value_name[]": ["Negro"],
                    "sku": "CAMP-NEG",
                    "stock_actual": "2",
                    "stock_minimo": "1",
                    "stock_maximo": "5",
                    "costo": "100",
                    "precio": "150",
                    "activo": "1",
                },
                follow_redirects=False,
            )
            self.assertEqual(respuesta_sin_token.status_code, 400)

            respuesta_ok = client.post(
                f"/productos/{producto_id}/variantes",
                data={
                    "csrf_token": "test-token",
                    "attribute_name[]": ["Color"],
                    "value_name[]": ["Negro"],
                    "sku": "CAMP-NEG",
                    "stock_actual": "2",
                    "stock_minimo": "1",
                    "stock_maximo": "5",
                    "costo": "100",
                    "precio": "150",
                    "activo": "1",
                },
                follow_redirects=False,
            )
            self.assertEqual(respuesta_ok.status_code, 302)

        variantes = self.product_variants.list_product_variants(producto_id)
        self.assertEqual(len(variantes), 1)
        self.assertEqual(variantes[0]["sku"], "CAMP-NEG")

    def test_stock_independiente_por_variante(self):
        producto_id = self._crear_producto(descripcion="Buzo", stock=15)

        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="BUZ-AZ",
            stock_actual=2,
        )
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Gris"}],
            sku="BUZ-GR",
            stock_actual=7,
        )

        variantes = self.product_variants.list_product_variants(producto_id)
        stock_por_sku = {item["sku"]: float(item["stock_actual"]) for item in variantes}
        stock_base = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)

        self.assertEqual(stock_por_sku["BUZ-AZ"], 2.0)
        self.assertEqual(stock_por_sku["BUZ-GR"], 7.0)
        self.assertEqual(float(stock_base["stock_actual"] or 0), 15.0)

    def test_migracion_sobre_base_existente_conserva_datos(self):
        legacy_db = Path(self.temp_dir.name) / "legacy_tienda.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_interno TEXT UNIQUE NOT NULL,
                codigo_barras TEXT DEFAULT '',
                descripcion TEXT NOT NULL,
                categoria TEXT DEFAULT '',
                unidad TEXT DEFAULT 'unidad',
                por_peso INTEGER DEFAULT 0,
                costo REAL DEFAULT 0,
                precio_venta REAL DEFAULT 0,
                iva TEXT DEFAULT '21%',
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER UNIQUE,
                stock_actual REAL DEFAULT 0,
                stock_minimo REAL DEFAULT 5,
                stock_maximo REAL DEFAULT 50,
                ultimo_ingreso TEXT DEFAULT '',
                proveedor_habitual TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO productos (codigo_interno, descripcion, categoria, costo, precio_venta) VALUES ('PRD-LEG', 'Producto legacy', 'General', 80, 120)"
        )
        conn.execute("INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo) VALUES (1, 9, 2, 15)")
        conn.commit()
        conn.close()

        self.database.DB_PATH = str(legacy_db)
        self.database._db_initialized = False
        self.database.init_db()

        producto = self.database.get_producto(1)
        stock = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=1", fetchone=True)
        variante_tabla = self.database.q(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='producto_variantes'",
            fetchone=True,
        )

        self.assertEqual(producto["descripcion"], "Producto legacy")
        self.assertEqual(float(stock["stock_actual"] or 0), 9.0)
        self.assertIsNotNone(variante_tabla)

    def test_init_db_es_idempotente(self):
        producto_id = self._crear_producto(descripcion="Producto idempotente", stock=5)

        self.database._db_initialized = False
        self.database.init_db()

        producto = self.database.get_producto(producto_id)
        stock = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        total_productos = self.database.q("SELECT COUNT(*) AS total FROM productos", fetchone=True)
        indices = self.database.q(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type='index' AND name IN (
                'idx_productos_codigo_barras_unique',
                'idx_producto_variantes_codigo_barras_unique'
            )
            ORDER BY name
            """,
        )

        self.assertEqual(producto["descripcion"], "Producto idempotente")
        self.assertEqual(float(stock["stock_actual"] or 0), 5.0)
        self.assertEqual(int(total_productos["total"] or 0), 1)
        self.assertEqual(len(indices), 2)
        for indice in indices:
            self.assertIn("TRIM(COALESCE(codigo_barras, ''))", indice["sql"])

    def test_conserva_producto_y_stock_actual_tras_agregar_variantes(self):
        producto_id = self._crear_producto(descripcion="Taladro", stock=11, costo=300, precio=450)
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Material", "value_name": "Acero"}],
            sku="TAL-ACE",
            precio=480,
            stock_actual=6,
        )

        producto = self.database.get_producto(producto_id)
        stock_base = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        variantes = self.product_variants.list_product_variants(producto_id)

        self.assertEqual(float(producto["precio_venta"] or 0), 450.0)
        self.assertEqual(float(producto["costo"] or 0), 300.0)
        self.assertEqual(float(stock_base["stock_actual"] or 0), 11.0)
        self.assertEqual(len(variantes), 1)

    def test_rollback_total_si_falla_despues_de_insertar_variante(self):
        producto_id = self._crear_producto(descripcion="Fallo insert variante")

        with mock.patch.object(
            self.product_variants,
            "_insert_variant_attribute_values",
            side_effect=RuntimeError("fallo-forzado-atributos"),
        ):
            with self.assertRaisesRegex(RuntimeError, "fallo-forzado-atributos"):
                self.product_variants.create_variant(
                    producto_id,
                    attributes=[{"attribute_name": "Color", "value_name": "Rojo"}],
                    sku="FAIL-1",
                    stock_actual=1,
                )
        self._assert_variant_tables_empty()

    def test_rollback_total_si_falla_durante_composicion_atributo_valor(self):
        producto_id = self._crear_producto(descripcion="Fallo composicion")
        original_helper = self.product_variants._ensure_attribute_value_in_cursor
        call_count = {"value": 0}

        def fail_on_second(cursor, attribute_name, value_name):
            call_count["value"] += 1
            if call_count["value"] == 2:
                raise RuntimeError("fallo-forzado-composicion")
            return original_helper(cursor, attribute_name, value_name)

        with mock.patch.object(self.product_variants, "_ensure_attribute_value_in_cursor", side_effect=fail_on_second):
            with self.assertRaisesRegex(RuntimeError, "fallo-forzado-composicion"):
                self.product_variants.create_variant(
                    producto_id,
                    attributes=[
                        {"attribute_name": "Color", "value_name": "Azul"},
                        {"attribute_name": "Talle", "value_name": "L"},
                    ],
                    sku="FAIL-2",
                    stock_actual=1,
                )
        self._assert_variant_tables_empty()

    def test_rollback_total_si_falla_antes_de_crear_stock(self):
        producto_id = self._crear_producto(descripcion="Fallo stock")

        with mock.patch.object(
            self.product_variants,
            "_insert_variant_stock",
            side_effect=RuntimeError("fallo-forzado-stock"),
        ):
            with self.assertRaisesRegex(RuntimeError, "fallo-forzado-stock"):
                self.product_variants.create_variant(
                    producto_id,
                    attributes=[{"attribute_name": "Material", "value_name": "Cuero"}],
                    sku="FAIL-3",
                    stock_actual=1,
                )
        self._assert_variant_tables_empty()

    def test_rechaza_codigo_barras_duplicado_entre_variantes(self):
        producto_id = self._crear_producto(descripcion="Mochila")
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Negro"}],
            sku="MOCH-NEG",
            codigo_barras="779000000100",
        )

        with self.assertRaisesRegex(ValueError, "otra variante con ese codigo de barras"):
            self.product_variants.create_variant(
                producto_id,
                attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
                sku="MOCH-AZU",
                codigo_barras="779000000100",
            )

    def test_rechaza_codigo_barras_de_variante_que_ya_existe_en_producto_legacy(self):
        producto_id = self._crear_producto(descripcion="Bolso")
        self._crear_producto(descripcion="Legacy con codigo", stock=1, costo=20, precio=30, codigo_barras="779000000200")

        with self.assertRaisesRegex(ValueError, "producto legacy con ese codigo de barras"):
            self.product_variants.create_variant(
                producto_id,
                attributes=[{"attribute_name": "Color", "value_name": "Verde"}],
                sku="BOL-VER",
                codigo_barras="779000000200",
            )

    def test_rechaza_codigo_barras_de_producto_legacy_si_ya_existe_en_variante(self):
        producto_id = self._crear_producto(descripcion="Termo")
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Capacidad", "value_name": "1L"}],
            sku="TER-1L",
            codigo_barras="779000000300",
        )

        with self.assertRaisesRegex(ValueError, "producto o variante con ese codigo de barras"):
            self._crear_producto(descripcion="Producto nuevo", stock=3, costo=15, precio=25, codigo_barras="779000000300")

    def test_codigos_barras_vacios_siguen_permitidos(self):
        producto_id = self._crear_producto(descripcion="Bufanda")
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Beige"}],
            sku="BUF-BEI",
            codigo_barras="",
        )
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Gris"}],
            sku="BUF-GRI",
            codigo_barras="   ",
        )

        variantes = self.product_variants.list_product_variants(producto_id)
        self.assertEqual(len(variantes), 2)
        self.assertEqual([item["codigo_barras"] for item in variantes], ["", ""])

    def test_sqlite_rechaza_insercion_directa_de_variante_con_codigo_de_producto(self):
        producto_id = self._crear_producto(descripcion="Legacy directo", codigo_barras="779000001000")
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "producto"):
            conn.execute(
                """
                INSERT INTO producto_variantes
                (producto_id, combination_key, nombre, sku, codigo_barras, activo)
                VALUES (?,?,?,?,?,1)
                """,
                (producto_id, "direct-a", "Directa A", "DIR-A", "779000001000"),
            )

    def test_sqlite_rechaza_insercion_directa_de_producto_con_codigo_de_variante(self):
        producto_id = self._crear_producto(descripcion="Base variante")
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Rojo"}],
            sku="BASE-ROJ",
            codigo_barras="779000001001",
        )
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "variante"):
            conn.execute(
                """
                INSERT INTO productos
                (codigo_interno, codigo_barras, descripcion, categoria, unidad, costo, precio_venta, iva, activo)
                VALUES (?,?,?,?,?,?,?,?,1)
                """,
                ("PRD-DIR-001", "779000001001", "Producto directo", "General", "unidad", 10, 20, "21%"),
            )

    def test_sqlite_rechaza_update_de_producto_hacia_codigo_de_variante(self):
        producto_a = self._crear_producto(descripcion="Producto A")
        producto_b = self._crear_producto(descripcion="Producto B")
        self.product_variants.create_variant(
            producto_a,
            attributes=[{"attribute_name": "Color", "value_name": "Negro"}],
            sku="A-NEG",
            codigo_barras="779000001002",
        )
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "variante"):
            conn.execute("UPDATE productos SET codigo_barras=? WHERE id=?", ("779000001002", producto_b))

    def test_sqlite_rechaza_update_de_variante_hacia_codigo_de_producto(self):
        self._crear_producto(descripcion="Producto C", codigo_barras="779000001003")
        producto_b = self._crear_producto(descripcion="Producto D")
        variante_id = self.product_variants.create_variant(
            producto_b,
            attributes=[{"attribute_name": "Color", "value_name": "Blanco"}],
            sku="D-BLA",
            codigo_barras="779000001004",
        )
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "producto"):
            conn.execute("UPDATE producto_variantes SET codigo_barras=? WHERE id=?", ("779000001003", variante_id))

    def test_sqlite_rechaza_duplicado_directo_entre_productos(self):
        producto_id = self._crear_producto(descripcion="Legacy 1", codigo_barras="779000001005")
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO productos
                (codigo_interno, codigo_barras, descripcion, categoria, unidad, costo, precio_venta, iva, activo)
                VALUES (?,?,?,?,?,?,?,?,1)
                """,
                ("PRD-DIR-002", "779000001005", "Legacy 2", "General", "unidad", 10, 20, "21%"),
            )
        self.assertIsNotNone(self.database.get_producto(producto_id))

    def test_sqlite_rechaza_duplicado_directo_entre_variantes(self):
        producto_id = self._crear_producto(descripcion="Base duplicado")
        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="BD-AZ",
            codigo_barras="779000001006",
        )
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO producto_variantes
                (producto_id, combination_key, nombre, sku, codigo_barras, activo)
                VALUES (?,?,?,?,?,1)
                """,
                (producto_id, "direct-b", "Directa B", "DIR-B", "779000001006"),
            )

    def test_sqlite_rechaza_duplicado_normalizado_entre_productos(self):
        conn = self._direct_conn()
        self.addCleanup(conn.close)
        values = ("PRD-7791", "7791", "Legacy 7791", "General", "unidad", 10, 20, "21%")
        conn.execute(
            """
            INSERT INTO productos
            (codigo_interno, codigo_barras, descripcion, categoria, unidad, costo, precio_venta, iva, activo)
            VALUES (?,?,?,?,?,?,?,?,1)
            """,
            values,
        )

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO productos
                (codigo_interno, codigo_barras, descripcion, categoria, unidad, costo, precio_venta, iva, activo)
                VALUES (?,?,?,?,?,?,?,?,1)
                """,
                ("PRD-7791-ESP", " 7791 ", "Legacy 7791 espacios", "General", "unidad", 10, 20, "21%"),
            )

    def test_sqlite_rechaza_duplicado_normalizado_entre_variantes(self):
        producto_id = self._crear_producto(descripcion="Base 8891")
        conn = self._direct_conn()
        self.addCleanup(conn.close)
        conn.execute(
            """
            INSERT INTO producto_variantes
            (producto_id, combination_key, nombre, sku, codigo_barras, activo)
            VALUES (?,?,?,?,?,1)
            """,
            (producto_id, "direct-8891", "Directa 8891", "DIR-8891", "8891"),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO producto_variantes
                (producto_id, combination_key, nombre, sku, codigo_barras, activo)
                VALUES (?,?,?,?,?,1)
                """,
                (producto_id, "direct-8891-spaces", "Directa 8891 espacios", "DIR-8891-ESP", " 8891 "),
            )

    def test_sqlite_permita_null_y_vacio_segun_politica(self):
        producto_id = self._crear_producto(descripcion="Base nulos")
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        conn.execute(
            """
            INSERT INTO producto_variantes
            (producto_id, combination_key, nombre, sku, codigo_barras, activo)
            VALUES (?,?,?,?,?,1)
            """,
            (producto_id, "direct-null", "Directa Null", "DIR-NULL", None),
        )
        conn.execute(
            """
            INSERT INTO producto_variantes
            (producto_id, combination_key, nombre, sku, codigo_barras, activo)
            VALUES (?,?,?,?,?,1)
            """,
            (producto_id, "direct-empty", "Directa Empty", "DIR-EMPTY", "   "),
        )
        conn.execute(
            """
            INSERT INTO productos
            (codigo_interno, codigo_barras, descripcion, categoria, unidad, costo, precio_venta, iva, activo)
            VALUES (?,?,?,?,?,?,?,?,1)
            """,
            ("PRD-DIR-003", "", "Legacy vacio", "General", "unidad", 10, 20, "21%"),
        )
        conn.commit()

    def test_sqlite_permite_update_conservando_codigo_propio(self):
        legacy_id = self._crear_producto(descripcion="Legacy propio", codigo_barras="779000001007")
        producto_id = self._crear_producto(descripcion="Base propia")
        variante_id = self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Verde"}],
            sku="BP-VER",
            codigo_barras="779000001008",
        )
        conn = self._direct_conn()
        self.addCleanup(conn.close)

        conn.execute("UPDATE productos SET codigo_barras=? WHERE id=?", ("779000001007", legacy_id))
        conn.execute("UPDATE producto_variantes SET codigo_barras=? WHERE id=?", ("779000001008", variante_id))
        conn.commit()

    def test_init_db_detecta_conflicto_previo_sin_borrar_datos(self):
        legacy_db = Path(self.temp_dir.name) / "legacy_conflicto_tienda.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_interno TEXT UNIQUE NOT NULL,
                codigo_barras TEXT DEFAULT '',
                descripcion TEXT NOT NULL,
                categoria TEXT DEFAULT '',
                unidad TEXT DEFAULT 'unidad',
                por_peso INTEGER DEFAULT 0,
                costo REAL DEFAULT 0,
                precio_venta REAL DEFAULT 0,
                iva TEXT DEFAULT '21%',
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE producto_variantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
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
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO productos (codigo_interno, codigo_barras, descripcion, categoria, costo, precio_venta) VALUES ('PRD-CONFLICTO', '779000001009', 'Legacy conflicto', 'General', 10, 20)"
        )
        conn.execute(
            "INSERT INTO producto_variantes (producto_id, combination_key, nombre, sku, codigo_barras, activo) VALUES (1, 'conflict', 'Variante conflicto', 'VAR-CONFLICTO', ' 779000001009 ', 1)"
        )
        conn.commit()
        conn.close()

        self.database.DB_PATH = str(legacy_db)
        self.database._db_initialized = False

        with self.assertRaisesRegex(RuntimeError, "compartidos entre productos y variantes"):
            self.database.init_db()

        verify_conn = sqlite3.connect(legacy_db)
        productos = verify_conn.execute("SELECT codigo_barras FROM productos").fetchall()
        variantes = verify_conn.execute("SELECT codigo_barras FROM producto_variantes").fetchall()
        verify_conn.close()
        self.assertEqual(productos, [("779000001009",)])
        self.assertEqual(variantes, [(" 779000001009 ",)])


if __name__ == "__main__":
    unittest.main()
