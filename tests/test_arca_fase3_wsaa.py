import importlib
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


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


class ArcaFase3WsaaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()

        import database
        from modules.arca.services import certificados_service
        from services import arca_config_service
        import services.arca.auth_service as auth_service
        import services.arca.certificate_diagnostics as certificate_diagnostics
        import services.arca.ticket_storage as ticket_storage

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.config_service = importlib.reload(arca_config_service)
        self.config_service.db = self.database
        self.certificados_service = importlib.reload(certificados_service)
        self.certificados_service.db = self.database
        self.certificate_diagnostics = importlib.reload(certificate_diagnostics)
        self.ticket_storage = importlib.reload(ticket_storage)
        self.auth_service = importlib.reload(auth_service)

        self.cert_path = Path(self.temp_dir.name) / "homologacion.crt"
        self.key_path = Path(self.temp_dir.name) / "homologacion.key"
        self._create_certificate_pair(self.cert_path, self.key_path)

    def tearDown(self):
        _reset_env()

    def _create_certificate_pair(
        self,
        cert_path: Path,
        key_path: Path,
        *,
        encrypted_key: bool = False,
        key_password: bytes = b"secret123",
    ) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nexar Tests"),
                x509.NameAttribute(NameOID.COMMON_NAME, "arca-demo"),
            ]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=365))
            .sign(private_key, hashes.SHA256())
        )
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        encryption = (
            serialization.BestAvailableEncryption(key_password)
            if encrypted_key
            else serialization.NoEncryption()
        )
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=encryption,
            )
        )

    def test_build_tra_xml_genera_campos_requeridos(self):
        base_time = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)
        tra = self.auth_service.build_tra_xml(now=base_time)

        self.assertIn("<service>wsfe</service>", tra["xml"])
        self.assertIn("<uniqueId>", tra["xml"])
        self.assertIn("<generationTime>2026-05-23T11:50:00Z</generationTime>", tra["xml"])
        self.assertIn("<expirationTime>2026-05-24T00:00:00Z</expirationTime>", tra["xml"])
        self.assertEqual(tra["service"], "wsfe")
        self.assertEqual(tra["unique_id"], int(base_time.timestamp()))

    def test_ticket_storage_detecta_ticket_vigente_y_vencido(self):
        vigente = self.ticket_storage.save_ticket(
            ambiente="homologacion",
            service="wsfe",
            token="token-demo",
            sign="sign-demo",
            generation_time=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            expiration_time=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        )
        vencido = self.ticket_storage.save_ticket(
            ambiente="produccion",
            service="wsfe",
            token="token-vencido",
            sign="sign-vencido",
            generation_time=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            expiration_time=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        )

        self.assertTrue(self.ticket_storage.is_ticket_valid(vigente))
        self.assertFalse(self.ticket_storage.is_ticket_valid(vencido))

    def test_get_valid_ticket_falla_con_configuracion_incompleta(self):
        self.config_service.save_config(
            {
                "cuit": "20-12345678-6",
                "razon_social": "Nexar Demo SA",
                "condicion_fiscal": "responsable_inscripto",
                "punto_venta": "5",
                "ambiente": "homologacion",
                "activo": "1",
            }
        )

        with self.assertRaises(self.auth_service.ArcaConfigError) as ctx:
            self.auth_service.get_valid_ticket()

        self.assertIn("Falta certificado", str(ctx.exception))

    def test_diagnostico_detecta_certificado_y_key_validos(self):
        diagnostico = self.certificate_diagnostics.diagnose_certificate_pair(
            self.cert_path,
            self.key_path,
        )

        self.assertTrue(diagnostico["certificate_exists"])
        self.assertTrue(diagnostico["certificate_valid"])
        self.assertEqual(diagnostico["certificate_format"], "PEM")
        self.assertTrue(diagnostico["key_exists"])
        self.assertTrue(diagnostico["key_valid"])
        self.assertEqual(diagnostico["key_format"], "PEM")
        self.assertTrue(diagnostico["pair_match"])
        self.assertTrue(diagnostico["certificate_not_valid_after"])

    def test_diagnostico_detecta_key_con_password(self):
        encrypted_key_path = Path(self.temp_dir.name) / "encrypted.key"
        encrypted_cert_path = Path(self.temp_dir.name) / "encrypted.crt"
        self._create_certificate_pair(
            encrypted_cert_path,
            encrypted_key_path,
            encrypted_key=True,
        )

        diagnostico = self.certificate_diagnostics.diagnose_certificate_pair(
            encrypted_cert_path,
            encrypted_key_path,
        )

        self.assertTrue(diagnostico["certificate_valid"])
        self.assertFalse(diagnostico["key_valid"])
        self.assertTrue(diagnostico["key_requires_password"])
        self.assertIn("requiere contraseña", diagnostico["key_error"])

    def test_diagnostico_detecta_par_no_coincidente(self):
        mismatch_key_path = Path(self.temp_dir.name) / "mismatch.key"
        mismatch_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        mismatch_key_path.write_bytes(
            mismatch_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

        diagnostico = self.certificate_diagnostics.diagnose_certificate_pair(
            self.cert_path,
            mismatch_key_path,
        )

        self.assertTrue(diagnostico["certificate_valid"])
        self.assertTrue(diagnostico["key_valid"])
        self.assertFalse(diagnostico["pair_match"])
        self.assertEqual(
            diagnostico["pair_error"],
            "El certificado y la clave privada no corresponden entre sí.",
        )

    def test_get_auth_context_reporta_key_con_password(self):
        encrypted_key_path = Path(self.temp_dir.name) / "auth-encrypted.key"
        encrypted_cert_path = Path(self.temp_dir.name) / "auth-encrypted.crt"
        self._create_certificate_pair(
            encrypted_cert_path,
            encrypted_key_path,
            encrypted_key=True,
        )
        self.config_service.save_config(
            {
                "cuit": "20-12345678-6",
                "razon_social": "Nexar Demo SA",
                "condicion_fiscal": "responsable_inscripto",
                "punto_venta": "5",
                "ambiente": "homologacion",
                "certificado_path": str(encrypted_cert_path),
                "key_path": str(encrypted_key_path),
                "activo": "1",
            }
        )

        with self.assertRaises(self.auth_service.ArcaConfigError) as ctx:
            self.auth_service.get_auth_context()

        self.assertIn("requiere contraseña", str(ctx.exception))

    def test_certificados_service_expone_diagnostico(self):
        certificado = self.certificados_service.registrar_certificado(
            {
                "nombre": "Diagnóstico",
                "ambiente": "homologacion",
                "cuit": "20123456786",
                "certificado_path": str(self.cert_path),
                "key_path": str(self.key_path),
                "vencimiento": "2030-12-31",
                "observaciones": "",
            }
        )

        self.assertTrue(certificado["certificado_valido"])
        self.assertTrue(certificado["key_valida"])
        self.assertTrue(certificado["par_coincide"])
