import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from flask import session


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class PermisosBasicosTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        import database
        from routes import main as routes_main
        import app as app_module

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.routes_main = importlib.reload(routes_main)
        self.routes_main.db = self.database

        os.environ["SECRET_KEY"] = "test-secret-key"
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
        self.empleado_id = self.database.add_usuario(
            "empleado",
            "1234",
            "Vendedor",
            "Empleado Test",
            security_question="color",
            security_answer="verde",
        )
        self.encargado_id = self.database.add_usuario(
            "encargado",
            "1234",
            "Encargado",
            "Encargado Test",
            security_question="color",
            security_answer="rojo",
        )

        self.producto_id = self.database.add_producto(
            {
                "descripcion": "Producto Permisos",
                "marca": "",
                "categoria": "General",
                "tipo_unidad": "unidad",
                "stock_actual": 20,
                "stock_minimo": 1,
                "stock_maximo": 50,
                "costo": 100,
                "precio_venta": 150,
                "iva": "21%",
            }
        )
        self.cliente_id = self.database.add_cliente(
            {
                "nombre": "Cliente Permisos",
                "dni_cuit": "",
                "telefono": "",
                "email": "",
                "limite_credito": 0,
                "activo": 1,
            }
        )
        self.proveedor_id = self.database.add_proveedor(
            {
                "nombre": "Proveedor Permisos",
                "cuit": "",
                "telefono": "",
                "email": "",
                "dias_credito": 30,
            }
        )

    def _set_session_user(self, user_id, username, rol, nombre):
        session["user"] = {
            "id": user_id,
            "rol": rol,
            "username": username,
            "nombre_completo": nombre,
        }
        session["_csrf_token"] = "test-token"

    def _login_admin(self):
        self._set_session_user(self.admin_id, "admin", "Administrador", "Administrador Test")

    def _login_empleado(self):
        self._set_session_user(self.empleado_id, "empleado", "Vendedor", "Empleado Test")

    def _login_encargado(self):
        self._set_session_user(self.encargado_id, "encargado", "Encargado", "Encargado Test")

    def _crear_venta_fiada(self, total=300, fecha="2026-05-19"):
        venta_id = self.database.crear_venta(
            [
                {
                    "producto_id": self.producto_id,
                    "codigo_interno": "PERM-001",
                    "descripcion": "Producto Permisos",
                    "categoria": "General",
                    "unidad": "Unidad",
                    "cantidad": 2,
                    "precio_unitario": 150,
                    "costo_unitario": 100,
                    "iva": "21%",
                    "descuento": 0,
                    "subtotal": total,
                }
            ],
            "Cliente Permisos",
            "Cuenta Corriente",
            0,
            "tester",
            cliente_id=self.cliente_id,
            temporada="",
        )
        self.database.q("UPDATE ventas SET fecha=? WHERE id=?", (fecha, venta_id), commit=True)
        self.database.decrementar_stock_venta(venta_id)
        self.database.reconciliar_cc_clientes_desde_ventas()
        return int(venta_id)

    def _crear_pago_cliente(self):
        self._crear_venta_fiada()
        return int(
            self.database.registrar_pago_cliente(
                self.cliente_id,
                40,
                numero_comprobante="REC-001",
                observaciones="Pago parcial",
                fecha="2026-05-19",
                medio_pago="Transferencia",
            )
        )

    def _crear_gasto(self):
        return int(
            self.database.add_gasto(
                {
                    "fecha": "2026-05-19",
                    "categoria": "Servicios",
                    "clasificacion": "Operativo",
                    "descripcion": "Internet",
                    "monto": 80,
                    "medio_pago": "Transferencia",
                }
            )
        )

    def _crear_compra(self):
        return int(
            self.database.add_compra(
                {
                    "fecha": "2026-05-19",
                    "numero_remito": "COMP-001",
                    "proveedor_id": self.proveedor_id,
                    "proveedor_nombre": "Proveedor Permisos",
                    "producto_id": self.producto_id,
                    "codigo_interno": "PERM-001",
                    "descripcion": "Producto Permisos",
                    "cantidad": 2,
                    "costo_unitario": 90,
                    "total": 180,
                    "observaciones": "",
                }
            )
        )

    def _crear_factura_proveedor(self):
        return int(
            self.database.crear_factura_proveedor(
                self.proveedor_id,
                "FAC-001",
                "2026-05-19",
                "2026-06-19",
                250,
                "Factura test",
            )
        )

    def _abrir_caja(self, user_id=None, fecha="2026-05-19"):
        return self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (user_id or self.admin_id, f"{fecha} 09:00:00", 0, 0),
            fetchall=False,
            commit=True,
        )

    def test_admin_puede_anular_gasto(self):
        gasto_id = self._crear_gasto()
        with self.app.test_request_context(
            f"/gastos/{gasto_id}/eliminar",
            method="POST",
            data={"motivo_anulacion": "Carga duplicada", "csrf_token": "test-token"},
        ):
            self._login_admin()
            response = self.routes_main.gasto_eliminar(gasto_id)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/gastos"))
        gasto = self.database.get_gasto(gasto_id)
        self.assertEqual(int(gasto["anulado"] or 0), 1)

    def test_empleado_no_puede_anular_operaciones_criticas_ni_ver_auditoria(self):
        venta_id = self._crear_venta_fiada(total=120)
        gasto_id = self._crear_gasto()
        movimiento_id = self._crear_pago_cliente()
        compra_id = self._crear_compra()
        factura_id = self._crear_factura_proveedor()
        with self.app.test_request_context(
            f"/historial/{venta_id}/eliminar",
            method="POST",
            data={"motivo_anulacion": "No corresponde", "confirmo_responsabilidad": "1", "csrf_token": "test-token"},
        ):
            self._login_empleado()
            response_venta = self.routes_main.historial_eliminar(venta_id)
        with self.app.test_request_context(
            f"/compras/{compra_id}/eliminar",
            method="POST",
            data={"motivo_anulacion": "No corresponde", "confirmo_responsabilidad": "1", "csrf_token": "test-token"},
        ):
            self._login_empleado()
            response_compra = self.routes_main.compra_eliminar(compra_id)
        with self.app.test_request_context(
            f"/gastos/{gasto_id}/eliminar",
            method="POST",
            data={"motivo_anulacion": "No corresponde", "csrf_token": "test-token"},
        ):
            self._login_empleado()
            response_gasto = self.routes_main.gasto_eliminar(gasto_id)
        with self.app.test_request_context(
            f"/clientes/{self.cliente_id}/movimiento/{movimiento_id}/anular",
            method="POST",
            data={"motivo_anulacion": "No corresponde", "csrf_token": "test-token"},
        ):
            self._login_empleado()
            response_cliente = self.routes_main.cliente_anular_movimiento(self.cliente_id, movimiento_id)
        with self.app.test_request_context(
            f"/proveedores/{self.proveedor_id}/facturas/{factura_id}/eliminar",
            method="POST",
            data={"motivo_anulacion": "No corresponde", "next": f"/proveedores/{self.proveedor_id}/facturas", "csrf_token": "test-token"},
        ):
            self._login_empleado()
            response_factura = self.routes_main.proveedor_factura_eliminar(self.proveedor_id, factura_id)
        with self.app.test_request_context("/auditoria"):
            self._login_empleado()
            response_auditoria = self.routes_main.auditoria()

        for response in (
            response_venta,
            response_compra,
            response_gasto,
            response_cliente,
            response_factura,
            response_auditoria,
        ):
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/"))

        self.assertEqual(int(self.database.q("SELECT anulada FROM ventas WHERE id=?", (venta_id,), fetchone=True)["anulada"] or 0), 0)
        self.assertEqual(int(self.database.get_gasto(gasto_id)["anulado"] or 0), 0)
        self.assertEqual(int(self.database.get_movimiento_cliente(movimiento_id)["anulado"] or 0), 0)
        self.assertEqual(int(self.database.get_compra(compra_id)["anulada"] or 0), 0)
        self.assertEqual(int(self.database.get_factura_proveedor(factura_id)["anulada"] or 0), 0)

    def test_vendedor_no_puede_editar_stock_ni_clientes_y_encargado_si(self):
        with self.app.test_request_context(f"/stock/{self.producto_id}/ajustar"):
            self._login_empleado()
            response_stock_vendedor = self.routes_main.stock_ajustar(self.producto_id)
        with self.app.test_request_context(f"/clientes/{self.cliente_id}/editar"):
            self._login_empleado()
            response_cliente_vendedor = self.routes_main.cliente_editar(self.cliente_id)
        with self.app.test_request_context(f"/stock/{self.producto_id}/ajustar"):
            self._login_encargado()
            html_stock_encargado = self.routes_main.stock_ajustar(self.producto_id)
        with self.app.test_request_context(f"/clientes/{self.cliente_id}/editar"):
            self._login_encargado()
            html_cliente_encargado = self.routes_main.cliente_editar(self.cliente_id)

        self.assertEqual(response_stock_vendedor.status_code, 302)
        self.assertTrue(response_stock_vendedor.location.endswith("/"))
        self.assertEqual(response_cliente_vendedor.status_code, 302)
        self.assertTrue(response_cliente_vendedor.location.endswith("/"))
        self.assertIsInstance(html_stock_encargado, str)
        self.assertIn("Ajustar Stock", html_stock_encargado)
        self.assertIsInstance(html_cliente_encargado, str)
        self.assertIn("Editar Cliente", html_cliente_encargado)

    def test_vendedor_no_puede_entrar_a_reportes_y_si_a_punto_venta(self):
        with self.app.test_request_context("/reportes"):
            self._login_empleado()
            response_reportes = self.routes_main.reportes()
        with self.app.test_request_context("/punto-venta"):
            self._login_empleado()
            html_punto_venta = self.routes_main.punto_venta()

        self.assertEqual(response_reportes.status_code, 302)
        self.assertTrue(response_reportes.location.endswith("/"))
        self.assertIsInstance(html_punto_venta, str)
        self.assertIn("Punto de Venta", html_punto_venta)

    def test_logout_advierte_si_hay_caja_abierta_y_force_sale(self):
        self._abrir_caja(user_id=self.empleado_id)

        with self.app.test_request_context("/logout"):
            self._login_empleado()
            response_warning = self.routes_main.logout()
            flashes = session.get("_flashes", [])

        self.assertEqual(response_warning.status_code, 302)
        self.assertTrue(response_warning.location.endswith("/"))
        self.assertTrue(any("caja abierta" in message.lower() for _category, message in flashes))

        with self.app.test_request_context("/logout?force=1"):
            self._login_empleado()
            response_force = self.routes_main.logout()
            user_removed = "user" not in session

        self.assertEqual(response_force.status_code, 302)
        self.assertTrue(response_force.location.endswith("/login"))
        self.assertTrue(user_removed)

    def test_desktop_close_warning_expone_urls_de_logout_y_caja(self):
        self._abrir_caja(user_id=self.encargado_id)

        with self.app.test_request_context("/api/desktop/close-warning"):
            self._login_encargado()
            response = self.routes_main.desktop_close_warning()
            payload = response.get_json()

        self.assertTrue(payload["caja_abierta"])
        self.assertTrue(str(payload["logout_url"]).endswith("/logout"))
        self.assertIn("force=1", str(payload["logout_force_url"]))
        self.assertIn("/caja", str(payload["caja_url"]))

    def test_ui_oculta_acciones_de_edicion_para_vendedor(self):
        with self.app.test_request_context("/productos"):
            self._login_empleado()
            html_productos = self.routes_main.productos()
        with self.app.test_request_context("/stock"):
            self._login_empleado()
            html_stock = self.routes_main.stock()
        with self.app.test_request_context("/clientes"):
            self._login_empleado()
            html_clientes = self.routes_main.clientes()

        self.assertNotIn("Nuevo Producto", html_productos)
        self.assertNotIn("Importar CSV", html_productos)
        self.assertIn("No tenés permisos para editar productos", html_productos)
        self.assertNotIn(f"/stock/{self.producto_id}/ajustar", html_stock)
        self.assertIn("No tenés permisos para ajustar stock", html_stock)
        self.assertNotIn("Nuevo Cliente", html_clientes)
        self.assertNotIn(f"/clientes/{self.cliente_id}/editar", html_clientes)
        self.assertIn("No tenés permisos para editar clientes", html_clientes)


if __name__ == "__main__":
    unittest.main()
