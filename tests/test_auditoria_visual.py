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


class AuditoriaVisualTests(unittest.TestCase):
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
        self.app = self.app_module.create_app()

        self.user_id = self.database.add_usuario(
            "admin",
            "1234",
            "admin",
            "Administrador Test",
            security_question="color",
            security_answer="azul",
        )

        self.cliente_id = self.database.add_cliente(
            {
                "nombre": "Cliente Test",
                "dni_cuit": "",
                "telefono": "",
                "email": "",
                "limite_credito": 0,
                "activo": 1,
            }
        )
        self.producto_id = self.database.add_producto(
            {
                "descripcion": "Producto Auditoria",
                "marca": "",
                "categoria": "General",
                "tipo_unidad": "unidad",
                "stock_actual": 10,
                "stock_minimo": 1,
                "stock_maximo": 30,
                "costo": 100,
                "precio_venta": 150,
                "iva": "21%",
            }
        )

    def _set_admin_session(self):
        session["user"] = {
            "id": self.user_id,
            "rol": "admin",
            "username": "admin",
            "nombre_completo": "Administrador Test",
        }
        session["_csrf_token"] = "test-token"

    def _abrir_caja_db(self, fecha="2026-05-19"):
        return self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (self.user_id, f"{fecha} 09:00:00", 0, 0),
            commit=True,
        )

    def _crear_venta_fiada(self, fecha="2026-05-19", total=300):
        venta_id = self.database.crear_venta(
            [
                {
                    "producto_id": self.producto_id,
                    "codigo_interno": "AUD-001",
                    "descripcion": "Producto Auditoria",
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
            "Cliente Test",
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

    def test_anular_gasto_y_pago_cliente_generan_auditoria(self):
        self._abrir_caja_db()
        gasto_id = int(
            self.database.add_gasto(
                {
                    "fecha": "2026-05-19",
                    "categoria": "Servicios",
                    "clasificacion": "Operativo",
                    "descripcion": "Internet",
                    "monto": 80,
                    "medio_pago": "Efectivo",
                }
            )
        )
        self.database.anular_gasto(gasto_id, motivo="Carga duplicada", usuario="admin")

        self._crear_venta_fiada()
        movimiento_id = int(
            self.database.registrar_pago_cliente(
                self.cliente_id,
                120,
                numero_comprobante="REC-900",
                observaciones="Pago parcial",
                fecha="2026-05-19",
                medio_pago="Efectivo",
            )
        )
        self.database.anular_movimiento_cliente(movimiento_id, "Pago duplicado", usuario="admin")

        auditoria = self.database.get_auditoria(limit=20)
        acciones = [row["accion"] for row in auditoria]

        self.assertIn("ANULACION_GASTO", acciones)
        self.assertIn("ANULACION_CC_CLIENTE", acciones)

    def test_abrir_y_cerrar_caja_registran_auditoria(self):
        with self.app.test_request_context("/caja/abrir", method="POST", data={"saldo_inicial": "150", "next": "/caja"}):
            self._set_admin_session()
            response_abrir = self.routes_main.caja_abrir()
        self.assertEqual(response_abrir.status_code, 302)

        with self.app.test_request_context("/caja/cerrar", method="POST", data={"saldo_real": "180", "next": "/caja"}):
            self._set_admin_session()
            response_cerrar = self.routes_main.caja_cerrar()
        self.assertEqual(response_cerrar.status_code, 302)

        auditoria = self.database.get_auditoria(limit=20)
        acciones = [row["accion"] for row in auditoria]

        self.assertIn("APERTURA_CAJA", acciones)
        self.assertIn("CIERRE_CAJA", acciones)

    def test_pantalla_auditoria_muestra_registros(self):
        self.database.registrar_auditoria(
            "ANULACION_GASTO",
            "gasto",
            7,
            detalle="Servicios · Internet · 80.00",
            motivo="Carga duplicada",
            usuario="admin",
        )

        with self.app.test_request_context("/auditoria"):
            self._set_admin_session()
            html = self.routes_main.auditoria()

        self.assertIsInstance(html, str)
        self.assertIn("Registro de acciones críticas", html)
        self.assertIn("ANULACION_GASTO", html)
        self.assertIn("Carga duplicada", html)


if __name__ == "__main__":
    unittest.main()
