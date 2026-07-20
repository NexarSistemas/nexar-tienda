import unittest
from unittest import mock

from services import pricing_resolver


class PricingResolverTests(unittest.TestCase):
    def setUp(self):
        pricing_resolver.clear_runtime_price_cache()

    def test_lee_precio_activo_desde_supabase(self):
        rows = [
            {
                "producto": "nexar-tienda",
                "plan_comercial": "FULL",
                "plan_tecnico": "MENSUAL_FULL",
                "monto": 19900,
                "estado": "activo",
                "vigencia_desde": "2026-01-01T00:00:00Z",
                "vigencia_hasta": None,
            }
        ]
        fake_response = mock.Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.text = "ok"
        fake_response.json.return_value = rows

        with mock.patch("services.pricing_resolver.os.getenv", side_effect=lambda key, default="": {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        }.get(key, default)), mock.patch("services.pricing_resolver.requests.get", return_value=fake_response):
            result = pricing_resolver.resolve_plan_price("FULL", producto="nexar-tienda")

        self.assertEqual(result["plan"], "FULL")
        self.assertEqual(result["monto"], 19900)
        self.assertEqual(result["source"], "supabase")

    def test_usa_fallback_si_supabase_falla(self):
        with mock.patch("services.pricing_resolver.os.getenv", side_effect=lambda key, default="": {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        }.get(key, default)), mock.patch(
            "services.pricing_resolver.requests.get",
            side_effect=pricing_resolver.requests.RequestException("network down"),
        ):
            result = pricing_resolver.resolve_plan_price("PRO", producto="nexar-tienda")

        self.assertEqual(result["plan"], "PRO")
        self.assertEqual(result["monto"], 9900)
        self.assertEqual(result["source"], "fallback_local")

    def test_resuelve_varios_planes_con_una_sola_consulta_remota(self):
        rows = [
            {
                "producto": "nexar-tienda",
                "plan_comercial": "BASICA",
                "plan_tecnico": "BASICA",
                "monto": 49900,
                "estado": "activo",
                "vigencia_desde": "2026-01-01T00:00:00Z",
                "vigencia_hasta": None,
            },
            {
                "producto": "nexar-tienda",
                "plan_comercial": "PRO",
                "plan_tecnico": "PRO",
                "monto": 9900,
                "estado": "activo",
                "vigencia_desde": "2026-01-01T00:00:00Z",
                "vigencia_hasta": None,
            },
            {
                "producto": "nexar-tienda",
                "plan_comercial": "FULL",
                "plan_tecnico": "MENSUAL_FULL",
                "monto": 19900,
                "estado": "activo",
                "vigencia_desde": "2026-01-01T00:00:00Z",
                "vigencia_hasta": None,
            },
        ]
        fake_response = mock.Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.text = "ok"
        fake_response.json.return_value = rows

        with mock.patch("services.pricing_resolver.os.getenv", side_effect=lambda key, default="": {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        }.get(key, default)), mock.patch("services.pricing_resolver.requests.get", return_value=fake_response) as get_mock:
            result = pricing_resolver.resolve_plan_prices(["BASICA", "PRO", "FULL"], producto="nexar-tienda")

        self.assertEqual(get_mock.call_count, 1)
        self.assertEqual(result["BASICA"]["monto"], 49900)
        self.assertEqual(result["PRO"]["monto"], 9900)
        self.assertEqual(result["FULL"]["monto"], 19900)
        self.assertEqual({item["source"] for item in result.values()}, {"supabase"})

    def test_resolucion_lote_incompleta_usa_fallback_consistente(self):
        rows = [
            {
                "producto": "nexar-tienda",
                "plan_comercial": "PRO",
                "plan_tecnico": "PRO",
                "monto": 11111,
                "estado": "activo",
                "vigencia_desde": "2026-01-01T00:00:00Z",
                "vigencia_hasta": None,
            }
        ]
        fake_response = mock.Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.text = "ok"
        fake_response.json.return_value = rows

        with mock.patch("services.pricing_resolver.os.getenv", side_effect=lambda key, default="": {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        }.get(key, default)), mock.patch("services.pricing_resolver.requests.get", return_value=fake_response):
            result = pricing_resolver.resolve_plan_prices(["PRO", "FULL"], producto="nexar-tienda")

        self.assertEqual(result["PRO"]["monto"], 9900)
        self.assertEqual(result["FULL"]["monto"], 19900)
        self.assertEqual({item["source"] for item in result.values()}, {"fallback_local"})

    def test_normaliza_full_y_mensual_full(self):
        pricing_resolver.set_runtime_price_cache("nexar-tienda", {"FULL": 19900})

        full = pricing_resolver.resolve_plan_price("FULL", producto="nexar-tienda")
        mensual_full = pricing_resolver.resolve_plan_price("MENSUAL_FULL", producto="nexar-tienda")

        self.assertEqual(full["monto"], 19900)
        self.assertEqual(mensual_full["monto"], 19900)
        self.assertEqual(full["source"], "runtime")
        self.assertEqual(mensual_full["source"], "runtime")

    def test_no_altera_montos_actuales(self):
        prices = pricing_resolver.get_default_price_map()

        self.assertEqual(prices["DEMO"], 0)
        self.assertEqual(prices["BASICA"], 49900)
        self.assertEqual(prices["PRO"], 9900)
        self.assertEqual(prices["FULL"], 19900)
