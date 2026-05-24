import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_module_env():
    for key in ("NEXAR_LICENSE_MODE", "NEXAR_PLAN", "NEXAR_MODULES", "NEXAR_EXTRA_MODULES", "SECRET_KEY", "FLASK_ENV"):
        os.environ.pop(key, None)


class ArcaBaseTests(unittest.TestCase):
    def tearDown(self):
        _reset_module_env()

    def test_get_modulos_extra_reconoce_nexar_extra_modules(self):
        from licensing import planes

        os.environ["NEXAR_EXTRA_MODULES"] = " arca_facturacion , otro_modulo "
        planes = importlib.reload(planes)

        self.assertEqual(planes.get_modulos_extra(), {"arca_facturacion", "otro_modulo"})

    def test_get_modulos_extra_mantiene_compatibilidad_con_nexar_modules(self):
        from licensing import planes

        os.environ["NEXAR_MODULES"] = " reportes , arca_facturacion "
        planes = importlib.reload(planes)

        self.assertEqual(planes.get_modulos_extra(), {"reportes", "arca_facturacion"})

    def test_modulo_activo_arca_facturacion_funciona_con_extra_modules(self):
        import licensing.permisos as permisos

        os.environ["NEXAR_EXTRA_MODULES"] = "arca_facturacion"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"
        permisos = importlib.reload(permisos)

        self.assertTrue(permisos.modulo_activo("arca_facturacion"))

    def test_tablas_arca_se_crean_sin_romper_init_db(self):
        import database

        original_db_path = database.DB_PATH
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        try:
            database = importlib.reload(database)
            database.DB_PATH = str(Path(temp_dir.name) / "test_tienda.db")
            database._db_initialized = False
            database.init_db()

            conn = database.get_conn()
            try:
                tablas = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'arca_%'"
                    ).fetchall()
                }
            finally:
                conn.close()

            self.assertTrue(
                {
                    "arca_configuracion",
                    "arca_certificados",
                    "arca_comprobantes",
                    "arca_eventos",
                    "arca_wsaa_tickets",
                }.issubset(tablas)
            )
        finally:
            database.DB_PATH = original_db_path

    def test_create_app_registra_blueprint_arca_si_modulo_esta_activo(self):
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        os.environ["NEXAR_EXTRA_MODULES"] = "arca_facturacion"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"

        import app as app_module
        import database

        original_db_path = database.DB_PATH
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        try:
            database = importlib.reload(database)
            database.DB_PATH = str(Path(temp_dir.name) / "test_tienda.db")
            database._db_initialized = False
            database.init_db()

            app_module = importlib.reload(app_module)
            app = app_module.create_app()

            self.assertIn("arca", app.blueprints)
        finally:
            database.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
