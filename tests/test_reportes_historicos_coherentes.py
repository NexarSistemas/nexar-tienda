import importlib
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ReportesHistoricosCoherentesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        import database
        from routes import main as main_routes

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.main_routes = importlib.reload(main_routes)
        self.main_routes.db = self.database

        self.proveedor_id = self.database.add_proveedor(
            {
                "nombre": "Proveedor Test",
                "cuit": "",
                "telefono": "",
                "email": "",
                "dias_credito": 30,
            }
        )
        self.producto_id = self.database.add_producto(
            {
                "descripcion": "Producto Reporte",
                "marca": "",
                "categoria": "General",
                "tipo_unidad": "unidad",
                "stock_actual": 20,
                "stock_minimo": 1,
                "stock_maximo": 50,
                "costo": 80,
                "precio_venta": 150,
                "iva": "21%",
            }
        )

    def _abrir_caja(self, fecha="2026-05-19"):
        return self.database.q(
            "INSERT INTO caja (usuario_id, fecha_apertura, saldo_inicial, saldo_final_real, estado) VALUES (?,?,?,?,1)",
            (1, f"{fecha} 09:00:00", 100, 0),
            fetchall=False,
            commit=True,
        )

    def _crear_venta(self, total, fecha="2026-05-19", medio_pago="Efectivo"):
        venta_id = int(
            self.database.crear_venta(
                [
                    {
                        "producto_id": self.producto_id,
                        "codigo_interno": "REP-001",
                        "descripcion": "Producto Reporte",
                        "categoria": "General",
                        "unidad": "Unidad",
                        "cantidad": 1,
                        "precio_unitario": total,
                        "costo_unitario": 80,
                        "iva": "21%",
                        "descuento": 0,
                        "subtotal": total,
                    }
                ],
                "Consumidor Final",
                medio_pago,
                0,
                "tester",
                cliente_id=0,
                temporada="",
            )
        )
        self.database.q("UPDATE ventas SET fecha=? WHERE id=?", (fecha, venta_id), commit=True)
        self.database.decrementar_stock_venta(venta_id)
        return venta_id

    def test_resumen_gastos_reportes_excluye_anulados(self):
        self.database.add_gasto(
            {
                "fecha": "2026-05-19",
                "categoria": "Servicios",
                "clasificacion": "Operativo",
                "descripcion": "Internet",
                "monto": 100,
                "medio_pago": "Transferencia",
                "necesario": "Necesario",
            }
        )
        gasto_anulado = int(
            self.database.add_gasto(
                {
                    "fecha": "2026-05-19",
                    "categoria": "Snacks",
                    "clasificacion": "Operativo",
                    "descripcion": "Gasto prescindible",
                    "monto": 50,
                    "medio_pago": "Transferencia",
                    "necesario": "Prescindible",
                }
            )
        )
        self.database.anular_gasto(gasto_anulado, motivo="No corresponde", usuario="admin")

        necesarios, prescindibles = self.main_routes._resumen_gastos_reportes(self.database.get_gastos())

        self.assertEqual(necesarios, 100.0)
        self.assertEqual(prescindibles, 0.0)

    def test_rentabilidad_y_dashboard_ignoran_venta_y_gasto_anulados(self):
        venta_activa = self._crear_venta(120)
        venta_anulada = self._crear_venta(80)
        self.database.anular_venta(venta_anulada, motivo="Error de carga", usuario="admin")

        self.database.add_gasto(
            {
                "fecha": "2026-05-19",
                "categoria": "Servicios",
                "clasificacion": "Operativo",
                "descripcion": "Internet",
                "monto": 30,
                "medio_pago": "Transferencia",
            }
        )
        gasto_anulado = int(
            self.database.add_gasto(
                {
                    "fecha": "2026-05-19",
                    "categoria": "Extras",
                    "clasificacion": "Operativo",
                    "descripcion": "Duplicado",
                    "monto": 20,
                    "medio_pago": "Transferencia",
                }
            )
        )
        self.database.anular_gasto(gasto_anulado, motivo="Duplicado", usuario="admin")

        rent = self.database.get_stats_rentabilidad("2026-05")
        dashboard = self.database.get_dashboard_stats()

        self.assertEqual(rent["ingresos"], 120.0)
        self.assertEqual(rent["total_gastos"], 30.0)
        self.assertEqual(dashboard["ventas_hoy"], 1)
        self.assertEqual(dashboard["monto_hoy"], 120.0)

    def test_compra_anulada_no_suma_como_compra_activa(self):
        compra_activa = int(
            self.database.add_compra(
                {
                    "fecha": "2026-05-19",
                    "numero_remito": "REM-001",
                    "proveedor_id": self.proveedor_id,
                    "proveedor_nombre": "Proveedor Test",
                    "producto_id": self.producto_id,
                    "codigo_interno": "REP-001",
                    "descripcion": "Compra activa",
                    "cantidad": 2,
                    "costo_unitario": 90,
                    "total": 180,
                    "observaciones": "",
                }
            )
        )
        compra_anulada = int(
            self.database.add_compra(
                {
                    "fecha": "2026-05-19",
                    "numero_remito": "REM-002",
                    "proveedor_id": self.proveedor_id,
                    "proveedor_nombre": "Proveedor Test",
                    "producto_id": self.producto_id,
                    "codigo_interno": "REP-001",
                    "descripcion": "Compra anulada",
                    "cantidad": 1,
                    "costo_unitario": 70,
                    "total": 70,
                    "observaciones": "",
                }
            )
        )
        self.database.anular_compra(compra_anulada, motivo="Carga duplicada", usuario="admin")

        stats = self.database.get_estadisticas_proveedor(self.proveedor_id)

        self.assertEqual(stats["total_compras"], 1)
        self.assertEqual(stats["monto_total"], 180.0)
        self.assertEqual(compra_activa > 0, True)

    def test_caja_resumen_no_duplica_anulaciones(self):
        caja_id = self._abrir_caja()
        venta_activa = self._crear_venta(100)
        venta_anulada = self._crear_venta(40)
        self.database.anular_venta(venta_anulada, motivo="Error", usuario="admin")

        ingreso_id = int(self.database.registrar_movimiento_caja_abierta("INGRESO", 25, "Aporte inicial"))
        egreso_id = int(self.database.registrar_movimiento_caja_abierta("EGRESO", 10, "Pago menor"))
        anulado_id = int(self.database.registrar_movimiento_caja_abierta("INGRESO", 50, "Ingreso duplicado"))
        self.database.anular_caja_movimiento(anulado_id, "Duplicado", usuario="admin")

        caja_row = self.database.q("SELECT * FROM caja WHERE id=?", (caja_id,), fetchone=True)
        resumen = self.main_routes._caja_resumen(caja_row)

        self.assertEqual(resumen["ventas"], 100.0)
        self.assertEqual(resumen["ingresos"], 25.0)
        self.assertEqual(resumen["egresos"], 10.0)
        self.assertEqual(resumen["total"], 215.0)
        self.assertTrue(venta_activa > 0)
        self.assertTrue(ingreso_id > 0 and egreso_id > 0)


if __name__ == "__main__":
    unittest.main()
