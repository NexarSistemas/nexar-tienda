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


class ArcaFase6FacturaDesdeVentaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()

        import database
        import modules.arca.services.arca_client as arca_client
        from modules.arca.services import comprobantes_service, facturacion_desde_venta_service

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.arca_client = importlib.reload(arca_client)
        self.comprobantes_service = importlib.reload(comprobantes_service)
        self.comprobantes_service.db = self.database
        self.facturacion_service = importlib.reload(facturacion_desde_venta_service)
        self.facturacion_service.db = self.database
        self.facturacion_service.arca_client = self.arca_client

    def tearDown(self):
        _reset_env()

    def _crear_venta(self) -> int:
        return int(
            self.database.crear_venta(
                [
                    {
                        "producto_id": 0,
                        "codigo_interno": "ARCA-F6",
                        "descripcion": "Producto fiscal",
                        "categoria": "General",
                        "unidad": "unidad",
                        "cantidad": 2,
                        "precio_unitario": 1000,
                        "costo_unitario": 650,
                        "iva": "21%",
                        "descuento": 0,
                        "subtotal": 2000,
                    }
                ],
                "Mostrador",
                "Efectivo",
                0,
                "admin",
            )
        )

    def test_no_permite_facturar_venta_inexistente(self):
        resultado = self.facturacion_service.facturar_venta_desde_existente(9999)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "venta_no_encontrada")

    def test_no_permite_facturar_dos_veces_la_misma_venta(self):
        venta_id = self._crear_venta()
        original_emitir = self.arca_client.emitir_factura
        self.addCleanup(setattr, self.arca_client, "emitir_factura", original_emitir)

        def fake_emitir(_payload):
            return {
                "ok": True,
                "modo": "simulacion",
                "estado": "MODO_TEST",
                "tipo_comprobante": "Factura B",
                "punto_venta": 1,
                "numero_comprobante": 1,
                "cae": "12345678901234",
                "cae_vencimiento": "2026-06-03",
                "importe_total": 2000.0,
                "fecha_emision": "2026-05-24",
                "pdf_path": "data/arca/comprobantes/2026/05/demo.pdf",
            }

        self.arca_client.emitir_factura = fake_emitir

        primero = self.facturacion_service.facturar_venta_desde_existente(venta_id)
        segundo = self.facturacion_service.facturar_venta_desde_existente(venta_id)

        self.assertTrue(primero["ok"])
        self.assertFalse(segundo["ok"])
        self.assertEqual(segundo["error_code"], "duplicado")
        row = self.database.q(
            "SELECT COUNT(*) AS total FROM arca_comprobantes WHERE venta_id = ?",
            (venta_id,),
            fetchone=True,
        )
        self.assertEqual(int(row["total"] or 0), 1)

    def test_error_de_arca_no_modifica_la_venta(self):
        venta_id = self._crear_venta()
        venta_antes = dict(self.database.q("SELECT * FROM ventas WHERE id = ?", (venta_id,), fetchone=True))
        original_emitir = self.arca_client.emitir_factura
        self.addCleanup(setattr, self.arca_client, "emitir_factura", original_emitir)

        def fake_emitir(_payload):
            return {
                "ok": False,
                "error_code": "error_wsfe",
                "mensaje": "ARCA no disponible.",
            }

        self.arca_client.emitir_factura = fake_emitir

        resultado = self.facturacion_service.facturar_venta_desde_existente(venta_id)
        venta_despues = dict(self.database.q("SELECT * FROM ventas WHERE id = ?", (venta_id,), fetchone=True))
        row = self.database.q(
            "SELECT COUNT(*) AS total FROM arca_comprobantes WHERE venta_id = ?",
            (venta_id,),
            fetchone=True,
        )

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "error_wsfe")
        self.assertEqual(venta_despues, venta_antes)
        self.assertEqual(int(row["total"] or 0), 0)

    def test_guarda_comprobante_con_cae_correctamente(self):
        venta_id = self._crear_venta()
        original_emitir = self.arca_client.emitir_factura
        self.addCleanup(setattr, self.arca_client, "emitir_factura", original_emitir)

        def fake_emitir(payload):
            self.assertEqual(payload["venta_id"], venta_id)
            self.assertEqual(payload["tipo_cbte"], 6)
            self.assertEqual(len(payload["items"]), 1)
            return {
                "ok": True,
                "modo": "wsfe",
                "estado": "AUTORIZADO",
                "resultado": "A",
                "tipo_comprobante": "Factura B",
                "punto_venta": 3,
                "numero_comprobante": 456,
                "cae": "61111111111111",
                "cae_vencimiento": "2026-06-10",
                "importe_total": 2000.0,
                "fecha_emision": "2026-05-24",
                "ambiente": "homologacion",
                "pdf_path": "data/arca/comprobantes/2026/05/venta-1-pv-0003-cbte-00000456.pdf",
                "observaciones": ["mock-ok"],
            }

        self.arca_client.emitir_factura = fake_emitir

        resultado = self.facturacion_service.facturar_venta_desde_existente(venta_id)

        self.assertTrue(resultado["ok"])
        comprobante = self.database.q(
            """
            SELECT venta_id, tipo_comprobante, punto_venta, numero_comprobante, cae, cae_vencimiento,
                   importe_total, estado, fecha_emision, respuesta_raw, pdf_path
            FROM arca_comprobantes
            WHERE venta_id = ?
            """,
            (venta_id,),
            fetchone=True,
        )
        self.assertIsNotNone(comprobante)
        self.assertEqual(int(comprobante["venta_id"] or 0), venta_id)
        self.assertEqual(comprobante["tipo_comprobante"], "Factura B")
        self.assertEqual(int(comprobante["punto_venta"] or 0), 3)
        self.assertEqual(int(comprobante["numero_comprobante"] or 0), 456)
        self.assertEqual(comprobante["cae"], "61111111111111")
        self.assertEqual(comprobante["cae_vencimiento"], "2026-06-10")
        self.assertEqual(float(comprobante["importe_total"] or 0), 2000.0)
        self.assertEqual(comprobante["estado"], "AUTORIZADO")
        self.assertEqual(comprobante["fecha_emision"], "2026-05-24")
        self.assertIn("61111111111111", comprobante["respuesta_raw"])
        self.assertEqual(
            comprobante["pdf_path"],
            "data/arca/comprobantes/2026/05/venta-1-pv-0003-cbte-00000456.pdf",
        )


if __name__ == "__main__":
    unittest.main()
