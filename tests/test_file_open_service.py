import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FileOpenServiceTests(unittest.TestCase):
    def test_url_http_en_linux_usa_xdg_open(self):
        from services.file_open_service import open_external_target

        with patch("services.file_open_service.platform.system", return_value="Linux"):
            with patch("services.file_open_service.subprocess.Popen") as popen_mock:
                resultado = open_external_target("http://127.0.0.1:5000/ticket/1")

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["method"], "xdg-open")
        popen_mock.assert_called_once_with(["xdg-open", "http://127.0.0.1:5000/ticket/1"])

    def test_archivo_inexistente_devuelve_error_controlado(self):
        from services.file_open_service import open_file_cross_platform

        missing_path = Path("/tmp/archivo-que-no-existe-nexar.txt")

        with patch("services.file_open_service.subprocess.Popen") as popen_mock:
            resultado = open_file_cross_platform(missing_path)

        self.assertFalse(resultado["ok"])
        self.assertIn("No se encontró", resultado["message"])
        popen_mock.assert_not_called()

    def test_archivo_existente_en_linux_usa_xdg_open(self):
        from services.file_open_service import open_file_cross_platform

        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "ticket.txt"
            test_file.write_text("ticket demo", encoding="utf-8")

            with patch("services.file_open_service.platform.system", return_value="Linux"):
                with patch("services.file_open_service.subprocess.Popen") as popen_mock:
                    resultado = open_file_cross_platform(test_file)

        self.assertTrue(resultado["ok"])
        popen_mock.assert_called_once_with(["xdg-open", str(test_file.resolve())])

    def test_linux_si_falla_xdg_open_devuelve_ruta_manual(self):
        from services.file_open_service import open_file_cross_platform

        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "ticket.txt"
            test_file.write_text("ticket demo", encoding="utf-8")

            with patch("services.file_open_service.platform.system", return_value="Linux"):
                with patch(
                    "services.file_open_service.subprocess.Popen",
                    side_effect=RuntimeError("xdg-open fallo"),
                ):
                    resultado = open_file_cross_platform(test_file)

        self.assertFalse(resultado["ok"])
        self.assertIn("Abrilo manualmente desde", resultado["message"])
        self.assertIn(str(test_file.resolve()), resultado["message"])

    def test_url_vacia_devuelve_error_controlado(self):
        from services.file_open_service import open_external_target

        with patch("services.file_open_service.subprocess.Popen") as popen_mock:
            resultado = open_external_target("   ")

        self.assertFalse(resultado["ok"])
        self.assertIn("No se recibió", resultado["message"])
        popen_mock.assert_not_called()
