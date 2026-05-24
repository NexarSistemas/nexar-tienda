import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_env():
    for key in (
        "NEXAR_LICENSE_MODE",
        "NEXAR_PLAN",
        "NEXAR_MODULES",
        "NEXAR_EXTRA_MODULES",
        "SECRET_KEY",
        "FLASK_ENV",
    ):
        os.environ.pop(key, None)


class ArcaFase4WsfeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()

        import database
        from modules.arca.services import certificados_service
        from services import arca_config_service
        import services.arca.wsfe_client as wsfe_client
        import services.arca.wsfe_service as wsfe_service

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.config_service = importlib.reload(arca_config_service)
        self.config_service.db = self.database
        self.certificados_service = importlib.reload(certificados_service)
        self.certificados_service.db = self.database
        self.wsfe_client = importlib.reload(wsfe_client)
        self.wsfe_service = importlib.reload(wsfe_service)
        self.wsfe_service.db = self.database

    def tearDown(self):
        _reset_env()

    def _save_valid_config(self) -> None:
        self.config_service.save_config(
            {
                "cuit": "20-12345678-6",
                "razon_social": "Nexar Demo SA",
                "condicion_fiscal": "responsable_inscripto",
                "punto_venta": "1",
                "ambiente": "homologacion",
                "activo": "1",
            }
        )

    def test_build_feauth_request_arma_campos_requeridos(self):
        auth = self.wsfe_client.build_feauth_request(
            token="token-demo",
            sign="sign-demo",
            cuit="20123456786",
        )

        self.assertEqual(auth["Token"], "token-demo")
        self.assertEqual(auth["Sign"], "sign-demo")
        self.assertEqual(auth["Cuit"], 20123456786)

    def test_soap_envelope_namespacia_auth_y_campos_wsfe(self):
        xml = self.wsfe_client._soap_envelope(
            "FEParamGetTiposCbte",
            {
                "Auth": {
                    "Token": "token-demo",
                    "Sign": "sign-demo",
                    "Cuit": 20123456786,
                }
            },
        ).decode()

        self.assertIn("<ar:FEParamGetTiposCbte>", xml)
        self.assertIn("<ar:Auth>", xml)
        self.assertIn("<ar:Token>token-demo</ar:Token>", xml)
        self.assertIn("<ar:Sign>sign-demo</ar:Sign>", xml)
        self.assertIn("<ar:Cuit>20123456786</ar:Cuit>", xml)
        self.assertNotIn("<Auth>", xml)

    def test_probar_wsfe_falla_sin_configuracion(self):
        resultado = self.wsfe_service.probar_wsfe()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "cuit_invalido")
        self.assertIn("CUIT inválido", resultado["mensaje"])

    def test_probar_wsfe_reutiliza_ticket_vigente(self):
        self._save_valid_config()

        self.wsfe_service.get_valid_ticket = lambda: {
            "token": "token-demo",
            "sign": "sign-demo",
            "reused": True,
        }
        self.wsfe_service.fedummy = lambda: {
            "appserver": "OK",
            "dbserver": "OK",
            "authserver": "OK",
        }
        self.wsfe_service.fe_param_get_tipos_cbte = lambda auth: {
            "items": [{"Id": "6", "Desc": "Factura B"}]
        }
        self.wsfe_service.fe_param_get_tipos_doc = lambda auth: {
            "items": [{"Id": "80", "Desc": "CUIT"}]
        }
        self.wsfe_service.fe_param_get_ptos_venta = lambda auth: {
            "items": [{"Nro": "1", "EmisionTipo": "CAE", "Bloqueado": "N"}]
        }
        self.wsfe_service.fe_comp_ultimo_autorizado = lambda auth, pto_vta, cbte_tipo: {
            "numero": 123,
            "punto_venta": pto_vta,
            "tipo_comprobante": cbte_tipo,
        }

        resultado = self.wsfe_service.probar_wsfe()

        self.assertTrue(resultado["ok"])
        self.assertTrue(resultado["ticket_reutilizado"])
        self.assertEqual(resultado["ultimo_comprobante"]["numero"], 123)

    def test_probar_wsfe_falla_si_ticket_no_es_wsfe(self):
        self._save_valid_config()
        self.wsfe_service.get_valid_ticket = lambda: {
            "token": "token-demo",
            "sign": "sign-demo",
            "service": "ws_sr_padron_a4",
            "reused": True,
        }

        resultado = self.wsfe_service.probar_wsfe()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error_code"], "sin_configuracion")
        self.assertIn("no corresponde al servicio wsfe", resultado["mensaje"].lower())

    def test_parsea_ultimo_comprobante(self):
        result_node = ET.fromstring(
            """
            <FECompUltimoAutorizadoResult>
                <CbteNro>456</CbteNro>
                <PtoVta>1</PtoVta>
                <CbteTipo>6</CbteTipo>
            </FECompUltimoAutorizadoResult>
            """
        )

        resultado = self.wsfe_client._parse_ultimo_resultado(result_node)

        self.assertEqual(resultado["numero"], 456)
        self.assertEqual(resultado["punto_venta"], 1)
        self.assertEqual(resultado["tipo_comprobante"], 6)

    def test_extrae_fault_soap_aun_con_http_500(self):
        response = type(
            "Response",
            (),
            {
                "status_code": 500,
                "text": """
                <soap:Envelope xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
                    <soap:Body>
                        <soap:Fault>
                            <faultcode>soap:Server</faultcode>
                            <faultstring>Campo Auth no fue ingresado o esta mal formado.</faultstring>
                        </soap:Fault>
                    </soap:Body>
                </soap:Envelope>
                """,
            },
        )()

        original_post = self.wsfe_client.requests.post
        self.addCleanup(setattr, self.wsfe_client.requests, "post", original_post)
        self.wsfe_client.requests.post = lambda *args, **kwargs: response

        with self.assertRaises(self.wsfe_client.WsfeClientError) as ctx:
            self.wsfe_client.fe_param_get_tipos_cbte(
                {"Token": "token-demo", "Sign": "sign-demo", "Cuit": 20123456786}
            )

        self.assertIn("campo auth", str(ctx.exception).lower())
