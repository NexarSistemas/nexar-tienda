import importlib
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ProveedorFacturasAnulacionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        import database

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.proveedor_id = self.database.add_proveedor(
            {
                "nombre": "Proveedor Test",
                "cuit": "",
                "telefono": "",
                "email": "",
                "dias_credito": 30,
            }
        )

    def _crear_factura(self, numero="FAC-001", importe=1500):
        factura_id = self.database.crear_factura_proveedor(
            self.proveedor_id,
            numero,
            "2026-05-18",
            "2026-05-30",
            importe,
            "Factura de prueba",
        )
        return int(factura_id)

    def test_anular_factura_sin_pagos_conserva_historial_y_quita_deuda(self):
        factura_id = self._crear_factura()

        self.database.anular_factura_proveedor(factura_id, motivo="Carga duplicada", usuario="admin")

        factura = self.database.get_factura_proveedor(factura_id)
        self.assertEqual(int(factura["anulada"] or 0), 1)
        self.assertEqual(factura["motivo_anulacion"], "Carga duplicada")
        self.assertEqual(factura["anulada_por"], "admin")
        self.assertTrue(str(factura["anulada_at"] or "").strip())
        self.assertEqual(self.database.get_deuda_proveedor_desde_facturas(self.proveedor_id), 0)

    def test_impide_doble_anulacion(self):
        factura_id = self._crear_factura(numero="FAC-002")

        self.database.anular_factura_proveedor(factura_id, motivo="Error", usuario="admin")

        with self.assertRaises(ValueError):
            self.database.anular_factura_proveedor(factura_id, motivo="Segundo intento", usuario="admin")

    def test_no_anula_factura_con_pagos_y_conserva_registro(self):
        factura_id = self._crear_factura(numero="FAC-003", importe=2000)
        self.database.registrar_pago_factura_proveedor(factura_id, 500)

        with self.assertRaises(ValueError):
            self.database.anular_factura_proveedor(factura_id, motivo="No debería", usuario="admin")

        factura = self.database.get_factura_proveedor(factura_id)
        self.assertIsNotNone(factura)
        self.assertEqual(int(factura["anulada"] or 0), 0)
        self.assertEqual(float(factura["pagado"] or 0), 500.0)

    def test_factura_anulada_no_bloquea_compra_tiene_factura_activa(self):
        compra_id = self.database.add_compra(
            {
                "fecha": "2026-05-18",
                "numero_remito": "REM-001",
                "proveedor_id": self.proveedor_id,
                "proveedor_nombre": "Proveedor Test",
                "producto_id": 0,
                "codigo_interno": "",
                "descripcion": "Compra auxiliar",
                "cantidad": 1,
                "costo_unitario": 100,
                "total": 100,
                "observaciones": "",
            }
        )
        factura = self.database.crear_factura_desde_compra(compra_id, self.proveedor_id, 100, numero_factura="FAC-004")
        factura_id = int(factura["id"])

        self.assertTrue(self.database.compra_tiene_factura(compra_id))

        self.database.anular_factura_proveedor(factura_id, motivo="Reemplazada", usuario="admin")

        self.assertFalse(self.database.compra_tiene_factura(compra_id))
        self.assertIsNone(self.database.get_factura_por_compra(compra_id))


if __name__ == "__main__":
    unittest.main()
