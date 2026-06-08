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


class VentaFinalizarTemporadaTests(unittest.TestCase):
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
        self.app.config["TESTING"] = True

        self.user_id = self.database.add_usuario(
            "admin",
            "1234",
            "admin",
            "Administrador Test",
            security_question="color",
            security_answer="azul",
        )
        self.producto_id = self.database.add_producto(
            {
                "descripcion": "Producto Temporada",
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
        self.database.q("UPDATE temporadas SET activa=0", commit=True)
        self.database.q(
            """
            INSERT INTO temporadas (nombre, descripcion, fecha_inicio, fecha_fin, activa)
            VALUES (?, ?, ?, ?, 1)
            """,
            ("Temporada Test Activa", "", "2020-01-01", "2099-12-31"),
            commit=True,
        )
        self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (self.user_id, "2026-06-08 09:00:00", 0, 0),
            commit=True,
        )

    def _cart_item(self):
        producto = self.database.get_producto(self.producto_id)
        return {
            "producto_id": self.producto_id,
            "codigo_interno": producto["codigo_interno"],
            "descripcion": producto["descripcion"],
            "categoria": producto["categoria"],
            "unidad": "Unidad",
            "cantidad": 1,
            "precio_unitario": 150,
            "costo_unitario": 100,
            "iva": "21%",
            "descuento": 0,
            "subtotal": 150,
        }

    def test_venta_finalizar_guarda_temporada_activa_sqlite_row(self):
        with self.app.test_request_context(
            "/venta/finalizar",
            method="POST",
            data={
                "cliente_id": "0",
                "cliente_nombre": "Mostrador",
                "medio_pago": "Efectivo",
                "descuento_adicional": "0",
            },
        ):
            session["user"] = {
                "id": self.user_id,
                "rol": "admin",
                "username": "admin",
                "nombre_completo": "Administrador Test",
            }
            session["cart"] = [self._cart_item()]

            response = self.routes_main.venta_finalizar()

        self.assertEqual(response.status_code, 302)
        venta = self.database.q("SELECT * FROM ventas ORDER BY id DESC LIMIT 1", fetchone=True)
        self.assertIsNotNone(venta)
        self.assertEqual(venta["temporada"], "Temporada Test Activa")
