import importlib
import io
import os
import re
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

    def test_preserves_absent_fields_and_accepts_explicit_zero(self):
        minimal = "Identificador de URL,Nombre,Código de barras\nx,Producto,7790000000099\n"
        row = parse_tiendanube_csv(minimal.encode())[0]
        self.assertIsNone(row["stock"])
        self.assertIsNone(row["visible"])
        zero = parse_tiendanube_csv((HEADER + "x,Producto,,,,1,1,0,,7790000000099,NO\n").encode())[0]
        self.assertEqual(zero["stock"], 0.0)
        self.assertFalse(zero["visible"])
        with self.assertRaisesRegex(ValueError, "Mostrar en tienda"):
            parse_tiendanube_csv((HEADER + "x,Producto,,,,1,1,1,,7790000000099,QUIZAS\n").encode())

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

    def test_new_preview_invalidates_previous_plan(self):
        plan = self.service.build_plan(self.service.parse_tiendanube_csv((HEADER + "uno,Uno,,,,1,1,1,,7790000000002,SI\n").encode()))
        old_id, old_token = self.service.store_plan(plan, self.owner)
        new_id, new_token = self.service.store_plan(plan, self.owner)
        with self.assertRaisesRegex(ValueError, "no existe"):
            self.service.apply_stored_plan(old_id, old_token, self.owner)
        self.service.apply_stored_plan(new_id, new_token, self.owner)

    def test_simple_update_preserves_limits_and_updates_commercial_fields(self):
        product_id = self.db.add_producto({"descripcion": "Anterior", "marca": "", "categoria": "General", "tipo_unidad": "unidad", "unidad": "unidad", "stock_actual": 10, "stock_minimo": 2, "stock_maximo": 20, "costo": 1, "precio_venta": 2, "codigo_barras": "7790000000003"})
        content = HEADER + "nuevo,Nuevo,Accesorios,,,0,0,7,,7790000000003,NO\n"
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(content.encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        self.service.apply_stored_plan(plan_id, token, self.owner)
        product = self.db.get_producto(product_id)
        stock = self.db.q("SELECT stock_actual, stock_minimo, stock_maximo FROM stock WHERE producto_id=?", (product_id,), fetchone=True)
        self.assertEqual((product["descripcion"], product["costo"], product["precio_venta"], product["activo"]), ("Nuevo", 0.0, 0.0, 0))
        self.assertEqual((stock["stock_actual"], stock["stock_minimo"], stock["stock_maximo"]), (7.0, 2.0, 20.0))

    def test_absent_stock_and_visibility_keep_local_values(self):
        product_id = self.db.add_producto({"descripcion": "Local", "marca": "", "categoria": "General", "tipo_unidad": "unidad", "unidad": "unidad", "stock_actual": 10, "stock_minimo": 2, "stock_maximo": 20, "costo": 1, "precio_venta": 2, "codigo_barras": "7790000000004"})
        self.db.q("UPDATE productos SET activo=0 WHERE id=?", (product_id,), fetchall=False, commit=True)
        content = "Identificador de URL,Nombre,Código de barras\nx,Local nuevo,7790000000004\n"
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(content.encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        self.service.apply_stored_plan(plan_id, token, self.owner)
        product = self.db.get_producto(product_id)
        stock = self.db.q("SELECT stock_actual, stock_minimo, stock_maximo FROM stock WHERE producto_id=?", (product_id,), fetchone=True)
        self.assertEqual(product["activo"], 0)
        self.assertEqual((stock["stock_actual"], stock["stock_minimo"], stock["stock_maximo"]), (10.0, 2.0, 20.0))

    def _import(self, content):
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(content.encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        self.service.apply_stored_plan(plan_id, token, self.owner)

    def test_variant_stock_presence_and_visibility_updates(self):
        initial = HEADER + "remera,Remera,Ropa,Color,Negro,100,40,10,REM-NEG,,SI\n"
        self._import(initial)
        variant = self.db.q("SELECT v.id, v.producto_id FROM producto_variantes v WHERE v.sku='REM-NEG'", fetchone=True)
        self.db.q("UPDATE stock_variantes SET stock_minimo=2, stock_maximo=20 WHERE variante_id=?", (variant["id"],), fetchall=False, commit=True)
        absent = "Identificador de URL,Nombre,Nombre de propiedad 1,Valor de propiedad 1,SKU\nremera,Remera,Color,Negro,REM-NEG\n"
        self._import(absent)
        empty = HEADER + "remera,Remera,Ropa,Color,Negro,100,40,,REM-NEG,,\n"
        self._import(empty)
        stock = self.db.q("SELECT stock_actual, stock_minimo, stock_maximo FROM stock_variantes WHERE variante_id=?", (variant["id"],), fetchone=True)
        self.assertEqual(tuple(stock), (10.0, 2.0, 20.0))
        movements_before = self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,0,REM-NEG,,NO\n")
        self.assertEqual(self.db.q("SELECT stock_actual FROM stock_variantes WHERE variante_id=?", (variant["id"],), fetchone=True)["stock_actual"], 0.0)
        movement = self.db.q("SELECT stock_anterior, stock_nuevo FROM stock_movimientos ORDER BY id DESC LIMIT 1", fetchone=True)
        self.assertEqual((movement["stock_anterior"], movement["stock_nuevo"]), (10.0, 0.0))
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 0)
        self.db.q("UPDATE stock_variantes SET stock_actual=10 WHERE variante_id=?", (variant["id"],), fetchall=False, commit=True)
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,7,REM-NEG,,SI\n")
        movement = self.db.q("SELECT stock_anterior, stock_nuevo FROM stock_movimientos ORDER BY id DESC LIMIT 1", fetchone=True)
        self.assertEqual((movement["stock_anterior"], movement["stock_nuevo"]), (10.0, 7.0))
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 1)
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,7,REM-NEG,,\n")
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"], movements_before + 2)

    def test_inactive_variant_stock_updates_only_through_catalog_import(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,10,REM-INACT,,SI\n")
        variant = self.db.q("SELECT id, producto_id FROM producto_variantes WHERE sku='REM-INACT'", fetchone=True)
        self.db.q("UPDATE producto_variantes SET activo=0 WHERE id=?", (variant["id"],), fetchall=False, commit=True)
        self.db.q("UPDATE stock_variantes SET stock_minimo=2, stock_maximo=20 WHERE variante_id=?", (variant["id"],), fetchall=False, commit=True)
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,7,REM-INACT,,\n")
        stock = self.db.q("SELECT stock_actual, stock_minimo, stock_maximo FROM stock_variantes WHERE variante_id=?", (variant["id"],), fetchone=True)
        self.assertEqual(tuple(stock), (7.0, 2.0, 20.0))
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 0)
        movement = self.db.q("SELECT stock_anterior, stock_nuevo FROM stock_movimientos ORDER BY id DESC LIMIT 1", fetchone=True)
        self.assertEqual((movement["stock_anterior"], movement["stock_nuevo"]), (10.0, 7.0))
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,,REM-INACT,,\n")
        self.assertEqual(self.db.q("SELECT stock_actual FROM stock_variantes WHERE variante_id=?", (variant["id"],), fetchone=True)["stock_actual"], 7.0)
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,6,REM-INACT,,SI\n")
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 1)
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,5,REM-INACT,,NO\n")
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 0)
        other_product = self.db.add_producto({"descripcion": "Otro", "marca": "", "categoria": "General", "tipo_unidad": "unidad", "unidad": "unidad", "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 1, "costo": 1, "precio_venta": 1})
        self.db.q("UPDATE productos SET stock_modo='variantes' WHERE id=?", (other_product,), fetchall=False, commit=True)
        conn = self.db.get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(ValueError, "no pertenece"):
                self.service.inventory.adjust_inventory_item_in_cursor(cursor, other_product, variant_id=variant["id"], stock_actual=1, stock_minimo=0, stock_maximo=1, allow_inactive_variant=True)
        finally:
            conn.rollback()
            conn.close()

    def test_existing_variant_updates_commercial_fields_without_changing_attributes(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,10,REM-OLD,7790000010101,SI\n")
        variant = self.db.q("SELECT * FROM producto_variantes WHERE sku='REM-OLD'", fetchone=True)
        self._import("Identificador de URL,Nombre,Nombre de propiedad 1,Valor de propiedad 1,SKU\nremera,Remera,Color,Negro,REM-OLD\n")
        original_values = self.db.q("SELECT costo, precio FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)
        self.assertEqual(tuple(original_values), (40.0, 100.0))
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,0,0,,REM-NEW,7790000010101,\n")
        updated = self.db.q("SELECT * FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)
        self.assertEqual((updated["sku"], updated["codigo_barras"], updated["costo"], updated["precio"], updated["activo"]), ("REM-NEW", "7790000010101", 0.0, 0.0, 1))
        self.assertEqual((updated["producto_id"], updated["combination_key"], updated["nombre"]), (variant["producto_id"], variant["combination_key"], variant["nombre"]))
        self._import("Identificador de URL,Nombre,Nombre de propiedad 1,Valor de propiedad 1,SKU\nremera,Remera,Color,Negro,REM-NEW\n")
        preserved = self.db.q("SELECT sku, codigo_barras, costo, precio FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)
        self.assertEqual(tuple(preserved), ("REM-NEW", "7790000010101", 0.0, 0.0))

    def test_variant_commercial_collision_rechecks_in_catalog_transaction(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,1,REM-ONE,7790000010102,SI\n")
        self._import(HEADER + "pantalon,Pantalon,Ropa,Talle,M,100,40,1,PAN-ONE,7790000010103,SI\n")
        product = self.db.q("SELECT producto_id FROM producto_variantes WHERE sku='REM-ONE'", fetchone=True)
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(HEADER.encode() + b"remera,Remera,Ropa,Color,Negro,100,40,1,REM-ONE,7790000010102,SI\n"))
        plan["products"][0]["rows"][0]["sku"] = "PAN-ONE"
        plan_id, token = self.service.store_plan(plan, self.owner)
        with self.assertRaisesRegex(ValueError, "SKU de la variante ya existe"):
            self.service.apply_stored_plan(plan_id, token, self.owner)
        self.assertEqual(self.db.q("SELECT sku FROM producto_variantes WHERE producto_id=?", (product["producto_id"],), fetchone=True)["sku"], "REM-ONE")

    def test_existing_variants_can_swap_skus_and_barcodes_atomically(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,1,REM-A,7790000010201,SI\nremera,,,Color,Blanco,110,45,2,REM-B,7790000010202,SI\n")
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,0,0,,REM-B,7790000010202,SI\nremera,,,Color,Blanco,0,0,,REM-A,7790000010201,SI\n")
        rows = self.db.q("SELECT nombre, sku, codigo_barras, costo, precio FROM producto_variantes ORDER BY nombre")
        self.assertEqual([(row["nombre"], row["sku"], row["codigo_barras"], row["costo"], row["precio"]) for row in rows], [("Color: Blanco", "REM-A", "7790000010201", 0.0, 0.0), ("Color: Negro", "REM-B", "7790000010202", 0.0, 0.0)])

    def test_variant_plan_rejects_deleted_existing_variant_without_replacement(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,10,REM-NEG,7790000010301,SI\n")
        variant = self.db.q("SELECT id FROM producto_variantes WHERE sku='REM-NEG'", fetchone=True)
        plan = self.service.build_plan(self.service.parse_tiendanube_csv((HEADER + "remera,Remera,Ropa,Color,Negro,100,40,7,REM-NEG,7790000010301,SI\n").encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        movements_before = self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]
        self.db.q("DELETE FROM producto_variantes WHERE id=?", (variant["id"],), fetchall=False, commit=True)
        with self.assertRaisesRegex(ValueError, "planificada para actualizar ya no existe"):
            self.service.apply_stored_plan(plan_id, token, self.owner)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM producto_variantes", fetchone=True)["total"], 0)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"], movements_before)

    def test_variant_plan_rejects_concurrently_occupied_new_combination_before_release(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,1,REM-NEG,7790000010302,SI\n")
        product_id = self.db.q("SELECT producto_id FROM producto_variantes WHERE sku='REM-NEG'", fetchone=True)["producto_id"]
        plan = self.service.build_plan(self.service.parse_tiendanube_csv((HEADER + "remera,Remera,Ropa,Color,Negro,100,40,1,REM-NEG,7790000010302,SI\nremera,,,Color,Blanco,110,45,2,REM-BLA,,SI\n").encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        self.service.product_variants.create_variant(product_id, attributes=[{"attribute_name": "Color", "value_name": "Blanco"}], sku="REM-BLA-CONC", costo=45, precio=110, stock_actual=2, stock_minimo=0, stock_maximo=0)
        with self.assertRaisesRegex(ValueError, "planificada para crear ya existe"):
            self.service.apply_stored_plan(plan_id, token, self.owner)
        rows = self.db.q("SELECT sku FROM producto_variantes ORDER BY sku")
        self.assertEqual([row["sku"] for row in rows], ["REM-BLA-CONC", "REM-NEG"])

    def test_old_variant_plan_without_identity_metadata_is_rejected(self):
        self._import(HEADER + "remera,Remera,Ropa,Color,Negro,100,40,1,REM-NEG,7790000010303,SI\n")
        plan = self.service.build_plan(self.service.parse_tiendanube_csv((HEADER + "remera,Remera,Ropa,Color,Negro,100,40,1,REM-NEG,7790000010303,SI\n").encode()))
        row = plan["products"][0]["rows"][0]
        for field in ("variant_action", "variant_id", "expected_combination_key"):
            row.pop(field, None)
        plan_id, token = self.service.store_plan(plan, self.owner)
        with self.assertRaisesRegex(ValueError, "requiere una nueva vista previa"):
            self.service.apply_stored_plan(plan_id, token, self.owner)
        self.assertEqual(self.db.q("SELECT sku FROM producto_variantes", fetchone=True)["sku"], "REM-NEG")

    def test_confirmation_projects_active_product_limit(self):
        self.db.set_config({
            "license_plan": "BASICA", "license_plan_original": "BASICA", "license_effective_plan": "BASICA",
            "license_tier": "BASICA", "license_status": "activa", "basica_activada": "1",
        })
        for index in range(202):
            self.db.add_producto({"descripcion": f"Local {index}", "marca": "", "categoria": "General", "tipo_unidad": "unidad", "unidad": "unidad", "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 1, "costo": 1, "precio_venta": 1, "codigo_barras": f"77900001{index:04d}"})
        barcodes = [row["codigo_barras"] for row in self.db.q("SELECT codigo_barras FROM productos ORDER BY id")]
        active_barcode, inactive_barcode = barcodes[0], barcodes[-1]

        def reset_active(count):
            self.db.q("UPDATE productos SET activo=0", fetchall=False, commit=True)
            self.db.q("UPDATE productos SET activo=1 WHERE id IN (SELECT id FROM productos ORDER BY id LIMIT ?)", (count,), fetchall=False, commit=True)

        def apply(content):
            plan = self.service.build_plan(self.service.parse_tiendanube_csv(content.encode()))
            self.assertFalse(plan["errors"], plan["errors"])
            plan_id, token = self.service.store_plan(plan, self.owner)
            return self.service.apply_stored_plan(plan_id, token, self.owner)

        def simple(url, name, barcode, visible=""):
            return f"{url},{name},General,,,1,1,,,{barcode},{visible}\n"

        reset_active(200)
        with self.assertRaisesRegex(ValueError, r"Limite de productos \(200\) excedido"):
            apply(HEADER + simple("reactivar", "Reactivar", inactive_barcode, "SI"))
        self.assertEqual(self.db.q("SELECT activo FROM productos WHERE codigo_barras=?", (inactive_barcode,), fetchone=True)["activo"], 0)

        reset_active(199)
        apply(HEADER + simple("reactivar", "Reactivar", inactive_barcode, "SI"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 200)

        reset_active(199)
        apply(HEADER + simple("alta-al-limite", "Alta al limite", "7790000099900", "SI"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 200)

        reset_active(200)
        with self.assertRaisesRegex(ValueError, r"Limite de productos \(200\) excedido"):
            apply(HEADER + simple("alta-excedida", "Alta excedida", "7790000099899", "SI"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE codigo_barras='7790000099899'", fetchone=True)["total"], 0)

        reset_active(200)
        apply(HEADER + simple("activo-si", "Activo", active_barcode, "SI"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 200)
        absent_header = "Identificador de URL,Nombre,Codigo de barras\n"
        apply(absent_header + f"activo-ausente,Activo,{active_barcode}\n")
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 200)

        apply(HEADER + simple("desactivar", "Desactivar", active_barcode, "NO"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 199)

        reset_active(200)
        apply(HEADER + simple("desactivar", "Desactivar", active_barcode, "NO") + simple("alta-neta", "Alta neta", "7790000099901", "SI"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 200)

        reset_active(200)
        with self.assertRaisesRegex(ValueError, r"Limite de productos \(200\) excedido"):
            apply(HEADER + simple("desactivar", "No aplicar", active_barcode, "NO") + simple("alta-uno", "Alta uno", "7790000099902", "SI") + simple("alta-dos", "Alta dos", "7790000099903", "SI"))
        self.assertEqual(self.db.q("SELECT activo FROM productos WHERE codigo_barras=?", (active_barcode,), fetchone=True)["activo"], 1)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE codigo_barras IN (?,?)", ("7790000099902", "7790000099903"), fetchone=True)["total"], 0)

        apply(HEADER + simple("alta-inactiva", "Alta inactiva", "7790000099904", "NO"))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE activo=1", fetchone=True)["total"], 200)
        self.assertEqual(self.db.q("SELECT activo FROM productos WHERE codigo_barras='7790000099904'", fetchone=True)["activo"], 0)

        reset_active(199)
        plan = self.service.build_plan(self.service.parse_tiendanube_csv((HEADER + simple("reactivar-preview", "Reactivar", inactive_barcode, "SI")).encode()))
        plan_id, token = self.service.store_plan(plan, self.owner)
        self.db.q("UPDATE productos SET activo=1 WHERE codigo_barras=?", (barcodes[-2],), fetchall=False, commit=True)
        with self.assertRaisesRegex(ValueError, r"Limite de productos \(200\) excedido"):
            self.service.apply_stored_plan(plan_id, token, self.owner)


class CatalogImportHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        import app as app_module
        import database
        from routes import main as routes_main
        from services import catalog_csv_import, inventory, product_variants
        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "catalog-http.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.db.add_usuario("admin", "1234", "Administrador", "Admin", security_question="color", security_answer="azul")
        self.db.add_usuario("vendedor", "1234", "Vendedor", "Vendedor", security_question="color", security_answer="rojo")
        self.db.add_usuario("otro", "1234", "Administrador", "Otro", security_question="color", security_answer="verde")
        self.db.set_rubro_configurado("tienda")
        self.service = importlib.reload(catalog_csv_import)
        routes_main = importlib.reload(routes_main)
        routes_main.db = self.db
        routes_main.catalog_csv_import = self.service
        routes_main.inventory = importlib.reload(inventory)
        routes_main.product_variants = importlib.reload(product_variants)
        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.db
        self.app = self.app_module.create_app()
        self.owner = int(self.db.get_usuario_by_username("admin")["id"])
        self.other = int(self.db.get_usuario_by_username("otro")["id"])

    def _client(self, username="admin", role="Administrador"):
        client = self.app.test_client()
        user_id = int(self.db.get_usuario_by_username(username)["id"])
        with client.session_transaction() as session:
            session["user"] = {"id": user_id, "username": username, "rol": role}
            session["_csrf_token"] = "catalog-csrf"
        return client

    def _preview(self, client, content, filename="catalogo.csv"):
        response = client.post("/productos/importar/tiendanube", data={"csrf_token": "catalog-csrf", "archivo_csv": (io.BytesIO(content.encode()), filename)}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        match = re.search(r'name="plan_token" value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1)

    def test_preview_confirm_csrf_session_permissions_and_plan_failures(self):
        content = HEADER + "mate,Mate,Accesorios,,,1200,600,3,,7790000010001,SI\n"
        client = self._client()
        self.assertEqual(client.get("/productos/importar/tiendanube").status_code, 200)
        self.assertEqual(client.post("/productos/importar/tiendanube", data={}).status_code, 400)
        self.assertIn("extensión .csv", client.post("/productos/importar/tiendanube", data={"csrf_token": "catalog-csrf", "archivo_csv": (io.BytesIO(b"x"), "x.txt")}, content_type="multipart/form-data").get_data(as_text=True))
        token = self._preview(client, content)
        with client.session_transaction() as session:
            self.assertEqual(set(session) - {"user", "_csrf_token", "catalog_csv_import_plan_id"}, set())
            plan_id = session["catalog_csv_import_plan_id"]
        cookie = client.get_cookie("session").value
        self.assertNotIn("Mate", cookie)
        self.assertNotIn("7790000010001", cookie)
        self.assertEqual(client.post("/productos/importar/tiendanube/confirmar", data={"plan_token": token}).status_code, 400)
        self.assertEqual(client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": "wrong"}).status_code, 302)
        with client.session_transaction() as session:
            self.assertNotIn("catalog_csv_import_plan_id", session)
        token = self._preview(client, content)
        with client.session_transaction() as session:
            plan_id = session["catalog_csv_import_plan_id"]
        confirmed = client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token})
        self.assertEqual(confirmed.status_code, 302)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE codigo_barras=?", ("7790000010001",), fetchone=True)["total"], 1)
        with client.session_transaction() as session:
            session.pop("_flashes", None)
            session["catalog_csv_import_plan_id"] = plan_id
        movements_before = self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]
        variants_before = self.db.q("SELECT COUNT(*) AS total FROM producto_variantes", fetchone=True)["total"]
        retry = client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token})
        self.assertEqual(retry.status_code, 302)
        with client.session_transaction() as session:
            flashes = session.get("_flashes", [])
            self.assertTrue(flashes)
            self.assertIn("ya fue utilizado", flashes[-1][1])
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE codigo_barras=?", ("7790000010001",), fetchone=True)["total"], 1)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM producto_variantes", fetchone=True)["total"], variants_before)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"], movements_before)
        with self._client("vendedor", "Vendedor") as seller:
            self.assertEqual(seller.get("/productos/importar/tiendanube").status_code, 302)
        foreign_plan, foreign_token = self.service.store_plan(self.service.build_plan(self.service.parse_tiendanube_csv(content.encode())), self.other)
        with client.session_transaction() as session:
            session["catalog_csv_import_plan_id"] = foreign_plan
        self.assertEqual(client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": foreign_token}).status_code, 302)
        expired, expired_token = self.service.store_plan(self.service.build_plan(self.service.parse_tiendanube_csv(content.encode())), self.owner)
        self.db.q("UPDATE catalog_import_plans SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (expired,), fetchall=False, commit=True)
        with client.session_transaction() as session:
            session["catalog_csv_import_plan_id"] = expired
        self.assertEqual(client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": expired_token}).status_code, 302)

    def test_preview_without_file_is_rejected_after_valid_csrf(self):
        client = self._client()
        response = client.post("/productos/importar/tiendanube", data={"csrf_token": "catalog-csrf"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Seleccion\u00e1 un archivo con extensi\u00f3n .csv.", response.get_data(as_text=True))
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM catalog_import_plans", fetchone=True)["total"], 0)

    def test_product_list_keeps_both_csv_import_routes(self):
        response = self._client().get("/productos")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('href="/productos/importar"', body)
        self.assertIn('href="/productos/importar/tiendanube"', body)

    def test_new_preview_invalidates_old_and_catalog_rollback_stays_consumed(self):
        client = self._client()
        first = HEADER + "uno,Uno,Accesorios,,,10,5,1,,7790000010002,SI\n"
        second = HEADER + "dos,Dos,Accesorios,,,10,5,1,,7790000010003,SI\n"
        old_token = self._preview(client, first)
        with client.session_transaction() as session:
            old_id = session["catalog_csv_import_plan_id"]
        self._preview(client, second)
        with self.assertRaisesRegex(ValueError, "no existe"):
            self.service.apply_stored_plan(old_id, old_token, self.owner)
        batch = HEADER + "tres,Tres,Accesorios,,,10,5,1,,7790000010004,SI\ncuatro,Cuatro,Accesorios,,,10,5,2,,7790000010005,SI\n"
        token = self._preview(client, batch)
        with client.session_transaction() as session:
            plan_id = session["catalog_csv_import_plan_id"]
        original = self.service.inventory.adjust_inventory_item_in_cursor
        calls = {"count": 0}
        def fail_second(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("forced persistence failure")
            return original(*args, **kwargs)
        with mock.patch.object(self.service.inventory, "adjust_inventory_item_in_cursor", side_effect=fail_second):
            self.assertEqual(client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token}).status_code, 302)
        self.assertEqual(self.db.q("SELECT COUNT(*) AS total FROM productos WHERE codigo_barras IN (?,?)", ("7790000010004", "7790000010005"), fetchone=True)["total"], 0)
        self.assertIsNotNone(self.db.q("SELECT consumed_at FROM catalog_import_plans WHERE id=? AND consumed_at IS NOT NULL", (plan_id,), fetchone=True))
        with self.assertRaisesRegex(ValueError, "ya fue utilizado"):
            self.service.apply_stored_plan(plan_id, token, self.owner)

    def test_http_variant_creation_update_and_preview_validation(self):
        client = self._client()
        initial = HEADER + "remera,Remera,Ropa,Color,Negro,100,40,10,REM-HTTP,,SI\n"
        token = self._preview(client, initial)
        self.assertEqual(client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token}).status_code, 302)
        variant = self.db.q("SELECT id, producto_id FROM producto_variantes WHERE sku='REM-HTTP'", fetchone=True)
        self.assertIsNotNone(variant)
        self.db.q("UPDATE stock_variantes SET stock_minimo=2, stock_maximo=20 WHERE variante_id=?", (variant["id"],), fetchall=False, commit=True)
        absent = "Identificador de URL,Nombre,Nombre de propiedad 1,Valor de propiedad 1,SKU\nremera,Remera,Color,Negro,REM-HTTP\n"
        token = self._preview(client, absent)
        client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token})
        stock = self.db.q("SELECT stock_actual, stock_minimo, stock_maximo FROM stock_variantes WHERE variante_id=?", (variant["id"],), fetchone=True)
        self.assertEqual(tuple(stock), (10.0, 2.0, 20.0))
        token = self._preview(client, HEADER + "remera,Remera,Ropa,Color,Negro,100,40,0,REM-HTTP,,NO\n")
        client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token})
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 0)
        token = self._preview(client, HEADER + "remera,Remera,Ropa,Color,Negro,100,40,7,REM-HTTP,,SI\n")
        client.post("/productos/importar/tiendanube/confirmar", data={"csrf_token": "catalog-csrf", "plan_token": token})
        self.assertEqual(self.db.q("SELECT activo FROM producto_variantes WHERE id=?", (variant["id"],), fetchone=True)["activo"], 1)
        self.assertEqual(self.db.q("SELECT stock_actual FROM stock_variantes WHERE variante_id=?", (variant["id"],), fetchone=True)["stock_actual"], 7.0)
        invalid = client.post("/productos/importar/tiendanube", data={"csrf_token": "catalog-csrf", "archivo_csv": (io.BytesIO((HEADER + "x,X,,,,1,1,1,,7790000010006,TALVEZ\n").encode()), "invalid.csv")}, content_type="multipart/form-data")
        self.assertIn("Fila 2", invalid.get_data(as_text=True))
        duplicate = HEADER + "x,X,Ropa,Color,Negro,1,1,1,A,,SI\nx,,,Color,Negro,1,1,1,B,,SI\n"
        preview = client.post("/productos/importar/tiendanube", data={"csrf_token": "catalog-csrf", "archivo_csv": (io.BytesIO(duplicate.encode()), "duplicate.csv")}, content_type="multipart/form-data")
        self.assertIn("combinacion de atributos duplicada", preview.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
