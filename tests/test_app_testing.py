import importlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class AppTestingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ.pop("NEXAR_TEST_DISABLE_LICENSE_AUTO_REFRESH", None)

    def test_detector_reconoce_unittest(self):
        import app as app_module

        with mock.patch.object(sys, "argv", ["python.exe -m unittest", "discover"]):
            self.assertTrue(app_module._is_test_process())

    def test_detector_reconoce_pytest_aunque_argv0_sea_main_py(self):
        import app as app_module

        with mock.patch.object(sys, "argv", ["__main__.py", "tests/test_app_testing.py"]):
            with mock.patch.dict(sys.modules, {"pytest": object()}):
                self.assertTrue(app_module._is_test_process())

    def test_detector_no_marca_testing_en_proceso_normal(self):
        import app as app_module

        pytest_module = sys.modules.pop("pytest", None)
        try:
            with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}):
                with mock.patch.object(sys, "argv", ["python.exe", "app.py"]):
                    self.assertFalse(app_module._is_test_process())
        finally:
            if pytest_module is not None:
                sys.modules["pytest"] = pytest_module

    def test_create_app_en_tests_no_inicia_auto_refresh_de_licencia(self):
        import database

        database = importlib.reload(database)
        database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        database._db_initialized = False
        database.init_db()

        import app as app_module

        app_module = importlib.reload(app_module)
        app_module.db = database
        app = app_module.create_app()

        self.assertEqual(app.extensions.get("license_auto_refresh_disabled"), "testing")
        self.assertNotIn("license_auto_refresh_thread", app.extensions)
        self.assertFalse(any(thread.name == "license-auto-refresh" for thread in threading.enumerate()))

    def test_auto_refresh_arranca_fuera_de_testing_y_sin_senal_de_tests(self):
        from routes import main as routes_main

        app = Flask(__name__)
        started = []

        class FakeThread:
            def __init__(self, target, args, daemon, name):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.name = name

            def is_alive(self):
                return True

            def start(self):
                started.append(self.name)

        with mock.patch.object(routes_main.threading, "Thread", FakeThread):
            routes_main.ensure_license_auto_refresh_thread(app)

        self.assertEqual(started, ["license-auto-refresh"])
        self.assertEqual(app.extensions["license_auto_refresh_thread"].name, "license-auto-refresh")
        self.assertNotIn("license_auto_refresh_disabled", app.extensions)


if __name__ == "__main__":
    unittest.main()
