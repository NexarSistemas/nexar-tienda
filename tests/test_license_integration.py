import importlib
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from licensing.planes import get_modulos_plan, get_plan_actions, get_plan_display_name


class LicenseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"

        import database
        import licensing.permisos as permisos
        import routes.main as routes_main
        import app as app_module

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.permisos = importlib.reload(permisos)
        self.routes_main = importlib.reload(routes_main)
        self.app_module = importlib.reload(app_module)

    def _sync_license(self, **overrides):
        payload = {
            "license_key": "NXR-TDA-TEST-001",
            "plan_original": "BASICA",
            "plan_efectivo": "BASICA",
            "plan": "BASICA",
            "tier": "BASICA",
            "estado": "activa",
            "fallback_aplicado": False,
            "plan_base_permanente": True,
            "expira": "",
        }
        payload.update(overrides)
        self.database.sync_license_from_remote(payload)
        return self.database.get_license_info()

    def test_basica_activa_devuelve_permisos_basica(self):
        info = self._sync_license()
        self.assertEqual(info["tier"], "BASICA")
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("BASICA"))

    def test_pro_activa_devuelve_permisos_pro(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=15)).isoformat(),
        )
        self.assertEqual(info["tier"], "PRO")
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("PRO"))

    def test_mensual_full_activa_devuelve_permisos_full(self):
        info = self._sync_license(
            plan_original="MENSUAL_FULL",
            plan_efectivo="MENSUAL_FULL",
            plan="MENSUAL_FULL",
            tier="MENSUAL_FULL",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=15)).isoformat(),
        )
        self.assertEqual(info["tier"], "FULL")
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("FULL"))

    def test_pro_vencida_con_base_permanente_devuelve_basica(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=True,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(info["plan_original"], "PRO")
        self.assertEqual(info["tier"], "BASICA")
        self.assertTrue(info["fallback_aplicado"])
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("BASICA"))

    def test_pro_vencida_sin_base_permanente_no_regala_basica(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=False,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(info["plan_original"], "PRO")
        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["fallback_aplicado"])
        self.assertEqual(self.permisos.get_modulos_activos(), set())

    def test_full_vencida_con_base_permanente_devuelve_basica(self):
        info = self._sync_license(
            plan_original="MENSUAL_FULL",
            plan_efectivo="MENSUAL_FULL",
            plan="MENSUAL_FULL",
            tier="MENSUAL_FULL",
            plan_base_permanente=True,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(info["plan_original"], "FULL")
        self.assertEqual(info["tier"], "BASICA")
        self.assertTrue(info["fallback_aplicado"])
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("BASICA"))

    def test_full_vencida_sin_base_permanente_no_regala_basica(self):
        info = self._sync_license(
            plan_original="MENSUAL_FULL",
            plan_efectivo="MENSUAL_FULL",
            plan="MENSUAL_FULL",
            tier="MENSUAL_FULL",
            plan_base_permanente=False,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(info["plan_original"], "FULL")
        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["fallback_aplicado"])
        self.assertEqual(self.permisos.get_modulos_activos(), set())

    def test_templates_no_exponen_demo_como_plan_comercial(self):
        licencia_template = (PROJECT_ROOT / "templates" / "licencia.html").read_text(encoding="utf-8")
        self.assertNotIn('<option value="DEMO">', licencia_template)
        self.assertIn('value="{{ option.plan }}"', licencia_template)
        self.assertIn('{{ option.plan_display }}', licencia_template)

    def test_demo_muestra_basica_pro_y_full(self):
        actions = get_plan_actions("DEMO", tiene_checkout=False)
        self.assertEqual(actions["planes_comprables"], ["BASICA", "PRO", "FULL"])

    def test_basica_muestra_pro_y_full(self):
        actions = get_plan_actions("BASICA")
        self.assertEqual(actions["planes_comprables"], ["PRO", "FULL"])

    def test_pro_muestra_full(self):
        actions = get_plan_actions("PRO")
        self.assertEqual(actions["planes_comprables"], ["FULL"])

    def test_full_no_muestra_compra(self):
        actions = get_plan_actions("MENSUAL_FULL")
        self.assertEqual(actions["planes_comprables"], [])
        self.assertTrue(actions["es_plan_completo"])

    def test_mensual_full_se_trata_como_full(self):
        actions = get_plan_actions("FULL")
        self.assertEqual(actions["plan_actual"], "FULL")
        self.assertTrue(actions["es_plan_completo"])

    def test_sin_plan_permite_comprar_basica_pro_y_full(self):
        actions = get_plan_actions("SIN_PLAN", tiene_checkout=False)
        self.assertEqual(actions["planes_comprables"], ["BASICA", "PRO", "FULL"])

    def test_normalize_plan_legacy_y_canonico_full(self):
        from licensing.planes import normalize_plan

        self.assertEqual(normalize_plan("PRO"), "PRO")
        self.assertEqual(normalize_plan("FULL"), "FULL")
        self.assertEqual(normalize_plan("MENSUAL_FULL"), "FULL")

    def test_pro_no_colapsa_a_full(self):
        pro_modules = get_modulos_plan("PRO")
        full_modules = get_modulos_plan("FULL")

        self.assertNotEqual(pro_modules, full_modules)
        self.assertTrue(full_modules.issuperset(pro_modules))

    def test_full_se_muestra_como_full_y_debug_expone_resolucion(self):
        self.assertEqual(get_plan_display_name("MENSUAL_FULL"), "FULL")

        app = self.app_module.create_app()
        fake_license = {
            "key": "NXR-TDA-TEST-001",
            "tier": "BASICA",
            "plan": "PRO",
            "plan_original": "PRO",
            "plan_efectivo": "BASICA",
            "effective_plan": "BASICA",
            "estado": "vencida_con_fallback_basica",
            "fallback_aplicado": True,
            "plan_base_permanente": True,
            "expirada": True,
            "modules": ["core"],
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}
                session["_csrf_token"] = "test"

            fake_user = {"security_question": "q", "security_answer_hash": "hash"}
            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value=fake_license), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_modules": '["core"]'}), \
                 mock.patch.object(self.routes_main, "get_license_debug_state", return_value={"validation_mode": "cache", "modules": ["core"], "last_error": "", "masked_license_key": "NXR...001"}), \
                 mock.patch.object(self.routes_main, "get_modulos_debug_info", return_value={"final_modules": ["core"], "tier_modules": ["core"], "final_source": "db_tier"}), \
                 mock.patch.object(self.routes_main, "get_supabase_debug_state", return_value={"configured": False}), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-TDA-TEST-001"}), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=fake_license), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", return_value=fake_user):
                response = client.get("/debug/licencia")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["plan_original"], "PRO")
        self.assertEqual(payload["plan_efectivo"], "BASICA")
        self.assertEqual(payload["estado"], "vencida_con_fallback_basica")
        self.assertTrue(payload["fallback_aplicado"])


if __name__ == "__main__":
    unittest.main()
