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


class PosVariantsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"

        import database
        from routes import main as routes_main
        from services import inventory
        from services import product_variants

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.inventory = importlib.reload(inventory)
        self.product_variants = importlib.reload(product_variants)
        self.routes_main = importlib.reload(routes_main)
        self.routes_main.db = self.database
        self.routes_main.inventory = self.inventory
        self.routes_main.product_variants = self.product_variants

        auto_refresh_patcher = mock.patch.object(self.routes_main, "ensure_license_auto_refresh_thread", autospec=True)
        auto_refresh_patcher.start()
        self.addCleanup(auto_refresh_patcher.stop)

        app_module = importlib.import_module("app")
        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.database
        self.app = self.app_module.create_app()
        self.app.config["TESTING"] = True

        self.user_id = self.database.add_usuario(
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

    def _login_admin(self, client):
        with client.session_transaction() as session:
            session["_csrf_token"] = "test-token"
        response = client.post(
            "/login",
            data={"username": "admin", "password": "1234", "csrf_token": "test-token"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def _abrir_caja(self):
        self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (self.user_id, "2026-07-29 09:00:00", 0, 0),
            commit=True,
        )

    def _crear_producto(self, descripcion="Producto", stock=0, costo=100, precio=150, codigo_barras=""):
        return int(
            self.database.add_producto(
                {
                    "descripcion": descripcion,
                    "marca": "",
                    "categoria": "General",
                    "tipo_unidad": "unidad",
                    "unidad": "unidad",
                    "stock_actual": stock,
                    "stock_minimo": 0,
                    "stock_maximo": 50,
                    "costo": costo,
                    "precio_venta": precio,
                    "iva": "21%",
                    "codigo_barras": codigo_barras,
                }
            )
        )

    def _crear_variante(self, producto_id, color, *, sku, codigo_barras="", costo=None, precio=None, promo=None, stock=0):
        return int(
            self.product_variants.create_variant(
                producto_id,
                attributes=[{"attribute_name": "Color", "value_name": color}],
                sku=sku,
                codigo_barras=codigo_barras,
                costo=costo,
                precio=precio,
                precio_promocional=promo,
                stock_actual=stock,
                stock_minimo=0,
                stock_maximo=50,
            )
        )

    def _activar_variantes(self, producto_id, allocations):
        self.inventory.activate_variant_stock_mode(
            producto_id,
            allocations,
            motivo="Test POS variantes",
            usuario="admin",
            rol="Administrador",
        )

    def _stock_producto(self, producto_id):
        row = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        return float(row["stock_actual"] or 0) if row else 0.0

    def _stock_variante(self, variante_id):
        row = self.database.q("SELECT stock_actual FROM stock_variantes WHERE variante_id=?", (variante_id,), fetchone=True)
        return float(row["stock_actual"] or 0) if row else 0.0

    def _cart_item(self, item, cantidad=1):
        return {
            "producto_id": int(item["producto_id"]),
            "variante_id": item.get("variante_id"),
            "stock_fuente": item["stock_fuente"],
            "codigo_interno": item["codigo_interno"],
            "descripcion": item["descripcion"],
            "categoria": item["categoria"],
            "unidad": "Unidad",
            "cantidad": cantidad,
            "precio_unitario": float(item["precio_venta"]),
            "costo_unitario": float(item["costo"]),
            "iva": "21%",
            "descuento": 0,
            "subtotal": cantidad * float(item["precio_venta"]),
        }

    def test_busqueda_pos_encuentra_legacy_y_variantes_por_descripcion_sku_y_barras(self):
        legacy_id = self._crear_producto("Yerba premium", stock=4, codigo_barras="YER-001")
        producto_id = self._crear_producto("Zapatilla", stock=3, costo=40, precio=100)
        azul = self._crear_variante(producto_id, "Azul", sku="ZAP-AZUL", codigo_barras="ZAP-BC", precio=120, stock=3)
        self._activar_variantes(producto_id, [{"variant_id": azul, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50}])

        self.assertEqual(int(self.database.buscar_productos_pos("YER-001")[0]["producto_id"]), legacy_id)
        self.assertEqual(int(self.database.buscar_productos_pos("ZAP-AZUL")[0]["variante_id"]), azul)
        self.assertEqual(int(self.database.buscar_productos_pos("ZAP-BC")[0]["variante_id"]), azul)
        self.assertEqual(int(self.database.buscar_productos_pos("Zapatilla")[0]["variante_id"]), azul)

    def test_lector_resuelve_unico_codigo_o_informa_ambiguedad(self):
        producto_id = self._crear_producto("Campera", stock=5, codigo_barras="CAMP")
        negro = self._crear_variante(producto_id, "Negro", sku="CAMP-NEG", stock=2)
        rojo = self._crear_variante(producto_id, "Rojo", sku="CAMP-ROJ", stock=3)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        exacto = self.database.resolve_producto_pos_exact("CAMP-NEG")
        ambiguo = self.database.resolve_producto_pos_exact("CAMP")

        self.assertEqual(exacto["status"], "found")
        self.assertEqual(int(exacto["items"][0]["variante_id"]), negro)
        self.assertEqual(ambiguo["status"], "ambiguous")
        self.assertEqual({int(item["variante_id"]) for item in ambiguo["items"]}, {negro, rojo})

    def test_api_producto_buscar_ambiguo_devuelve_409_y_todas_las_variantes(self):
        producto_id = self._crear_producto("Campera API", stock=5, codigo_barras="CAMP-API")
        negro = self._crear_variante(producto_id, "Negro", sku="CAMP-API-NEG", stock=2)
        rojo = self._crear_variante(producto_id, "Rojo", sku="CAMP-API-ROJ", stock=3)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get("/api/producto/buscar?codigo=CAMP-API")

        data = response.get_json()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertTrue(data["ambiguous"])
        self.assertEqual({int(item["variante_id"]) for item in data["productos"]}, {negro, rojo})

    def test_codigo_unico_sigue_resolviendo_variante_correcta(self):
        producto_id = self._crear_producto("Zapatilla unica", stock=5, codigo_barras="ZAP-PADRE")
        azul = self._crear_variante(producto_id, "Azul", sku="ZAP-UNICA-AZUL", codigo_barras="ZAP-AZUL-BC", stock=2)
        rojo = self._crear_variante(producto_id, "Rojo", sku="ZAP-UNICA-ROJO", stock=3)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": azul, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        result = self.database.resolve_producto_pos_exact("ZAP-AZUL-BC")

        self.assertEqual(result["status"], "found")
        self.assertEqual(int(result["items"][0]["variante_id"]), azul)

    def test_codigo_exacto_no_depende_del_limite_de_busqueda_general(self):
        for index in range(55):
            self._crear_producto(f"A Coincidencia limite {index:02d}", stock=1, codigo_barras=f"LIM-{index:02d}")
        producto_id = self._crear_producto("Z Coincidencia limite exacta", stock=2, codigo_barras="LIMITE-EXACTO")

        busqueda_general = self.database.buscar_productos_pos("LIMITE")
        result = self.database.resolve_producto_pos_exact("LIMITE-EXACTO")

        self.assertEqual(len(busqueda_general), 50)
        self.assertNotIn(producto_id, {int(item["producto_id"]) for item in busqueda_general})
        self.assertEqual(result["status"], "found")
        self.assertEqual(int(result["items"][0]["producto_id"]), producto_id)

    def test_codigo_padre_compartido_exige_seleccion_manual(self):
        producto_id = self._crear_producto("Buzo padre", stock=5)
        self.database.q(
            "UPDATE productos SET codigo_interno=? WHERE id=?",
            ("BUZ-PADRE", producto_id),
            commit=True,
        )
        negro = self._crear_variante(producto_id, "Negro", sku="BUZ-PADRE-NEG", stock=2)
        rojo = self._crear_variante(producto_id, "Rojo", sku="BUZ-PADRE-ROJ", stock=3)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        result = self.database.resolve_producto_pos_exact("BUZ-PADRE")

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual({int(item["variante_id"]) for item in result["items"]}, {negro, rojo})

    def test_codigo_padre_compartido_por_mas_de_50_variantes_devuelve_ambiguedad_completa(self):
        producto_id = self._crear_producto("Buzo masivo", stock=55)
        self.database.q(
            "UPDATE productos SET codigo_interno=? WHERE id=?",
            ("BUZ-MASIVO", producto_id),
            commit=True,
        )
        variants = [
            self._crear_variante(producto_id, f"Color {index:02d}", sku=f"BUZ-MASIVO-{index:02d}", stock=0)
            for index in range(55)
        ]
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": variant_id, "stock_actual": 1, "stock_minimo": 0, "stock_maximo": 50}
                for variant_id in variants
            ],
        )

        result = self.database.resolve_producto_pos_exact("BUZ-MASIVO")

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["items"]), len(variants))
        self.assertEqual({int(item["variante_id"]) for item in result["items"]}, set(variants))

    def test_busqueda_por_descripcion_con_unico_resultado_sigue_disponible(self):
        producto_id = self._crear_producto("Descripcion exacta POS", stock=2)

        items = self.database.buscar_productos_pos("Descripcion exacta POS")

        self.assertEqual(len(items), 1)
        self.assertEqual(int(items[0]["producto_id"]), producto_id)
        self.assertIsNone(items[0]["variante_id"])

    def test_template_pos_no_resuelve_automaticamente_primera_coincidencia_ambigua(self):
        template = (PROJECT_ROOT / "templates" / "punto_venta.html").read_text(encoding="utf-8")
        buscar_inicio = template.index("async function buscarProducto()")
        buscar_fin = template.index("async function confirmarItem()", buscar_inicio)
        buscar_producto = template[buscar_inicio:buscar_fin]

        self.assertIn("exactResult.status === 'ambiguous'", buscar_producto)
        self.assertNotIn("items.find", buscar_producto)
        self.assertIn("if (items.length === 1)", buscar_producto)

    def test_carrito_manual_persiste_variante_y_precio_promocional(self):
        producto_id = self._crear_producto("Remera", stock=4, costo=20, precio=100)
        negro = self._crear_variante(producto_id, "Negro", sku="REM-NEG", costo=35, precio=120, promo=99, stock=4)
        self._activar_variantes(producto_id, [{"variant_id": negro, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50}])

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                "/api/carrito/agregar",
                json={"producto_id": producto_id, "variante_id": negro, "cantidad": 2},
                headers={"X-CSRFToken": "test-token"},
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        item = data["carrito"][0]
        self.assertEqual(item["variante_id"], negro)
        self.assertEqual(item["stock_fuente"], "variante")
        self.assertEqual(float(item["precio_unitario"]), 99.0)
        self.assertEqual(float(item["costo_unitario"]), 35.0)

    def test_venta_descuenta_exactamente_variante_elegida_y_detalle_conserva_fuente(self):
        producto_id = self._crear_producto("Buzo", stock=5, costo=30, precio=100)
        negro = self._crear_variante(producto_id, "Negro", sku="BUZ-NEG", stock=3)
        rojo = self._crear_variante(producto_id, "Rojo", sku="BUZ-ROJ", stock=2)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        item = self.database.get_sellable_item_pos(producto_id, negro)

        venta_id = self.database.crear_venta([self._cart_item(item, 2)], "Mostrador", "Efectivo", 0, "admin")

        detalle = self.database.get_venta_detalle(venta_id)[0]
        self.assertEqual(int(detalle["variante_id"]), negro)
        self.assertEqual(detalle["stock_fuente"], "variante")
        self.assertEqual(self._stock_variante(negro), 1.0)
        self.assertEqual(self._stock_variante(rojo), 2.0)
        self.assertEqual(self._stock_producto(producto_id), 5.0)

    def test_venta_sin_stock_no_persistente_ni_descuenta_otra_variante(self):
        producto_id = self._crear_producto("Gorra", stock=5)
        negro = self._crear_variante(producto_id, "Negro", sku="GOR-NEG", stock=1)
        rojo = self._crear_variante(producto_id, "Rojo", sku="GOR-ROJ", stock=4)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 1, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        item = self.database.get_sellable_item_pos(producto_id, negro)

        with self.assertRaisesRegex(ValueError, "stock negativo"):
            self.database.crear_venta([self._cart_item(item, 2)], "Mostrador", "Efectivo", 0, "admin")

        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM ventas", fetchone=True)["total"]), 0)
        self.assertEqual(self._stock_variante(negro), 1.0)
        self.assertEqual(self._stock_variante(rojo), 4.0)

    def test_venta_falla_si_carrito_legacy_queda_migrado_a_variantes(self):
        producto_id = self._crear_producto("Migrado POS", stock=5, costo=10, precio=20, codigo_barras="MIG-POS")
        item_legacy = self.database.get_sellable_item_pos(producto_id)
        variante = self._crear_variante(producto_id, "Unica", sku="MIG-POS-VAR", stock=0)
        self._activar_variantes(producto_id, [{"variant_id": variante, "stock_actual": 5, "stock_minimo": 0, "stock_maximo": 50}])

        with self.assertRaisesRegex(ValueError, "debe indicar una variante"):
            self.database.crear_venta([self._cart_item(item_legacy, 2)], "Mostrador", "Efectivo", 0, "admin")

        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM ventas", fetchone=True)["total"]), 0)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM ventas_detalle", fetchone=True)["total"]), 0)
        self.assertEqual(self._stock_producto(producto_id), 5.0)
        self.assertEqual(self._stock_variante(variante), 5.0)

    def test_venta_con_variante_valida_no_confia_en_stock_fuente_del_carrito(self):
        producto_id = self._crear_producto("Migrado con variante", stock=3, costo=10, precio=20)
        variante = self._crear_variante(producto_id, "Unica", sku="MIG-VAR-OK", stock=0)
        self._activar_variantes(producto_id, [{"variant_id": variante, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50}])
        item = self._cart_item(self.database.get_sellable_item_pos(producto_id, variante), 2)
        item["stock_fuente"] = "producto"

        venta_id = self.database.crear_venta([item], "Mostrador", "Efectivo", 0, "admin")

        detalle = self.database.get_venta_detalle(venta_id)[0]
        self.assertEqual(int(detalle["variante_id"]), variante)
        self.assertEqual(detalle["stock_fuente"], "variante")
        self.assertEqual(self._stock_producto(producto_id), 3.0)
        self.assertEqual(self._stock_variante(variante), 1.0)

    def test_rollback_completo_si_falla_descuento_de_venta(self):
        producto_id = self._crear_producto("Rollback venta", stock=3)
        item = self.database.get_sellable_item_pos(producto_id)

        with mock.patch.object(self.inventory, "apply_inventory_delta_in_cursor", side_effect=RuntimeError("fallo stock")):
            with self.assertRaisesRegex(RuntimeError, "fallo stock"):
                self.database.crear_venta([self._cart_item(item, 1)], "Mostrador", "Efectivo", 0, "admin")

        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM ventas", fetchone=True)["total"]), 0)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM ventas_detalle", fetchone=True)["total"]), 0)
        self.assertEqual(self._stock_producto(producto_id), 3.0)

    def test_anulacion_repone_misma_variante_aunque_este_inactiva(self):
        producto_id = self._crear_producto("Camisa", stock=4)
        vendida = self._crear_variante(producto_id, "Negro", sku="CAM-NEG", stock=2)
        otra = self._crear_variante(producto_id, "Azul", sku="CAM-AZU", stock=2)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": vendida, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": otra, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        venta_id = self.database.crear_venta([self._cart_item(self.database.get_sellable_item_pos(producto_id, vendida), 1)], "Mostrador", "Efectivo", 0, "admin")
        self.product_variants.set_variant_active(producto_id, vendida, False)

        self.database.anular_venta(venta_id, motivo="Devolucion", usuario="admin", rol="Administrador")

        self.assertEqual(self._stock_variante(vendida), 2.0)
        self.assertEqual(self._stock_variante(otra), 2.0)
        movimientos = self.database.q(
            "SELECT variante_id, stock_fuente, tipo, cantidad FROM stock_movimientos WHERE producto_id=? ORDER BY id",
            (producto_id,),
        )
        self.assertIn((vendida, "stock_variantes", "VENTA", -1.0), [(row["variante_id"], row["stock_fuente"], row["tipo"], float(row["cantidad"])) for row in movimientos])
        self.assertIn((vendida, "stock_variantes", "ANULACION_VENTA", 1.0), [(row["variante_id"], row["stock_fuente"], row["tipo"], float(row["cantidad"])) for row in movimientos])

    def test_anulacion_historica_legacy_restaura_fuente_original_tras_migrar(self):
        producto_id = self._crear_producto("Venta legacy historica", stock=5, costo=10, precio=20)
        venta_id = self.database.crear_venta(
            [self._cart_item(self.database.get_sellable_item_pos(producto_id), 2)],
            "Mostrador",
            "Efectivo",
            0,
            "admin",
        )
        variante = self._crear_variante(producto_id, "Unica", sku="LEG-HIST-VAR", stock=0)
        self._activar_variantes(producto_id, [{"variant_id": variante, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50}])

        self.database.anular_venta(venta_id, motivo="Devolucion historica", usuario="admin", rol="Administrador")

        detalle = self.database.get_venta_detalle(venta_id)[0]
        self.assertEqual(detalle["stock_fuente"], "producto")
        self.assertEqual(self._stock_producto(producto_id), 5.0)
        self.assertEqual(self._stock_variante(variante), 3.0)

    def test_producto_legacy_mantiene_flujo_de_venta(self):
        producto_id = self._crear_producto("Legacy POS", stock=3, costo=10, precio=25, codigo_barras="LEG-POS")
        item = self.database.buscar_productos_pos("LEG-POS")[0]

        venta_id = self.database.crear_venta([self._cart_item(item, 2)], "Mostrador", "Efectivo", 0, "admin")

        detalle = self.database.get_venta_detalle(venta_id)[0]
        self.assertIsNone(detalle["variante_id"])
        self.assertEqual(detalle["stock_fuente"], "producto")
        self.assertEqual(self._stock_producto(producto_id), 1.0)

    def test_base_legacy_recibe_columnas_de_detalle_venta_sin_inferir_variante(self):
        legacy_db = Path(self.temp_dir.name) / "legacy_pos.db"
        conn = sqlite3.connect(legacy_db)
        conn.executescript(
            """
            CREATE TABLE ventas_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER,
                producto_id INTEGER DEFAULT 0,
                descripcion TEXT DEFAULT '',
                cantidad REAL DEFAULT 1
            );
            """
        )
        conn.execute("INSERT INTO ventas_detalle (venta_id, producto_id, descripcion, cantidad) VALUES (1, 1, 'Legacy', 1)")
        conn.commit()
        conn.close()

        self.database.DB_PATH = str(legacy_db)
        self.database._db_initialized = False
        self.database.init_db()

        detalle = self.database.q("SELECT variante_id, stock_fuente FROM ventas_detalle WHERE id=1", fetchone=True)
        self.assertIsNone(detalle["variante_id"])
        self.assertEqual(detalle["stock_fuente"], "producto")


if __name__ == "__main__":
    unittest.main()
