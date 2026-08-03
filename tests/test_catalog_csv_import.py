import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.catalog_csv_import import build_plan, parse_tiendanube_csv


HEADER = "Identificador de URL,Nombre,Categorías,Nombre de propiedad 1,Valor de propiedad 1,Precio,Costo,Stock,SKU,Código de barras,Mostrar en tienda\n"


class TiendanubeCsvAdapterTests(unittest.TestCase):
    def test_utf8_bom_simple_product(self):
        rows = parse_tiendanube_csv(("\ufeff" + HEADER + "mate,Maté,Accesorios,,,1200,600,3,,7790000000001,SI\n").encode())
        self.assertEqual(rows[0]["external_group"], "mate")
        self.assertEqual(rows[0]["stock"], 3)

    def test_groups_multiple_variants_with_neutral_attributes(self):
        content = HEADER + "remera,Remera,Ropa,Material,Algodón,100,40,2,R-ALG,,SI\nremera,,,Material,Lino,110,45,1,R-LIN,,SI\n"
        rows = parse_tiendanube_csv(content.encode())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["attributes"], [{"name": "Material", "value": "Lino"}])

    def test_rejects_missing_headers_empty_and_non_finite_numbers(self):
        with self.assertRaisesRegex(ValueError, "incompatibles"):
            parse_tiendanube_csv(b"Nombre,Precio\nProducto,10\n")
        with self.assertRaisesRegex(ValueError, "vacio"):
            parse_tiendanube_csv(b"")
        with self.assertRaisesRegex(ValueError, "finito"):
            parse_tiendanube_csv((HEADER + "x,Producto,,,,NaN,2,1,,,SI\n").encode())

    def test_rejects_malformed_row_and_duplicate_sku_before_persistence(self):
        with self.assertRaisesRegex(ValueError, "cantidad incorrecta"):
            parse_tiendanube_csv((HEADER + "x,Producto\n").encode())
        rows = parse_tiendanube_csv((HEADER + "x,Producto,,,,1,1,1,DUP,,SI\ny,Otro,,,,1,1,1,DUP,,SI\n").encode())
        plan = build_plan(rows)
        self.assertTrue(any(error["field"] == "SKU" for error in plan["errors"]))

    def test_rejects_duplicate_combination(self):
        content = HEADER + "camisa,Camisa,Ropa,Material,Lino,100,40,2,C-1,,SI\ncamisa,,,Material,Lino,100,40,2,C-2,,SI\n"
        with mock.patch("services.catalog_csv_import.db.get_conn") as get_conn:
            plan = build_plan(parse_tiendanube_csv(content.encode()))
        self.assertTrue(any(error["field"] == "combinacion" for error in plan["errors"]))


class CatalogImportPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        import database
        from services import catalog_csv_import
        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "catalog.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.service = importlib.reload(catalog_csv_import)
        self.db.add_usuario("importador", "1234", "Administrador", "Importador", security_question="color", security_answer="azul")
        self.owner = int(self.db.get_usuario_by_username("importador")["id"])

    def test_confirms_simple_product_with_cursor_code_and_single_use_plan(self):
        content = HEADER + "mate,Mate,Accesorios,,,1200,600,3,,7790000000001,SI\n"
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(content.encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        result = self.service.apply_stored_plan(plan_id, token, self.owner)
        self.assertEqual(result["created"], 1)
        product = self.db.q("SELECT * FROM productos WHERE codigo_barras=?", ("7790000000001",), fetchone=True)
        self.assertIsNotNone(product)
        with self.assertRaisesRegex(ValueError, "ya fue utilizado"):
            self.service.apply_stored_plan(plan_id, token, self.owner)

    def test_reimport_simple_barcode_updates_absolute_stock_without_duplicate(self):
        content = HEADER + "mate,Mate,Accesorios,,,1200,600,3,,7790000000001,SI\n"
        for stock in ("3", "7", "7"):
            current = content.replace(",3,,779", f",{stock},,779")
            plan = self.service.build_plan(self.service.parse_tiendanube_csv(current.encode()))
            plan_id, token = self.service.store_plan(plan, self.owner)
            self.service.apply_stored_plan(plan_id, token, self.owner)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos", fetchone=True)["total"], 1)
        movement = self.db.q("SELECT stock_anterior, stock_nuevo FROM stock_movimientos ORDER BY id DESC LIMIT 1", fetchone=True)
        self.assertEqual((movement["stock_anterior"], movement["stock_nuevo"]), (3.0, 7.0))


if __name__ == "__main__":
    unittest.main()
