import importlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class LicenseRefreshBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ.pop("NEXAR_TEST_DISABLE_LICENSE_AUTO_REFRESH", None)

    def test_import_app_primero_en_discovery_filtrado_no_inicia_auto_refresh(self):
        self._assert_create_app_no_inicia_auto_refresh()

    def test_create_app_bajo_pytest_no_inicia_auto_refresh_aunque_argv0_sea_main_py(self):
        with mock.patch.object(sys, "argv", ["__main__.py", "tests/test_license_refresh_bootstrap.py"]):
            with mock.patch.dict(sys.modules, {"pytest": object()}):
                self._assert_create_app_no_inicia_auto_refresh()

    def _assert_create_app_no_inicia_auto_refresh(self):
        import database

        database = importlib.reload(database)
        database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        database._db_initialized = False
        database.init_db()

        import app as app_module

        app_module = importlib.reload(app_module)
        app_module.db = database
        app = app_module.create_app()

        self.assertTrue(app.config["TESTING"])
        self.assertEqual(app.extensions.get("license_auto_refresh_disabled"), "testing")
        self.assertNotIn("license_auto_refresh_thread", app.extensions)
        self.assertFalse(any(thread.name == "license-auto-refresh" for thread in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
