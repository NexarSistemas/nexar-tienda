import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import mercadopago_checkout


class MercadoPagoCheckoutTests(unittest.TestCase):
    def test_basica_usa_fallback_actual(self):
        self.assertEqual(mercadopago_checkout.get_price_for_plan("BASICA"), 49900)

    def test_pro_usa_fallback_actual(self):
        self.assertEqual(mercadopago_checkout.get_price_for_plan("PRO"), 9900)

    def test_full_usa_fallback_actual(self):
        self.assertEqual(mercadopago_checkout.get_price_for_plan("FULL"), 19900)

    def test_full_acepta_mensual_full_desde_supabase(self):
        with mock.patch.object(
            mercadopago_checkout.pricing_resolver,
            "resolve_plan_price",
            return_value={"plan": "FULL", "monto": 19900, "source": "supabase"},
        ) as resolver_mock:
            price = mercadopago_checkout.get_price_for_plan("MENSUAL_FULL")

        self.assertEqual(price, 19900)
        resolver_mock.assert_called_once_with("FULL")

    def test_si_supabase_falla_mantiene_fallback_actual(self):
        with mock.patch("services.pricing_resolver.os.getenv", side_effect=lambda key, default="": {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        }.get(key, default)), mock.patch(
            "services.pricing_resolver.requests.get",
            side_effect=mercadopago_checkout.requests.RequestException("network down"),
        ):
            price = mercadopago_checkout.get_price_for_plan("FULL")

        self.assertEqual(price, 19900)

    def test_no_cambia_tipo_solicitud_alta_licencia(self):
        reference = mercadopago_checkout.build_external_reference(
            producto="nexar-tienda",
            plan_destino="PRO",
            tipo_solicitud="alta_licencia",
            activation_id="NXID-TEST-123",
        )

        self.assertEqual(reference, "ALTA|NXID-TEST-123|nexar-tienda|PRO")

    def test_no_cambia_tipo_solicitud_cambio_plan(self):
        reference = mercadopago_checkout.build_external_reference(
            producto="nexar-tienda",
            plan_destino="FULL",
            tipo_solicitud="cambio_plan",
            license_key="NXR-TDA-TEST-001",
        )

        self.assertEqual(reference, "NXR-TDA-TEST-001|nexar-tienda|FULL")
