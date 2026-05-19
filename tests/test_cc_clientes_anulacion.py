import importlib
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class CuentaCorrienteClientesSeguraTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        import database

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

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
                "descripcion": "Producto CC",
                "marca": "",
                "categoria": "General",
                "tipo_unidad": "unidad",
                "stock_actual": 10,
                "stock_minimo": 1,
                "stock_maximo": 20,
                "costo": 100,
                "precio_venta": 150,
                "iva": "21%",
            }
        )

    def _abrir_caja(self, fecha="2026-05-19"):
        return self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (1, f"{fecha} 09:00:00", 0, 0),
            fetchall=False,
            commit=True,
        )

    def _crear_venta_fiada(self, fecha="2026-05-19", total=300):
        venta_id = self.database.crear_venta(
            [
                {
                    "producto_id": self.producto_id,
                    "codigo_interno": "P-CC",
                    "descripcion": "Producto CC",
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

    def test_registrar_pago_y_anularlo_restaurando_saldo_y_caja(self):
        self._abrir_caja()
        self._crear_venta_fiada()

        movimiento_id = int(
            self.database.registrar_pago_cliente(
                self.cliente_id,
                120,
                numero_comprobante="REC-001",
                observaciones="Pago parcial",
                fecha="2026-05-19",
                medio_pago="Efectivo",
            )
        )

        self.assertEqual(self.database.get_saldo_cliente(self.cliente_id), 180.0)
        movimiento = self.database.get_movimiento_cliente(movimiento_id)
        caja_movimiento = self.database.get_caja_movimiento(int(movimiento["caja_movimiento_id"] or 0))
        self.assertIsNotNone(caja_movimiento)
        self.assertEqual(str(caja_movimiento["tipo"]), "INGRESO")
        self.assertEqual(float(caja_movimiento["monto"] or 0), 120.0)

        self.database.anular_movimiento_cliente(movimiento_id, "Pago duplicado", usuario="admin")

        movimiento_anulado = self.database.get_movimiento_cliente(movimiento_id)
        caja_movimiento_anulado = self.database.get_caja_movimiento(int(movimiento_anulado["caja_movimiento_id"] or 0))
        self.assertEqual(int(movimiento_anulado["anulado"] or 0), 1)
        self.assertEqual(movimiento_anulado["motivo_anulacion"], "Pago duplicado")
        self.assertEqual(self.database.get_saldo_cliente(self.cliente_id), 300.0)
        self.assertEqual(int(caja_movimiento_anulado["anulado"] or 0), 1)

    def test_impide_doble_anulacion_de_pago(self):
        self._abrir_caja()
        self._crear_venta_fiada()
        movimiento_id = int(
            self.database.registrar_pago_cliente(
                self.cliente_id,
                50,
                numero_comprobante="REC-002",
                fecha="2026-05-19",
                medio_pago="Efectivo",
            )
        )

        self.database.anular_movimiento_cliente(movimiento_id, "Error de carga", usuario="admin")

        with self.assertRaises(ValueError):
            self.database.anular_movimiento_cliente(movimiento_id, "Segundo intento", usuario="admin")

    def test_anular_venta_fiada_compensa_deuda_y_conserva_historial(self):
        venta_id = self._crear_venta_fiada()

        self.assertEqual(self.database.get_saldo_cliente(self.cliente_id), 300.0)

        self.database.anular_venta(venta_id, motivo="Venta cancelada", usuario="admin")

        self.assertEqual(self.database.get_saldo_cliente(self.cliente_id), 0.0)
        movimientos = self.database.get_movimientos_cliente(self.cliente_id, limit=10)
        tipos = [str(m["tipo"]) for m in movimientos]
        self.assertIn("Venta", tipos)
        self.assertIn("Anulación venta", tipos)
        venta = self.database.q("SELECT anulada FROM ventas WHERE id=?", (venta_id,), fetchone=True)
        self.assertEqual(int(venta["anulada"] or 0), 1)

    def test_movimiento_de_venta_no_se_puede_anular_desde_clientes(self):
        venta_id = self._crear_venta_fiada()
        movimiento_venta = self.database.q(
            "SELECT id FROM cc_clientes_mov WHERE venta_id=? AND tipo='Venta' LIMIT 1",
            (venta_id,),
            fetchone=True,
        )

        with self.assertRaises(ValueError):
            self.database.anular_movimiento_cliente(int(movimiento_venta["id"]), "No corresponde", usuario="admin")


if __name__ == "__main__":
    unittest.main()
