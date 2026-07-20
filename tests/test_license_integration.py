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
    normalize_plan,
)
from services.rubros import get_rubros_disponibles


class LicenseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        os.environ.pop("NEXAR_MODULES", None)
        os.environ.pop("NEXAR_EXTRA_MODULES", None)
        os.environ.pop("NEXAR_PLAN", None)
        os.environ.pop("NEXAR_LICENSE_MODE", None)
        for key in (
            "NEXAR_LICENSES_VALIDATION_URL",
            "NEXAR_LICENSES_SUPABASE_KEY",
            "NEXAR_LICENSES_TIMEOUT",
            "NEXAR_LICENSES_CONNECT_TIMEOUT",
            "NEXAR_LICENSES_READ_TIMEOUT",
            "NEXAR_LICENSES_MAX_RETRIES",
            "NEXAR_LICENSES_RETRY_BACKOFF",
            "NEXAR_LICENSES_RETRY_STATUS_CODES",
            "NEXAR_LICENSES_CACHE_FILE",
            "NEXAR_LICENSES_CACHE_DIR",
            "NEXAR_LICENSES_CACHE_TTL",
            "NEXAR_LICENSES_OFFLINE_FALLBACK",
            "SUPABASE_URL",
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "NEXAR_CACHE_FILE",
            "NEXAR_CACHE_DAYS",
        ):
            os.environ.pop(key, None)

        import database
        import licensing.permisos as permisos
        import routes.main as routes_main
        import app as app_module
        import services.license_sdk as license_sdk

        os.environ["NEXAR_LICENSE_MODE"] = "prod"
        os.environ.pop("NEXAR_MODULES", None)
        os.environ.pop("NEXAR_EXTRA_MODULES", None)
        os.environ.pop("NEXAR_PLAN", None)

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.permisos = importlib.reload(permisos)
        self.routes_main = importlib.reload(routes_main)
        self.app_module = importlib.reload(app_module)
        self.license_sdk = importlib.reload(license_sdk)

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

    def test_pro_bloqueada_con_fecha_futura_no_concede_permisos(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            estado="bloqueada",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=30)).isoformat(),
        )
        status = get_license_status_context(info)

        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["expirada"])
        self.assertEqual(self.permisos.get_modulos_activos(), set())
        self.assertEqual(status["estado_comercial"], "licencia_bloqueada")

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

    def test_full_suspendida_con_fecha_futura_no_concede_permisos(self):
        info = self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            estado="suspendida",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=30)).isoformat(),
        )
        status = get_license_status_context(info)

        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["expirada"])
        self.assertEqual(self.permisos.get_modulos_activos(), set())
        self.assertEqual(status["estado_comercial"], "licencia_bloqueada")

    def test_pro_vencida_con_base_permanente_no_degrada_a_basica(self):
        info = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=True,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(info["plan_original"], "PRO")
        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["fallback_aplicado"])
        self.assertEqual(self.permisos.get_modulos_activos(), set())
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "pro_vencido")
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
        self.assertEqual(status["estado_comercial"], "pro_vencido")
        self.assertTrue(status["recomendar_basica"])

    def test_full_vencida_con_base_permanente_no_degrada_a_basica(self):
        info = self._sync_license(
            plan_original="MENSUAL_FULL",
            plan_efectivo="MENSUAL_FULL",
            plan="MENSUAL_FULL",
            tier="MENSUAL_FULL",
            plan_base_permanente=True,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(info["plan_original"], "FULL")
        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["fallback_aplicado"])
        self.assertEqual(self.permisos.get_modulos_activos(), set())
        status = get_license_status_context(info)
        self.assertEqual(status["estado_comercial"], "full_vencido")

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
        self.assertEqual(status["estado_comercial"], "full_vencido")

    def test_pro_renovada_recupera_permisos_al_revalidar(self):
        expired = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            plan_base_permanente=False,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(expired["tier"], "SIN_PLAN")
        self.assertEqual(self.permisos.get_modulos_activos(), set())

        renewed = self._sync_license(
            plan_original="PRO",
            plan_efectivo="PRO",
            plan="PRO",
            tier="PRO",
            estado="activa",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=30)).isoformat(),
        )

        self.assertEqual(renewed["tier"], "PRO")
        self.assertFalse(renewed["expirada"])
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("PRO"))

    def test_full_renovada_recupera_permisos_al_revalidar(self):
        expired = self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            plan_base_permanente=False,
            expira=(date.today() - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(expired["tier"], "SIN_PLAN")
        self.assertEqual(self.permisos.get_modulos_activos(), set())

        renewed = self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            estado="activa",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=30)).isoformat(),
        )

        self.assertEqual(renewed["tier"], "FULL")
        self.assertFalse(renewed["expirada"])
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("FULL"))

    def test_refresh_licencia_no_encontrada_mantiene_full_local_vigente(self):
        self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=10)).isoformat(),
        )

        with mock.patch("services.supabase_license_api.activate_license", return_value=(False, "No existe esa licencia para este producto.", None)), \
             mock.patch("services.supabase_license_api.get_supabase_debug_state", return_value={"status": "not_found"}), \
             mock.patch("services.license_storage.cargar_licencia", return_value={"license_key": "NXR-FULL-001"}), \
             mock.patch.object(self.license_sdk, "get_current_hwid", return_value="HWID-1"):
            ok, message, refreshed_info = self.license_sdk.refresh_saved_license_online(debug=False)

        self.assertFalse(ok)
        self.assertEqual(
            message,
            "No pudimos validar la licencia en el servidor. Tu plan seguira activo hasta la fecha registrada localmente. Contacta soporte si el problema continua.",
        )
        self.assertEqual(refreshed_info["tier"], "FULL")
        self.assertEqual(self.database.get_license_info()["tier"], "FULL")

    def test_refresh_licencia_suspendida_no_mantiene_full(self):
        self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=10)).isoformat(),
        )

        remote_license = {
            "license_key": "NXR-FULL-001",
            "plan": "FULL",
            "tier": "FULL",
            "estado": "suspendida",
            "activa": False,
        }
        with mock.patch("services.supabase_license_api.activate_license", return_value=(False, "La licencia esta desactivada/revocada.", remote_license)), \
             mock.patch("services.supabase_license_api.get_supabase_debug_state", return_value={"status": "inactive"}), \
             mock.patch("services.license_storage.cargar_licencia", return_value={"license_key": "NXR-FULL-001"}), \
             mock.patch.object(self.license_sdk, "get_current_hwid", return_value="HWID-1"):
            ok, message, refreshed_info = self.license_sdk.refresh_saved_license_online(debug=False)

        self.assertFalse(ok)
        self.assertEqual(message, "La licencia fue suspendida. Contacta soporte.")
        self.assertEqual(refreshed_info["tier"], "SIN_PLAN")
        self.assertNotEqual(self.database.get_license_info()["tier"], "FULL")

    def test_refresh_licencia_vencida_resuelve_sin_plan(self):
        self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=10)).isoformat(),
        )

        remote_license = {
            "license_key": "NXR-FULL-001",
            "plan": "FULL",
            "tier": "FULL",
            "estado": "activa",
            "activa": True,
            "expires_at": (date.today() - timedelta(days=1)).isoformat(),
            "plan_base_permanente": False,
            "modules": ["core", "reportes"],
        }
        with mock.patch("services.supabase_license_api.activate_license", return_value=(True, "ok", remote_license)), \
             mock.patch("services.license_storage.cargar_licencia", return_value={"license_key": "NXR-FULL-001"}), \
             mock.patch.object(self.license_sdk, "get_current_hwid", return_value="HWID-1"):
            ok, message, refreshed_info = self.license_sdk.refresh_saved_license_online(debug=False)

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia actualizada desde Supabase.")
        self.assertEqual(refreshed_info["tier"], "SIN_PLAN")
        self.assertTrue(refreshed_info["expirada"])

    def test_refresh_licencia_error_conexion_mantiene_cache_local_vigente(self):
        self._sync_license(
            plan_original="FULL",
            plan_efectivo="FULL",
            plan="FULL",
            tier="FULL",
            plan_base_permanente=False,
            expira=(date.today() + timedelta(days=10)).isoformat(),
        )

        with mock.patch("services.supabase_license_api.activate_license", return_value=(False, "network error", None)), \
             mock.patch("services.supabase_license_api.get_supabase_debug_state", return_value={"status": "network_error"}), \
             mock.patch("services.license_storage.cargar_licencia", return_value={"license_key": "NXR-FULL-001"}), \
             mock.patch.object(self.license_sdk, "get_current_hwid", return_value="HWID-1"):
            ok, message, refreshed_info = self.license_sdk.refresh_saved_license_online(debug=False)

        self.assertFalse(ok)
        self.assertEqual(
            message,
            "No pudimos conectar con el servidor de licencias. Se mantiene el estado local hasta el vencimiento.",
        )
        self.assertEqual(refreshed_info["tier"], "FULL")
        self.assertEqual(self.database.get_license_info()["tier"], "FULL")

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

    def test_basica_legacy_con_fecha_pasada_permanece_activa(self):
        self.database.set_config({
            "demo_mode": "0",
            "license_key": "NXR-BASICA-LEGACY",
            "license_plan": "BASICA",
            "license_plan_original": "BASICA",
            "license_tier": "BASICA",
            "license_effective_plan": "BASICA",
            "license_status": "activa",
            "license_plan_base_permanente": "1",
            "basica_activada": "1",
            "license_expires_at": "2020-01-01",
            "license_modules": '["core", "clientes", "proveedores", "pos", "stock", "caja"]',
        })

        info = self.database.get_license_info()
        status = get_license_status_context(info)
        modules = self.permisos.get_modulos_activos()

        self.assertEqual(info["tier"], "BASICA")
        self.assertFalse(info["expirada"])
        self.assertEqual(info["expires_at"], "")
        self.assertEqual(status["estado_comercial"], "basica_permanente")
        self.assertIsNone(status["dias_para_vencer"])
        self.assertFalse(status["mostrar_aviso_preventivo"])
        self.assertFalse(status["mostrar_aviso_vencimiento"])
        self.assertEqual(modules, get_modulos_plan("BASICA"))

    def test_basica_legacy_con_fecha_futura_no_genera_cuenta_regresiva(self):
        info = self._sync_license(
            plan_original="BASICA",
            plan_efectivo="BASICA",
            plan="BASICA",
            tier="BASICA",
            plan_base_permanente=True,
            expira="2099-12-31",
        )
        status = get_license_status_context({**info, "expires_at": "2099-12-31"})
        actions = get_plan_actions("BASICA", plan_original="BASICA", dias_para_vencer=9999)

        self.assertEqual(info["tier"], "BASICA")
        self.assertEqual(info["expires_at"], "")
        self.assertFalse(info["expirada"])
        self.assertEqual(status["expires_at"], "")
        self.assertIsNone(status["dias_para_vencer"])
        self.assertFalse(actions["puede_renovar"])
        self.assertNotIn("Renovar", " ".join(str(value) for value in actions.values()))

    def test_basica_no_caduca_ante_cambio_grande_de_fecha_evaluada(self):
        cfg = {
            "license_plan": "BASICA",
            "license_plan_original": "BASICA",
            "license_tier": "BASICA",
            "license_effective_plan": "BASICA",
            "license_status": "activa",
            "license_plan_base_permanente": "1",
            "basica_activada": "1",
            "license_expires_at": "1900-01-01",
        }

        snapshot = self.database._resolve_license_snapshot(cfg)

        self.assertEqual(snapshot["plan_original"], "BASICA")
        self.assertEqual(snapshot["plan_efectivo"], "BASICA")
        self.assertFalse(snapshot["expirada"])
        self.assertIsNone(snapshot["remaining_days"])
        self.assertEqual(snapshot["expires_at"], "")

    def test_basica_conserva_permisos_sin_obtener_pro_o_full(self):
        self._sync_license(expira="2020-01-01")

        modules = self.permisos.get_modulos_activos()

        self.assertEqual(modules, get_modulos_plan("BASICA"))
        self.assertNotIn("compras", modules)
        self.assertNotIn("multiusuario", modules)
        self.assertNotIn("temporadas", modules)
        self.assertNotIn("multinegocio", modules)

    def test_basica_suspendida_no_se_trata_como_activa(self):
        info = self._sync_license(
            estado="suspendida",
            plan_base_permanente=True,
            expira="2020-01-01",
        )
        status = get_license_status_context(info)
        actions = self.routes_main._get_plan_actions_context(info, license_status=status)

        self.assertEqual(info["plan_original"], "BASICA")
        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["fallback_aplicado"])
        self.assertEqual(info["modules"], [])
        self.assertEqual(status["estado_comercial"], "licencia_bloqueada")
        self.assertNotEqual(status["estado_comercial"], "basica_permanente")
        self.assertFalse(actions["puede_renovar"])
        self.assertEqual(actions["planes_comprables"], [])

    def test_basica_bloqueada_no_conserva_fallback_permanente(self):
        info = self._sync_license(
            estado="bloqueada",
            plan_base_permanente=True,
            expira="2030-01-01",
        )
        status = get_license_status_context(info)
        cfg = self.database.get_config()

        self.assertEqual(info["plan_original"], "BASICA")
        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["plan_base_permanente"])
        self.assertFalse(status["licencia_utilizable"])
        self.assertFalse(status["basica_activada"])
        self.assertEqual(cfg["license_plan_base_permanente"], "0")
        self.assertEqual(cfg["basica_activada"], "0")

    def test_basica_anulada_no_se_trata_como_activa(self):
        info = self._sync_license(
            estado="anulada",
            plan_base_permanente=True,
            expira="2030-01-01",
        )
        status = get_license_status_context(info)

        self.assertEqual(info["tier"], "SIN_PLAN")
        self.assertFalse(info["plan_base_permanente"])
        self.assertEqual(status["estado_comercial"], "licencia_bloqueada")
        self.assertFalse(status["licencia_utilizable"])

    def test_basica_revocada_desde_sdk_no_queda_activa_por_permanencia(self):
        payload = self.license_sdk._resolve_effective_license_data({
            "license_key": "NXR-BASICA-REV",
            "plan": "BASICA",
            "tier": "BASICA",
            "estado": "revocada",
            "plan_base_permanente": True,
            "expires_at": "2020-01-01",
        })

        self.assertEqual(payload["plan_efectivo"], "SIN_PLAN")
        self.assertEqual(payload["effective_plan"], "SIN_PLAN")
        self.assertEqual(payload["tier"], "SIN_PLAN")
        self.assertFalse(payload["fallback_aplicado"])

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
        self.assertEqual(status["plan_efectivo"], "SIN_PLAN")
        self.assertFalse(status["basica_activada"])
        self.assertTrue(status["mostrar_aviso_vencimiento"])
        self.assertEqual(status["titulo_estado"], "Tu demo de 14 dias vencio")
        self.assertIn("periodo de prueba finalizo", status["mensaje_estado"])

    def test_demo_nuevo_arranca_con_14_dias(self):
        self.assertEqual(self.database.get_demo_status()["dias_demo"], 14)

    def test_demo_nueva_persiste_inicio_y_vencimiento_14_dias(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "",
        })

        status = self.database.get_demo_status(today="2026-01-01")
        cfg = self.database.get_config()

        self.assertEqual(status["install_date"], "2026-01-01")
        self.assertEqual(status["expires_at"], "2026-01-15")
        self.assertEqual(status["dias_demo"], 14)
        self.assertEqual(status["dias_restantes"], 14)
        self.assertFalse(status["vencido"])
        self.assertEqual(cfg["demo_install_date"], "2026-01-01")
        self.assertEqual(cfg["demo_expires_at"], "2026-01-15")

    def test_demo_reinicio_conserva_fechas_persistidas(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2026-01-15",
        })

        first = self.database.get_demo_status(today="2026-01-05")
        second = self.database.get_demo_status(today="2026-01-05")

        self.assertEqual(first["install_date"], "2026-01-01")
        self.assertEqual(first["expires_at"], "2026-01-15")
        self.assertEqual(second["install_date"], "2026-01-01")
        self.assertEqual(second["expires_at"], "2026-01-15")
        self.assertEqual(second["dias_restantes"], 10)

    def test_demo_ultimo_dia_valido_no_vence_por_off_by_one(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2026-01-15",
        })

        status = self.database.get_demo_status(today="2026-01-14")

        self.assertFalse(status["vencido"])
        self.assertEqual(status["dias_restantes"], 1)
        self.assertEqual(status["dias_usados"], 13)

    def test_demo_vence_al_dia_siguiente_del_periodo_otorgado(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2026-01-15",
        })

        status = self.database.get_demo_status(today="2026-01-15")

        self.assertTrue(status["vencido"])
        self.assertEqual(status["dias_restantes"], 0)
        self.assertEqual(status["dias_usados"], 14)

    def test_demo_historica_30_dias_conserva_vencimiento_original(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "30",
            "demo_expires_at": "2026-01-31",
        })

        status = self.database.get_demo_status(today="2026-01-15")

        self.assertFalse(status["vencido"])
        self.assertEqual(status["dias_demo"], 30)
        self.assertEqual(status["dias_restantes"], 16)
        self.assertEqual(self.database.get_config()["demo_expires_at"], "2026-01-31")

    def test_demo_antigua_activa_no_se_reduce_a_14_dias(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "30",
            "demo_expires_at": "",
        })

        status = self.database.get_demo_status(today="2026-01-20")

        self.assertFalse(status["vencido"])
        self.assertEqual(status["dias_demo"], 30)
        self.assertEqual(status["expires_at"], "2026-01-31")
        self.assertEqual(status["dias_restantes"], 11)

    def test_demo_antigua_vencida_no_se_reactiva_en_migracion(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2025-12-01",
            "demo_dias": "30",
            "demo_expires_at": "2025-12-31",
        })

        status = self.database.get_demo_status(today="2026-01-20")

        self.assertTrue(status["vencido"])
        self.assertEqual(status["dias_restantes"], 0)
        self.assertEqual(self.database.get_config()["demo_expires_at"], "2025-12-31")

    def test_demo_legacy_sin_vencimiento_migra_de_forma_segura(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "",
        })

        status = self.database.get_demo_status(today="2026-01-02")
        cfg = self.database.get_config()

        self.assertEqual(status["expires_at"], "2026-01-15")
        self.assertEqual(cfg["demo_expires_at"], "2026-01-15")
        self.assertFalse(status["vencido"])

    def test_demo_legacy_con_vencimiento_valido_gana_sobre_duracion_discrepante(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2026-01-31",
        })

        status = self.database.get_demo_status(today="2026-01-20")
        cfg = self.database.get_config()

        self.assertFalse(status["vencido"])
        self.assertEqual(status["dias_demo"], 30)
        self.assertEqual(status["dias_restantes"], 11)
        self.assertEqual(cfg["demo_expires_at"], "2026-01-31")
        self.assertEqual(cfg["demo_dias"], "30")

    def test_demo_migracion_es_idempotente(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "",
        })

        first = self.database.get_demo_status(today="2026-01-03")
        cfg_first = self.database.get_config()
        second = self.database.get_demo_status(today="2026-01-03")
        cfg_second = self.database.get_config()

        self.assertEqual(first, second)
        self.assertEqual(cfg_first["demo_install_date"], cfg_second["demo_install_date"])
        self.assertEqual(cfg_first["demo_expires_at"], cfg_second["demo_expires_at"])
        self.assertEqual(cfg_first["demo_dias"], cfg_second["demo_dias"])

    def test_demo_vencida_no_habilita_modulos_pagos(self):
        self.database.set_config({
            "demo_mode": "1",
            "license_tier": "DEMO",
            "license_plan": "DEMO",
            "license_modules": "[]",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2026-01-15",
        })

        status = self.database.get_demo_status(today="2026-01-16")
        modules = self.permisos.get_modulos_activos()

        self.assertTrue(status["vencido"])
        self.assertEqual(self.database.get_license_info()["tier"], "DEMO")
        self.assertEqual(modules, set())
        self.assertNotIn("compras", modules)
        self.assertNotIn("multiusuario", modules)

    def test_demo_status_no_muestra_dias_negativos(self):
        self.database.set_config({
            "demo_mode": "1",
            "demo_install_date": "2026-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2026-01-15",
        })

        status = self.database.get_demo_status(today="2026-02-20")

        self.assertTrue(status["vencido"])
        self.assertEqual(status["dias_restantes"], 0)

    def test_demo_calculo_puro_usa_fecha_fija_sin_reloj_real(self):
        lifecycle = self.database.calculate_demo_lifecycle(
            install_date="2026-01-01",
            demo_days=14,
            today="2026-01-14",
        )

        self.assertEqual(lifecycle["expires_at"], "2026-01-15")
        self.assertEqual(lifecycle["dias_restantes"], 1)
        self.assertFalse(lifecycle["vencido"])

    def test_templates_no_exponen_demo_como_plan_comercial(self):
        licencia_template = (PROJECT_ROOT / "templates" / "licencia.html").read_text(encoding="utf-8")
        self.assertNotIn('<option value="DEMO">', licencia_template)
        self.assertIn('value="{{ option.plan }}"', licencia_template)
        self.assertIn('{{ option.plan_display }}', licencia_template)

    def test_template_activacion_inicial_muestra_demo_14_dias(self):
        activation_template = (PROJECT_ROOT / "templates" / "activacion_inicial.html").read_text(encoding="utf-8")
        self.assertIn("DEMO 14 días", activation_template)

    def test_demo_muestra_basica_pro_y_full(self):
        actions = get_plan_actions("DEMO", tiene_checkout=False)
        self.assertEqual(actions["planes_comprables"], ["BASICA", "PRO", "FULL"])

    def test_checkout_disponible_en_demo_sin_license_key(self):
        self.assertTrue(self.routes_main._has_checkout_license({"tier": "DEMO", "key": ""}))
        self.assertEqual(
            self.routes_main._get_available_checkout_plans({"tier": "DEMO", "key": ""}),
            ["BASICA", "PRO", "FULL"],
        )

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

    def _build_mi_plan_view_for_test(self, license_info, demo_status=None, checkout_pending=None):
        demo_status = demo_status or {"demo": False, "vencido": False, "dias_restantes": 0, "dias_demo": 14}
        status = get_license_status_context(license_info, demo_status=demo_status)
        actions = self.routes_main._get_plan_actions_context(license_info, license_status=status)
        with mock.patch.object(self.routes_main.db, "get_demo_status", return_value=demo_status):
            return self.routes_main._build_mi_plan_view(
                license_info=license_info,
                license_status=status,
                plan_actions=actions,
                license_holder={
                    "nombre": license_info.get("owner_name", ""),
                    "email": license_info.get("owner_email", ""),
                    "telefono": license_info.get("owner_phone", ""),
                    "codigo_vendedor": license_info.get("vendor_code", ""),
                    "palabra_recuperacion": "",
                },
                checkout_pending=checkout_pending or {"pending": False},
                modulos_activos=sorted(license_info.get("modules", []) or []),
                modulos_bloqueados=[],
            )

    def test_mi_plan_view_demo_activa_muestra_dias_y_planes_pagos(self):
        demo_status = {"demo": True, "vencido": False, "dias_restantes": 6, "dias_demo": 14, "expires_at": "2099-01-15"}
        view = self._build_mi_plan_view_for_test(
            {"tier": "DEMO", "plan": "DEMO", "plan_original": "DEMO", "owner_email": "admin@test.com"},
            demo_status=demo_status,
        )

        self.assertEqual(view["estado_comercial"], "demo_activo")
        self.assertIn({"label": "Dias restantes", "value": "6"}, view["summary_items"])
        self.assertEqual([action["plan"] for action in view["checkout_actions"]], ["BASICA", "PRO", "FULL"])
        self.assertFalse(view["renewal"]["show"])

    def test_mi_plan_view_demo_vencida_no_ofrece_demo_nueva(self):
        demo_status = {"demo": True, "vencido": True, "dias_restantes": 0, "dias_demo": 14, "expires_at": "2026-01-15"}
        view = self._build_mi_plan_view_for_test(
            {"tier": "DEMO", "plan": "DEMO", "plan_original": "DEMO"},
            demo_status=demo_status,
        )

        self.assertEqual(view["estado_comercial"], "demo_vencido")
        self.assertEqual([action["plan"] for action in view["checkout_actions"]], ["BASICA", "PRO", "FULL"])
        self.assertNotIn("DEMO", [action["plan"] for action in view["checkout_actions"]])
        self.assertIn("ya fue utilizada", view["mensaje_estado"])

    def test_mi_plan_view_basica_activa_no_vence_ni_renueva(self):
        view = self._build_mi_plan_view_for_test({
            "tier": "BASICA",
            "plan": "BASICA",
            "plan_original": "BASICA",
            "plan_efectivo": "BASICA",
            "plan_base_permanente": True,
            "limits": self.database.TIER_LIMITS["BASICA"],
        })

        self.assertEqual(view["estado_comercial"], "basica_permanente")
        self.assertIn({"label": "Vencimiento", "value": "No vence"}, view["summary_items"])
        self.assertFalse(view["renewal"]["show"])
        self.assertEqual([action["plan"] for action in view["checkout_actions"]], ["PRO", "FULL"])

    def test_mi_plan_view_pro_activo_muestra_vencimiento_renovacion_y_full(self):
        expires_at = (date.today() + timedelta(days=20)).isoformat()
        view = self._build_mi_plan_view_for_test({
            "key": "NXR-PRO-001",
            "tier": "PRO",
            "plan": "PRO",
            "plan_original": "PRO",
            "plan_efectivo": "PRO",
            "expires_at": expires_at,
            "limits": self.database.TIER_LIMITS["PRO"],
        })

        self.assertEqual(view["estado_comercial"], "mensual_activo")
        self.assertIn({"label": "Vencimiento", "value": self.routes_main._format_display_date(expires_at)}, view["summary_items"])
        self.assertIn({"label": "Dias restantes", "value": "20"}, view["summary_items"])
        self.assertTrue(view["renewal"]["show"])
        self.assertEqual([action["plan"] for action in view["checkout_actions"]], ["FULL"])

    def test_mi_plan_view_full_activo_muestra_renovacion_sin_upgrades(self):
        expires_at = (date.today() + timedelta(days=15)).isoformat()
        view = self._build_mi_plan_view_for_test({
            "key": "NXR-FULL-001",
            "tier": "FULL",
            "plan": "FULL",
            "plan_original": "FULL",
            "plan_efectivo": "FULL",
            "expires_at": expires_at,
        })

        self.assertEqual(view["plan_display"], "FULL")
        self.assertTrue(view["renewal"]["show"])
        self.assertEqual(view["checkout_actions"], [])

    def test_mi_plan_view_licencia_bloqueada_no_se_presenta_activa(self):
        for estado in ("suspendida", "bloqueada", "revocada", "anulada"):
            view = self._build_mi_plan_view_for_test({
                "key": "NXR-BLOCK-001",
                "tier": "SIN_PLAN",
                "plan": "PRO",
                "plan_original": "PRO",
                "plan_efectivo": "SIN_PLAN",
                "estado": estado,
            })
            self.assertEqual(view["estado_comercial"], "licencia_bloqueada")
            self.assertEqual(view["plan_display"], "SIN PLAN")
            self.assertFalse(view["checkout_actions"])

    def test_mi_plan_view_oculta_email_y_vendedor_ausentes(self):
        view = self._build_mi_plan_view_for_test({
            "tier": "BASICA",
            "plan": "BASICA",
            "plan_original": "BASICA",
            "plan_efectivo": "BASICA",
            "plan_base_permanente": True,
            "owner_email": "",
            "vendor_code": "",
        })

        labels = [item["label"] for item in view["summary_items"]]
        self.assertNotIn("Email asociado", labels)
        self.assertNotIn("Codigo de vendedor", labels)

    def test_normalize_plan_legacy_y_canonico_full(self):
        self.assertEqual(normalize_plan("PRO"), "PRO")
        self.assertEqual(normalize_plan("FULL"), "FULL")
        self.assertEqual(normalize_plan("MENSUAL_FULL"), "FULL")

    def test_normalize_plan_preserva_basica(self):
        self.assertEqual(normalize_plan("BASICA"), "BASICA")

    def test_build_checkout_context_permite_alta_licencia_desde_demo(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/checkout", method="POST", json={"plan_destino": "PRO"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "expirada": False}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_owner_name": "Admin", "license_owner_email": "admin@test.com", "license_owner_phone": ""}), \
                 mock.patch.object(self.routes_main, "cargar_licencia", return_value={}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-TEST-123", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-TEST-123"):
                context, error_response = self.routes_main._build_checkout_context()

        self.assertIsNone(error_response)
        self.assertEqual(context["tipo_solicitud"], "alta_licencia")
        self.assertEqual(context["activation_id"], "NXID-TEST-123")
        self.assertEqual(context["plan_destino"], "PRO")
        self.assertEqual(context["license_key"], "")
        self.assertTrue(str(context["external_reference"]).startswith("ALTA|NXID-TEST-123|"))

    def test_build_checkout_context_permite_alta_licencia_basica_desde_demo(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/checkout", method="POST", json={"plan_destino": "BASICA"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "expirada": False}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_owner_name": "Admin", "license_owner_email": "admin@test.com", "license_owner_phone": ""}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-TEST-123", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-TEST-123"):
                context, error_response = self.routes_main._build_checkout_context()

        self.assertIsNone(error_response)
        self.assertEqual(context["tipo_solicitud"], "alta_licencia")
        self.assertEqual(context["plan_destino"], "BASICA")

    def test_build_checkout_context_permite_alta_licencia_full_desde_demo(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/checkout", method="POST", json={"plan_destino": "MENSUAL_FULL"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "expirada": False}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_owner_name": "Admin", "license_owner_email": "admin@test.com", "license_owner_phone": ""}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-TEST-789", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-TEST-789"):
                context, error_response = self.routes_main._build_checkout_context()

        self.assertIsNone(error_response)
        self.assertEqual(context["tipo_solicitud"], "alta_licencia")
        self.assertEqual(context["plan_destino"], "FULL")

    def test_build_checkout_context_permite_alta_pro_sin_demo_previa(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/checkout", method="POST", json={"plan_destino": "PRO"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "SIN_PLAN", "key": "", "expirada": False}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_owner_name": "Admin", "license_owner_email": "admin@test.com", "license_owner_phone": ""}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-SIN-DEMO", {"host": "new"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-SIN-DEMO"):
                context, error_response = self.routes_main._build_checkout_context()

        self.assertIsNone(error_response)
        self.assertEqual(context["tipo_solicitud"], "alta_licencia")
        self.assertEqual(context["activation_id"], "NXID-SIN-DEMO")
        self.assertEqual(context["plan_destino"], "PRO")
        self.assertEqual(context["license_key"], "")

    def test_checkout_inicial_pago_no_concede_permisos_ni_completa_activacion(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/checkout", method="POST", json={"plan_destino": "FULL"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            self.database.set_config({
                "activation_initial_completed": "0",
                "license_owner_name": "Admin",
                "license_owner_email": "admin@test.com",
                "license_owner_phone": "123",
            })
            with mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-CHECKOUT-1", {"host": "new"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-CHECKOUT-1"), \
                 mock.patch.object(self.routes_main, "create_checkout_preference", return_value="https://pagos.test/checkout") as checkout_mock:
                init_point, context, error_response = self.routes_main._create_checkout_init_point()

        self.assertIsNone(error_response)
        self.assertEqual(init_point, "https://pagos.test/checkout")
        self.assertEqual(context["tipo_solicitud"], "alta_licencia")
        self.assertEqual(context["activation_id"], "NXID-CHECKOUT-1")
        self.assertEqual(checkout_mock.call_args.kwargs["activation_id"], "NXID-CHECKOUT-1")
        self.assertEqual(checkout_mock.call_args.kwargs["plan_destino"], "FULL")
        cfg = self.database.get_config()
        self.assertEqual(cfg["activation_initial_completed"], "0")
        self.assertEqual(cfg["activation_checkout_status"], "iniciado")
        self.assertEqual(cfg["activation_checkout_plan"], "FULL")
        self.assertEqual(cfg["activation_checkout_activation_id"], "NXID-CHECKOUT-1")
        self.assertEqual(self.database.get_license_info()["tier"], "DEMO")
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("DEMO"))

    def test_revalidar_pago_pendiente_no_concede_permisos(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/refrescar", method="GET"):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            self.database.set_config({
                "activation_initial_completed": "0",
                "activation_checkout_status": "iniciado",
                "activation_checkout_plan": "PRO",
                "activation_checkout_activation_id": "NXID-PENDING-1",
                "license_owner_email": "admin@test.com",
            })
            with mock.patch.object(self.routes_main, "find_active_license_for_machine", return_value=(False, "pendiente", None)), \
                 mock.patch.object(self.routes_main, "get_supabase_debug_state", return_value={"status": "not_found"}):
                payload, ok = self.routes_main._refresh_license_response(force=True)

        self.assertFalse(ok)
        self.assertIn("Todavia no encontramos", payload["message"])
        self.assertEqual(self.database.get_config()["activation_initial_completed"], "0")
        self.assertEqual(self.database.get_license_info()["tier"], "DEMO")
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("DEMO"))

    def test_revalidar_pago_error_red_no_concede_permisos(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/refrescar", method="GET"):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            self.database.set_config({
                "activation_initial_completed": "0",
                "activation_checkout_status": "iniciado",
                "activation_checkout_plan": "FULL",
                "activation_checkout_activation_id": "NXID-NET-1",
            })
            with mock.patch.object(self.routes_main, "find_active_license_for_machine", return_value=(False, "sin conexion", None)), \
                 mock.patch.object(self.routes_main, "get_supabase_debug_state", return_value={"status": "network_error"}):
                payload, ok = self.routes_main._refresh_license_response(force=True)

        self.assertFalse(ok)
        self.assertIn("No pudimos verificar", payload["message"])
        self.assertEqual(self.database.get_config()["activation_initial_completed"], "0")
        self.assertEqual(self.database.get_license_info()["tier"], "DEMO")
        self.assertNotEqual(self.database.get_license_info()["tier"], "FULL")

    def test_revalidar_pago_confirmado_activa_basica_permanente(self):
        app = self.app_module.create_app()
        remote_license = {
            "license_key": "NXR-BASICA-DIRECTA",
            "plan": "BASICA",
            "tier": "BASICA",
            "estado": "activa",
            "expires_at": "2099-01-01",
            "modules": ["core", "clientes", "proveedores", "pos", "stock", "caja"],
        }
        with app.test_request_context("/mi-plan/refrescar", method="GET"):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            self.database.set_config({
                "activation_initial_completed": "0",
                "activation_checkout_status": "iniciado",
                "activation_checkout_plan": "BASICA",
                "activation_checkout_activation_id": "NXID-BASICA-1",
            })
            with mock.patch.object(self.routes_main, "find_active_license_for_machine", return_value=(True, "ok", remote_license)):
                payload, ok = self.routes_main._refresh_license_response(force=True)

        info = self.database.get_license_info()
        self.assertTrue(ok)
        self.assertEqual(payload["message"], "Tu plan fue activado correctamente.")
        self.assertEqual(info["tier"], "BASICA")
        self.assertEqual(info["expires_at"], "")
        self.assertFalse(info["updates"])
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("BASICA"))
        self.assertNotIn("reportes", self.permisos.get_modulos_activos())
        self.assertEqual(self.database.get_config()["activation_initial_completed"], "1")
        self.assertEqual(self.database.get_config()["activation_checkout_status"], "")

    def test_revalidar_pago_confirmado_activa_pro_sin_full(self):
        app = self.app_module.create_app()
        expires_at = (date.today() + timedelta(days=30)).isoformat()
        remote_license = {
            "license_key": "NXR-PRO-DIRECTA",
            "plan": "PRO",
            "tier": "PRO",
            "estado": "activa",
            "expires_at": expires_at,
        }
        with app.test_request_context("/mi-plan/refrescar", method="GET"):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            self.database.set_config({
                "activation_initial_completed": "0",
                "activation_checkout_status": "iniciado",
                "activation_checkout_plan": "PRO",
                "activation_checkout_activation_id": "NXID-PRO-1",
            })
            with mock.patch.object(self.routes_main, "find_active_license_for_machine", return_value=(True, "ok", remote_license)):
                _payload, ok = self.routes_main._refresh_license_response(force=True)

        info = self.database.get_license_info()
        self.assertTrue(ok)
        self.assertEqual(info["tier"], "PRO")
        self.assertEqual(info["expires_at"], expires_at)
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("PRO"))
        self.assertNotIn("temporadas", self.permisos.get_modulos_activos())

    def test_revalidar_pago_confirmado_activa_full(self):
        app = self.app_module.create_app()
        expires_at = (date.today() + timedelta(days=30)).isoformat()
        remote_license = {
            "license_key": "NXR-FULL-DIRECTA",
            "plan": "FULL",
            "tier": "FULL",
            "estado": "activa",
            "expires_at": expires_at,
        }
        with app.test_request_context("/mi-plan/refrescar", method="GET"):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            self.database.set_config({
                "activation_initial_completed": "0",
                "activation_checkout_status": "iniciado",
                "activation_checkout_plan": "FULL",
                "activation_checkout_activation_id": "NXID-FULL-1",
            })
            with mock.patch.object(self.routes_main, "find_active_license_for_machine", return_value=(True, "ok", remote_license)):
                _payload, ok = self.routes_main._refresh_license_response(force=True)

        self.assertTrue(ok)
        self.assertEqual(self.database.get_license_info()["tier"], "FULL")
        self.assertEqual(self.database.get_license_info()["expires_at"], expires_at)
        self.assertEqual(self.permisos.get_modulos_activos(), get_modulos_plan("FULL"))

    def test_checkout_con_license_json_stale_sigue_tratando_demo_como_alta(self):
        self.assertEqual(
            self.routes_main._resolve_checkout_request_type({"tier": "DEMO", "key": ""}),
            "alta_licencia",
        )

    def test_solicitud_manual_desde_demo_envia_alta_licencia(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/solicitar-upgrade", method="POST", data={"plan_destino": "FULL"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin", "nombre_completo": "Administrador"}
            captured = {}

            def _fake_create_upgrade_request(payload):
                captured.update(payload)
                return {"ok": True}

            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "owner_name": "", "owner_email": ""}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"nombre_negocio": "Nexar Test", "email_contacto": "admin@test.com", "telefono": "123"}), \
                 mock.patch.object(self.routes_main, "cargar_licencia", return_value={}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-456", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-456"), \
                 mock.patch.object(self.routes_main, "create_upgrade_request", side_effect=_fake_create_upgrade_request):
                response = self.routes_main.mi_plan_solicitar_upgrade()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(captured["tipo_solicitud"], "alta_licencia")
        self.assertEqual(captured["activation_id"], "NXID-DEMO-456")
        self.assertEqual(captured["plan_destino"], "FULL")
        self.assertEqual(captured["license_key"], "")
        self.assertEqual(captured["email"], "admin@test.com")

    def test_solicitud_manual_sin_email_no_envia_a_supabase_y_muestra_mensaje(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/solicitar-upgrade", method="POST", data={"plan_destino": "PRO"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin", "nombre_completo": "Administrador"}

            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "owner_name": "", "owner_email": ""}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"nombre_negocio": "Nexar Test", "email_contacto": "", "telefono": "123"}), \
                 mock.patch.object(self.routes_main, "cargar_licencia", return_value={}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-456", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-456"), \
                 mock.patch.object(self.routes_main, "create_upgrade_request") as create_upgrade_request_mock:
                response = self.routes_main.mi_plan_solicitar_upgrade()
                flashes = session.get("_flashes", [])

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/mi-plan"))
        create_upgrade_request_mock.assert_not_called()
        self.assertTrue(
            any("completá el email del titular antes de solicitar el upgrade" in message.lower() for _category, message in flashes)
        )

    def test_solicitud_manual_upgrade_conserva_codigo_vendedor(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/solicitar-upgrade", method="POST", data={"plan_destino": "PRO"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin", "nombre_completo": "Administrador"}
            captured = {}

            def _fake_create_upgrade_request(payload):
                captured.update(payload)
                return {"ok": True}

            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "owner_name": "", "owner_email": "", "vendor_code": "vend123"}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_vendor_code": "vend123", "nombre_negocio": "Nexar Test", "email_contacto": "admin@test.com", "telefono": "123"}), \
                 mock.patch.object(self.routes_main, "cargar_licencia", return_value={}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-456", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-456"), \
                 mock.patch.object(self.routes_main, "create_upgrade_request", side_effect=_fake_create_upgrade_request):
                response = self.routes_main.mi_plan_solicitar_upgrade()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(captured["codigo_vendedor"], "VEND123")

    def test_solicitud_manual_con_email_valido_y_sin_codigo_vendedor_envia_solicitud_igual(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/solicitar-upgrade", method="POST", data={"plan_destino": "PRO"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin", "nombre_completo": "Administrador"}
            captured = {}

            def _fake_create_upgrade_request(payload):
                captured.update(payload)
                return {"ok": True}

            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "owner_name": "", "owner_email": ""}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"nombre_negocio": "Nexar Test", "email_contacto": "admin@test.com", "telefono": "123", "license_vendor_code": ""}), \
                 mock.patch.object(self.routes_main, "cargar_licencia", return_value={}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-456", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-456"), \
                 mock.patch.object(self.routes_main, "create_upgrade_request", side_effect=_fake_create_upgrade_request):
                response = self.routes_main.mi_plan_solicitar_upgrade()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(captured["email"], "admin@test.com")
        self.assertEqual(captured["plan_destino"], "PRO")
        self.assertEqual(captured["tipo_solicitud"], "alta_licencia")
        self.assertEqual(captured["codigo_vendedor"], "")

    def test_build_checkout_context_con_license_key_sigue_usando_cambio_plan(self):
        app = self.app_module.create_app()
        with app.test_request_context("/mi-plan/checkout", method="POST", json={"plan_destino": "PRO"}):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}
            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "BASICA", "key": "NXR-TDA-TEST-001", "expirada": False}), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_owner_name": "Admin", "license_owner_email": "admin@test.com", "license_owner_phone": ""}), \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-UPG-321", {"host": "licensed"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-UPG-321"):
                context, error_response = self.routes_main._build_checkout_context()

        self.assertIsNone(error_response)
        self.assertEqual(context["tipo_solicitud"], "cambio_plan")
        self.assertEqual(context["license_key"], "NXR-TDA-TEST-001")

    def test_licencia_solicitar_guarda_y_envia_codigo_vendedor_normalizado(self):
        app = self.app_module.create_app()
        with app.test_request_context(
            "/licencia/solicitar",
            method="POST",
            data={
                "activation_id": "NXID-TEST-123",
                "nombre": "Admin",
                "email": "admin@test.com",
                "whatsapp": "123",
                "codigo_vendedor": " vend123 ",
                "plan": "PRO",
                "accept_license_agreement": "1",
            },
        ):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}

            with mock.patch.object(self.routes_main.db, "set_config") as set_config_mock, \
                 mock.patch.object(self.routes_main, "create_license_request", return_value=(True, "ok", None)) as request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-TEST-123", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-TEST-123"):
                response = self.routes_main.licencia_solicitar()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(set_config_mock.call_args.args[0]["license_vendor_code"], "VEND123")
        self.assertEqual(request_mock.call_args.kwargs["codigo_vendedor"], "VEND123")

    def test_mi_plan_guardar_codigo_vendedor_demo_sin_license_key_guarda_local(self):
        app = self.app_module.create_app()
        with app.test_request_context(
            "/mi-plan/codigo-vendedor",
            method="POST",
            data={"codigo_vendedor": " vend123 "},
        ):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}

            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO", "key": "", "vendor_code": ""}), \
                 mock.patch.object(self.routes_main.db, "set_config") as set_config_mock:
                response = self.routes_main.mi_plan_guardar_codigo_vendedor()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(set_config_mock.call_args.args[0]["license_vendor_code"], "VEND123")

    def test_mi_plan_guardar_codigo_vendedor_licencia_activa_sincroniza_supabase(self):
        app = self.app_module.create_app()
        with app.test_request_context(
            "/mi-plan/codigo-vendedor",
            method="POST",
            data={"codigo_vendedor": " vend123 "},
        ):
            from flask import session

            session["user"] = {"rol": "admin", "id": 1, "username": "admin"}

            with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "BASICA", "key": "NXR-BASICA-001", "vendor_code": ""}), \
                 mock.patch.object(self.routes_main.db, "set_config") as set_config_mock, \
                 mock.patch.object(self.routes_main, "get_license_product", return_value="nexar-tienda"), \
                 mock.patch.object(self.routes_main, "update_license_vendor_code", return_value=(True, "ok", {"codigo_vendedor": "VEND123"})) as update_mock:
                response = self.routes_main.mi_plan_guardar_codigo_vendedor()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(set_config_mock.call_args.args[0]["license_vendor_code"], "VEND123")
        self.assertEqual(update_mock.call_args.kwargs["vendor_code"], "VEND123")

    def test_validate_license_key_permite_activar_basica_desde_demo(self):
        license_payload = {
            "license_key": "NXR-BASICA-001",
            "plan": "BASICA",
            "tier": "BASICA",
            "modules": ["core", "clientes"],
        }

        with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO"}), \
             mock.patch.object(self.routes_main.db, "sync_license_from_remote") as sync_mock, \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=lambda *args, **kwargs: {"ok": True, "license": license_payload, "source": "online"}), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None):
            ok, message = self.routes_main.validate_license_key("NXR-BASICA-001", debug=False)

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia validada correctamente.")
        sync_mock.assert_called_once()
        synced = sync_mock.call_args.args[0]
        self.assertEqual(synced["license_key"], license_payload["license_key"])
        self.assertEqual(synced["plan_original"], "BASICA")
        self.assertEqual(synced["plan_efectivo"], "BASICA")
        self.assertEqual(synced["tier"], "BASICA")

    def test_validate_license_key_sincroniza_codigo_vendedor_si_existe(self):
        license_payload = {
            "license_key": "NXR-BASICA-001",
            "plan": "BASICA",
            "tier": "BASICA",
            "modules": ["core", "clientes"],
        }
        remote_payload = dict(license_payload)
        remote_payload["codigo_vendedor"] = "VEND123"

        with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO"}), \
             mock.patch.object(self.routes_main.db, "sync_license_from_remote") as sync_mock, \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=lambda *args, **kwargs: {"ok": True, "license": license_payload, "source": "online"}), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None), \
             mock.patch("services.supabase_license_api.activate_license", return_value=(True, "ok", remote_payload)) as activate_mock:
            ok, message = self.routes_main.validate_license_key("NXR-BASICA-001", debug=False, vendor_code=" vend123 ")

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia validada correctamente.")
        activate_mock.assert_called_once()
        self.assertEqual(activate_mock.call_args.kwargs["vendor_code"], "VEND123")
        sync_mock.assert_called_once()
        synced = sync_mock.call_args.args[0]
        self.assertEqual(synced["license_key"], remote_payload["license_key"])
        self.assertEqual(synced["codigo_vendedor"], "VEND123")
        self.assertEqual(synced["plan_original"], "BASICA")
        self.assertEqual(synced["plan_efectivo"], "BASICA")

    def test_validate_license_key_permite_activar_pro_desde_demo(self):
        license_payload = {
            "license_key": "NXR-PRO-001",
            "plan": "PRO",
            "tier": "PRO",
            "modules": ["core", "reportes"],
        }

        with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO"}), \
             mock.patch.object(self.routes_main.db, "sync_license_from_remote") as sync_mock, \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=lambda *args, **kwargs: {"ok": True, "license": license_payload, "source": "online"}), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None):
            ok, message = self.routes_main.validate_license_key("NXR-PRO-001", debug=False)

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia validada correctamente.")
        sync_mock.assert_called_once()
        synced = sync_mock.call_args.args[0]
        self.assertEqual(synced["license_key"], license_payload["license_key"])
        self.assertEqual(synced["plan_original"], "PRO")
        self.assertEqual(synced["plan_efectivo"], "PRO")
        self.assertEqual(synced["tier"], "PRO")

    def test_validate_license_key_permite_activar_full_desde_demo_sin_basica_previa(self):
        license_payload = {
            "license_key": "NXR-FULL-001",
            "plan": "MENSUAL_FULL",
            "tier": "MENSUAL_FULL",
            "modules": ["core", "reportes", "multinegocio"],
        }

        with mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO"}), \
             mock.patch.object(self.routes_main.db, "get_config", return_value={"basica_activada": "0"}), \
             mock.patch.object(self.routes_main.db, "sync_license_from_remote") as sync_mock, \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=lambda *args, **kwargs: {"ok": True, "license": license_payload, "source": "online"}), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None):
            ok, message = self.routes_main.validate_license_key("NXR-FULL-001", debug=False)

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia validada correctamente.")
        sync_mock.assert_called_once()
        synced = sync_mock.call_args.args[0]
        self.assertEqual(synced["license_key"], license_payload["license_key"])
        self.assertEqual(synced["plan_original"], "MENSUAL_FULL")
        self.assertEqual(synced["plan_efectivo"], "MENSUAL_FULL")
        self.assertEqual(synced["tier"], "MENSUAL_FULL")

    def test_licensing_payload_acepta_full_y_alias_mensual_full(self):
        from services.licensing import validate_license_payload

        ok_full, msg_full = validate_license_payload({"plan": "FULL"}, machine_id="MID-1")
        ok_alias, msg_alias = validate_license_payload({"plan": "MENSUAL_FULL"}, machine_id="MID-1")

        self.assertTrue(ok_full, msg_full)
        self.assertTrue(ok_alias, msg_alias)

    def test_activar_licencia_legacy_permite_full_sin_basica_previa(self):
        token_payload = {
            "tier": "MENSUAL_FULL",
            "type": "TDA_FULL",
            "license_key": "NXR-FULL-LEGACY-001",
            "max_machines": 1,
            "expires_at": (date.today() + timedelta(days=30)).isoformat(),
        }

        with mock.patch.object(self.database, "validar_licencia_rsa", return_value=(True, "OK", token_payload)), \
             mock.patch.object(self.database, "set_config") as set_config_mock:
            ok, message = self.database.activar_licencia("token-demo")

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia activada correctamente.")
        updates = set_config_mock.call_args.args[0]
        self.assertEqual(updates["license_tier"], "FULL")
        self.assertEqual(updates["license_plan"], "FULL")

    def test_sync_license_from_remote_no_borra_codigo_vendedor_local(self):
        self.database.set_config({"license_vendor_code": "VEND123"})

        self.database.sync_license_from_remote({
            "license_key": "NXR-BASICA-001",
            "plan": "BASICA",
            "tier": "BASICA",
            "modules": ["core"],
        })

        self.assertEqual(self.database.get_license_info()["vendor_code"], "VEND123")

    def test_sdk_config_central_usa_variables_nuevas_y_pasa_config_a_validacion(self):
        captured = {}

        class FakeConfig:
            def __init__(self, validation_url="", supabase_key="", cache_file="", cache_ttl_days=""):
                self.validation_url = validation_url
                self.supabase_key = supabase_key
                self.cache_file = cache_file
                self.cache_ttl_days = cache_ttl_days

            @classmethod
            def from_env(cls):
                return cls(
                    validation_url=os.environ.get("NEXAR_LICENSES_VALIDATION_URL") or os.environ.get("SUPABASE_URL", ""),
                    supabase_key=os.environ.get("NEXAR_LICENSES_SUPABASE_KEY") or os.environ.get("SUPABASE_KEY", ""),
                    cache_file=os.environ.get("NEXAR_LICENSES_CACHE_FILE") or os.environ.get("NEXAR_CACHE_FILE", ""),
                    cache_ttl_days=os.environ.get("NEXAR_LICENSES_CACHE_TTL") or os.environ.get("NEXAR_CACHE_DAYS", ""),
                )

        def fake_validator(licencia_dict, public_key, product_name, debug=False, *, config=None):
            captured["config"] = config
            return {
                "ok": True,
                "source": "online",
                "license": {"license_key": licencia_dict["license_key"], "plan": "BASICA", "tier": "BASICA"},
            }

        os.environ["NEXAR_LICENSES_VALIDATION_URL"] = "https://nuevo.supabase.co"
        os.environ["NEXAR_LICENSES_SUPABASE_KEY"] = "new-public-key"
        os.environ["NEXAR_LICENSES_CACHE_FILE"] = "nuevo-cache.json"
        os.environ["NEXAR_LICENSES_CACHE_TTL"] = "7"
        os.environ["SUPABASE_URL"] = "https://legacy.supabase.co"
        os.environ["SUPABASE_KEY"] = "legacy-key"
        os.environ["NEXAR_CACHE_FILE"] = "legacy-cache.json"
        os.environ["NEXAR_CACHE_DAYS"] = "3"

        with mock.patch("services.license_sdk.import_sdk_contracts", return_value={"SDKConfig": FakeConfig, "DEFAULT_CONFIG": FakeConfig()}), \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=fake_validator), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None), \
             mock.patch.object(self.routes_main.db, "sync_license_from_remote") as sync_mock:
            ok, message = self.routes_main.validate_license_key("NXR-BASICA-001", debug=False)

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia validada correctamente.")
        self.assertEqual(captured["config"].validation_url, "https://nuevo.supabase.co")
        self.assertEqual(captured["config"].supabase_key, "new-public-key")
        self.assertEqual(captured["config"].cache_file, "nuevo-cache.json")
        self.assertEqual(captured["config"].cache_ttl_days, "7")
        sync_mock.assert_called_once()

    def test_sdk_config_central_conserva_aliases_legacy(self):
        captured = {}

        class FakeConfig:
            @classmethod
            def from_env(cls):
                config = cls()
                config.validation_url = os.environ.get("NEXAR_LICENSES_VALIDATION_URL") or os.environ.get("SUPABASE_URL", "")
                config.supabase_key = os.environ.get("NEXAR_LICENSES_SUPABASE_KEY") or os.environ.get("SUPABASE_KEY", "")
                config.cache_file = os.environ.get("NEXAR_LICENSES_CACHE_FILE") or os.environ.get("NEXAR_CACHE_FILE", "")
                config.cache_ttl_days = os.environ.get("NEXAR_LICENSES_CACHE_TTL") or os.environ.get("NEXAR_CACHE_DAYS", "")
                return config

        def fake_validator(_licencia_dict, _public_key, _product_name, debug=False, *, config=None):
            captured["config"] = config
            return {"ok": False, "reason": "no_existe", "source": "online"}

        os.environ["SUPABASE_URL"] = "https://legacy.supabase.co"
        os.environ["SUPABASE_KEY"] = "legacy-key"
        os.environ["NEXAR_CACHE_FILE"] = "legacy-cache.json"
        os.environ["NEXAR_CACHE_DAYS"] = "4"

        with mock.patch("services.license_sdk.import_sdk_contracts", return_value={"SDKConfig": FakeConfig, "DEFAULT_CONFIG": FakeConfig()}), \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=fake_validator), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None):
            ok, _message = self.routes_main.validate_license_key("NXR-NOEXISTE-001", debug=False)

        self.assertFalse(ok)
        self.assertEqual(captured["config"].validation_url, "https://legacy.supabase.co")
        self.assertEqual(captured["config"].supabase_key, "legacy-key")
        self.assertEqual(captured["config"].cache_file, "legacy-cache.json")
        self.assertEqual(captured["config"].cache_ttl_days, "4")

    def test_validate_license_key_fallback_online_resuelve_y_persiste_cache(self):
        remote_payload = {
            "license_key": "NXR-PRO-001",
            "plan": "PRO",
            "tier": "PRO",
            "expires_at": (date.today() + timedelta(days=15)).isoformat(),
            "modules": ["core", "reportes"],
        }

        def fake_resolver(payload):
            resolved = dict(payload)
            resolved["plan_original"] = "PRO"
            resolved["plan_efectivo"] = "PRO"
            resolved["effective_plan"] = "PRO"
            return resolved

        with mock.patch("services.license_sdk.import_sdk_contracts", return_value={"resolve_effective_license": fake_resolver}), \
             mock.patch("services.license_sdk.import_validar_licencia_detalle", return_value=lambda *args, **kwargs: {"ok": False, "reason": "sin_cache", "source": "online"}), \
             mock.patch("services.license_sdk.import_validar_licencia", return_value=None), \
             mock.patch("services.license_sdk.get_current_hwid", return_value="HWID-1"), \
             mock.patch("services.license_sdk._save_sdk_cache") as save_cache_mock, \
             mock.patch("services.supabase_license_api.activate_license", return_value=(True, "ok", remote_payload)), \
             mock.patch.object(self.routes_main.db, "sync_license_from_remote") as sync_mock:
            ok, message = self.routes_main.validate_license_key("NXR-PRO-001", debug=False)

        self.assertTrue(ok)
        self.assertEqual(message, "Licencia validada correctamente.")
        sync_mock.assert_called_once()
        self.assertEqual(sync_mock.call_args.args[0]["plan_original"], "PRO")
        self.assertEqual(sync_mock.call_args.args[0]["plan_efectivo"], "PRO")
        save_cache_mock.assert_called()

    def test_resolucion_sdk_no_mantiene_full_si_licencia_remota_esta_suspendida(self):
        resolved = self.license_sdk._resolve_effective_license_data({
            "license_key": "NXR-FULL-001",
            "plan": "FULL",
            "tier": "FULL",
            "estado": "suspendida",
            "activa": True,
            "plan_base_permanente": False,
        })

        self.assertEqual(resolved["estado"], "suspendida")
        self.assertEqual(resolved["tier"], "SIN_PLAN")
        self.assertEqual(resolved["plan_efectivo"], "SIN_PLAN")

    def test_supabase_license_api_prefiere_variables_nexar_licenses_y_timeouts(self):
        import services.supabase_license_api as supabase_api

        os.environ["NEXAR_LICENSES_VALIDATION_URL"] = "https://nuevo.supabase.co/rest/v1"
        os.environ["NEXAR_LICENSES_SUPABASE_KEY"] = "new-public-key"
        os.environ["NEXAR_LICENSES_CONNECT_TIMEOUT"] = "2"
        os.environ["NEXAR_LICENSES_READ_TIMEOUT"] = "8"
        os.environ["SUPABASE_URL"] = "https://legacy.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "legacy-anon"

        self.assertTrue(supabase_api.is_configured())
        self.assertEqual(
            supabase_api.build_supabase_rest_url("licencias"),
            "https://nuevo.supabase.co/rest/v1/licencias",
        )
        self.assertEqual(supabase_api._headers()["apikey"], "new-public-key")
        self.assertEqual(supabase_api._request_timeout(), (2.0, 8.0))

    def test_debug_y_logs_no_exponen_secretos_de_configuracion_sdk(self):
        secret = "super-secret-token"

        class BrokenConfig:
            @classmethod
            def from_env(cls):
                raise RuntimeError(secret)

        os.environ["NEXAR_LICENSES_SUPABASE_KEY"] = secret

        with self.assertLogs("services.license_sdk", level="WARNING") as logs:
            with mock.patch("services.license_sdk.import_sdk_contracts", return_value={"SDKConfig": BrokenConfig, "DEFAULT_CONFIG": None}):
                config = self.license_sdk.get_sdk_config()

        self.assertIsNone(config)
        self.assertNotIn(secret, "\n".join(logs.output))
        self.assertNotIn(secret, str(self.license_sdk.get_license_debug_state()))

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
            "tier": "SIN_PLAN",
            "plan": "PRO",
            "plan_original": "PRO",
            "plan_efectivo": "SIN_PLAN",
            "effective_plan": "SIN_PLAN",
            "estado": "pro_vencida",
            "fallback_aplicado": False,
            "plan_base_permanente": True,
            "expirada": True,
            "modules": [],
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}
                session["_csrf_token"] = "test"

            fake_user = {"security_question": "q", "security_answer_hash": "hash"}
            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value=fake_license), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"license_modules": "[]"}), \
                 mock.patch.object(self.routes_main, "get_license_debug_state", return_value={"validation_mode": "cache", "modules": ["core"], "last_error": "", "masked_license_key": "NXR...001"}), \
                 mock.patch.object(self.routes_main, "get_modulos_debug_info", return_value={"final_modules": ["core"], "tier_modules": ["core"], "final_source": "db_tier"}), \
                 mock.patch.object(self.routes_main, "get_supabase_debug_state", return_value={"configured": False}), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-TDA-TEST-001"}), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=fake_license), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module.db, "q", return_value=fake_user):
                response = client.get("/api/licencia/estado")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["plan_original"], "PRO")
        self.assertEqual(payload["plan_efectivo"], "SIN_PLAN")
        self.assertEqual(payload["estado"], "pro_vencida")
        self.assertFalse(payload["fallback_aplicado"])
        self.assertEqual(payload["license_status"]["estado_comercial"], "pro_vencido")

    def test_pro_con_sin_plan_no_queda_como_mensual_activo(self):
        status = get_license_status_context({
            "key": "NXR-PRO-SINPLAN-001",
            "tier": "SIN_PLAN",
            "plan": "PRO",
            "plan_original": "PRO",
            "plan_efectivo": "SIN_PLAN",
            "effective_plan": "SIN_PLAN",
            "estado": "sin_licencia_remota",
            "expirada": False,
            "expires_at": (date.today() + timedelta(days=30)).isoformat(),
        })

        self.assertEqual(status["estado_comercial"], "sin_plan")
        self.assertFalse(status["licencia_utilizable"])

    def test_full_con_sin_plan_no_queda_como_mensual_activo(self):
        status = get_license_status_context({
            "key": "NXR-FULL-SINPLAN-001",
            "tier": "SIN_PLAN",
            "plan": "FULL",
            "plan_original": "FULL",
            "plan_efectivo": "SIN_PLAN",
            "effective_plan": "SIN_PLAN",
            "estado": "sin_licencia_remota",
            "expirada": False,
            "expires_at": (date.today() + timedelta(days=30)).isoformat(),
        })

        self.assertEqual(status["estado_comercial"], "sin_plan")
        self.assertFalse(status["licencia_utilizable"])

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

    def test_licencia_y_mi_plan_son_accesibles_con_recuperacion_pendiente(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "", "security_answer_hash": ""}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.routes_main.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={}), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "SIN_PLAN", "key": "INVALID"}), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_config", return_value={}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "SIN_PLAN", "key": "INVALID"}), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "INVALID"}), \
                 mock.patch.object(self.app_module, "validate_saved_license", return_value=(False, "invalid")):
                response_recovery = client.get("/configurar-recuperacion", follow_redirects=False)
                response_licencia = client.get("/licencia", follow_redirects=False)
                response_mi_plan = client.get("/mi-plan", follow_redirects=False)

        self.assertEqual(response_recovery.status_code, 200)
        self.assertEqual(response_licencia.status_code, 200)
        self.assertEqual(response_mi_plan.status_code, 200)

    def test_dashboard_demo_activo_no_redirige_a_licencia_por_license_key_invalida(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"demo": True, "vencido": False}), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "SIN_PLAN", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config", return_value={}), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_onboarding_context", return_value={}), \
                 mock.patch.object(self.app_module.db, "debe_mostrar_aviso_rubro_pendiente", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_resumen_dashboard_financiero", return_value={}), \
                 mock.patch.object(self.app_module.db, "get_facturas_proveedores_vencidas_resumen", return_value=[]), \
                 mock.patch.object(self.app_module.db, "get_facturas_proveedores_por_vencer_resumen", return_value=[]), \
                 mock.patch.object(self.app_module.db, "get_clientes_con_deuda", return_value=[]), \
                 mock.patch.object(self.app_module.db, "get_dashboard_stats", return_value={}), \
                 mock.patch.object(self.routes_main, "render_template", return_value="dashboard"), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "INVALID"}), \
                 mock.patch.object(self.app_module, "validate_saved_license", return_value=(False, "invalid")):
                response = client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 200)

    def test_pro_vencida_bloquea_operaciones_y_mantiene_recuperacion_accesible(self):
        app = self.app_module.create_app()
        expired_license = {
            "key": "NXR-PRO-001",
            "tier": "SIN_PLAN",
            "plan": "PRO",
            "plan_original": "PRO",
            "plan_efectivo": "SIN_PLAN",
            "estado": "pro_vencida",
            "expirada": True,
            "modules": [],
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"vencido": True, "demo": False}), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=expired_license), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-PRO-001"}), \
                 mock.patch.object(self.routes_main, "refresh_saved_license_online", return_value=(False, "offline", expired_license)), \
                 mock.patch.object(self.routes_main, "render_template", return_value="ok"):
                blocked = client.get("/productos/nuevo", follow_redirects=False)
                mi_plan = client.get("/mi-plan", follow_redirects=False)
                licencia = client.get("/licencia", follow_redirects=False)
                api_estado = client.get("/api/licencia/estado", follow_redirects=False)

        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(blocked.headers["Location"].endswith("/mi-plan"))
        self.assertEqual(mi_plan.status_code, 200)
        self.assertEqual(licencia.status_code, 200)
        self.assertEqual(api_estado.status_code, 200)

    def test_demo_vencida_bloquea_dashboard_y_permite_comprar_plan(self):
        app = self.app_module.create_app()
        demo_info = {"key": "", "tier": "DEMO", "plan": "DEMO", "plan_original": "DEMO"}
        demo_status = {"demo": True, "vencido": True, "dias_restantes": 0, "dias_demo": 14}

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value=demo_status), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=demo_info), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value=None), \
                 mock.patch.object(self.routes_main, "refresh_saved_license_online", return_value=(False, "sin licencia", demo_info)), \
                 mock.patch.object(self.routes_main, "render_template", return_value="ok"):
                blocked = client.get("/", follow_redirects=False)
                mi_plan = client.get("/mi-plan", follow_redirects=False)

        actions = self.routes_main._get_plan_actions_context(demo_info, license_status=get_license_status_context(demo_info, demo_status=demo_status))
        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(blocked.headers["Location"].endswith("/mi-plan"))
        self.assertEqual(mi_plan.status_code, 200)
        self.assertEqual(actions["planes_comprables"], ["BASICA", "PRO", "FULL"])

    def test_basica_bloqueada_con_basica_activada_no_restaurada_redirige_a_mi_plan(self):
        app = self.app_module.create_app()
        blocked_license = {
            "key": "NXR-BASICA-BLOCK-001",
            "tier": "SIN_PLAN",
            "plan": "BASICA",
            "plan_original": "BASICA",
            "plan_efectivo": "SIN_PLAN",
            "effective_plan": "SIN_PLAN",
            "estado": "bloqueada",
            "plan_base_permanente": False,
            "expirada": False,
            "modules": [],
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"vencido": True, "demo": False}), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=blocked_license), \
                 mock.patch.object(self.app_module.db, "get_config", return_value={"basica_activada": "1"}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-BASICA-BLOCK-001"}), \
                 mock.patch.object(self.app_module, "validate_saved_license", return_value=(False, "invalid")), \
                 mock.patch.object(self.routes_main, "refresh_saved_license_online", return_value=(False, "blocked", blocked_license)), \
                 mock.patch.object(self.routes_main, "render_template", return_value="ok"):
                blocked = client.get("/productos/nuevo", follow_redirects=False)
                mi_plan = client.get("/mi-plan", follow_redirects=False)

        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(blocked.headers["Location"].endswith("/mi-plan"))
        self.assertEqual(mi_plan.status_code, 200)

    def test_full_sin_licencia_remota_bloquea_rutas_de_negocio_y_permite_mi_plan(self):
        app = self.app_module.create_app()
        no_remote_license = {
            "key": "NXR-FULL-SINPLAN-001",
            "tier": "SIN_PLAN",
            "plan": "FULL",
            "plan_original": "FULL",
            "plan_efectivo": "SIN_PLAN",
            "effective_plan": "SIN_PLAN",
            "estado": "sin_licencia_remota",
            "expirada": False,
            "modules": [],
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"vencido": True, "demo": False}), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=no_remote_license), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-FULL-SINPLAN-001"}), \
                 mock.patch.object(self.routes_main, "refresh_saved_license_online", return_value=(False, "sin licencia remota", no_remote_license)), \
                 mock.patch.object(self.routes_main, "render_template", return_value="ok"):
                blocked = client.get("/productos/nuevo", follow_redirects=False)
                mi_plan = client.get("/mi-plan", follow_redirects=False)
                licencia = client.get("/licencia", follow_redirects=False)

        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(blocked.headers["Location"].endswith("/mi-plan"))
        self.assertEqual(mi_plan.status_code, 200)
        self.assertEqual(licencia.status_code, 200)

    def test_login_demo_con_next_mi_plan_vuelve_al_dashboard(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test-token"

            user = {
                "id": 1,
                "username": "admin",
                "nombre_completo": "Administrador",
                "rol": "Administrador",
                "activo": 1,
                "password_hash": "hash",
                "security_question": "Color",
                "security_answer_hash": "hash2",
            }

            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_usuario_by_username", return_value=user), \
                 mock.patch.object(self.routes_main.db, "verify_password", return_value=True), \
                 mock.patch.object(self.routes_main.db, "get_demo_status", return_value={"vencido": False}), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "DEMO"}):
                response = client.post(
                    "/login",
                    data={
                        "username": "admin",
                        "password": "secret",
                        "next": "/mi-plan",
                        "csrf_token": "test-token",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))

    def test_login_con_demo_vencido_puede_respetar_next_mi_plan(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test-token"

            user = {
                "id": 1,
                "username": "admin",
                "nombre_completo": "Administrador",
                "rol": "Administrador",
                "activo": 1,
                "password_hash": "hash",
                "security_question": "Color",
                "security_answer_hash": "hash2",
            }

            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_usuario_by_username", return_value=user), \
                 mock.patch.object(self.routes_main.db, "verify_password", return_value=True), \
                 mock.patch.object(self.routes_main.db, "get_demo_status", return_value={"vencido": True}), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value={"tier": "SIN_PLAN"}):
                response = client.post(
                    "/login",
                    data={
                        "username": "admin",
                        "password": "secret",
                        "next": "/mi-plan",
                        "csrf_token": "test-token",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/mi-plan"))

    def test_close_warning_demo_activo_sigue_accesible_con_license_key_invalida(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"vencido": False}), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "SIN_PLAN", "key": ""}), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "INVALID"}), \
                 mock.patch.object(self.app_module, "validate_saved_license", return_value=(False, "invalid")), \
                 mock.patch.object(self.routes_main, "_caja_abierta", return_value=None):
                response = client.get("/api/desktop/close-warning", follow_redirects=False)

        self.assertEqual(response.status_code, 200)

    def test_apagar_rapido_devuelve_pantalla_de_apagado(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test-token"
                session["user"] = {"rol": "admin", "id": 1}

            response = client.post("/apagar-rapido", data={"csrf_token": "test-token"}, follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sistema cerrado", response.data)

    def test_windows_update_helper_script_espera_cierre_y_lanza_instalador(self):
        installer = Path(self.temp_dir.name) / "NexarTienda_1.32.0_Setup.exe"
        installer.write_text("stub", encoding="utf-8")

        script = self.routes_main._build_windows_update_launcher_script(
            installer=installer,
            target_version="1.32.0",
        )

        self.assertIn("Stop-Process -Id $AppPid -Force", script)
        self.assertIn("Start-Process -FilePath $InstallerPath", script)
        self.assertIn("Write-Status 'ready_restart'", script)
        self.assertIn(str(installer), script)

    def test_consume_windows_update_status_sincroniza_config_y_limpia_archivo(self):
        status_path = Path(self.temp_dir.name) / "windows_update_status.json"
        status_path.write_text(
            '{"status":"install_failed","target_version":"1.32.0","installer_name":"NexarTienda_1.32.0_Setup.exe","error":"boom","finished_at":"2026-05-13 10:00"}',
            encoding="utf-8",
        )

        with mock.patch.object(self.routes_main, "WINDOWS_UPDATE_STATUS_PATH", status_path), \
             mock.patch.object(self.routes_main.db, "set_config") as mocked_set_config:
            self.routes_main._consume_windows_update_status()

        mocked_set_config.assert_called_once_with({
            "update_install_status": "install_failed",
            "update_finished_at": "2026-05-13 10:00",
            "update_install_error": "boom",
            "update_target_version": "1.32.0",
            "update_installer_name": "NexarTienda_1.32.0_Setup.exe",
        })
        self.assertFalse(status_path.exists())

    def test_actualizacion_instalar_windows_prepara_helper_y_cierra_app(self):
        app = self.app_module.create_app()
        installer = Path(self.temp_dir.name) / "NexarTienda_1.32.0_Setup.exe"
        installer.write_text("stub", encoding="utf-8")

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

            license_info = {"key": "NXR-TDA-TEST-001", "tier": "PRO", "updates": True}
            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_license_info", return_value=license_info), \
                 mock.patch.object(self.routes_main, "_update_file", return_value=installer), \
                 mock.patch.object(self.routes_main, "_installer_version", return_value="1.32.0"), \
                 mock.patch.object(self.routes_main, "_make_backup", return_value=Path("backup.db")), \
                 mock.patch.object(self.routes_main, "_write_windows_update_status") as mocked_write_status, \
                 mock.patch.object(self.routes_main, "_launch_windows_update_helper") as mocked_launch_helper, \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"vencido": False, "dias_restantes": 0}), \
                 mock.patch.object(self.app_module.db, "get_config", return_value={}), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=license_info), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-TDA-TEST-001"}):
                response = client.post(
                    "/respaldo/actualizacion/instalar/NexarTienda_1.32.0_Setup.exe",
                    data={"csrf_token": "test"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cerrando Nexar Comercio para actualizar", response.data)
        mocked_write_status.assert_called_once_with(
            "in_progress",
            target_version="1.32.0",
            installer_name="NexarTienda_1.32.0_Setup.exe",
        )
        mocked_launch_helper.assert_called_once_with(installer=installer, target_version="1.32.0")

    def test_inno_setup_no_relanzamiento_automatico_postinstall(self):
        iss_template = (PROJECT_ROOT / "build" / "nexar_tienda.iss").read_text(encoding="utf-8")
        self.assertNotIn("Flags: nowait postinstall", iss_template)
        self.assertNotIn('Description: "Iniciar {#AppName} ahora"', iss_template)

    def test_rubros_visibles_se_limitan_a_tienda_y_almacen(self):
        self.assertEqual(get_rubros_disponibles(), ["tienda", "almacen"])

    def test_registro_inicial_guarda_admin_rubro_y_datos_comercio(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test"
            response = client.post(
                "/registro-inicial",
                data={
                    "csrf_token": "test",
                    "nombre_completo": "Admin Comercio",
                    "username": "admin",
                    "admin_email": "admin@comercio.com",
                    "admin_telefono": "264123456",
                    "password": "Abc123$",
                    "password_confirm": "Abc123$",
                    "accept_license_agreement": "1",
                    "rubro": "almacen",
                    "nombre_negocio": "Comercio Central",
                    "cuit": "20-12345678-9",
                    "direccion": "Calle Falsa 123",
                    "localidad": "San Juan",
                    "provincia": "San Juan",
                    "negocio_email": "ventas@comercio.com",
                    "telefono": "264555000",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        usuario = self.database.get_usuario_by_username("admin")
        cfg = self.database.get_config()
        self.assertEqual(usuario["email"], "admin@comercio.com")
        self.assertEqual(usuario["telefono"], "264123456")
        self.assertEqual(self.database.get_rubro_configurado(), "almacen")
        self.assertEqual(cfg["nombre_negocio"], "Comercio Central")
        self.assertEqual(cfg["localidad"], "San Juan")
        self.assertEqual(cfg["provincia"], "San Juan")
        self.assertEqual(cfg["negocio_email"], "ventas@comercio.com")

    def test_registro_inicial_requiere_aceptacion_licencia(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_csrf_token"] = "test"
            response = client.post(
                "/registro-inicial",
                data={
                    "csrf_token": "test",
                    "nombre_completo": "Admin Comercio",
                    "username": "admin",
                    "admin_email": "admin@comercio.com",
                    "admin_telefono": "264123456",
                    "password": "Abc123$",
                    "password_confirm": "Abc123$",
                    "rubro": "almacen",
                    "nombre_negocio": "Comercio Central",
                    "cuit": "20-12345678-9",
                    "direccion": "Calle Falsa 123",
                    "localidad": "San Juan",
                    "provincia": "San Juan",
                    "negocio_email": "ventas@comercio.com",
                    "telefono": "264555000",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Debés aceptar el Acuerdo de Licencia de Uso para continuar.".encode("utf-8"), response.data)
        self.assertIsNone(self.database.get_usuario_by_username("admin"))

    def test_acuerdo_licencia_es_publico_y_muestra_license_txt(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            response = client.get("/acuerdo-licencia")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Nexar Sistemas".encode("utf-8"), response.data)
        self.assertIn("aceptación completa".encode("utf-8"), response.data)

    def test_licencia_activar_inicial_requiere_aceptacion(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"id": 1, "rol": "Administrador", "username": "admin"}
                session["_csrf_token"] = "test"
            with mock.patch.object(self.routes_main, "validate_license_key") as validate_mock:
                response = client.post(
                    "/licencia/activar",
                    data={"csrf_token": "test", "license_key": "NXR-TEST-001"},
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/licencia"))
        validate_mock.assert_not_called()

    def test_licencia_solicitar_inicial_requiere_aceptacion(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"id": 1, "rol": "Administrador", "username": "admin"}
                session["_csrf_token"] = "test"
            with mock.patch.object(self.routes_main, "create_license_request") as request_mock:
                response = client.post(
                    "/licencia/solicitar",
                    data={
                        "csrf_token": "test",
                        "activation_id": "HWID-1",
                        "nombre": "Admin Comercio",
                        "email": "admin@comercio.com",
                        "whatsapp": "264123456",
                        "plan": "BASICA",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/licencia"))
        request_mock.assert_not_called()

    def test_middleware_redirige_a_activacion_inicial_si_queda_pendiente(self):
        app = self.app_module.create_app()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "admin", "id": 1, "username": "admin"}

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"demo": True, "vencido": False, "dias_restantes": 14}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.app_module.db, "get_config", return_value={}), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q):
                response = client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/activacion-inicial"))

    def test_activacion_inicial_muestra_planes_independientes_y_pago_pendiente(self):
        app = self.app_module.create_app()
        self.database.set_config({
            "activation_initial_completed": "0",
            "activation_checkout_status": "iniciado",
            "activation_checkout_plan": "PRO",
            "activation_checkout_activation_id": "NXID-PENDING-UI",
        })
        config_snapshot = dict(self.database.get_config())

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                if "FROM config" in query:
                    if fetchone and params:
                        return {"valor": config_snapshot.get(params[0])}
                    return [{"clave": key, "valor": value} for key, value in config_snapshot.items()]
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default):
                response = client.get("/activacion-inicial")

        self.assertEqual(response.status_code, 200)
        self.assertIn("DEMO, BASICA, PRO y FULL son caminos independientes".encode("utf-8"), response.data)
        self.assertIn(b'value="BASICA"', response.data)
        self.assertIn(b'value="PRO"', response.data)
        self.assertIn(b'value="FULL"', response.data)
        self.assertIn("Pago pendiente de verificación".encode("utf-8"), response.data)
        self.assertIn(b"Ya pag", response.data)

    def test_activacion_inicial_demo_guarda_datos_y_habilita_ingreso(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({
            "activation_initial_completed": "0",
            "demo_install_date": "2099-01-01",
            "demo_dias": "14",
            "demo_expires_at": "2099-01-15",
        })
        config_snapshot = dict(self.database.get_config())

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                if "FROM config" in query:
                    if fetchone and params:
                        return {"valor": config_snapshot.get(params[0])}
                    return [{"clave": key, "valor": value} for key, value in config_snapshot.items()]
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value=None), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", return_value=(True, "ok", [])), \
                 mock.patch.object(self.routes_main, "create_demo_request", return_value=(True, "ok")) as create_demo_request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                        "marketing_opt_in": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))
        cfg = self.database.get_config()
        self.assertEqual(cfg["activation_initial_completed"], "1")
        self.assertEqual(cfg["activation_initial_plan"], "DEMO")
        self.assertEqual(cfg["license_owner_name"], "Admin Comercio")
        self.assertEqual(cfg["license_owner_email"], "admin@comercio.com")
        self.assertEqual(cfg["license_marketing_opt_in"], "1")
        self.assertEqual(cfg["activation_demo_request_key"], "NXID-DEMO-001|admin@comercio.com|nexar-tienda")
        expected_started = date.today()
        expected_expires = expected_started + timedelta(days=14)
        self.assertEqual(cfg["demo_install_date"], expected_started.isoformat())
        self.assertEqual(cfg["demo_expires_at"], expected_expires.isoformat())
        self.assertEqual(self.database.get_rubro_configurado(), "almacen")
        self.assertEqual(create_demo_request_mock.call_args.kwargs["estado"], "pendiente")
        self.assertEqual(create_demo_request_mock.call_args.kwargs["plan_interes"], "DEMO_14_DIAS")
        self.assertIn('"activation_id": "NXID-DEMO-001"', create_demo_request_mock.call_args.kwargs["mensaje"])
        self.assertIn(f'"demo_started_at": "{expected_started.isoformat()}"', create_demo_request_mock.call_args.kwargs["mensaje"])
        self.assertIn(f'"demo_expires_at": "{expected_expires.isoformat()}"', create_demo_request_mock.call_args.kwargs["mensaje"])
        self.assertIn('"demo_status": "demo_activa"', create_demo_request_mock.call_args.kwargs["mensaje"])
        self.assertIn('"identity_hashes"', create_demo_request_mock.call_args.kwargs["mensaje"])

    def test_activacion_inicial_demo_reintento_no_duplica_envio_remoto(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({
            "activation_initial_completed": "0",
            "activation_demo_request_key": "NXID-DEMO-001|admin@comercio.com|nexar-tienda",
        })

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.routes_main, "create_demo_request") as create_demo_request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))
        create_demo_request_mock.assert_not_called()

    def test_activacion_inicial_demo_no_guarda_dedupe_si_falla_envio_remoto(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({"activation_initial_completed": "0"})

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", side_effect=[(True, "ok", []), (False, "network", [])]), \
                 mock.patch.object(self.routes_main, "create_demo_request", return_value=(False, "Error en Supabase (400).")) as create_demo_request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("No pudimos verificar si este equipo ya utiliz".encode("utf-8"), response.data)
        cfg = self.database.get_config()
        self.assertEqual(cfg["activation_initial_completed"], "0")
        self.assertNotIn("activation_demo_request_key", cfg)
        self.assertEqual(cfg["activation_demo_eligibility_state"], "offline_unverified")
        create_demo_request_mock.assert_called_once()

    def test_activacion_inicial_demo_remota_vencida_bloquea_base_local_nueva(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({"activation_initial_completed": "0"})
        expired_record = {
            "producto": "nexar-tienda",
            "email": "admin@comercio.com",
            "mensaje": (
                '{"activation_id":"NXID-DEMO-001","demo_started_at":"2026-01-01",'
                '"demo_expires_at":"2026-01-15","demo_status":"demo_vencida"}'
            ),
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", return_value=(True, "ok", [expired_record])), \
                 mock.patch.object(self.routes_main, "create_demo_request") as create_demo_request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Este equipo ya utiliz".encode("utf-8"), response.data)
        cfg = self.database.get_config()
        self.assertEqual(cfg["activation_initial_completed"], "0")
        self.assertEqual(cfg["activation_demo_eligibility_state"], "expired")
        create_demo_request_mock.assert_not_called()

    def test_activacion_inicial_demo_remota_activa_recupera_sin_extender(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({"activation_initial_completed": "0"})
        active_record = {
            "producto": "nexar-tienda",
            "email": "admin@comercio.com",
            "mensaje": (
                '{"activation_id":"NXID-DEMO-001","demo_started_at":"2099-01-01",'
                '"demo_expires_at":"2099-01-15","demo_status":"demo_activa"}'
            ),
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", return_value=(True, "ok", [active_record])), \
                 mock.patch.object(self.routes_main, "create_demo_request") as create_demo_request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        cfg = self.database.get_config()
        self.assertEqual(cfg["activation_initial_completed"], "1")
        self.assertEqual(cfg["demo_install_date"], "2099-01-01")
        self.assertEqual(cfg["demo_expires_at"], "2099-01-15")
        create_demo_request_mock.assert_not_called()

    def test_demo_eligibility_usa_identidad_fuerte_y_no_email_solo(self):
        from services.demo_eligibility import build_demo_identity, resolve_demo_eligibility_from_records

        identity = build_demo_identity(
            product="nexar-tienda",
            activation_id=" NXID-ABC ",
            hardware_id="",
            email="admin@comercio.com",
            machine_details={},
        )
        email_only = [{"producto": "nexar-tienda", "email": "admin@comercio.com", "mensaje": "{}"}]
        self.assertEqual(resolve_demo_eligibility_from_records(identity=identity, records=email_only).state, "eligible")

        matching = [{"producto": "nexar-tienda", "email": "otro@comercio.com", "mensaje": '{"activation_id":"nxid-abc"}'}]
        self.assertEqual(resolve_demo_eligibility_from_records(identity=identity, records=matching).state, "already_used")

    def test_demo_eligibility_bloqueo_administrativo_prevalece_sobre_fila_activa(self):
        from services.demo_eligibility import build_demo_identity, resolve_demo_eligibility_from_records

        identity = build_demo_identity(
            product="nexar-tienda",
            activation_id="NXID-ABC",
            hardware_id="HWID-ABC",
            email="admin@comercio.com",
            machine_details={},
        )
        records = [
            {
                "id": 20,
                "producto": "nexar-tienda",
                "estado": "pendiente",
                "mensaje": '{"activation_id":"NXID-ABC","demo_started_at":"2099-01-01","demo_expires_at":"2099-01-15"}',
                "created_at": "2099-01-01T10:00:00",
            },
            {
                "id": 21,
                "producto": "nexar-tienda",
                "estado": "bloqueada",
                "mensaje": '{"activation_id":"NXID-ABC"}',
                "created_at": "2098-12-31T09:00:00",
            },
        ]

        result = resolve_demo_eligibility_from_records(identity=identity, records=records, today=date(2099, 1, 2))
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.matched_record["id"], 21)

    def test_demo_eligibility_bloqueo_suspendido_prevalece_sobre_vencida(self):
        from services.demo_eligibility import build_demo_identity, resolve_demo_eligibility_from_records

        identity = build_demo_identity(
            product="nexar-tienda",
            activation_id="NXID-ABC",
            hardware_id="",
            email="admin@comercio.com",
            machine_details={},
        )
        records = [
            {
                "id": 30,
                "producto": "nexar-tienda",
                "estado": "pendiente",
                "mensaje": '{"activation_id":"NXID-ABC","demo_started_at":"2026-01-01","demo_expires_at":"2026-01-15"}',
                "created_at": "2026-01-01T10:00:00",
            },
            {
                "id": 31,
                "producto": "nexar-tienda",
                "estado": "suspendida",
                "mensaje": '{"activation_id":"NXID-ABC"}',
                "created_at": "2026-01-20T10:00:00",
            },
        ]

        result = resolve_demo_eligibility_from_records(identity=identity, records=records, today=date(2026, 2, 1))
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.matched_record["id"], 31)

    def test_demo_eligibility_selecciona_activa_de_forma_determinista_sin_extender(self):
        from services.demo_eligibility import build_demo_identity, resolve_demo_eligibility_from_records

        identity = build_demo_identity(
            product="nexar-tienda",
            activation_id="NXID-ABC",
            hardware_id="",
            email="admin@comercio.com",
            machine_details={},
        )
        records = [
            {
                "id": 41,
                "producto": "nexar-tienda",
                "estado": "pendiente",
                "mensaje": '{"activation_id":"NXID-ABC","demo_started_at":"2099-01-01","demo_expires_at":"2099-01-20"}',
                "created_at": "2099-01-01T10:00:00",
            },
            {
                "id": 40,
                "producto": "nexar-tienda",
                "estado": "pendiente",
                "mensaje": '{"activation_id":"NXID-ABC","demo_started_at":"2099-01-01","demo_expires_at":"2099-01-15"}',
                "created_at": "2099-01-02T10:00:00",
            },
        ]

        result = resolve_demo_eligibility_from_records(identity=identity, records=records, today=date(2099, 1, 5))
        self.assertEqual(result.state, "active")
        self.assertEqual(result.expires_at, "2099-01-15")
        self.assertEqual(result.matched_record["id"], 40)

    def test_find_demo_requests_for_identity_consulta_solicitudes_demo_por_identidad(self):
        import services.supabase_license_api as supabase_api

        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ["SUPABASE_KEY"] = "service-key"
        response = mock.Mock(status_code=200, text="[]")
        response.json.return_value = []

        with mock.patch.object(supabase_api.requests, "get", return_value=response) as get_mock:
            ok, message, rows = supabase_api.find_demo_requests_for_identity(
                producto="nexar-tienda",
                activation_id="NXID-DEMO-001",
                hardware_id="HWID-001",
            )

        self.assertTrue(ok)
        self.assertIn("completada", message.lower())
        self.assertEqual(rows, [])
        params = get_mock.call_args.kwargs["params"]
        self.assertEqual(params["producto"], "eq.nexar-tienda")
        self.assertIn("mensaje.ilike.*NXID-DEMO-001*", params["or"])
        self.assertIn("mensaje.ilike.*HWID-001*", params["or"])

    def test_create_demo_request_reintenta_solo_por_incompatibilidad_de_esquema(self):
        import services.supabase_license_api as supabase_api

        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ.pop("SUPABASE_ANON_KEY", None)
        os.environ["SUPABASE_KEY"] = "service-key"

        bad_response = mock.Mock(status_code=400, text='{"message":"column origen does not exist"}')
        bad_response_2 = mock.Mock(status_code=400, text='{"message":"Could not find the \'estado\' column of \'solicitudes_demo\' in the schema cache","code":"PGRST204"}')
        ok_response = mock.Mock(status_code=201, text='[{"id":1}]')

        with mock.patch.object(supabase_api.requests, "post", side_effect=[bad_response, bad_response_2, ok_response]) as post_mock:
            ok, message = supabase_api.create_demo_request(
                nombre="Admin Comercio",
                email="admin@comercio.com",
                telefono="264555000",
                negocio="Comercio Central",
                producto="nexar-tienda",
                plan_interes="DEMO_14_DIAS",
                mensaje='{"activation_id":"NXID-DEMO-001","identity_hashes":{"activation_id":"hash-1","hardware_id":"hash-2","machine_id":"hash-3"}}',
                origen="app_activacion_inicial",
                estado="pendiente",
            )

        self.assertTrue(ok)
        self.assertIn("registrada correctamente", message.lower())
        self.assertEqual(post_mock.call_count, 3)
        self.assertEqual(post_mock.call_args_list[0].args[0], "https://demo.supabase.co/rest/v1/solicitudes_demo")
        self.assertEqual(post_mock.call_args_list[0].kwargs["headers"]["apikey"], "service-key")
        self.assertEqual(post_mock.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer service-key")
        self.assertEqual(post_mock.call_args_list[0].kwargs["headers"]["Prefer"], "return=minimal")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["estado"], "pendiente")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["origen"], "app_activacion_inicial")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["leida"], False)
        self.assertNotIn("origen", post_mock.call_args_list[1].kwargs["json"])
        self.assertIn("identity_hash", post_mock.call_args_list[1].kwargs["json"])
        self.assertNotIn("estado", post_mock.call_args_list[2].kwargs["json"])
        self.assertIn("identity_hash", post_mock.call_args_list[2].kwargs["json"])

    def test_create_demo_request_conflicto_409_no_reintenta_payload_legacy(self):
        import services.supabase_license_api as supabase_api

        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ["SUPABASE_KEY"] = "service-key"
        conflict_response = mock.Mock(status_code=409, text='{"message":"duplicate key value violates unique constraint","code":"23505"}')

        with mock.patch.object(supabase_api.requests, "post", return_value=conflict_response) as post_mock:
            ok, message = supabase_api.create_demo_request(
                nombre="Admin Comercio",
                email="admin@comercio.com",
                telefono="264555000",
                negocio="Comercio Central",
                producto="nexar-tienda",
                plan_interes="DEMO_14_DIAS",
                mensaje='{"activation_id":"NXID-DEMO-001","identity_hashes":{"activation_id":"hash-1"}}',
            )

        self.assertFalse(ok)
        self.assertIn("error en supabase", message.lower())
        self.assertEqual(post_mock.call_count, 1)

    def test_create_demo_request_duplicate_key_no_reintenta_payload_legacy(self):
        import services.supabase_license_api as supabase_api

        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ["SUPABASE_KEY"] = "service-key"
        duplicate_response = mock.Mock(status_code=400, text='{"message":"duplicate key value violates unique constraint idx_solicitudes_demo_producto_identity_hash_unique","code":"23505"}')

        with mock.patch.object(supabase_api.requests, "post", return_value=duplicate_response) as post_mock:
            ok, _message = supabase_api.create_demo_request(
                nombre="Admin Comercio",
                email="admin@comercio.com",
                telefono="264555000",
                negocio="Comercio Central",
                producto="nexar-tienda",
                plan_interes="DEMO_14_DIAS",
                mensaje='{"activation_id":"NXID-DEMO-001","identity_hashes":{"activation_id":"hash-1"}}',
            )

        self.assertFalse(ok)
        self.assertEqual(post_mock.call_count, 1)

    def test_create_demo_request_error_autorizacion_no_habilita_fallback(self):
        import services.supabase_license_api as supabase_api

        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ["SUPABASE_KEY"] = "service-key"
        auth_response = mock.Mock(status_code=403, text='{"message":"new row violates row-level security policy"}')

        with mock.patch.object(supabase_api.requests, "post", return_value=auth_response) as post_mock:
            ok, message = supabase_api.create_demo_request(
                nombre="Admin Comercio",
                email="admin@comercio.com",
                telefono="264555000",
                negocio="Comercio Central",
                producto="nexar-tienda",
                plan_interes="DEMO_14_DIAS",
                mensaje='{"activation_id":"NXID-DEMO-001","identity_hashes":{"activation_id":"hash-1"}}',
            )

        self.assertFalse(ok)
        self.assertIn("permisos o autenticaci", message.lower())
        self.assertEqual(post_mock.call_count, 1)

    def test_create_demo_request_error_500_no_habilita_fallback(self):
        import services.supabase_license_api as supabase_api

        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ["SUPABASE_KEY"] = "service-key"
        server_response = mock.Mock(status_code=500, text='{"message":"internal server error"}')

        with mock.patch.object(supabase_api.requests, "post", return_value=server_response) as post_mock:
            ok, _message = supabase_api.create_demo_request(
                nombre="Admin Comercio",
                email="admin@comercio.com",
                telefono="264555000",
                negocio="Comercio Central",
                producto="nexar-tienda",
                plan_interes="DEMO_14_DIAS",
                mensaje='{"activation_id":"NXID-DEMO-001","identity_hashes":{"activation_id":"hash-1"}}',
            )

        self.assertFalse(ok)
        self.assertEqual(post_mock.call_count, 1)

    def test_activacion_inicial_demo_conflicto_reconsulta_y_recupera_activa(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({"activation_initial_completed": "0"})
        active_record = {
            "producto": "nexar-tienda",
            "email": "admin@comercio.com",
            "mensaje": (
                '{"activation_id":"NXID-DEMO-001","demo_started_at":"2099-01-01",'
                '"demo_expires_at":"2099-01-15","demo_status":"demo_activa"}'
            ),
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", side_effect=[(True, "ok", []), (True, "ok", [active_record])]), \
                 mock.patch.object(self.routes_main, "create_demo_request", return_value=(False, "Error en Supabase (409).")) as create_demo_request_mock, \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))
        cfg = self.database.get_config()
        self.assertEqual(cfg["activation_initial_completed"], "1")
        self.assertEqual(cfg["demo_install_date"], "2099-01-01")
        self.assertEqual(cfg["demo_expires_at"], "2099-01-15")
        create_demo_request_mock.assert_called_once()

    def test_activacion_inicial_demo_conflicto_reconsulta_y_bloquea_si_esta_vencida(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({"activation_initial_completed": "0"})
        expired_record = {
            "producto": "nexar-tienda",
            "email": "admin@comercio.com",
            "mensaje": (
                '{"activation_id":"NXID-DEMO-001","demo_started_at":"2026-01-01",'
                '"demo_expires_at":"2026-01-15","demo_status":"demo_vencida"}'
            ),
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", side_effect=[(True, "ok", []), (True, "ok", [expired_record])]), \
                 mock.patch.object(self.routes_main, "create_demo_request", return_value=(False, "Error en Supabase (409).")), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Este equipo ya utiliz".encode("utf-8"), response.data)
        self.assertEqual(self.database.get_config()["activation_demo_eligibility_state"], "expired")

    def test_activacion_inicial_demo_conflicto_reconsulta_y_bloquea_si_hay_estado_administrativo(self):
        app = self.app_module.create_app()
        self.database.add_usuario("admin", "Abc123$", "Administrador", "Admin Comercio")
        self.database.set_config({"activation_initial_completed": "0"})
        blocked_record = {
            "producto": "nexar-tienda",
            "estado": "bloqueada",
            "email": "admin@comercio.com",
            "mensaje": '{"activation_id":"NXID-DEMO-001"}',
        }

        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = {"rol": "Administrador", "id": 1, "username": "admin"}
                session["_csrf_token"] = "test"

            def fake_q(query, params=(), fetchone=False, **kwargs):
                if "FROM usuarios" in query:
                    if "nombre_completo, email, telefono" in query:
                        return {"nombre_completo": "Admin Comercio", "email": "admin@comercio.com", "telefono": "264555000"}
                    return {"security_question": "Color", "security_answer_hash": "hash"}
                return {"valor": None} if fetchone else []

            with mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value={"tier": "DEMO", "key": ""}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: "0" if key == "activation_initial_completed" else default), \
                 mock.patch.object(self.routes_main, "find_demo_requests_for_identity", side_effect=[(True, "ok", []), (True, "ok", [blocked_record])]), \
                 mock.patch.object(self.routes_main, "create_demo_request", return_value=(False, "Error en Supabase (409).")), \
                 mock.patch.object(self.routes_main, "generate_activation_id", return_value=("NXID-DEMO-001", {"host": "demo"})), \
                 mock.patch.object(self.routes_main, "get_current_hwid", return_value="NXID-DEMO-001"):
                response = client.post(
                    "/activacion-inicial",
                    data={
                        "csrf_token": "test",
                        "titular_nombre": "Admin Comercio",
                        "negocio": "Comercio Central",
                        "email": "admin@comercio.com",
                        "telefono": "264555000",
                        "rubro": "almacen",
                        "plan_destino": "DEMO",
                        "accept_license_agreement": "1",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Contacta a soporte".encode("utf-8"), response.data)
        self.assertEqual(self.database.get_config()["activation_demo_eligibility_state"], "blocked")

    def test_rubro_inicial_queda_solo_lectura_si_ya_esta_configurado(self):
        self.database.set_rubro_configurado("tienda")
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

            fake_license = {"key": "NXR-TDA-TEST-001", "tier": "PRO", "updates": True}
            with mock.patch.object(self.routes_main.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.routes_main.db, "get_config", return_value={"rubro_negocio": "tienda", "rubro_negocio_confirmado": "1"}), \
                 mock.patch.object(self.app_module.db, "count_usuarios", return_value=1), \
                 mock.patch.object(self.app_module.db, "necesita_configuracion_inicial_rubro", return_value=False), \
                 mock.patch.object(self.app_module.db, "q", side_effect=fake_q), \
                 mock.patch.object(self.app_module.db, "get_license_info", return_value=fake_license), \
                 mock.patch.object(self.app_module.db, "get_demo_status", return_value={"vencido": False, "dias_restantes": 0}), \
                 mock.patch.object(self.app_module.db, "get_config", return_value={"rubro_negocio": "tienda", "rubro_negocio_confirmado": "1"}), \
                 mock.patch.object(self.app_module.db, "get_config_valor", side_effect=lambda key, default=None: default), \
                 mock.patch.object(self.app_module, "cargar_licencia", return_value={"license_key": "NXR-TDA-TEST-001"}):
                response = client.get("/configuracion/rubro-inicial")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"contact", response.data.lower())


if __name__ == "__main__":
    unittest.main()
