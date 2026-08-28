import importlib
import os
import tempfile
import unittest
from pathlib import Path


HEADER = "Identificador de URL,Nombre,Categorías,Nombre de propiedad 1,Valor de propiedad 1,Precio,Costo,Stock,SKU,Código de barras,Mostrar en tienda\n"


class CompatibilidadTiendanubeArcaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"

        import database
        import modules.arca.services.arca_client as arca_client
        from modules.arca.services import comprobantes_service, facturacion_desde_venta_service
        from services import catalog_csv_import

        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "compatibilidad.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.catalog = importlib.reload(catalog_csv_import)
        self.arca_client = importlib.reload(arca_client)
        comprobantes = importlib.reload(comprobantes_service)
        comprobantes.db = self.db
        self.facturacion = importlib.reload(facturacion_desde_venta_service)
        self.facturacion.db = self.db
        self.facturacion.arca_client = self.arca_client
        self.db.add_usuario("importador", "1234", "Administrador", "Importador", security_question="color", security_answer="azul")
        self.owner = int(self.db.get_usuario_by_username("importador")["id"])
        self.db.q(
            "INSERT INTO arca_configuracion (id,cuit,razon_social,condicion_fiscal,punto_venta,ambiente,activo) VALUES (1,?,?,?,?,?,1)",
            ("20304050607", "Comercio Demo SA", "responsable_inscripto", 3, "homologacion"),
            commit=True,
        )

    def tearDown(self):
        os.environ.pop("SECRET_KEY", None)

    def _importar(self, content):
        plan = self.catalog.build_plan(self.catalog.parse_tiendanube_csv(content.encode()))
        self.assertFalse(plan["errors"], plan["errors"])
        plan_id, token = self.catalog.store_plan(plan, self.owner)
        self.catalog.apply_stored_plan(plan_id, token, self.owner)

    def _vender_y_obtener_payload(self, producto_id, variante_id=None, *, descuento=0, interes=0, iva_catalogo_despues=None):
        producto = self.db.get_producto(producto_id)
        item = self.db.get_sellable_item_pos(producto_id, variante_id)
        venta_id = self.db.crear_venta(
            [{
                "producto_id": producto_id,
                "variante_id": variante_id,
                "codigo_interno": item["codigo_interno"],
                "descripcion": item["descripcion"],
                "categoria": producto["categoria"],
                "unidad": producto["unidad"],
                "cantidad": 1,
                "precio_unitario": item["precio_venta"],
                "costo_unitario": item["costo"],
                "iva": producto["iva"],
                "descuento": 0,
                "subtotal": item["precio_venta"],
            }],
            "Mostrador", "Efectivo", descuento, "admin", interes_financiacion=interes,
        )
        if iva_catalogo_despues:
            self.db.q("UPDATE productos SET iva=? WHERE id=?", (iva_catalogo_despues, producto_id), commit=True)
        payloads = []

        def emitir(payload):
            payloads.append(payload)
            return {
                "ok": True, "modo": "simulacion", "estado": "MODO_TEST",
                "tipo_comprobante": "Factura B", "punto_venta": 3,
                "numero_comprobante": 1, "cae": "12345678901234",
                "cae_vencimiento": "2026-08-30", "importe_total": payload["totales"]["importe_total"],
                "fecha_emision": payload["fecha_emision"], "ambiente": "simulacion",
            }

        original = self.arca_client.emitir_factura
        self.addCleanup(setattr, self.arca_client, "emitir_factura", original)
        self.arca_client.emitir_factura = emitir
        return venta_id, self.facturacion.facturar_venta_desde_existente(venta_id), payloads

    def test_venta_normal_21_conserva_totales_coherentes(self):
        self._importar(HEADER + "mate,Mate,Accesorios,,,121,60,2,,7790000100001,SI\n")
        producto = self.db.q("SELECT * FROM productos WHERE codigo_barras=?", ("7790000100001",), fetchone=True)

        _, resultado, payloads = self._vender_y_obtener_payload(int(producto["id"]))

        self.assertTrue(resultado["ok"])
        self.assertEqual(len(payloads), 1)
        wsfe = payloads[0]["wsfe"]
        self.assertEqual((wsfe["ImpTotal"], wsfe["ImpNeto"], wsfe["ImpIVA"]), (121.0, 100.0, 21.0))

    def test_venta_con_otra_alicuota_admitida_usa_el_snapshot(self):
        self.db.set_config({"iva_predeterminado_importacion": "10.5%"})
        self._importar(HEADER + "leche,Leche,Alimentos,,,110.5,50,2,,7790000100002,SI\n")
        producto = self.db.q("SELECT * FROM productos WHERE codigo_barras=?", ("7790000100002",), fetchone=True)
        _, resultado, payloads = self._vender_y_obtener_payload(
            int(producto["id"]), iva_catalogo_despues="21%"
        )

        self.assertTrue(resultado["ok"])
        self.assertEqual(payloads[0]["items"][0]["iva"], "10.5%")
        self.assertEqual(payloads[0]["wsfe"]["Iva"], [{"Id": 4, "BaseImp": 100.0, "Importe": 10.5, "Alic": 10.5}])

    def test_variante_importada_se_vende_y_arca_usa_snapshot(self):
        self.db.set_config({"iva_predeterminado_importacion": "10.5%"})
        self._importar(HEADER + "remera,Remera,Ropa,Color,Azul,110.5,40,2,REM-AZU,,SI\n")
        variante = self.db.q("SELECT * FROM producto_variantes WHERE sku='REM-AZU'", fetchone=True)
        producto_id = int(variante["producto_id"])
        _, resultado, payloads = self._vender_y_obtener_payload(
            producto_id, int(variante["id"]), iva_catalogo_despues="21%"
        )

        self.assertTrue(resultado["ok"])
        self.assertEqual(payloads[0]["items"][0]["iva"], "10.5%")
        self.assertEqual(payloads[0]["items"][0]["producto_id"], producto_id)

    def test_descuento_adicional_bloquea_emision_sin_llamar_arca(self):
        self._importar(HEADER + "mate,Mate,Accesorios,,,121,60,2,,7790000100003,SI\n")
        producto = self.db.q("SELECT id FROM productos WHERE codigo_barras=?", ("7790000100003",), fetchone=True)

        _, resultado, payloads = self._vender_y_obtener_payload(int(producto["id"]), descuento=10)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "ajustes_fiscales_no_soportados")
        self.assertEqual(payloads, [])

    def test_interes_financiacion_bloquea_emision_sin_llamar_arca(self):
        self._importar(HEADER + "mate,Mate,Accesorios,,,121,60,2,,7790000100004,SI\n")
        producto = self.db.q("SELECT id FROM productos WHERE codigo_barras=?", ("7790000100004",), fetchone=True)

        _, resultado, payloads = self._vender_y_obtener_payload(int(producto["id"]), interes=10)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "ajustes_fiscales_no_soportados")
        self.assertEqual(payloads, [])


if __name__ == "__main__":
    unittest.main()
