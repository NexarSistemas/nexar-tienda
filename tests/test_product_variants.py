import importlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ProductVariantsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        import database
        from services import product_variants

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()
        self.product_variants = importlib.reload(product_variants)

    def _crear_producto(self, descripcion="Producto base", stock=12, costo=100, precio=150):
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
                    "codigo_barras": "",
                }
            )
        )

    def test_creacion_producto_comun_permanece_compatible(self):
        producto_id = self._crear_producto(descripcion="Producto común", stock=8, costo=50, precio=90)

        producto = self.database.get_producto(producto_id)
        stock_row = self.database.q("SELECT * FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        variantes = self.product_variants.list_product_variants(producto_id)

        self.assertEqual(producto["descripcion"], "Producto común")
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
            {"attribute_name": "Número", "value_name": "40"},
            {"attribute_name": "Color", "value_name": "Negro"},
        ]
        self.product_variants.create_variant(producto_id, attributes=payload, sku="ZAP-40-NEG")

        with self.assertRaisesRegex(ValueError, "combinación de atributos ya existe"):
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
        conn.execute(
            "INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo) VALUES (1, 9, 2, 15)"
        )
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

        self.assertEqual(producto["descripcion"], "Producto idempotente")
        self.assertEqual(float(stock["stock_actual"] or 0), 5.0)
        self.assertEqual(int(total_productos["total"] or 0), 1)

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


if __name__ == "__main__":
    unittest.main()
