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
        producto_id = self._crear_producto("Historico", stock=0)
        compra_id = self.database.add_compra(self._compra_data(producto_id, cantidad=1))
        self.database.q("UPDATE compras SET variante_id=NULL WHERE id=?", (compra_id,), fetchall=False, commit=True)

        compra = self.database.get_compra(compra_id)
        self.assertIsNone(compra["variante_id"])

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
        compra = self.database.q("SELECT variante_id FROM compras WHERE id=1", fetchone=True)
        self.assertIsNone(compra["variante_id"])

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
