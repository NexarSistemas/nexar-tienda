import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


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


class ArcaFase7DatosFiscalesTests(unittest.TestCase):
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
        from modules.arca.services import comprobantes_service, facturacion_desde_venta_service
        from routes import main as routes_main

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.comprobantes_service = importlib.reload(comprobantes_service)
        self.comprobantes_service.db = self.database
        self.arca_client = importlib.reload(arca_client)
        self.facturacion_service = importlib.reload(facturacion_desde_venta_service)
        self.facturacion_service.db = self.database
        self.facturacion_service.arca_client = self.arca_client

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
                "descripcion": "Producto ARCA",
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

    def _crear_venta(self) -> int:
        return int(
            self.database.crear_venta(
                [
                    {
                        "producto_id": self.producto_id,
                        "codigo_interno": "ARCA-F7",
                        "descripcion": "Producto ARCA",
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
                "Cliente ARCA",
                "Efectivo",
                0,
                "admin",
            )
        )

    def _emitir_factura_mock(self, venta_id: int):
        original_emitir = self.arca_client.emitir_factura
        self.addCleanup(setattr, self.arca_client, "emitir_factura", original_emitir)

        def fake_emitir(payload):
            self.assertEqual(payload["venta_id"], venta_id)
            return {
                "ok": True,
                "modo": "wsfe",
                "estado": "AUTORIZADO",
                "resultado": "A",
                "tipo_comprobante": "Factura C",
                "punto_venta": 2,
                "numero_comprobante": 1,
                "cae": "61111111111111",
                "cae_vencimiento": "2026-06-10",
                "importe_total": 3000.0,
                "fecha_emision": "2026-05-24",
                "ambiente": "homologacion",
                "pdf_path": "",
                "observaciones": ["mock-ok"],
            }

        self.arca_client.emitir_factura = fake_emitir
        return self.facturacion_service.facturar_venta_desde_existente(venta_id)

    def test_venta_facturada_muestra_datos_arca_en_ticket_e_historial(self):
        venta_id = self._crear_venta()
        resultado = self._emitir_factura_mock(venta_id)
        self.assertTrue(resultado["ok"])

        with self.app.test_client() as client:
            self._login_admin(client)

            response_ticket = client.get(f"/ticket/{venta_id}")
            response_historial = client.get("/historial")

        html_ticket = response_ticket.get_data(as_text=True)
        html_historial = response_historial.get_data(as_text=True)

        self.assertIn("Factura C 0002-00000001", html_ticket)
        self.assertIn("CAE: 61111111111111", html_ticket)
        self.assertIn("Vencimiento CAE: 2026-06-10", html_ticket)
        self.assertIn("PDF local: pendiente", html_ticket)
        self.assertIn("Factura ARCA generada", html_ticket)
        self.assertIn("Factura C 0002-00000001", html_historial)
        self.assertIn("CAE 61111111111111", html_historial)

    def test_venta_sin_factura_sigue_permitiendo_accion(self):
        venta_id = self._crear_venta()

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/ticket/{venta_id}")

        html = response.get_data(as_text=True)
        self.assertIn("Facturar con ARCA", html)
        self.assertNotIn("Factura ARCA generada", html)

    def test_venta_facturada_no_permite_nueva_emision(self):
        venta_id = self._crear_venta()
        resultado = self._emitir_factura_mock(venta_id)
        self.assertTrue(resultado["ok"])

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                f"/arca/ventas/{venta_id}/emitir",
                data={"csrf_token": "test-token", "next": f"/ticket/{venta_id}"},
                follow_redirects=True,
            )

        row = self.database.q(
            "SELECT COUNT(*) AS total FROM arca_comprobantes WHERE venta_id = ?",
            (venta_id,),
            fetchone=True,
        )
        html = response.get_data(as_text=True)
        self.assertEqual(int(row["total"] or 0), 1)
        self.assertIn("La venta ya fue facturada con ARCA.", html)

    def test_listado_de_comprobantes_muestra_registros_guardados(self):
        venta_id = self._crear_venta()
        resultado = self._emitir_factura_mock(venta_id)
        self.assertTrue(resultado["ok"])
        comprobante_id = int(resultado["comprobante"]["id"])

        with self.app.test_client() as client:
            self._login_admin(client)
            response_listado = client.get("/arca/comprobantes")
            response_detalle = client.get(f"/arca/comprobantes/{comprobante_id}")

        html_listado = response_listado.get_data(as_text=True)
        html_detalle = response_detalle.get_data(as_text=True)
        self.assertIn("Factura C 0002-00000001", html_listado)
        self.assertIn("Venta #1", html_listado)
        self.assertIn("Pendiente", html_listado)
        self.assertIn("Resumen técnico seguro", html_detalle)
        self.assertIn("61111111111111", html_detalle)


if __name__ == "__main__":
    unittest.main()
