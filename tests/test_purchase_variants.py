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


class PurchaseVariantsTests(unittest.TestCase):
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
        from services import inventory
        from services import product_variants

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.product_variants = importlib.reload(product_variants)
        self.inventory = importlib.reload(inventory)
        self.routes_main = importlib.reload(routes_main)
        self.routes_main.db = self.database
        self.routes_main.inventory = self.inventory
        self.routes_main.product_variants = self.product_variants

        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.database
        self.app = self.app_module.create_app()
        self.app.config["TESTING"] = True

        self.database.add_usuario(
            "admin",
            "1234",
            "Administrador",
            "Administrador Test",
            security_question="color",
            security_answer="azul",
        )
        self.database.set_rubro_configurado("tienda")
        self.proveedor_id = int(self.database.add_proveedor({"nombre": "Proveedor Compras"}))

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

    def _crear_variante(self, producto_id, color, *, sku, codigo_barras="", costo=None, stock=0, activo=1):
        variant_id = int(
            self.product_variants.create_variant(
                producto_id,
                attributes=[{"attribute_name": "Color", "value_name": color}],
                sku=sku,
                codigo_barras=codigo_barras,
                costo=costo,
                precio=None,
                precio_promocional=None,
                stock_actual=stock,
                stock_minimo=0,
                stock_maximo=50,
            )
        )
        if not activo:
            self.product_variants.update_variant(producto_id, variant_id, activo=0)
        return variant_id

    def _activar_variantes(self, producto_id, allocations):
        self.inventory.activate_variant_stock_mode(
            producto_id,
            allocations,
            motivo="Test variantes",
            usuario="admin",
            rol="Administrador",
        )

    def _stock_producto(self, producto_id):
        row = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        return float(row["stock_actual"] or 0) if row else 0.0

    def _stock_variante(self, variant_id):
        row = self.database.q("SELECT stock_actual FROM stock_variantes WHERE variante_id=?", (variant_id,), fetchone=True)
        return float(row["stock_actual"] or 0) if row else 0.0

    def _stock_operativo_total(self, producto_id):
        return sum(
            float(item["stock_actual"] or 0)
            for item in self.inventory.list_inventory_items()
            if int(item["producto_id"]) == int(producto_id)
        )

    def _compra_data(self, producto_id, *, variante_id=None, cantidad=2, costo_unitario=0):
        return {
            "fecha": "2026-07-28",
            "numero_remito": "REM-001",
            "proveedor_id": self.proveedor_id,
            "proveedor_nombre": "Proveedor Compras",
            "producto_id": producto_id,
            "variante_id": variante_id or "",
            "cantidad": cantidad,
            "costo_unitario": costo_unitario,
            "total": float(cantidad) * float(costo_unitario),
            "observaciones": "",
        }

    def test_compra_legacy_incrementa_solo_stock(self):
        producto_id = self._crear_producto("Legacy", stock=3, costo=80, codigo_barras="LEG-BC")

        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=4, costo_unitario=80))

        self.assertGreater(compra_id, 0)
        self.assertEqual(self._stock_producto(producto_id), 7.0)
        self.assertEqual(self.database.q("SELECT COUNT(*) AS total FROM stock_variantes", fetchone=True)["total"], 0)
        compra = self.database.get_compra(compra_id)
        self.assertIsNone(compra["variante_id"])
        self.assertEqual(compra["stock_fuente"], "producto")

    def test_compra_legacy_anulacion_antes_de_migrar_revierte_stock_producto(self):
        producto_id = self._crear_producto("Legacy anulable", stock=3, costo=80)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=4, costo_unitario=80))

        self.database.anular_compra(compra_id, motivo="Carga duplicada", usuario="admin", rol="Administrador")

        compra = self.database.get_compra(compra_id)
        self.assertEqual(int(compra["anulada"]), 1)
        self.assertEqual(self._stock_producto(producto_id), 3.0)
        self.assertEqual(self._stock_operativo_total(producto_id), 3.0)
        movimientos = self.database.q(
            "SELECT variante_id, stock_fuente, cantidad FROM stock_movimientos WHERE producto_id=? AND tipo IN ('COMPRA', 'ANULACION_COMPRA') ORDER BY id",
            (producto_id,),
        )
        self.assertEqual(
            [(row["variante_id"], row["stock_fuente"], float(row["cantidad"])) for row in movimientos],
            [(None, "stock", 4.0), (None, "stock", -4.0)],
        )

    def test_compra_por_variante_incrementa_solo_variante_elegida(self):
        producto_id = self._crear_producto("Remera", stock=0, costo=50)
        negro = self._crear_variante(producto_id, "Negro", sku="REM-NEG", codigo_barras="789NEG", costo=70)
        rojo = self._crear_variante(producto_id, "Rojo", sku="REM-ROJ", codigo_barras="789ROJ", costo=90)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": rojo, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=negro, cantidad=5, costo_unitario=70))

        self.assertGreater(compra_id, 0)
        self.assertEqual(self._stock_producto(producto_id), 0.0)
        self.assertEqual(self._stock_variante(negro), 5.0)
        self.assertEqual(self._stock_variante(rojo), 0.0)
        compra = self.database.get_compra(compra_id)
        self.assertEqual(int(compra["variante_id"]), negro)
        self.assertEqual(compra["stock_fuente"], "variante")
        self.assertEqual(int(compra["stock_reversion_bloqueada"]), 0)
        self.assertIn("Color: Negro", compra["descripcion"])

    def test_busqueda_por_sku_codigo_y_descripcion(self):
        legacy_id = self._crear_producto("Yerba premium", stock=0, codigo_barras="YER-001")
        producto_id = self._crear_producto("Zapatilla", stock=0)
        variante_id = self._crear_variante(producto_id, "Azul", sku="ZAP-AZUL", codigo_barras="ZAP-BC", costo=None)
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])

        self.assertEqual(int(self.database.get_purchase_items("YER-001")[0]["producto_id"]), legacy_id)
        self.assertEqual(int(self.database.get_purchase_items("ZAP-AZUL")[0]["variante_id"]), variante_id)
        self.assertEqual(int(self.database.get_purchase_items("ZAP-BC")[0]["variante_id"]), variante_id)
        self.assertEqual(int(self.database.get_purchase_items("Zapatilla")[0]["variante_id"]), variante_id)

    def test_selector_compras_incluye_mas_de_500_items_y_permite_ultimo(self):
        ultimo_id = None
        for index in range(501):
            descripcion = f"Item masivo {index:03d}"
            if index == 500:
                descripcion = "ZZZ ultimo seleccionable"
            ultimo_id = self._crear_producto(descripcion, stock=0, costo=11)

        items = self.database.get_purchase_items()
        self.assertGreaterEqual(len(items), 501)
        self.assertTrue(any(int(item["producto_id"]) == ultimo_id for item in items))

        with self.app.test_client() as client:
            self._login_admin(client)
            response_listado = client.get("/compras")
            self.assertEqual(response_listado.status_code, 200)
            self.assertIn(b"ZZZ ultimo seleccionable", response_listado.data)
            response = client.post(
                "/compras/nueva",
                data={
                    "csrf_token": "test-token",
                    "fecha": "2026-07-28",
                    "proveedor_id": self.proveedor_id,
                    "producto_item": f"{ultimo_id}:",
                    "cantidad": "2",
                    "costo_unitario": "11",
                    "condicion_pago": "contado",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._stock_producto(ultimo_id), 2.0)

    def test_costo_propio_y_fallback(self):
        producto_id = self._crear_producto("Buzo", stock=0, costo=40)
        propio = self._crear_variante(producto_id, "Negro", sku="BUZ-NEG", costo=65)
        fallback = self._crear_variante(producto_id, "Blanco", sku="BUZ-BLA", costo=None)
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": propio, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": fallback, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        costos = {int(item["variante_id"]): float(item["costo_unitario"]) for item in self.database.get_purchase_items("Buzo")}

        self.assertEqual(costos[propio], 65.0)
        self.assertEqual(costos[fallback], 40.0)

    def test_rechaza_variante_inactiva_ajena_y_producto_sin_variante(self):
        producto_id = self._crear_producto("Camisa", stock=0)
        otro_producto_id = self._crear_producto("Pantalon", stock=0)
        activa = self._crear_variante(producto_id, "Negro", sku="CAM-NEG")
        inactiva = self._crear_variante(producto_id, "Rojo", sku="CAM-ROJ", activo=0)
        ajena = self._crear_variante(otro_producto_id, "Azul", sku="PAN-AZU")
        self._activar_variantes(producto_id, [{"variant_id": activa, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])

        with self.assertRaisesRegex(ValueError, "selecciona una variante activa"):
            self.database.add_compra(self._compra_data(producto_id, variante_id=None, cantidad=1))
        with self.assertRaisesRegex(ValueError, "inactiva|pertenece"):
            self.database.add_compra(self._compra_data(producto_id, variante_id=inactiva, cantidad=1))
        with self.assertRaisesRegex(ValueError, "inactiva|pertenece"):
            self.database.add_compra(self._compra_data(producto_id, variante_id=ajena, cantidad=1))

    def test_rollback_completo_si_falla_una_linea(self):
        producto_id = self._crear_producto("Campera", stock=0)
        variante_id = self._crear_variante(producto_id, "Negro", sku="CAMP-NEG")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])

        with mock.patch.object(self.database, "_apply_purchase_delta", side_effect=RuntimeError("fallo stock")):
            with self.assertRaises(RuntimeError):
                self.database.add_compra(self._compra_data(producto_id, variante_id=variante_id, cantidad=3))

        self.assertEqual(self.database.q("SELECT COUNT(*) AS total FROM compras", fetchone=True)["total"], 0)
        self.assertEqual(self._stock_variante(variante_id), 0.0)

    def test_edicion_cantidad_aplica_solo_diferencia(self):
        producto_id = self._crear_producto("Legacy editable", stock=0, costo=10)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5, costo_unitario=10))

        data = self._compra_data(producto_id, cantidad=7, costo_unitario=10)
        data["total"] = 70
        self.database.update_compra(compra_id, data)

        self.assertEqual(self._stock_producto(producto_id), 7.0)
        movimientos = self.database.q("SELECT cantidad FROM stock_movimientos WHERE producto_id=? ORDER BY id", (producto_id,))
        self.assertEqual([float(row["cantidad"]) for row in movimientos], [5.0, 2.0])

    def test_cambio_de_variante_revierte_origen_y_aplica_destino(self):
        producto_id = self._crear_producto("Gorra", stock=0)
        negro = self._crear_variante(producto_id, "Negro", sku="GOR-NEG")
        azul = self._crear_variante(producto_id, "Azul", sku="GOR-AZU")
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": negro, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": azul, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=negro, cantidad=4))

        self.database.update_compra(compra_id, self._compra_data(producto_id, variante_id=azul, cantidad=4))

        self.assertEqual(self._stock_variante(negro), 0.0)
        self.assertEqual(self._stock_variante(azul), 4.0)

    def test_edicion_de_legacy_a_variante_revierte_fuente_anterior_y_aplica_nueva(self):
        producto_legacy = self._crear_producto("Origen legacy", stock=0, costo=10)
        producto_variantes = self._crear_producto("Destino variante", stock=1, costo=20)
        variante_id = self._crear_variante(producto_variantes, "Negro", sku="EVF-NEG")
        self._activar_variantes(producto_variantes, [{"variant_id": variante_id, "stock_actual": 1, "stock_minimo": 0, "stock_maximo": 50}])
        compra_id = self.database.add_compra(self._compra_data(producto_legacy, cantidad=4, costo_unitario=10))

        data = self._compra_data(producto_variantes, variante_id=variante_id, cantidad=3, costo_unitario=20)
        self.database.update_compra(compra_id, data)

        compra = self.database.get_compra(compra_id)
        self.assertEqual(compra["stock_fuente"], "variante")
        self.assertEqual(self._stock_producto(producto_legacy), 0.0)
        self.assertEqual(self._stock_variante(variante_id), 4.0)
        movimientos = self.database.q(
            "SELECT producto_id, variante_id, stock_fuente, cantidad FROM stock_movimientos WHERE tipo IN ('COMPRA', 'ANULACION_COMPRA') ORDER BY id",
        )
        self.assertEqual(
            [
                (int(row["producto_id"]), row["variante_id"], row["stock_fuente"], float(row["cantidad"]))
                for row in movimientos
            ],
            [
                (producto_legacy, None, "stock", 4.0),
                (producto_legacy, None, "stock", -4.0),
                (producto_variantes, variante_id, "stock_variantes", 3.0),
            ],
        )

    def test_producto_legacy_sin_compras_pendientes_migra_correctamente(self):
        producto_id = self._crear_producto("Legacy limpio", stock=7, costo=10)
        variante_a = self._crear_variante(producto_id, "Negro", sku="LM-NEG")
        variante_b = self._crear_variante(producto_id, "Rojo", sku="LM-ROJ")
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": variante_a, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": variante_b, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        producto = self.database.get_producto(producto_id)
        self.assertEqual(producto["stock_modo"], "variantes")
        self.assertEqual(self._stock_producto(producto_id), 7.0)
        self.assertEqual(self._stock_variante(variante_a), 4.0)
        self.assertEqual(self._stock_variante(variante_b), 3.0)
        self.assertEqual(self._stock_operativo_total(producto_id), 7.0)

    def test_producto_con_compras_legacy_validas_puede_migrar_y_marca_no_reversible(self):
        producto_id = self._crear_producto("Legacy migrable", stock=2, costo=10)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5, costo_unitario=10))
        variante_a = self._crear_variante(producto_id, "Negro", sku="LB-NEG")
        variante_b = self._crear_variante(producto_id, "Rojo", sku="LB-ROJ")
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": variante_a, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": variante_b, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )

        compra = self.database.get_compra(compra_id)
        producto = self.database.get_producto(producto_id)
        self.assertEqual(int(compra["anulada"]), 0)
        self.assertEqual(int(compra["stock_reversion_bloqueada"]), 1)
        self.assertEqual(producto["stock_modo"], "variantes")
        self.assertEqual(self._stock_producto(producto_id), 7.0)
        self.assertEqual(self._stock_variante(variante_a), 4.0)
        self.assertEqual(self._stock_variante(variante_b), 3.0)
        movimientos = self.database.q(
            "SELECT tipo, variante_id, cantidad FROM stock_movimientos WHERE producto_id=? ORDER BY id",
            (producto_id,),
        )
        self.assertEqual(
            [(row["tipo"], row["variante_id"], float(row["cantidad"])) for row in movimientos],
            [("COMPRA", None, 5.0), ("TRANSICION_VARIANTES", variante_a, 4.0), ("TRANSICION_VARIANTES", variante_b, 3.0)],
        )

    def test_compra_legacy_anulada_previa_no_se_marca_al_migrar(self):
        producto_id = self._crear_producto("Legacy anulado migra", stock=2)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5))
        self.database.anular_compra(compra_id, motivo="Duplicada")
        variante_id = self._crear_variante(producto_id, "Negro", sku="LAM-NEG")

        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 2, "stock_minimo": 0, "stock_maximo": 50}])

        self.assertEqual(self.database.get_producto(producto_id)["stock_modo"], "variantes")
        self.assertEqual(self._stock_variante(variante_id), 2.0)
        self.assertEqual(int(self.database.get_compra(compra_id)["stock_reversion_bloqueada"]), 0)

    def test_varias_compras_legacy_marca_solo_las_activas(self):
        producto_id = self._crear_producto("Legacy varias", stock=1)
        compra_anulada = self.database.add_compra(self._compra_data(producto_id, cantidad=2))
        self.database.anular_compra(compra_anulada)
        compra_activa = self.database.add_compra(self._compra_data(producto_id, cantidad=3))
        variante_id = self._crear_variante(producto_id, "Negro", sku="LVB-NEG")

        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50}])

        self.assertEqual(int(self.database.get_compra(compra_activa)["anulada"]), 0)
        self.assertEqual(int(self.database.get_compra(compra_activa)["stock_reversion_bloqueada"]), 1)
        self.assertEqual(int(self.database.get_compra(compra_anulada)["stock_reversion_bloqueada"]), 0)
        self.assertEqual(self.database.get_producto(producto_id)["stock_modo"], "variantes")
        self.assertEqual(self._stock_variante(variante_id), 4.0)

    def test_compra_por_variante_no_aplica_al_bloqueo_de_migracion_de_otro_producto(self):
        producto_variantes = self._crear_producto("Ya variantes", stock=0)
        variante_origen = self._crear_variante(producto_variantes, "Negro", sku="CPV-NEG")
        self._activar_variantes(producto_variantes, [{"variant_id": variante_origen, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])
        self.database.add_compra(self._compra_data(producto_variantes, variante_id=variante_origen, cantidad=3))
        producto_legacy = self._crear_producto("Legacy independiente", stock=4)
        variante_destino = self._crear_variante(producto_legacy, "Rojo", sku="CPV-ROJ")

        self._activar_variantes(producto_legacy, [{"variant_id": variante_destino, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50}])

        self.assertEqual(self.database.get_producto(producto_legacy)["stock_modo"], "variantes")

    def test_compra_legacy_sigue_editable_y_anulable_antes_de_migrar(self):
        producto_id = self._crear_producto("Legacy antes de migrar", stock=1)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5))

        self.database.update_compra(compra_id, self._compra_data(producto_id, cantidad=3))
        self.assertEqual(self._stock_producto(producto_id), 4.0)
        self.database.anular_compra(compra_id, motivo="Reversion legacy")

        compra = self.database.get_compra(compra_id)
        self.assertEqual(int(compra["anulada"]), 1)
        self.assertEqual(self._stock_producto(producto_id), 1.0)
        movimientos = self.database.q(
            "SELECT variante_id, stock_fuente, cantidad FROM stock_movimientos WHERE producto_id=? AND tipo IN ('COMPRA', 'ANULACION_COMPRA') ORDER BY id",
            (producto_id,),
        )
        self.assertEqual(
            [(row["variante_id"], row["stock_fuente"], float(row["cantidad"])) for row in movimientos],
            [(None, "stock", 5.0), (None, "stock", -2.0), (None, "stock", -3.0)],
        )

    def test_compra_legacy_migrada_bloquea_anulacion_eliminacion_y_cambios_de_stock(self):
        producto_id = self._crear_producto("Legacy no reversible", stock=1)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5, costo_unitario=10))
        variante_id = self._crear_variante(producto_id, "Negro", sku="LNR-NEG")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 6, "stock_minimo": 0, "stock_maximo": 50}])
        otro_producto = self._crear_producto("Otro destino", stock=0)
        otro_proveedor = int(self.database.add_proveedor({"nombre": "Proveedor alternativo"}))
        compra_antes = self.database.get_compra(compra_id)
        stock_producto_antes = self._stock_producto(producto_id)
        stock_variante_antes = self._stock_variante(variante_id)
        movimientos_antes = int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"])
        auditoria_antes = int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"])

        with self.assertRaisesRegex(ValueError, "compra migrada"):
            self.database.anular_compra(compra_id)
        with self.assertRaisesRegex(ValueError, "compra migrada"):
            self.database.delete_compra(compra_id)
        casos_bloqueados = [
            self._compra_data(producto_id, cantidad=4, costo_unitario=10),
            self._compra_data(producto_id, variante_id=variante_id, cantidad=5, costo_unitario=10),
            self._compra_data(otro_producto, cantidad=5, costo_unitario=10),
            self._compra_data(producto_id, cantidad=5, costo_unitario=11),
            {**self._compra_data(producto_id, cantidad=5, costo_unitario=10), "total": 51},
            {**self._compra_data(producto_id, cantidad=5, costo_unitario=10), "fecha": "2026-07-29"},
            {
                **self._compra_data(producto_id, cantidad=5, costo_unitario=10),
                "proveedor_id": otro_proveedor,
                "proveedor_nombre": "Proveedor alternativo",
            },
        ]
        for data in casos_bloqueados:
            with self.assertRaisesRegex(ValueError, "compra migrada"):
                self.database.update_compra(compra_id, data)

        compra_despues = self.database.get_compra(compra_id)
        self.assertEqual(int(compra_despues["anulada"]), int(compra_antes["anulada"]))
        self.assertEqual(float(compra_despues["cantidad"]), float(compra_antes["cantidad"]))
        self.assertEqual(int(compra_despues["producto_id"]), int(compra_antes["producto_id"]))
        self.assertEqual(compra_despues["variante_id"], compra_antes["variante_id"])
        self.assertEqual(str(compra_despues["fecha"]), str(compra_antes["fecha"]))
        self.assertEqual(int(compra_despues["proveedor_id"]), int(compra_antes["proveedor_id"]))
        self.assertEqual(float(compra_despues["costo_unitario"]), float(compra_antes["costo_unitario"]))
        self.assertEqual(float(compra_despues["total"]), float(compra_antes["total"]))
        self.assertEqual(self._stock_producto(producto_id), stock_producto_antes)
        self.assertEqual(self._stock_variante(variante_id), stock_variante_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]), movimientos_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"]), auditoria_antes)
        movimientos = self.database.q(
            "SELECT * FROM stock_movimientos WHERE producto_id=? AND tipo='ANULACION_COMPRA'",
            (producto_id,),
        )
        self.assertEqual(movimientos, [])

    def test_compra_legacy_migrada_permite_edicion_documental_y_lectura_detalle(self):
        producto_id = self._crear_producto("Legacy documental", stock=1)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5))
        variante_id = self._crear_variante(producto_id, "Negro", sku="LDOC-NEG")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 6, "stock_minimo": 0, "stock_maximo": 50}])
        stock_producto_antes = self._stock_producto(producto_id)
        stock_variante_antes = self._stock_variante(variante_id)
        movimientos_antes = int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"])
        auditoria_antes = int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"])

        data = self._compra_data(producto_id, cantidad=5)
        data["numero_remito"] = "REM-DOC"
        data["observaciones"] = "Solo documental"
        self.database.update_compra(compra_id, data)
        self.database.actualizar_compra_basica(
            compra_id,
            self.proveedor_id,
            "2026-07-28",
            "Solo documental via basica",
            numero_remito="REM-BASICA",
            proveedor_nombre="Proveedor Compras",
        )

        compra = self.database.get_compra(compra_id)
        self.assertEqual(compra["numero_remito"], "REM-BASICA")
        self.assertEqual(compra["observaciones"], "Solo documental via basica")
        self.assertEqual(int(compra["stock_reversion_bloqueada"]), 1)
        self.assertEqual(float(compra["costo_unitario"]), 0.0)
        self.assertEqual(float(compra["total"]), 0.0)
        self.assertEqual(self._stock_producto(producto_id), stock_producto_antes)
        self.assertEqual(self._stock_variante(variante_id), stock_variante_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]), movimientos_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"]), auditoria_antes)
        compras = self.database.get_compras()
        self.assertTrue(any(int(row["id"]) == int(compra_id) for row in compras))

    def test_compra_legacy_migrada_bloquea_fecha_proveedor_y_preserva_factura_asociada(self):
        producto_id = self._crear_producto("Legacy factura", stock=1)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=5, costo_unitario=10))
        factura = self.database.crear_factura_desde_compra(
            compra_id,
            self.proveedor_id,
            50,
            numero_factura="FAC-LOCK",
            fecha="2026-07-28",
            fecha_vencimiento="2026-08-28",
            observaciones="Factura original",
        )
        variante_id = self._crear_variante(producto_id, "Negro", sku="LFAC-NEG")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 6, "stock_minimo": 0, "stock_maximo": 50}])
        otro_proveedor = int(self.database.add_proveedor({"nombre": "Proveedor factura alternativo"}))
        compra_antes = self.database.get_compra(compra_id)
        factura_antes = self.database.get_factura_proveedor(int(factura["id"]))
        stock_producto_antes = self._stock_producto(producto_id)
        stock_variante_antes = self._stock_variante(variante_id)
        movimientos_antes = int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"])
        auditoria_antes = int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"])

        with self.assertRaisesRegex(ValueError, "fecha o proveedor|compra migrada"):
            self.database.actualizar_compra_basica(
                compra_id,
                otro_proveedor,
                "2026-07-28",
                "Intento proveedor",
                numero_remito="REM-BLOCK",
                proveedor_nombre="Proveedor factura alternativo",
            )
        with self.assertRaisesRegex(ValueError, "fecha o proveedor|compra migrada"):
            self.database.actualizar_compra_basica(
                compra_id,
                self.proveedor_id,
                "2026-07-29",
                "Intento fecha",
                numero_remito="REM-BLOCK",
                proveedor_nombre="Proveedor Compras",
            )

        compra_despues = self.database.get_compra(compra_id)
        factura_despues = self.database.get_factura_proveedor(int(factura["id"]))
        self.assertEqual(int(compra_despues["proveedor_id"]), int(compra_antes["proveedor_id"]))
        self.assertEqual(str(compra_despues["proveedor_nombre"]), str(compra_antes["proveedor_nombre"]))
        self.assertEqual(str(compra_despues["fecha"]), str(compra_antes["fecha"]))
        self.assertEqual(compra_despues["numero_remito"], compra_antes["numero_remito"])
        self.assertEqual(int(factura_despues["proveedor_id"]), int(factura_antes["proveedor_id"]))
        self.assertEqual(factura_despues["numero_factura"], factura_antes["numero_factura"])
        self.assertEqual(str(factura_despues["fecha"]), str(factura_antes["fecha"]))
        self.assertEqual(self._stock_producto(producto_id), stock_producto_antes)
        self.assertEqual(self._stock_variante(variante_id), stock_variante_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]), movimientos_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"]), auditoria_antes)

    def test_anulacion_revierte_una_sola_vez(self):
        producto_id = self._crear_producto("Bufanda", stock=0)
        variante_id = self._crear_variante(producto_id, "Verde", sku="BUF-VER")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])
        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=variante_id, cantidad=3))

        self.database.anular_compra(compra_id, motivo="Duplicada", usuario="admin", rol="Administrador")
        with self.assertRaisesRegex(ValueError, "ya"):
            self.database.anular_compra(compra_id)

        self.assertEqual(self._stock_variante(variante_id), 0.0)
        movimientos = self.database.q(
            "SELECT cantidad FROM stock_movimientos WHERE variante_id=? AND tipo IN ('COMPRA', 'ANULACION_COMPRA') ORDER BY id",
            (variante_id,),
        )
        self.assertEqual([float(row["cantidad"]) for row in movimientos], [3.0, -3.0])

    def test_anulacion_revierte_variante_desactivada_sin_tocar_otras_fuentes(self):
        producto_id = self._crear_producto("Campera variante", stock=4)
        comprada = self._crear_variante(producto_id, "Negro", sku="CVAR-NEG")
        otra = self._crear_variante(producto_id, "Rojo", sku="CVAR-ROJ")
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": comprada, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": otra, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=comprada, cantidad=3))
        self.product_variants.set_variant_active(producto_id, comprada, False)

        self.database.anular_compra(compra_id, motivo="Historica", usuario="admin", rol="Administrador")

        compra = self.database.get_compra(compra_id)
        self.assertEqual(int(compra["anulada"]), 1)
        self.assertEqual(compra["stock_fuente"], "variante")
        self.assertEqual(self._stock_variante(comprada), 0.0)
        self.assertEqual(self._stock_variante(otra), 4.0)
        self.assertEqual(self._stock_producto(producto_id), 4.0)
        movimientos = self.database.q(
            "SELECT variante_id, cantidad FROM stock_movimientos WHERE tipo IN ('COMPRA', 'ANULACION_COMPRA') ORDER BY id",
        )
        self.assertEqual([(int(row["variante_id"]), float(row["cantidad"])) for row in movimientos], [(comprada, 3.0), (comprada, -3.0)])

    def test_edicion_reduce_cantidad_de_variante_desactivada(self):
        producto_id = self._crear_producto("Edicion historica", stock=0)
        variante_id = self._crear_variante(producto_id, "Negro", sku="EH-NEG")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])
        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=variante_id, cantidad=5))
        self.product_variants.set_variant_active(producto_id, variante_id, False)

        data = self._compra_data(producto_id, variante_id=variante_id, cantidad=2)
        self.database.update_compra(compra_id, data)

        compra = self.database.get_compra(compra_id)
        self.assertEqual(float(compra["cantidad"]), 2.0)
        self.assertEqual(self._stock_variante(variante_id), 2.0)
        movimientos = self.database.q(
            "SELECT cantidad FROM stock_movimientos WHERE variante_id=? AND tipo IN ('COMPRA', 'ANULACION_COMPRA') ORDER BY id",
            (variante_id,),
        )
        self.assertEqual([float(row["cantidad"]) for row in movimientos], [5.0, -3.0])

    def test_variante_inactiva_sigue_rechazada_para_alta_y_destino_de_edicion(self):
        producto_id = self._crear_producto("Destino inactivo", stock=0)
        origen = self._crear_variante(producto_id, "Negro", sku="DIN-NEG")
        destino = self._crear_variante(producto_id, "Azul", sku="DIN-AZU")
        self._activar_variantes(
            producto_id,
            [
                {"variant_id": origen, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
                {"variant_id": destino, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50},
            ],
        )
        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=origen, cantidad=2))
        self.product_variants.set_variant_active(producto_id, destino, False)

        with self.assertRaisesRegex(ValueError, "inactiva|pertenece"):
            self.database.add_compra(self._compra_data(producto_id, variante_id=destino, cantidad=1))
        with self.assertRaisesRegex(ValueError, "inactiva|pertenece"):
            self.database.update_compra(compra_id, self._compra_data(producto_id, variante_id=destino, cantidad=2))

        compra = self.database.get_compra(compra_id)
        self.assertEqual(int(compra["variante_id"]), origen)
        self.assertEqual(self._stock_variante(origen), 2.0)
        self.assertEqual(self._stock_variante(destino), 0.0)

    def test_rollback_completo_si_falla_reversion_historica(self):
        producto_id = self._crear_producto("Rollback historico", stock=0)
        variante_id = self._crear_variante(producto_id, "Negro", sku="RBH-NEG")
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])
        compra_id = self.database.add_compra(self._compra_data(producto_id, variante_id=variante_id, cantidad=3))
        self.product_variants.set_variant_active(producto_id, variante_id, False)
        self.database.q(
            "UPDATE stock_variantes SET stock_actual=1 WHERE variante_id=?",
            (variante_id,),
            fetchall=False,
            commit=True,
        )

        with self.assertRaisesRegex(ValueError, "stock negativo"):
            self.database.anular_compra(compra_id)

        compra = self.database.get_compra(compra_id)
        self.assertEqual(int(compra["anulada"]), 0)
        self.assertEqual(self._stock_variante(variante_id), 1.0)
        movimientos = self.database.q(
            "SELECT cantidad FROM stock_movimientos WHERE variante_id=? AND tipo='ANULACION_COMPRA'",
            (variante_id,),
        )
        self.assertEqual(movimientos, [])

    def test_compras_historicas_sin_variante_e_init_db_idempotente(self):
        self.database.init_db()
        columnas = [row["name"] for row in self.database.q("PRAGMA table_info(compras)")]
        self.assertIn("variante_id", columnas)
        self.assertIn("stock_fuente", columnas)
        producto_id = self._crear_producto("Historico", stock=0)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=1))
        variante_id = self._crear_variante(producto_id, "Negro", sku="BF-NEG")
        self.database.q("UPDATE compras SET variante_id=NULL, stock_fuente='' WHERE id=?", (compra_id,), fetchall=False, commit=True)
        self.database.q(
            """
            INSERT INTO compras (producto_id, variante_id, stock_fuente, descripcion, cantidad)
            VALUES (?, ?, '', 'Historico variante', 1)
            """,
            (producto_id, variante_id),
            fetchall=False,
            commit=True,
        )

        self.database._db_initialized = False
        self.database.init_db()
        self.database._db_initialized = False
        self.database.init_db()

        compra = self.database.get_compra(compra_id)
        self.assertIsNone(compra["variante_id"])
        self.assertEqual(compra["stock_fuente"], "producto")
        compra_variante = self.database.q("SELECT stock_fuente FROM compras WHERE descripcion='Historico variante'", fetchone=True)
        self.assertEqual(compra_variante["stock_fuente"], "variante")

    def test_init_db_idempotente_sin_tabla_de_asignacion_migrada(self):
        table_name = "stock_migracion_" + "variantes_ledger"
        self.database.q(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)",
            fetchall=False,
            commit=True,
        )
        self.database._db_initialized = False
        self.database.init_db()
        self.database._db_initialized = False
        self.database.init_db()

        tablas = [row["name"] for row in self.database.q("SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertNotIn(table_name, tablas)
        columnas = [row["name"] for row in self.database.q("PRAGMA table_info(compras)")]
        self.assertIn("stock_reversion_bloqueada", columnas)

    def test_init_db_backfill_bloquea_compras_legacy_activas_de_productos_ya_migrados(self):
        producto_migrado = self._crear_producto("Backfill migrado", stock=1)
        compra_legacy_activa = self.database.add_compra(self._compra_data(producto_migrado, cantidad=5, costo_unitario=10))
        factura = self.database.crear_factura_desde_compra(
            compra_legacy_activa,
            self.proveedor_id,
            50,
            numero_factura="FAC-BACKFILL",
            fecha="2026-07-28",
            fecha_vencimiento="2026-08-28",
            observaciones="Factura backfill",
        )
        compra_legacy_anulada = self.database.add_compra(self._compra_data(producto_migrado, cantidad=2, costo_unitario=10))
        self.database.anular_compra(compra_legacy_anulada, motivo="Anulada antes de migrar")
        variante_migrada = self._crear_variante(producto_migrado, "Negro", sku="BFILL-NEG")
        self._activar_variantes(producto_migrado, [{"variant_id": variante_migrada, "stock_actual": 6, "stock_minimo": 0, "stock_maximo": 50}])
        compra_por_variante = self.database.add_compra(
            self._compra_data(producto_migrado, variante_id=variante_migrada, cantidad=3, costo_unitario=10)
        )
        producto_legacy = self._crear_producto("Backfill legacy", stock=1)
        compra_producto_legacy = self.database.add_compra(self._compra_data(producto_legacy, cantidad=4, costo_unitario=10))
        self.database.q(
            """
            UPDATE compras
            SET stock_reversion_bloqueada=0
            WHERE id IN (?, ?, ?, ?)
            """,
            (compra_legacy_activa, compra_legacy_anulada, compra_por_variante, compra_producto_legacy),
            fetchall=False,
            commit=True,
        )
        compra_antes = self.database.get_compra(compra_legacy_activa)
        factura_antes = self.database.get_factura_proveedor(int(factura["id"]))
        stock_producto_migrado_antes = self._stock_producto(producto_migrado)
        stock_variante_antes = self._stock_variante(variante_migrada)
        stock_producto_legacy_antes = self._stock_producto(producto_legacy)
        movimientos_antes = int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"])
        auditoria_antes = int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"])

        self.database._db_initialized = False
        self.database.init_db()
        self.database._db_initialized = False
        self.database.init_db()

        self.assertEqual(int(self.database.get_compra(compra_legacy_activa)["stock_reversion_bloqueada"]), 1)
        self.assertEqual(int(self.database.get_compra(compra_legacy_anulada)["stock_reversion_bloqueada"]), 0)
        self.assertEqual(int(self.database.get_compra(compra_por_variante)["stock_reversion_bloqueada"]), 0)
        self.assertEqual(int(self.database.get_compra(compra_producto_legacy)["stock_reversion_bloqueada"]), 0)
        with self.assertRaisesRegex(ValueError, "compra migrada"):
            self.database.update_compra(compra_legacy_activa, self._compra_data(producto_migrado, cantidad=4, costo_unitario=10))
        with self.assertRaisesRegex(ValueError, "compra migrada"):
            self.database.anular_compra(compra_legacy_activa)
        with self.assertRaisesRegex(ValueError, "compra migrada"):
            self.database.delete_compra(compra_legacy_activa)

        compra_despues = self.database.get_compra(compra_legacy_activa)
        factura_despues = self.database.get_factura_proveedor(int(factura["id"]))
        self.assertEqual(float(compra_despues["cantidad"]), float(compra_antes["cantidad"]))
        self.assertEqual(float(compra_despues["costo_unitario"]), float(compra_antes["costo_unitario"]))
        self.assertEqual(float(compra_despues["total"]), float(compra_antes["total"]))
        self.assertEqual(int(compra_despues["anulada"]), 0)
        self.assertEqual(int(factura_despues["proveedor_id"]), int(factura_antes["proveedor_id"]))
        self.assertEqual(factura_despues["numero_factura"], factura_antes["numero_factura"])
        self.assertEqual(float(factura_despues["importe"]), float(factura_antes["importe"]))
        self.assertEqual(self._stock_producto(producto_migrado), stock_producto_migrado_antes)
        self.assertEqual(self._stock_variante(variante_migrada), stock_variante_antes)
        self.assertEqual(self._stock_producto(producto_legacy), stock_producto_legacy_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"]), movimientos_antes)
        self.assertEqual(int(self.database.q("SELECT COUNT(*) AS total FROM auditoria", fetchone=True)["total"]), auditoria_antes)

    def test_migracion_legacy_conserva_compra_sin_inferir_variante(self):
        legacy_db = Path(self.temp_dir.name) / "legacy.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute("CREATE TABLE productos (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo_interno TEXT, codigo_barras TEXT DEFAULT '', descripcion TEXT, activo INTEGER DEFAULT 1, costo REAL DEFAULT 0)")
        conn.execute("CREATE TABLE compras (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER DEFAULT 0, descripcion TEXT DEFAULT '', cantidad REAL DEFAULT 1)")
        conn.execute("INSERT INTO productos (codigo_interno, descripcion, activo, costo) VALUES ('LEG', 'Legacy', 1, 1)")
        conn.execute("INSERT INTO compras (producto_id, descripcion, cantidad) VALUES (1, 'Legacy', 2)")
        conn.commit()
        conn.close()

        self.database.DB_PATH = str(legacy_db)
        self.database._db_initialized = False
        self.database.init_db()
        compra = self.database.q("SELECT variante_id, stock_fuente FROM compras WHERE id=1", fetchone=True)
        self.assertIsNone(compra["variante_id"])
        self.assertEqual(compra["stock_fuente"], "producto")

    def test_fallo_en_distribucion_de_variante_revierte_stock_modo(self):
        producto_id = self._crear_producto("Rollback distribucion", stock=5)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=2))
        variante_a = self._crear_variante(producto_id, "Negro", sku="RD-NEG")
        variante_b = self._crear_variante(producto_id, "Rojo", sku="RD-ROJ")

        with mock.patch.object(self.inventory, "_movement_insert", side_effect=RuntimeError("fallo distribucion")):
            with self.assertRaisesRegex(RuntimeError, "fallo distribucion"):
                self._activar_variantes(
                    producto_id,
                    [
                        {"variant_id": variante_a, "stock_actual": 3, "stock_minimo": 0, "stock_maximo": 50},
                        {"variant_id": variante_b, "stock_actual": 4, "stock_minimo": 0, "stock_maximo": 50},
                    ],
                )

        producto = self.database.get_producto(producto_id)
        self.assertEqual(producto["stock_modo"], "legacy")
        self.assertEqual(int(self.database.get_compra(compra_id)["stock_reversion_bloqueada"]), 0)
        self.assertEqual(self._stock_variante(variante_a), 0.0)
        self.assertEqual(self._stock_variante(variante_b), 0.0)
        self.assertEqual(self._stock_producto(producto_id), 7.0)

    def test_ruta_compra_con_variante_respeta_login_csrf_y_validacion(self):
        producto_id = self._crear_producto("Ruta", stock=0)
        variante_id = self._crear_variante(producto_id, "Negro", sku="RUTA-NEG", costo=22)
        self._activar_variantes(producto_id, [{"variant_id": variante_id, "stock_actual": 0, "stock_minimo": 0, "stock_maximo": 50}])

        with self.app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test-token"
            response_sin_login = client.post("/compras/nueva", data={"csrf_token": "test-token"})
            self.assertEqual(response_sin_login.status_code, 302)
            self._login_admin(client)
            response_listado = client.get("/compras")
            self.assertEqual(response_listado.status_code, 200)
            self.assertIn(b"RUTA-NEG", response_listado.data)
            response_sin_csrf = client.post("/compras/nueva", data={})
            self.assertEqual(response_sin_csrf.status_code, 400)
            response = client.post(
                "/compras/nueva",
                data={
                    "csrf_token": "test-token",
                    "fecha": "2026-07-28",
                    "proveedor_id": self.proveedor_id,
                    "producto_item": f"{producto_id}:{variante_id}",
                    "cantidad": "2",
                    "costo_unitario": "22",
                    "condicion_pago": "contado",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._stock_variante(variante_id), 2.0)
