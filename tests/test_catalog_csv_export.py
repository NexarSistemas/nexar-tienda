import csv
import importlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class CatalogCsvExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        import database
        from services import catalog_csv_export, catalog_csv_import, product_variants, tiendanube_csv_export
        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "catalog-export.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.db.set_rubro_configurado("tienda")
        self.export = importlib.reload(catalog_csv_export)
        self.adapter = importlib.reload(tiendanube_csv_export)
        self.importer = importlib.reload(catalog_csv_import)
        self.variants = importlib.reload(product_variants)

    def _product(self, description, *, category="General", barcode="", price=100, cost=40, stock=2):
        return self.db.add_producto({
            "descripcion": description, "marca": "Nexar", "categoria": category,
            "tipo_unidad": "unidad", "unidad": "unidad", "stock_actual": stock,
            "stock_minimo": 0, "stock_maximo": 50, "costo": cost,
            "precio_venta": price, "codigo_barras": barcode,
        })

    def _rows(self, **filters):
        return list(self.adapter.iter_rows(rubro="tienda", **filters))

    def test_contract_fixture_and_legacy_simple_product(self):
        product_id = self._product("Mate clásico", category="Accesorios", barcode="7790000000001", price=1200.5, cost=600.25, stock=3)
        fixture = Path(__file__).parent / "fixtures" / "tiendanube_catalog_csv_v2026_07.csv"
        with fixture.open(encoding="utf-8") as stream:
            self.assertEqual(next(csv.reader(stream)), list(self.adapter.CSV_COLUMNS))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        parsed = dict(zip(self.adapter.CSV_COLUMNS, rows[0]))
        self.assertEqual(parsed["Nombre"], "Mate clásico")
        self.assertEqual(parsed["Categorías"], "Accesorios")
        self.assertEqual(parsed["Código de barras"], "7790000000001")
        self.assertEqual(parsed["Precio"], "1200.5")
        self.assertEqual(parsed["Costo"], "600.25")
        self.assertEqual(parsed["Stock"], "3")
        self.assertEqual(parsed["Mostrar en tienda"], "SI")
        self.assertEqual(parsed["Identificador de URL"], f"nexar-{product_id}")
        self.assertEqual(parsed["Producto físico"], "")

    def test_url_identifier_does_not_change_when_product_is_renamed(self):
        product_id = self._product("Nombre inicial", barcode="7790000000009")
        before = dict(zip(self.adapter.CSV_COLUMNS, self._rows()[0]))["Identificador de URL"]
        self.db.q("UPDATE productos SET descripcion=? WHERE id=?", ("Nombre completamente nuevo", product_id), fetchall=False, commit=True)
        after = dict(zip(self.adapter.CSV_COLUMNS, self._rows()[0]))["Identificador de URL"]
        self.assertEqual((before, after), (f"nexar-{product_id}", f"nexar-{product_id}"))

    def test_modern_variants_are_unique_and_keep_attributes_commercial_data(self):
        product_id = self._product("Remera", category="Ropa", price=100, cost=40)
        first = self.variants.create_variant(
            product_id, attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="REM-AZ", codigo_barras="7790000000011", precio=110, costo=50,
            precio_promocional=90, stock_actual=4, stock_minimo=0, stock_maximo=20,
        )
        second = self.variants.create_variant(
            product_id, attributes=[{"attribute_name": "Color", "value_name": "Rojo"}, {"attribute_name": "Talle", "value_name": "M"}],
            sku="REM-RO-M", codigo_barras="7790000000012", precio=120, costo=55,
            stock_actual=5, stock_minimo=0, stock_maximo=20,
        )
        self.db.q("UPDATE productos SET stock_modo='variantes' WHERE id=?", (product_id,), fetchall=False, commit=True)
        rows = self._rows()
        self.assertEqual(len(rows), 2)
        parsed = [dict(zip(self.adapter.CSV_COLUMNS, row)) for row in rows]
        self.assertEqual([row["SKU"] for row in parsed], ["REM-AZ", "REM-RO-M"])
        self.assertEqual([row["Código de barras"] for row in parsed], ["7790000000011", "7790000000012"])
        self.assertEqual(parsed[0]["Precio promocional"], "90")
        self.assertEqual(parsed[1]["Nombre"], "")
        self.assertEqual(parsed[1]["Nombre de propiedad 2"], "Talle")
        self.assertEqual(len({tuple(row) for row in rows}), 2)
        self.assertEqual({first, second}, {item["id"] for item in self.variants.list_product_variants(product_id)})

    def test_single_variant_and_inactive_variant_follow_export_policy(self):
        product_id = self._product("Buzo", category="Ropa", price=70, cost=30)
        active_id = self.variants.create_variant(
            product_id, attributes=[{"attribute_name": "Talle", "value_name": "L"}],
            sku="BUZO-L", codigo_barras="7790000000019", precio=80, costo=35,
            stock_actual=6, stock_minimo=0, stock_maximo=20,
        )
        inactive_id = self.variants.create_variant(
            product_id, attributes=[{"attribute_name": "Talle", "value_name": "XL"}],
            sku="BUZO-XL", codigo_barras="7790000000020", precio=90, costo=40,
            stock_actual=7, stock_minimo=0, stock_maximo=20, activo=False,
        )
        self.db.q("UPDATE productos SET stock_modo='variantes' WHERE id=?", (product_id,), fetchall=False, commit=True)
        rows = [dict(zip(self.adapter.CSV_COLUMNS, row)) for row in self._rows()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["SKU"], "BUZO-L")
        self.assertEqual(rows[0]["Nombre de propiedad 1"], "Talle")
        self.assertNotIn("BUZO-XL", {row["SKU"] for row in rows})
        self.assertEqual({active_id, inactive_id}, {item["id"] for item in self.variants.list_product_variants(product_id)})

    def test_csv_serialization_round_trip_special_text_and_formula_safety(self):
        product_id = self._product('=Mate, "edición"\núnica', category="Hogar, regalos", barcode="7790000000021", price=10.5, cost=0, stock=0)
        self.db.q("UPDATE productos SET codigo_barras=? WHERE id=?", ("@7790000000021", product_id), fetchall=False, commit=True)
        content = "".join(self.adapter.iter_csv(rubro="tienda"))
        self.assertTrue(content.startswith("\ufeff"))
        parsed_rows = list(csv.DictReader(io.StringIO(content.lstrip("\ufeff"))))
        self.assertEqual(parsed_rows[0]["Nombre"], '\'=Mate, "edición"\núnica')
        self.assertEqual(parsed_rows[0]["Código de barras"], "'@7790000000021")
        imported = self.importer.parse_tiendanube_csv(content.encode("utf-8"))
        plan = self.importer.build_plan(imported)
        self.assertFalse(plan["errors"], plan["errors"])

    def test_categories_escape_tiendanube_separators_without_losing_accents(self):
        self._product("Mate", category=r"Hogar\\mate, regalos > edición", barcode="7790000000022")
        parsed = dict(zip(self.adapter.CSV_COLUMNS, self._rows()[0]))
        self.assertEqual(parsed["Categorías"], r"Hogar\\\\mate\, regalos \> edición")

    def test_legacy_product_with_configured_variants_uses_legacy_stock(self):
        product_id = self._product("Combo legacy", barcode="7790000000023", price=25, cost=10, stock=7)
        self.variants.create_variant(product_id, attributes=[{"attribute_name": "Color", "value_name": "Azul"}], sku="COM-AZ", precio=99, costo=30, stock_actual=2, stock_minimo=0, stock_maximo=5)
        self.db.q("UPDATE productos SET stock_modo='legacy' WHERE id=?", (product_id,), fetchall=False, commit=True)
        parsed = dict(zip(self.adapter.CSV_COLUMNS, self._rows()[0]))
        self.assertEqual((parsed["Stock"], parsed["Precio"], parsed["SKU"]), ("7", "25", ""))

    def test_decimal_formatter_has_no_scientific_notation_or_precision_cutoff(self):
        self.assertEqual(self.export.decimal_text("0.000000000000000000123", "precio", "Producto 1"), "0.000000000000000000123")
        self.assertEqual(self.export.decimal_text("12345678901234567890.123456789", "precio", "Producto 1"), "12345678901234567890.123456789")
        for invalid in ("NaN", "Infinity", "-1"):
            with self.assertRaises(self.export.CatalogExportValidationError):
                self.export.decimal_text(invalid, "precio", "Producto 1")

    def test_export_import_preserves_variant_promotional_price(self):
        product_id = self._product("Remera promo", barcode="7790000000024")
        variant_id = self.variants.create_variant(product_id, attributes=[{"attribute_name": "Color", "value_name": "Verde"}], sku="REM-VER", precio=120, costo=50, precio_promocional=90, stock_actual=4, stock_minimo=0, stock_maximo=10)
        self.db.q("UPDATE productos SET stock_modo='variantes' WHERE id=?", (product_id,), fetchall=False, commit=True)
        content = "".join(self.adapter.iter_csv(rubro="tienda"))
        plan = self.importer.build_plan(self.importer.parse_tiendanube_csv(content.encode("utf-8")))
        self.assertFalse(plan["errors"], plan["errors"])
        self.db.add_usuario("exportador", "1234", "Administrador", "Exportador", security_question="color", security_answer="azul")
        owner = self.db.get_usuario_by_username("exportador")["id"]
        plan_id, token = self.importer.store_plan(plan, owner)
        self.importer.apply_stored_plan(plan_id, token, owner)
        self.assertEqual(self.db.q("SELECT precio_promocional FROM producto_variantes WHERE id=?", (variant_id,), fetchone=True)["precio_promocional"], 90.0)

    def test_filters_and_inactive_policy(self):
        keep = self._product("Mate", category="Accesorios", barcode="7790000000031")
        excluded = self._product("Remera", category="Ropa", barcode="7790000000032")
        inactive = self._product("Oculto", category="Accesorios", barcode="7790000000033")
        self.db.q("UPDATE productos SET activo=0 WHERE id=?", (inactive,), fetchall=False, commit=True)
        self.assertEqual([dict(zip(self.adapter.CSV_COLUMNS, row))["Nombre"] for row in self._rows(category="Accesorios")], ["Mate"])
        self.assertEqual([dict(zip(self.adapter.CSV_COLUMNS, row))["Nombre"] for row in self._rows(search="Remera")], ["Remera"])
        self.assertNotEqual(keep, excluded)

    def test_invalid_active_variant_is_reported_without_silent_omission(self):
        product_id = self._product("Campera", barcode="7790000000041")
        variant_id = self.variants.create_variant(
            product_id, attributes=[{"attribute_name": "Color", "value_name": "Negro"}],
            sku="CAMP-NEG", precio=100, costo=50, stock_actual=1, stock_minimo=0, stock_maximo=2,
        )
        self.db.q("UPDATE productos SET stock_modo='variantes' WHERE id=?", (product_id,), fetchall=False, commit=True)
        self.db.q("UPDATE producto_variantes SET precio_promocional=100 WHERE id=?", (variant_id,), fetchall=False, commit=True)
        with self.assertRaisesRegex(self.export.CatalogExportValidationError, "precio promocional"):
            self.adapter.validate_catalog(rubro="tienda")
        self.db.q("UPDATE producto_variantes SET activo=0 WHERE id=?", (variant_id,), fetchall=False, commit=True)
        with self.assertRaisesRegex(self.export.CatalogExportValidationError, "todas sus variantes están inactivas"):
            self.adapter.validate_catalog(rubro="tienda")


class CatalogCsvExportHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        import app as app_module
        import database
        from routes import main as routes_main
        from services import catalog_csv_export, tiendanube_csv_export
        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "catalog-export-http.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.db.set_rubro_configurado("tienda")
        self.db.add_usuario("admin", "1234", "Administrador", "Admin", security_question="color", security_answer="azul")
        self.db.add_usuario("vendedor", "1234", "Vendedor", "Vendedor", security_question="color", security_answer="rojo")
        self.db.add_producto({"descripcion": "Mate exportable", "marca": "", "categoria": "Accesorios", "tipo_unidad": "unidad", "unidad": "unidad", "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 5, "costo": 2, "precio_venta": 5, "codigo_barras": "7790000000051"})
        routes_main = importlib.reload(routes_main)
        routes_main.db = self.db
        routes_main.catalog_csv_export = importlib.reload(catalog_csv_export)
        routes_main.tiendanube_csv_export = importlib.reload(tiendanube_csv_export)
        self.routes_main = routes_main
        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.db
        self.app = self.app_module.create_app()

    def _client(self, username, role):
        client = self.app.test_client()
        user_id = int(self.db.get_usuario_by_username(username)["id"])
        with client.session_transaction() as session:
            session["user"] = {"id": user_id, "username": username, "rol": role}
            session["_csrf_token"] = "catalog-csrf"
        return client

    def test_download_headers_encoding_filters_and_permissions(self):
        self.assertEqual(self._client("vendedor", "Vendedor").get("/productos/exportar/tiendanube").status_code, 302)
        with mock.patch.object(self.routes_main, "require_modulo"):
            response = self._client("admin", "Administrador").get("/productos/exportar/tiendanube?categoria=Accesorios")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("attachment; filename=catalogo_tiendanube_", response.headers["Content-Disposition"])
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Mate exportable", response.data.decode("utf-8-sig"))
        response.close()

    def test_product_list_renders_tiendanube_export_link_when_export_is_enabled(self):
        with mock.patch.object(self.app_module, "modulo_activo", return_value=True):
            response = self._client("admin", "Administrador").get("/productos")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/productos/exportar/tiendanube?', response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
