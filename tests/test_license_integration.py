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

from licensing.planes import (
    get_license_status_context,
    get_modulos_plan,
    get_plan_actions,
    get_plan_display_name,
    get_update_access_context,
)


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

    def test_pro_activo_con_10_dias_no_muestra_aviso_critico(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=10)).isoformat(),
        )
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "mensual_activo")
        self.assertEqual(status["dias_para_vencer"], 10)
        self.assertFalse(status["mostrar_aviso_preventivo"])
        self.assertFalse(status["mostrar_aviso_vencimiento"])

    def test_pro_activo_con_7_dias_muestra_aviso_preventivo(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=7)).isoformat(),
        )
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "mensual_por_vencer")
        self.assertEqual(status["dias_para_vencer"], 7)
        self.assertTrue(status["mostrar_aviso_preventivo"])
        self.assertFalse(status["mostrar_aviso_vencimiento"])

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
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "mensual_vencido_con_basica")
        self.assertTrue(status["mostrar_revalidar"])

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
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "mensual_vencido_sin_plan")
        self.assertTrue(status["recomendar_basica"])

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
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "mensual_vencido_con_basica")

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
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "mensual_vencido_sin_plan")

    def test_basica_no_vence(self):
        info = self._sync_license(
            plan_original="BASICA",
            plan_efectivo="BASICA",
            plan="BASICA",
            tier="BASICA",
            plan_base_permanente=True,
            expira="",
        )
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "basica_permanente")
        self.assertIsNone(status["dias_para_vencer"])
        self.assertFalse(status["mostrar_aviso_vencimiento"])

    def test_demo_vencido_no_se_convierte_en_basica_gratis(self):
        status = get_license_status_context(
            {
                "plan_original": "DEMO",
                "plan_efectivo": "DEMO",
                "plan": "DEMO",
                "tier": "DEMO",
                "expirada": False,
                "plan_base_permanente": False,
                "expires_at": "",
            },
            demo_status={"demo": True, "vencido": True, "dias_restantes": 0},
        )
        self.assertEqual(status["estado_comercial"], "demo_vencido")
        self.assertEqual(status["plan_efectivo"], "DEMO")
        self.assertFalse(status["basica_activada"])

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

    def test_pro_activo_puede_renovar(self):
        actions = get_plan_actions("PRO", plan_original="PRO", dias_para_vencer=15)
        self.assertTrue(actions["puede_renovar"])
        self.assertEqual(actions["plan_renovable"], "PRO")
        self.assertEqual(actions["cta_renovacion"], "Renovar PRO")
        self.assertFalse(actions["renovacion_destacada"])
        self.assertFalse(actions["auto_renovacion"])

    def test_full_activo_puede_renovar(self):
        actions = get_plan_actions("FULL", plan_original="FULL", dias_para_vencer=15)
        self.assertTrue(actions["puede_renovar"])
        self.assertEqual(actions["plan_renovable"], "FULL")
        self.assertEqual(actions["cta_renovacion"], "Renovar FULL")
        self.assertFalse(actions["renovacion_destacada"])

    def test_full_no_muestra_compra(self):
        actions = get_plan_actions("MENSUAL_FULL")
        self.assertEqual(actions["planes_comprables"], [])
        self.assertTrue(actions["es_plan_completo"])

    def test_mensual_full_se_trata_como_full(self):
        actions = get_plan_actions("FULL")
        self.assertEqual(actions["plan_actual"], "FULL")
        self.assertTrue(actions["es_plan_completo"])

    def test_sin_plan_permite_comprar_basica_pro_y_full(self):
        actions = get_plan_actions("SIN_PLAN", tiene_checkout=False, plan_original="SIN_PLAN")
        self.assertEqual(actions["planes_comprables"], ["BASICA", "PRO", "FULL"])
        self.assertFalse(actions["puede_renovar"])

    def test_basica_no_muestra_renovar_solo_upgrade(self):
        actions = get_plan_actions("BASICA", plan_original="BASICA")
        self.assertFalse(actions["puede_renovar"])
        self.assertEqual(actions["planes_comprables"], ["PRO", "FULL"])

    def test_demo_no_muestra_renovar(self):
        actions = get_plan_actions("DEMO", tiene_checkout=False, plan_original="DEMO")
        self.assertFalse(actions["puede_renovar"])
        self.assertEqual(actions["planes_comprables"], ["BASICA", "PRO", "FULL"])

    def test_pro_proximo_a_vencer_muestra_renovacion_destacada(self):
        actions = get_plan_actions("PRO", plan_original="PRO", dias_para_vencer=7)
        self.assertTrue(actions["puede_renovar"])
        self.assertTrue(actions["renovacion_destacada"])
        self.assertEqual(actions["cta_renovacion"], "Renovar ahora")

    def test_full_proximo_a_vencer_muestra_renovacion_destacada(self):
        actions = get_plan_actions("FULL", plan_original="FULL", dias_para_vencer=3)
        self.assertTrue(actions["puede_renovar"])
        self.assertTrue(actions["renovacion_destacada"])
        self.assertEqual(actions["cta_renovacion"], "Renovar ahora")

    def test_pro_vencido_muestra_reactivar_renovar(self):
        actions = get_plan_actions(
            "BASICA",
            plan_original="PRO",
            basica_activada=True,
            licencia_vencida=True,
            dias_para_vencer=-2,
        )
        self.assertTrue(actions["puede_renovar"])
        self.assertEqual(actions["plan_renovable"], "PRO")
        self.assertEqual(actions["cta_renovacion"], "Reactivar/Renovar plan")
        self.assertTrue(actions["renovacion_destacada"])

    def test_full_vencido_muestra_reactivar_renovar(self):
        actions = get_plan_actions(
            "SIN_PLAN",
            plan_original="FULL",
            basica_activada=False,
            licencia_vencida=True,
            dias_para_vencer=-2,
            tiene_checkout=False,
        )
        self.assertTrue(actions["puede_renovar"])
        self.assertEqual(actions["plan_renovable"], "FULL")
        self.assertEqual(actions["cta_renovacion"], "Reactivar/Renovar plan")
        self.assertTrue(actions["renovacion_destacada"])

    def test_no_muestra_cancelar_auto_renovacion_si_no_existe_backend(self):
        actions = get_plan_actions("PRO", plan_original="PRO", dias_para_vencer=20)
        self.assertFalse(actions["puede_cancelar_auto_renovacion"])
        self.assertFalse(actions["puede_activar_auto_renovacion"])
        mi_plan_template = (PROJECT_ROOT / "templates" / "mi_plan.html").read_text(encoding="utf-8")
        self.assertNotIn("Cancelar renovacion automatica", mi_plan_template)

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

    def test_pro_tiene_acceso_a_actualizaciones_normales(self):
        access = get_update_access_context({"tier": "PRO", "updates": True})
        self.assertTrue(access["puede_actualizar"])
        self.assertEqual(access["plan"], "PRO")

    def test_full_legacy_tiene_acceso_a_actualizaciones_normales(self):
        access = get_update_access_context({"tier": "MENSUAL_FULL", "updates": True})
        self.assertTrue(access["puede_actualizar"])
        self.assertEqual(access["plan"], "FULL")

    def test_basica_no_tiene_actualizaciones_normales(self):
        access = get_update_access_context({"tier": "BASICA", "updates": False})
        self.assertFalse(access["puede_actualizar"])
        self.assertIn("PRO y FULL", access["mensaje"])

    def test_respaldo_pro_no_queda_bloqueado_por_check_full_only(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "q", "security_answer_hash": "hash"}
                if "FROM config" in query:
                    return {"valor": None}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value={"key": "NXR-TDA-TEST-001", "tier": "PRO", "updates": True}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={}), \
                 mock.patch.object(self.routes_main, "get_cached_update_info", return_value={"available": False}), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"key": "NXR-TDA-TEST-001", "tier": "PRO", "updates": True}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-TDA-TEST-001"}):
                response = client.post("/respaldo/actualizacion/descargar", data={"csrf_token": "test"}, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No hay una actualizacion nueva disponible.", response.data)
        self.assertNotIn(b"solo para el plan FULL", response.data)


if __name__ == "__main__":
    unittest.main()
