import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class PrintServiceTests(unittest.TestCase):
    def test_send_file_to_printer_falla_si_no_existe_archivo(self):
        from services.print_service import send_file_to_printer

        resultado = send_file_to_printer("/tmp/no-existe-ticket-nexar.pdf")

        self.assertFalse(resultado["ok"])
        self.assertIn("No se encontró el archivo", resultado["message"])

    def test_send_file_to_printer_falla_si_no_hay_lp_ni_lpr(self):
        from services.print_service import send_file_to_printer

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "ticket.pdf"
            pdf_path.write_text("demo", encoding="utf-8")

            with patch("services.print_service.shutil.which", return_value=None):
                resultado = send_file_to_printer(pdf_path)

        self.assertFalse(resultado["ok"])
        self.assertIn("No se encontró servicio de impresión Linux", resultado["message"])

    def test_send_file_to_printer_con_lp_exitoso(self):
        from services.print_service import send_file_to_printer

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "ticket.pdf"
            pdf_path.write_text("demo", encoding="utf-8")

            def fake_which(name):
                mapping = {
                    "lp": "/usr/bin/lp",
                    "lpr": None,
                    "lpstat": "/usr/bin/lpstat",
                }
                return mapping.get(name)

            with patch("services.print_service.shutil.which", side_effect=fake_which):
                with patch("services.print_service.subprocess.run") as run_mock:
                    run_mock.side_effect = [
                        type("Completed", (), {"returncode": 0, "stdout": "system default destination: Caja\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 0, "stdout": "request id is Caja-12 (1 file(s))\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 0, "stdout": "Caja-12 usuario 1024 dom 24 May 2026 12:00:00\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 0, "stdout": "Caja-12\n    Status: processing since Sun 24 May 2026 12:00:00\n", "stderr": ""})(),
                    ]
                    resultado = send_file_to_printer(pdf_path)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["printer"], "Caja")
        self.assertEqual(resultado["job_id"], "Caja-12")
        self.assertEqual(resultado["cups_status"]["state"], "queued")
        self.assertEqual(resultado["command"], ["/usr/bin/lp", "-d", "Caja", str(pdf_path.resolve())])

    def test_send_file_to_printer_con_error_de_comando(self):
        from services.print_service import send_file_to_printer

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "ticket.pdf"
            pdf_path.write_text("demo", encoding="utf-8")

            def fake_which(name):
                mapping = {
                    "lp": None,
                    "lpr": "/usr/bin/lpr",
                    "lpstat": "/usr/bin/lpstat",
                }
                return mapping.get(name)

            with patch("services.print_service.shutil.which", side_effect=fake_which):
                with patch("services.print_service.subprocess.run") as run_mock:
                    run_mock.side_effect = [
                        type("Completed", (), {"returncode": 0, "stdout": "system default destination: Termica\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "printer offline"})(),
                    ]
                    resultado = send_file_to_printer(pdf_path)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["printer"], "Termica")
        self.assertIn("printer offline", resultado["message"])
        self.assertEqual(resultado["command"], ["/usr/bin/lpr", "-P", "Termica", str(pdf_path.resolve())])

    def test_send_file_to_printer_agrega_fit_to_page_y_detecta_job_demorado(self):
        from services.print_service import send_file_to_printer

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "ticket.pdf"
            pdf_path.write_text("demo", encoding="utf-8")

            def fake_which(name):
                mapping = {
                    "lp": "/usr/bin/lp",
                    "lpr": None,
                    "lpstat": "/usr/bin/lpstat",
                }
                return mapping.get(name)

            with patch("services.print_service.shutil.which", side_effect=fake_which):
                with patch("services.print_service.subprocess.run") as run_mock:
                    run_mock.side_effect = [
                        type("Completed", (), {"returncode": 0, "stdout": "system default destination: Brother_DCP_T720DW\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 0, "stdout": "request id is Brother_DCP_T720DW-82 (1 file(s))\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 0, "stdout": "Brother_DCP_T720DW-82 usuario 1024 Sun 24 May 2026 12:00:00\n", "stderr": ""})(),
                        type("Completed", (), {"returncode": 0, "stdout": "Brother_DCP_T720DW-82\n    Alerts: job-hold-until-specified\n    Status: held since Sun 24 May 2026 12:00:00\n", "stderr": ""})(),
                    ]
                    resultado = send_file_to_printer(pdf_path, cups_print_mode="fit-to-page")

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["job_id"], "Brother_DCP_T720DW-82")
        self.assertEqual(resultado["print_mode"], "fit-to-page")
        self.assertIn("-o", resultado["command"])
        self.assertIn("fit-to-page", resultado["command"])
        self.assertEqual(resultado["cups_status"]["state"], "held")
        self.assertIn("demorado", resultado["message"])


if __name__ == "__main__":
    unittest.main()
