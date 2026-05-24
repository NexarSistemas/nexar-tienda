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


class ArcaFase5SimulacionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()

        import database
        from modules.arca.services import comprobantes_service
        from services import arca_config_service
        import services.arca.wsfe_service as wsfe_service

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.comprobantes_service = importlib.reload(comprobantes_service)
        self.comprobantes_service.db = self.database
        self.config_service = importlib.reload(arca_config_service)
        self.config_service.db = self.database
        self.wsfe_service = importlib.reload(wsfe_service)
        self.wsfe_service.db = self.database

    def tearDown(self):
        _reset_env()

    def _crear_venta(self) -> int:
        return int(
            self.database.crear_venta(
                [
                    {
                        "producto_id": 0,
                        "codigo_interno": "TEST-ARCA",
                        "descripcion": "Producto ARCA",
                        "categoria": "General",
                        "unidad": "unidad",
                        "cantidad": 1,
                        "precio_unitario": 1500,
                        "costo_unitario": 1000,
                        "iva": "21%",
                        "descuento": 0,
                        "subtotal": 1500,
                    }
                ],
                "Mostrador",
                "Efectivo",
                0,
                "admin",
            )
        )

    def test_emitir_comprobante_simulado_desde_venta_existente(self):
        os.environ["FLASK_ENV"] = "development"
        venta_id = self._crear_venta()

        resultado = self.comprobantes_service.emitir_comprobante_desde_venta(venta_id)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["modo"], "simulacion")
        self.assertEqual(resultado["comprobante"]["estado"], "MODO_TEST")
        self.assertEqual(resultado["comprobante"]["venta_id"], venta_id)
        self.assertGreater(int(resultado["comprobante"]["numero_comprobante"]), 0)
        self.assertTrue(str(resultado["comprobante"]["cae"]).isdigit())

    def test_no_duplica_comprobante_para_la_misma_venta(self):
        os.environ["FLASK_ENV"] = "development"
        venta_id = self._crear_venta()

        primero = self.comprobantes_service.emitir_comprobante_desde_venta(venta_id)
        segundo = self.comprobantes_service.emitir_comprobante_desde_venta(venta_id)

        self.assertTrue(primero["ok"])
        self.assertFalse(segundo["ok"])
        self.assertEqual(segundo["error_code"], "duplicado")

        row = self.database.q(
            "SELECT COUNT(*) AS total FROM arca_comprobantes WHERE venta_id = ?",
            (venta_id,),
            fetchone=True,
        )
        self.assertEqual(int(row["total"] or 0), 1)

    def test_falta_venta_id_devuelve_error_controlado(self):
        resultado = self.comprobantes_service.emitir_comprobante_desde_venta(None)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "venta_invalida")

    def test_modo_simulacion_no_llama_wsfe_real(self):
        os.environ["ARCA_MODO_SIMULACION"] = "true"
        venta_id = self._crear_venta()

        original_probar_wsfe = self.wsfe_service.probar_wsfe
        self.addCleanup(setattr, self.wsfe_service, "probar_wsfe", original_probar_wsfe)

        def _fail_if_called():
            raise AssertionError("WSFE real no debe invocarse en simulación.")

        self.wsfe_service.probar_wsfe = _fail_if_called

        resultado = self.comprobantes_service.emitir_comprobante_desde_venta(venta_id)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["modo"], "simulacion")
