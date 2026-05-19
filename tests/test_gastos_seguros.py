import importlib
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GastosSegurosTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        import database

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

    def _abrir_caja(self, fecha="2026-05-19"):
        return self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (1, f"{fecha} 09:00:00", 0, 0),
            fetchall=False,
            commit=True,
        )

    def _crear_gasto_efectivo(self, monto=250, fecha="2026-05-19"):
        return int(
            self.database.add_gasto(
                {
                    "fecha": fecha,
                    "tipo": "Gasto",
                    "categoria": "Servicios",
                    "clasificacion": "Operativo",
                    "descripcion": "Pago proveedor",
                    "monto": monto,
                    "medio_pago": "Efectivo",
                    "proveedor": "Proveedor Test",
                    "observaciones": "Caja chica",
                }
            )
        )

    def test_crear_gasto_efectivo_con_caja_abierta_genera_movimiento(self):
        self._abrir_caja()
        gasto_id = self._crear_gasto_efectivo()

        gasto = self.database.get_gasto(gasto_id)
        movimiento = self.database.get_caja_movimiento_activo_por_gasto(gasto_id)

        self.assertEqual(int(gasto["anulado"] or 0), 0)
        self.assertIsNotNone(movimiento)
        self.assertEqual(str(movimiento["tipo"]), "EGRESO")
        self.assertEqual(float(movimiento["monto"] or 0), 250.0)

    def test_bloquea_gasto_efectivo_sin_caja_abierta(self):
        with self.assertRaises(ValueError):
            self._crear_gasto_efectivo()

    def test_anular_gasto_conserva_historial_y_anula_caja(self):
        self._abrir_caja()
        gasto_id = self._crear_gasto_efectivo(monto=180)

        self.database.anular_gasto(gasto_id, motivo="Carga duplicada", usuario="admin")

        gasto = self.database.get_gasto(gasto_id)
        movimiento = self.database.q(
            "SELECT * FROM caja_movimientos WHERE gasto_id=? ORDER BY id DESC LIMIT 1",
            (gasto_id,),
            fetchone=True,
        )

        self.assertEqual(int(gasto["anulado"] or 0), 1)
        self.assertEqual(gasto["motivo_anulacion"], "Carga duplicada")
        self.assertEqual(gasto["anulada_por"], "admin")
        self.assertTrue(str(gasto["anulada_at"] or "").strip())
        self.assertIsNotNone(movimiento)
        self.assertEqual(int(movimiento["anulado"] or 0), 1)

        gastos_categoria = self.database.get_gastos_por_categoria_periodo("2026-05-01", "2026-05-31")
        self.assertEqual(gastos_categoria, [])

        historial = self.database.get_gastos()
        self.assertEqual(len(historial), 1)
        self.assertEqual(int(historial[0]["anulado"] or 0), 1)

    def test_impide_doble_anulacion_y_edicion_destructiva(self):
        self._abrir_caja()
        gasto_id = self._crear_gasto_efectivo(monto=90)

        with self.assertRaises(ValueError):
            self.database.update_gasto(gasto_id, {"descripcion": "Cambio"})

        self.database.anular_gasto(gasto_id, motivo="Error de carga", usuario="admin")

        with self.assertRaises(ValueError):
            self.database.anular_gasto(gasto_id, motivo="Segundo intento", usuario="admin")


if __name__ == "__main__":
    unittest.main()
