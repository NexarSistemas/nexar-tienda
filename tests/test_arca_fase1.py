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
        "NEXAR_LICENSE_MODE",
        "NEXAR_PLAN",
        "NEXAR_MODULES",
        "NEXAR_EXTRA_MODULES",
        "SECRET_KEY",
        "FLASK_ENV",
    ):
        os.environ.pop(key, None)


class ArcaFase1Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()

        import database
        from licensing import permisos
        from modules.arca.services import arca_client, certificados_service, config_service

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.config_service = importlib.reload(config_service)
        self.config_service.db = self.database
        self.certificados_service = importlib.reload(certificados_service)
        self.certificados_service.db = self.database
        self.arca_client = importlib.reload(arca_client)
        self.permisos = importlib.reload(permisos)

        self.cert_path_a = Path(self.temp_dir.name) / "homologacion.crt"
        self.key_path_a = Path(self.temp_dir.name) / "homologacion.key"
        self.cert_path_b = Path(self.temp_dir.name) / "produccion.crt"
        self.key_path_b = Path(self.temp_dir.name) / "produccion.key"
        self.cert_path_a.write_text("cert-a", encoding="utf-8")
        self.key_path_a.write_text("key-a", encoding="utf-8")
        self.cert_path_b.write_text("cert-b", encoding="utf-8")
        self.key_path_b.write_text("key-b", encoding="utf-8")
        self.repo_cert_dir = PROJECT_ROOT / "data" / "arca" / "certificados"
        self.repo_key_dir = PROJECT_ROOT / "data" / "arca" / "keys"
        self.repo_cert_dir.mkdir(parents=True, exist_ok=True)
        self.repo_key_dir.mkdir(parents=True, exist_ok=True)
        self.repo_cert_path = self.repo_cert_dir / "test-rel-cert.crt"
        self.repo_key_path = self.repo_key_dir / "test-rel-key.key"
        self.repo_cert_path.write_text("repo-cert", encoding="utf-8")
        self.repo_key_path.write_text("repo-key", encoding="utf-8")
        self.addCleanup(lambda: self.repo_cert_path.unlink(missing_ok=True))
        self.addCleanup(lambda: self.repo_key_path.unlink(missing_ok=True))

    def tearDown(self):
        _reset_env()

    def test_migraciones_arca_agregan_columnas_y_directorios(self):
        conn = self.database.get_conn()
        try:
            config_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(arca_configuracion)").fetchall()
            }
            cert_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(arca_certificados)").fetchall()
            }
        finally:
            conn.close()

        self.assertTrue(
            {
                "nombre_fantasia",
                "domicilio_fiscal",
                "ingresos_brutos",
                "telefono_fiscal",
                "updated_by",
                "email_fiscal",
                "inicio_actividades",
            }.issubset(config_columns)
        )
        self.assertTrue({"cuit", "observaciones", "vencimiento", "estado"}.issubset(cert_columns))
        self.assertTrue((Path(self.database.DB_PATH).parent / "arca" / "certificados").is_dir())
        self.assertTrue((Path(self.database.DB_PATH).parent / "arca" / "keys").is_dir())

    def test_certificados_aceptan_rutas_relativas_al_repo(self):
        certificado = self.certificados_service.registrar_certificado(
            {
                "nombre": "Cert relativo",
                "ambiente": "homologacion",
                "cuit": "20123456786",
                "certificado_path": "data/arca/certificados/test-rel-cert.crt",
                "key_path": "data/arca/keys/test-rel-key.key",
                "vencimiento": "2030-12-31",
                "observaciones": "Demo relativa",
            }
        )

        self.assertEqual(certificado["estado"], "pendiente")
        self.assertEqual(certificado["vencimiento"], "2030-12-31")
        self.assertTrue(certificado["certificado_existe"])
        self.assertTrue(certificado["key_existe"])
        self.assertEqual(certificado["certificado_path"], str(self.repo_cert_path.resolve()))
        self.assertEqual(certificado["key_path"], str(self.repo_key_path.resolve()))

    def test_configuracion_valida_normaliza_cuit_y_guarda(self):
        config = self.config_service.guardar_configuracion(
            {
                "cuit": "20-12345678-6",
                "razon_social": "Nexar Demo SA",
                "nombre_fantasia": "Nexar Demo",
                "condicion_fiscal": "responsable_inscripto",
                "punto_venta": "5",
                "ambiente": "homologacion",
                "domicilio_fiscal": "Calle Falsa 123",
                "activo": "1",
                "inicio_actividades": "2024-01-10",
                "ingresos_brutos": "901-123456-7",
                "email_fiscal": "Fiscal@Nexar.test",
                "telefono_fiscal": "+54 264 5551234",
                "updated_by": "admin_test",
            }
        )

        self.assertEqual(config["cuit"], "20123456786")
        self.assertEqual(config["punto_venta"], 5)
        self.assertEqual(config["email_fiscal"], "fiscal@nexar.test")
        self.assertEqual(config["nombre_fantasia"], "Nexar Demo")
        self.assertEqual(config["updated_by"], "admin_test")
        self.assertTrue(self.config_service.arca_esta_configurado())

    def test_configuracion_invalida_por_ambiente(self):
        with self.assertRaisesRegex(ValueError, "ambiente debe ser homologacion o produccion"):
            self.config_service.guardar_configuracion(
                {
                    "cuit": "20123456786",
                    "razon_social": "Nexar Demo SA",
                    "nombre_fantasia": "Nexar Demo",
                    "condicion_fiscal": "responsable_inscripto",
                    "punto_venta": "5",
                    "ambiente": "sandbox",
                    "domicilio_fiscal": "Calle Falsa 123",
                    "activo": "1",
                    "inicio_actividades": "2024-01-10",
                    "ingresos_brutos": "901-123456-7",
                    "email_fiscal": "fiscal@nexar.test",
                    "telefono_fiscal": "+54 264 5551234",
                }
            )

    def test_configuracion_invalida_por_punto_venta(self):
        with self.assertRaisesRegex(ValueError, "punto de venta debe ser mayor a cero"):
            self.config_service.guardar_configuracion(
                {
                    "cuit": "20123456786",
                    "razon_social": "Nexar Demo SA",
                    "nombre_fantasia": "Nexar Demo",
                    "condicion_fiscal": "responsable_inscripto",
                    "punto_venta": "0",
                    "ambiente": "homologacion",
                    "domicilio_fiscal": "Calle Falsa 123",
                    "activo": "1",
                    "inicio_actividades": "2024-01-10",
                    "ingresos_brutos": "901-123456-7",
                    "email_fiscal": "fiscal@nexar.test",
                    "telefono_fiscal": "+54 264 5551234",
                }
            )

    def test_modulo_arca_activo_e_inactivo_por_env(self):
        os.environ["NEXAR_LICENSE_MODE"] = "prod"
        os.environ["NEXAR_EXTRA_MODULES"] = "arca_facturacion"
        permisos = importlib.reload(self.permisos)
        self.assertTrue(permisos.modulo_activo("arca_facturacion"))

        os.environ.pop("NEXAR_EXTRA_MODULES", None)
        permisos = importlib.reload(permisos)
        self.assertFalse(permisos.modulo_activo("arca_facturacion"))

    def test_certificados_rechazan_rutas_invalidas(self):
        with self.assertRaisesRegex(ValueError, "ruta de certificado no existe"):
            self.certificados_service.registrar_certificado(
                {
                    "nombre": "Cert inválido",
                    "ambiente": "homologacion",
                    "certificado_path": str(Path(self.temp_dir.name) / "missing.crt"),
                    "key_path": str(self.key_path_a),
                }
            )

    def test_activar_certificado_desactiva_otro_del_mismo_ambiente(self):
        cert_1 = self.certificados_service.registrar_certificado(
            {
                "nombre": "Homologación A",
                "ambiente": "homologacion",
                "certificado_path": str(self.cert_path_a),
                "key_path": str(self.key_path_a),
                "cuit": "20-12345678-6",
                "vencimiento": "2031-01-10",
                "observaciones": "Principal",
            }
        )
        cert_2 = self.certificados_service.registrar_certificado(
            {
                "nombre": "Homologación B",
                "ambiente": "homologacion",
                "certificado_path": str(self.cert_path_b),
                "key_path": str(self.key_path_b),
                "cuit": "20123456786",
                "vencimiento": "2031-06-10",
                "observaciones": "Backup",
            }
        )

        self.certificados_service.activar_certificado(cert_1["id"])
        activo_1 = self.certificados_service.obtener_certificado_activo("homologacion")
        self.assertEqual(activo_1["id"], cert_1["id"])

        self.certificados_service.activar_certificado(cert_2["id"])
        activo_2 = self.certificados_service.obtener_certificado_activo("homologacion")
        self.assertEqual(activo_2["id"], cert_2["id"])

        certificados = {
            row["id"]: row for row in self.certificados_service.listar_certificados()
        }
        self.assertEqual(certificados[cert_1["id"]]["activo"], 0)
        self.assertEqual(certificados[cert_2["id"]]["activo"], 1)
        self.assertEqual(certificados[cert_1["id"]]["estado"], "pendiente")
        self.assertEqual(certificados[cert_2["id"]]["estado"], "activo")

    def test_cliente_placeholder_siempre_devuelve_ok_false(self):
        resultado_conexion = self.arca_client.probar_conexion()
        resultado_ultimo = self.arca_client.obtener_ultimo_comprobante()
        resultado_emitir = self.arca_client.emitir_comprobante({"venta_id": 10})

        self.assertFalse(resultado_conexion["ok"])
        self.assertFalse(resultado_ultimo["ok"])
        self.assertFalse(resultado_emitir["ok"])
        self.assertEqual(resultado_conexion["modo"], "placeholder")
        self.assertEqual(resultado_emitir["operacion"], "emitir_comprobante")

        eventos = self.database.q(
            "SELECT mensaje, detalle_json FROM arca_eventos ORDER BY id DESC LIMIT 1"
        )
        self.assertTrue(eventos)
        self.assertIn("Intento placeholder de conexión ARCA", eventos[0]["mensaje"])

    def test_eventos_arca_registran_acciones_sin_secretos(self):
        self.config_service.guardar_configuracion(
            {
                "cuit": "20123456786",
                "razon_social": "Nexar Demo SA",
                "nombre_fantasia": "Nexar Demo",
                "condicion_fiscal": "responsable_inscripto",
                "punto_venta": "8",
                "ambiente": "homologacion",
                "domicilio_fiscal": "Calle Falsa 123",
                "activo": "1",
                "inicio_actividades": "2024-01-10",
                "ingresos_brutos": "901-123456-7",
                "email_fiscal": "fiscal@nexar.test",
                "telefono_fiscal": "+54 264 5551234",
                "updated_by": "admin_test",
            }
        )
        certificado = self.certificados_service.registrar_certificado(
            {
                "nombre": "Homologación A",
                "ambiente": "homologacion",
                "certificado_path": str(self.cert_path_a),
                "key_path": str(self.key_path_a),
                "vencimiento": "2030-12-31",
                "observaciones": "Solo metadatos",
            }
        )
        self.certificados_service.activar_certificado(certificado["id"])

        eventos = self.database.q(
            "SELECT mensaje, detalle_json FROM arca_eventos ORDER BY id ASC"
        )
        mensajes = [row["mensaje"] for row in eventos]
        detalles = " ".join(row["detalle_json"] or "" for row in eventos)

        self.assertIn("Configuración ARCA guardada", mensajes)
        self.assertIn("Certificado ARCA registrado", mensajes)
        self.assertIn("Certificado ARCA activado", mensajes)
        self.assertNotIn("key-a", detalles)


if __name__ == "__main__":
    unittest.main()
