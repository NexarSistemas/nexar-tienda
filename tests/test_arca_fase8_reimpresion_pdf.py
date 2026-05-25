import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_env():
    for key in (
        "ARCA_MODO_SIMULACION",
        "FLASK_ENV",
        "NEXAR_LICENSE_MODE",
        "NEXAR_PLAN",
        "NEXAR_MODULES",
        "NEXAR_EXTRA_MODULES",
        "SECRET_KEY",
    ):
        os.environ.pop(key, None)


class ArcaFase8ReimpresionPdfTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        os.environ["NEXAR_EXTRA_MODULES"] = "arca_facturacion"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"

        import app as app_module
        import database
        import modules.arca.routes as arca_routes
        import modules.arca.services.arca_client as arca_client
        from modules.arca.services import comprobantes_service, reimpresion_pdf_service
        from routes import main as routes_main

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.comprobantes_service = importlib.reload(comprobantes_service)
        self.comprobantes_service.db = self.database

        self.reimpresion_service = importlib.reload(reimpresion_pdf_service)
        self.reimpresion_service.db = self.database

        self.arca_client = importlib.reload(arca_client)
        self.routes_main = importlib.reload(routes_main)
        self.routes_main.db = self.database
        self.arca_routes = importlib.reload(arca_routes)

        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.database
        self.app = self.app_module.create_app()

        self.admin_id = self.database.add_usuario(
            "admin",
            "1234",
            "Administrador",
            "Administrador Test",
            security_question="color",
            security_answer="azul",
        )
        self.producto_id = self.database.add_producto(
            {
                "descripcion": "Producto Fase 8",
                "marca": "",
                "categoria": "General",
                "tipo_unidad": "unidad",
                "stock_actual": 20,
                "stock_minimo": 1,
                "stock_maximo": 50,
                "costo": 1000,
                "precio_venta": 1500,
                "iva": "21%",
            }
        )
        self.database.set_rubro_configurado("tienda")
        self.database.q(
            """
            INSERT INTO arca_configuracion
            (id, cuit, razon_social, nombre_fantasia, condicion_fiscal, punto_venta, ambiente, activo)
            VALUES (1, ?, ?, ?, ?, ?, ?, 1)
            """,
            ("20304050607", "Comercio Central SA", "", "responsable_inscripto", 2, "homologacion"),
            commit=True,
        )
        self.database.set_config(
            {
                "nombre_negocio": "Comercio Centro",
            }
        )
        self.cliente_id = self.database.add_cliente(
            {
                "nombre": "Cliente Fiscal SA",
                "dni_cuit": "20-12345678-6",
                "telefono": "",
                "email": "",
                "limite_credito": 0,
            }
        )
        self.cliente_dni_id = self.database.add_cliente(
            {
                "nombre": "Cliente DNI",
                "dni_cuit": "30111222",
                "telefono": "",
                "email": "",
                "limite_credito": 0,
            }
        )

    def tearDown(self):
        _reset_env()

    def _login_admin(self, client):
        with client.session_transaction() as session:
            session["_csrf_token"] = "test-token"
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "1234",
                "csrf_token": "test-token",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def _crear_venta(
        self,
        cliente_nombre: str = "Cliente Fiscal",
        cliente_id: int = 0,
        vendedor: str = "admin",
        descuento_adicional: float = 0,
    ) -> int:
        return int(
            self.database.crear_venta(
                [
                    {
                        "producto_id": self.producto_id,
                        "codigo_interno": "ARCA-F8",
                        "descripcion": "Producto fiscal reimpresion",
                        "categoria": "General",
                        "unidad": "unidad",
                        "cantidad": 2,
                        "precio_unitario": 1500,
                        "costo_unitario": 1000,
                        "iva": "21%",
                        "descuento": 0,
                        "subtotal": 3000,
                    }
                ],
                cliente_nombre,
                "Efectivo",
                descuento_adicional,
                vendedor,
                cliente_id=cliente_id,
            )
        )

    def _registrar_comprobante(
        self,
        venta_id: int,
        tipo_comprobante: str = "Factura B",
        numero_comprobante: int = 123,
        importe_total: float = 3000.0,
    ):
        return self.comprobantes_service.registrar_comprobante_fiscal(
            venta_id=venta_id,
            tipo_comprobante=tipo_comprobante,
            punto_venta=2,
            numero_comprobante=numero_comprobante,
            cae="61111111111111",
            cae_vencimiento="2026-06-10",
            importe_total=importe_total,
            estado="AUTORIZADO",
            fecha_emision="2026-05-24",
            payload={"items": 1},
            respuesta={"ok": True},
            respuesta_raw='{"ok": true}',
            pdf_path=str(Path(self.temp_dir.name) / "arca" / f"venta-{venta_id}.pdf"),
            modo="wsfe",
            ambiente="homologacion",
        )

    def test_venta_sin_comprobante_arca_no_genera_pdf_fiscal(self):
        venta_id = self._crear_venta()

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "comprobante_no_encontrado")

    def test_venta_con_cae_genera_respuesta_pdf(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id)

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/arca/comprobante/{venta_id}/pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF"))
        response.close()

        comprobante = self.comprobantes_service.obtener_comprobante_por_venta(venta_id)
        self.assertTrue(comprobante["pdf_path"])
        self.assertTrue(Path(str(comprobante["pdf_path"])).exists())

    def test_monotributo_genera_contexto_factura_c_en_pdf(self):
        venta_id = self._crear_venta()
        self.database.q(
            "UPDATE arca_configuracion SET condicion_fiscal = ? WHERE id = 1",
            ("monotributo",),
            commit=True,
        )
        self._registrar_comprobante(venta_id, tipo_comprobante="Factura C", numero_comprobante=4)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Factura C", contenido_pdf)

    def test_pdf_muestra_nombre_fantasia_y_razon_social_en_encabezado(self):
        venta_id = self._crear_venta()
        self.database.q(
            "UPDATE arca_configuracion SET nombre_fantasia = ?, razon_social = ? WHERE id = 1",
            ("Sucursal Centro", "Comercio Central SA"),
            commit=True,
        )
        self._registrar_comprobante(venta_id)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Sucursal Centro", contenido_pdf)
        self.assertIn("Comercio Central SA", contenido_pdf)

    def test_pdf_no_muestra_nexar_demo_si_no_esta_configurado(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Comercio Centro", contenido_pdf)
        self.assertIn("Comercio Central SA", contenido_pdf)
        self.assertNotIn("Nexar Demo", contenido_pdf)

    def test_numero_completo_de_comprobante_se_renderiza_en_pdf(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id, numero_comprobante=4)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("0002-00000004", contenido_pdf)

    def test_factura_vieja_respeta_tipo_persistido(self):
        venta_id = self._crear_venta()
        self.database.q(
            "UPDATE arca_configuracion SET condicion_fiscal = ? WHERE id = 1",
            ("monotributo",),
            commit=True,
        )
        self._registrar_comprobante(venta_id, tipo_comprobante="Factura B", numero_comprobante=7)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Factura B", contenido_pdf)
        self.assertNotIn("Factura C", contenido_pdf)

    def test_cliente_con_cuit_muestra_nombre_y_cuit(self):
        venta_id = self._crear_venta(cliente_nombre="Cliente Fiscal SA", cliente_id=self.cliente_id)
        self._registrar_comprobante(venta_id)

        contexto = self.reimpresion_service.get_comprobante_pdf_context(venta_id)

        self.assertTrue(contexto["ok"])
        self.assertEqual(contexto["cliente_fiscal"]["nombre"], "Cliente Fiscal SA")
        self.assertEqual(contexto["cliente_fiscal"]["documento"], "20123456786")
        self.assertEqual(contexto["cliente_fiscal"]["documento_label"], "CUIT")

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Cliente Fiscal SA", contenido_pdf)
        self.assertIn("20-12345678-6", contenido_pdf)

    def test_cliente_con_dni_muestra_nombre_y_dni(self):
        venta_id = self._crear_venta(cliente_nombre="Cliente DNI", cliente_id=self.cliente_dni_id)
        self._registrar_comprobante(venta_id)

        contexto = self.reimpresion_service.get_comprobante_pdf_context(venta_id)

        self.assertTrue(contexto["ok"])
        self.assertEqual(contexto["cliente_fiscal"]["nombre"], "Cliente DNI")
        self.assertEqual(contexto["cliente_fiscal"]["documento"], "30111222")
        self.assertEqual(contexto["cliente_fiscal"]["documento_label"], "DNI")

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Cliente DNI", contenido_pdf)
        self.assertIn("30111222", contenido_pdf)

    def test_venta_mostrador_muestra_consumidor_final(self):
        venta_id = self._crear_venta(cliente_nombre="Mostrador", cliente_id=0)
        self._registrar_comprobante(venta_id)

        contexto = self.reimpresion_service.get_comprobante_pdf_context(venta_id)

        self.assertTrue(contexto["ok"])
        self.assertEqual(contexto["cliente_fiscal"]["nombre"], "CONSUMIDOR FINAL")
        self.assertEqual(contexto["cliente_fiscal"]["documento"], "")

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("CONSUMIDOR FINAL", contenido_pdf)
        self.assertNotIn("Mostrador", contenido_pdf)

    def test_pdf_muestra_cae_y_vencimiento(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("61111111111111", contenido_pdf)
        self.assertIn("10/06/2026", contenido_pdf)

    def test_factura_arca_con_descuento_muestra_linea_descuento(self):
        venta_id = self._crear_venta(descuento_adicional=300)
        self._registrar_comprobante(venta_id, importe_total=2700.0)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Subtotal", contenido_pdf)
        self.assertIn("Descuento", contenido_pdf)
        self.assertIn("-$ 300,00", contenido_pdf)
        self.assertIn("$ 2.700,00", contenido_pdf)

    def test_factura_arca_sin_descuento_no_muestra_linea_descuento(self):
        venta_id = self._crear_venta(descuento_adicional=0)
        self._registrar_comprobante(venta_id, importe_total=3000.0)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertNotIn("Descuento", contenido_pdf)

    def test_factura_arca_con_descuento_mantiene_total_final_persistido(self):
        venta_id = self._crear_venta(descuento_adicional=300)
        self._registrar_comprobante(venta_id, importe_total=2700.0)

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id, force_regenerate=True)

        self.assertTrue(resultado["ok"])
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("$ 2.700,00", contenido_pdf)
        venta = self.database.q("SELECT subtotal, descuento_adicional, total FROM ventas WHERE id = ?", (venta_id,), fetchone=True)
        self.assertEqual(float(venta["subtotal"] or 0), 3000.0)
        self.assertEqual(float(venta["descuento_adicional"] or 0), 300.0)
        self.assertEqual(float(venta["total"] or 0), 2700.0)

    def test_reimpresion_no_llama_emision_wsfe(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id)
        original_emitir = self.arca_client.emitir_factura
        self.addCleanup(setattr, self.arca_client, "emitir_factura", original_emitir)

        def fail_emitir(_payload):
            raise AssertionError("La reimpresión no debe invocar emisión WSFE.")

        self.arca_client.emitir_factura = fail_emitir

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/arca/comprobante/{venta_id}/pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        response.close()

    def test_si_falta_pdf_fisico_se_regenera_desde_datos_persistidos(self):
        venta_id = self._crear_venta(cliente_nombre="Cliente Fiscal SA", cliente_id=self.cliente_id)
        comprobante = self._registrar_comprobante(venta_id, numero_comprobante=88)
        pdf_path = Path(str(comprobante["pdf_path"]))
        if pdf_path.exists():
            pdf_path.unlink()

        resultado = self.reimpresion_service.generar_pdf_comprobante_arca(venta_id)

        self.assertTrue(resultado["ok"])
        self.assertTrue(Path(str(resultado["pdf_path"])).exists())
        contenido_pdf = Path(str(resultado["pdf_path"])).read_bytes().decode("latin-1", errors="ignore")
        self.assertIn("Factura B", contenido_pdf)
        self.assertIn("0002-00000088", contenido_pdf)
        self.assertIn("61111111111111", contenido_pdf)
        self.assertIn("Cliente Fiscal SA", contenido_pdf)

    def test_reimpresion_no_modifica_stock_ni_duplica_venta(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id)
        stock_antes = self.database.q("SELECT stock_actual FROM stock WHERE producto_id = ?", (self.producto_id,), fetchone=True)
        ventas_antes = self.database.q("SELECT COUNT(*) AS total FROM ventas", fetchone=True)

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/arca/comprobante/{venta_id}/pdf")

        self.assertEqual(response.status_code, 200)
        response.close()

        stock_despues = self.database.q("SELECT stock_actual FROM stock WHERE producto_id = ?", (self.producto_id,), fetchone=True)
        ventas_despues = self.database.q("SELECT COUNT(*) AS total FROM ventas", fetchone=True)
        self.assertEqual(float(stock_despues["stock_actual"] or 0), float(stock_antes["stock_actual"] or 0))
        self.assertEqual(int(ventas_despues["total"] or 0), int(ventas_antes["total"] or 0))

    def test_apertura_desktop_genera_archivo_local_y_usa_visor_predeterminado(self):
        venta_id = self._crear_venta()
        self._registrar_comprobante(venta_id)

        with patch("modules.arca.routes.open_file_cross_platform") as open_mock:
            open_mock.return_value = {
                "ok": True,
                "message": "Se abrió correctamente.",
                "path": "",
                "platform": "linux",
                "method": "xdg-open",
            }
            with self.app.test_client() as client:
                self._login_admin(client)
                response = client.post(
                    f"/arca/comprobante/{venta_id}/abrir",
                    headers={"X-CSRFToken": "test-token"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["pdf_path"])
        open_mock.assert_called_once()
        opened_path = Path(open_mock.call_args.args[0])
        self.assertTrue(opened_path.exists())

    def test_comprobante_interno_muestra_leyenda_no_valido_como_factura(self):
        venta_id = self._crear_venta(cliente_nombre="Mostrador", cliente_id=0)

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/ticket/{venta_id}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("COMPROBANTE INTERNO DE VENTA", html)
        self.assertIn("No válido como factura", html)
        self.assertNotIn("CAE:", html)

    def test_comprobante_interno_muestra_nombre_visible_de_vendedor(self):
        self.database.add_usuario(
            "vendedor1",
            "1234",
            "Vendedor",
            "Juan Perez",
            security_question="color",
            security_answer="rojo",
        )
        venta_id = self._crear_venta(cliente_nombre="Mostrador", cliente_id=0, vendedor="vendedor1")

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/ticket/{venta_id}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Juan Perez", html)
        self.assertNotIn("<strong>vendedor1</strong>", html)


if __name__ == "__main__":
    unittest.main()
