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

    def _crear_variante(self, producto_id, **overrides):
        payload = {
            "attributes": [{"attribute_name": "Color", "value_name": "Negro"}],
            "sku": f"VAR-{producto_id}",
            "codigo_barras": "",
            "costo": 100,
            "precio": 150,
            "precio_promocional": None,
            "stock_actual": 2,
            "stock_minimo": 1,
            "stock_maximo": 5,
        }
        payload.update(overrides)
        return self.product_variants.create_variant(producto_id, **payload)

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

    def test_post_variantes_respeta_checkbox_activo_marcado_y_desmarcado(self):
        producto_activo = self._crear_producto(descripcion="Producto activo")
        producto_inactivo = self._crear_producto(descripcion="Producto inactivo")
        with self.app.test_client() as client:
            self._login_admin(client)
            base_data = {
                "csrf_token": "test-token",
                "attribute_name[]": ["Color"],
                "value_name[]": ["Negro"],
                "stock_actual": "2",
                "stock_minimo": "1",
                "stock_maximo": "5",
                "costo": "100",
                "precio": "150",
            }

            respuesta_activa = client.post(
                f"/productos/{producto_activo}/variantes",
                data={**base_data, "sku": "VAR-ACTIVA", "activo": "1"},
                follow_redirects=False,
            )
            respuesta_inactiva = client.post(
                f"/productos/{producto_inactivo}/variantes",
                data={**base_data, "sku": "VAR-INACTIVA"},
                follow_redirects=False,
            )

        self.assertEqual(respuesta_activa.status_code, 302)
        self.assertEqual(respuesta_inactiva.status_code, 302)
        self.assertEqual(self.product_variants.list_product_variants(producto_activo)[0]["activo"], 1)
        self.assertEqual(self.product_variants.list_product_variants(producto_inactivo)[0]["activo"], 0)

    def test_create_variant_acepta_stock_valido(self):
        producto_id = self._crear_producto(descripcion="Stock valido")

        self.product_variants.create_variant(
            producto_id,
            sku="STOCK-OK",
            stock_actual="3.5",
            stock_minimo="1",
            stock_maximo="8",
        )

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(float(variante["stock_actual"]), 3.5)
        self.assertEqual(float(variante["stock_minimo"]), 1.0)
        self.assertEqual(float(variante["stock_maximo"]), 8.0)

    def test_create_variant_rechaza_stock_invalido_sin_persistencia(self):
        producto_id = self._crear_producto(descripcion="Stock invalido")
        invalid_cases = (
            ("stock_actual", -1, "stock actual no puede ser negativo"),
            ("stock_minimo", -1, "stock minimo no puede ser negativo"),
            ("stock_maximo", -1, "stock maximo no puede ser negativo"),
            ("stock_actual", "NaN", "stock actual debe ser un numero finito"),
            ("stock_minimo", "inf", "stock minimo debe ser un numero finito"),
            ("stock_maximo", "-inf", "stock maximo debe ser un numero finito"),
            ("stock_actual", "no-numerico", "stock actual debe ser numerico"),
        )

        for field, value, message in invalid_cases:
            with self.subTest(field=field, value=value):
                stock = {"stock_actual": 0, "stock_minimo": 0, "stock_maximo": 0}
                stock[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.product_variants.create_variant(
                        producto_id,
                        attributes=[{"attribute_name": "Color", "value_name": "Negro"}],
                        sku="STOCK-INVALIDO",
                        **stock,
                    )
                self._assert_variant_tables_empty()

    def test_post_variantes_muestra_error_claro_para_stock_no_numerico(self):
        producto_id = self._crear_producto(descripcion="Stock ruta invalido")
        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                f"/productos/{producto_id}/variantes",
                data={
                    "csrf_token": "test-token",
                    "attribute_name[]": ["Color"],
                    "value_name[]": ["Negro"],
                    "sku": "STOCK-RUTA-INVALIDO",
                    "stock_actual": "no-numerico",
                    "stock_minimo": "1",
                    "stock_maximo": "5",
                    "costo": "100",
                    "precio": "150",
                },
                follow_redirects=False,
            )
            with client.session_transaction() as session:
                flashes = session.get("_flashes", [])

        self.assertEqual(response.status_code, 302)
        self.assertIn(("warning", "El stock actual debe ser numerico."), flashes)
        self._assert_variant_tables_empty()

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

    def test_update_variant_modifica_datos_y_asociaciones(self):
        producto_id = self._crear_producto(descripcion="Producto editable")
        variante_id = self._crear_variante(producto_id)

        self.product_variants.update_variant(
            producto_id,
            variante_id,
            attributes=[
                {"attribute_name": "Material", "value_name": "Acero"},
                {"attribute_name": "Terminacion", "value_name": "Mate"},
            ],
            sku="VAR-EDITADA",
            codigo_barras="779000002001",
            costo="120.50",
            precio="210.75",
            precio_promocional="199.90",
            stock_actual="7",
            stock_minimo="2",
            stock_maximo="12",
        )

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["resumen_atributos"], "Material: Acero, Terminacion: Mate")
        self.assertEqual(variante["sku"], "VAR-EDITADA")
        self.assertEqual(variante["codigo_barras"], "779000002001")
        self.assertEqual(variante["costo_propio"], 120.5)
        self.assertEqual(variante["precio_propio"], 210.75)
        self.assertEqual(variante["precio_promocional"], 199.9)
        self.assertEqual(variante["stock_actual"], 7.0)
        self.assertEqual(variante["stock_minimo"], 2.0)
        self.assertEqual(variante["stock_maximo"], 12.0)

    def test_set_variant_active_activa_y_desactiva(self):
        producto_id = self._crear_producto(descripcion="Producto estado")
        variante_id = self._crear_variante(producto_id)

        self.product_variants.set_variant_active(producto_id, variante_id, False)
        self.assertEqual(self.product_variants.list_product_variants(producto_id)[0]["activo"], 0)

        self.product_variants.set_variant_active(producto_id, variante_id, True)
        self.assertEqual(self.product_variants.list_product_variants(producto_id)[0]["activo"], 1)

    def test_update_variant_rechaza_combinacion_duplicada(self):
        producto_id = self._crear_producto(descripcion="Producto combinaciones")
        primera_id = self._crear_variante(producto_id)
        segunda_id = self._crear_variante(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="VAR-AZUL",
        )

        with self.assertRaisesRegex(ValueError, "combinacion de atributos ya existe"):
            self.product_variants.update_variant(
                producto_id,
                segunda_id,
                attributes=[{"attribute_name": "Color", "value_name": "Negro"}],
                sku="VAR-AZUL",
                stock_actual=2,
                stock_minimo=1,
                stock_maximo=5,
            )

        variantes = {item["id"]: item for item in self.product_variants.list_product_variants(producto_id)}
        self.assertEqual(variantes[primera_id]["resumen_atributos"], "Color: Negro")
        self.assertEqual(variantes[segunda_id]["resumen_atributos"], "Color: Azul")

    def test_update_variant_rechaza_sku_duplicado(self):
        producto_id = self._crear_producto(descripcion="Producto SKU")
        self._crear_variante(producto_id, sku="SKU-UNO")
        segunda_id = self._crear_variante(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="SKU-DOS",
        )

        with self.assertRaisesRegex(ValueError, "SKU de la variante ya existe"):
            self.product_variants.update_variant(
                producto_id,
                segunda_id,
                attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
                sku="SKU-UNO",
                stock_actual=2,
                stock_minimo=1,
                stock_maximo=5,
            )

    def test_update_variant_rechaza_codigo_barras_duplicado(self):
        producto_id = self._crear_producto(descripcion="Producto barras")
        self._crear_variante(producto_id, sku="BAR-UNO", codigo_barras="779000002002")
        segunda_id = self._crear_variante(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="BAR-DOS",
            codigo_barras="779000002003",
        )

        with self.assertRaisesRegex(ValueError, "otra variante con ese codigo de barras"):
            self.product_variants.update_variant(
                producto_id,
                segunda_id,
                attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
                sku="BAR-DOS",
                codigo_barras="779000002002",
                stock_actual=2,
                stock_minimo=1,
                stock_maximo=5,
            )

    def test_update_variant_rechaza_atributos_dinero_y_stock_invalidos(self):
        producto_id = self._crear_producto(descripcion="Producto validaciones")
        variante_id = self._crear_variante(producto_id)
        invalid_cases = (
            (
                {"attributes": [{"attribute_name": "Color", "value_name": ""}]},
                "Cada variante debe completar atributo y valor",
            ),
            (
                {
                    "attributes": [
                        {"attribute_name": "Color", "value_name": "Negro"},
                        {"attribute_name": " color ", "value_name": "Azul"},
                    ]
                },
                "No se puede repetir el mismo atributo",
            ),
            ({"costo": "-1"}, "costo no puede ser negativo"),
            ({"precio": "NaN"}, "precio debe ser un numero finito"),
            ({"precio_promocional": "invalido"}, "precio promocional debe ser numerico"),
            ({"stock_actual": "-1"}, "stock actual no puede ser negativo"),
        )
        base = {
            "attributes": [{"attribute_name": "Color", "value_name": "Negro"}],
            "sku": "VAR-VALIDA",
            "stock_actual": 2,
            "stock_minimo": 1,
            "stock_maximo": 5,
        }

        for overrides, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.product_variants.update_variant(
                        producto_id,
                        variante_id,
                        **{**base, **overrides},
                    )

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["sku"], f"VAR-{producto_id}")
        self.assertEqual(variante["resumen_atributos"], "Color: Negro")

    def test_operaciones_rechazan_variante_de_otro_producto(self):
        producto_a = self._crear_producto(descripcion="Producto A")
        producto_b = self._crear_producto(descripcion="Producto B")
        variante_id = self._crear_variante(producto_a)

        with self.assertRaisesRegex(ValueError, "no pertenece al producto"):
            self.product_variants.update_variant(
                producto_b,
                variante_id,
                sku="AJENA",
                stock_actual=0,
                stock_minimo=0,
                stock_maximo=0,
            )
        with self.assertRaisesRegex(ValueError, "no pertenece al producto"):
            self.product_variants.set_variant_active(producto_b, variante_id, False)
        with self.assertRaisesRegex(ValueError, "no pertenece al producto"):
            self.product_variants.delete_variant(producto_b, variante_id)

        self.assertIsNotNone(
            self.database.q("SELECT id FROM producto_variantes WHERE id=?", (variante_id,), fetchone=True)
        )

    def test_delete_variant_sin_referencias_elimina_dependencias_propias(self):
        producto_id = self._crear_producto(descripcion="Producto eliminable")
        variante_id = self._crear_variante(producto_id)

        result = self.product_variants.delete_variant(producto_id, variante_id)

        self.assertTrue(result["deleted"])
        self.assertIsNone(
            self.database.q("SELECT id FROM producto_variantes WHERE id=?", (variante_id,), fetchone=True)
        )
        self.assertIsNone(
            self.database.q(
                "SELECT id FROM producto_variante_valores WHERE variante_id=?",
                (variante_id,),
                fetchone=True,
            )
        )
        self.assertIsNone(
            self.database.q("SELECT id FROM stock_variantes WHERE variante_id=?", (variante_id,), fetchone=True)
        )

    def test_delete_variant_referenciada_la_desactiva_sin_borrarla(self):
        producto_id = self._crear_producto(descripcion="Producto con historial")
        variante_id = self._crear_variante(producto_id)
        conn = self._direct_conn()
        self.addCleanup(conn.close)
        conn.execute(
            """
            CREATE TABLE historial_variante_test (
                id INTEGER PRIMARY KEY,
                variante_id INTEGER NOT NULL REFERENCES producto_variantes(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute("INSERT INTO historial_variante_test (variante_id) VALUES (?)", (variante_id,))
        conn.commit()

        result = self.product_variants.delete_variant(producto_id, variante_id)

        self.assertFalse(result["deleted"])
        self.assertEqual(result["references"], ["historial_variante_test"])
        variante = self.database.q(
            "SELECT activo FROM producto_variantes WHERE id=?",
            (variante_id,),
            fetchone=True,
        )
        historial = self.database.q(
            "SELECT variante_id FROM historial_variante_test WHERE variante_id=?",
            (variante_id,),
            fetchone=True,
        )
        self.assertEqual(int(variante["activo"]), 0)
        self.assertEqual(int(historial["variante_id"]), variante_id)

    def test_update_variant_hace_rollback_ante_fallo_intermedio(self):
        producto_id = self._crear_producto(descripcion="Producto rollback")
        variante_id = self._crear_variante(producto_id, sku="ROLLBACK-ORIGINAL")

        with mock.patch.object(
            self.product_variants,
            "_insert_variant_attribute_values",
            side_effect=RuntimeError("fallo-edicion-intermedia"),
        ):
            with self.assertRaisesRegex(RuntimeError, "fallo-edicion-intermedia"):
                self.product_variants.update_variant(
                    producto_id,
                    variante_id,
                    attributes=[{"attribute_name": "Material", "value_name": "Madera"}],
                    sku="ROLLBACK-NUEVO",
                    precio=999,
                    stock_actual=99,
                    stock_minimo=1,
                    stock_maximo=100,
                )

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["sku"], "ROLLBACK-ORIGINAL")
        self.assertEqual(variante["resumen_atributos"], "Color: Negro")
        self.assertEqual(variante["precio"], 150.0)
        self.assertEqual(variante["stock_actual"], 2.0)
        self.assertFalse(
            any(item["nombre"] == "Material" for item in self.product_variants.list_attributes_catalog())
        )

    def test_rutas_gestion_exigen_csrf(self):
        producto_id = self._crear_producto(descripcion="Producto CSRF gestion")
        variante_id = self._crear_variante(producto_id)
        paths = (
            (f"/productos/{producto_id}/variantes/{variante_id}/editar", {}),
            (f"/productos/{producto_id}/variantes/{variante_id}/estado", {"activo": "0"}),
            (f"/productos/{producto_id}/variantes/{variante_id}/eliminar", {}),
        )
        with self.app.test_client() as client:
            self._login_admin(client)
            for path, data in paths:
                with self.subTest(path=path):
                    response = client.post(path, data=data, follow_redirects=False)
                    self.assertEqual(response.status_code, 400)

        self.assertIsNotNone(
            self.database.q("SELECT id FROM producto_variantes WHERE id=?", (variante_id,), fetchone=True)
        )

    def test_gestion_renderiza_controles_accesibles(self):
        producto_id = self._crear_producto(descripcion="Producto UI")
        variante_id = self._crear_variante(producto_id, sku="UI-VAR")
        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/productos/{producto_id}/variantes")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(f'id="editarVariante{variante_id}"', html)
        self.assertIn("Guardar cambios", html)
        self.assertIn("Desactivar", html)
        self.assertIn(f'aria-label="Eliminar variante Color: Negro"', html)

    def test_ruta_edicion_invalida_conserva_datos_ingresados_sin_persistir(self):
        producto_id = self._crear_producto(descripcion="Producto formulario")
        variante_id = self._crear_variante(producto_id, sku="FORM-ORIGINAL")
        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                f"/productos/{producto_id}/variantes/{variante_id}/editar",
                data={
                    "csrf_token": "test-token",
                    "attribute_name[]": ["Material"],
                    "value_name[]": ["Intento"],
                    "sku": "FORM-INTENTO",
                    "precio": "no-numerico",
                    "stock_actual": "2",
                    "stock_minimo": "1",
                    "stock_maximo": "5",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 400)
        html = response.get_data(as_text=True)
        self.assertIn('value="FORM-INTENTO"', html)
        self.assertIn('value="Material"', html)
        self.assertIn(f'id="editarVariante{variante_id}"', html)
        self.assertIn("collapse show", html)
        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["sku"], "FORM-ORIGINAL")
        self.assertEqual(variante["resumen_atributos"], "Color: Negro")

    def test_rutas_gestion_bloquean_vendedor(self):
        producto_id = self._crear_producto(descripcion="Producto permisos")
        variante_id = self._crear_variante(producto_id)
        self.database.add_usuario(
            "vendedor",
            "1234",
            "vendedor",
            "Vendedor Test",
            security_question="color",
            security_answer="azul",
        )
        vendedor = self.database.q(
            "SELECT id, username, rol FROM usuarios WHERE username='vendedor'",
            fetchone=True,
        )
        paths = (
            (f"/productos/{producto_id}/variantes/{variante_id}/editar", {}),
            (f"/productos/{producto_id}/variantes/{variante_id}/estado", {"activo": "0"}),
            (f"/productos/{producto_id}/variantes/{variante_id}/eliminar", {}),
        )
        with self.app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test-token"
                session["user"] = {
                    "id": int(vendedor["id"]),
                    "username": vendedor["username"],
                    "rol": vendedor["rol"],
                }
            for path, data in paths:
                with self.subTest(path=path):
                    response = client.post(
                        path,
                        data={**data, "csrf_token": "test-token"},
                        follow_redirects=False,
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers["Location"], "/")

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["activo"], 1)
        self.assertEqual(variante["sku"], f"VAR-{producto_id}")

    def test_rutas_registran_edicion_estado_y_eliminacion(self):
        producto_id = self._crear_producto(descripcion="Producto auditable")
        variante_edicion = self._crear_variante(producto_id, sku="AUD-EDIT")
        variante_eliminacion = self._crear_variante(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Azul"}],
            sku="AUD-DELETE",
        )
        edit_data = {
            "csrf_token": "test-token",
            "attribute_name[]": ["Color"],
            "value_name[]": ["Verde"],
            "sku": "AUD-EDITADA",
            "stock_actual": "2",
            "stock_minimo": "1",
            "stock_maximo": "5",
            "costo": "100",
            "precio": "150",
        }

        with self.app.test_client() as client:
            self._login_admin(client)
            edit_response = client.post(
                f"/productos/{producto_id}/variantes/{variante_edicion}/editar",
                data=edit_data,
                follow_redirects=False,
            )
            state_response = client.post(
                f"/productos/{producto_id}/variantes/{variante_edicion}/estado",
                data={"csrf_token": "test-token", "activo": "0"},
                follow_redirects=False,
            )
            delete_response = client.post(
                f"/productos/{producto_id}/variantes/{variante_eliminacion}/eliminar",
                data={"csrf_token": "test-token"},
                follow_redirects=False,
            )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(state_response.status_code, 302)
        self.assertEqual(delete_response.status_code, 302)
        self.assertIsNone(
            self.database.q(
                "SELECT id FROM producto_variantes WHERE id=?",
                (variante_eliminacion,),
                fetchone=True,
            )
        )
        acciones = {
            row["accion"]
            for row in self.database.q(
                """
                SELECT accion
                FROM auditoria
                WHERE entidad='producto_variante'
                """
            )
        }
        self.assertIn("EDICION_VARIANTE_PRODUCTO", acciones)
        self.assertIn("DESACTIVACION_VARIANTE_PRODUCTO", acciones)
        self.assertIn("ELIMINACION_VARIANTE_PRODUCTO", acciones)

    def test_ruta_eliminacion_referenciada_audita_desactivacion_segura(self):
        producto_id = self._crear_producto(descripcion="Producto fallback auditable")
        variante_id = self._crear_variante(producto_id, sku="AUD-FALLBACK")
        conn = self._direct_conn()
        self.addCleanup(conn.close)
        conn.execute(
            """
            CREATE TABLE historial_variante_auditoria_test (
                id INTEGER PRIMARY KEY,
                variante_id INTEGER NOT NULL REFERENCES producto_variantes(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            "INSERT INTO historial_variante_auditoria_test (variante_id) VALUES (?)",
            (variante_id,),
        )
        conn.commit()

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                f"/productos/{producto_id}/variantes/{variante_id}/eliminar",
                data={"csrf_token": "test-token"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        variante = self.database.q(
            "SELECT activo FROM producto_variantes WHERE id=?",
            (variante_id,),
            fetchone=True,
        )
        self.assertIsNotNone(variante)
        self.assertEqual(int(variante["activo"]), 0)
        auditorias = self.database.q(
            """
            SELECT accion, detalle, motivo
            FROM auditoria
            WHERE entidad='producto_variante' AND entidad_id=?
            ORDER BY id
            """,
            (variante_id,),
        )
        self.assertEqual(len(auditorias), 1)
        self.assertEqual(auditorias[0]["accion"], "DESACTIVACION_VARIANTE_PRODUCTO")
        self.assertIn("Desactivacion segura por eliminacion bloqueada", auditorias[0]["detalle"])
        self.assertIn("historial_variante_auditoria_test", auditorias[0]["motivo"])
        self.assertNotEqual(auditorias[0]["accion"], "INTENTO_ELIMINACION_VARIANTE_PRODUCTO")

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
