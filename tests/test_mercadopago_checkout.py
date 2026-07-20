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
            price = mercadopago_checkout.get_price_for_plan("MENSUAL_FULL", producto="nexar-tienda")

        self.assertEqual(price, 19900)
        resolver_mock.assert_called_once_with("FULL", producto="nexar-tienda")

    def test_build_external_reference_valida_checkout_con_producto_correcto(self):
        with mock.patch.object(mercadopago_checkout, "plan_supports_checkout", return_value=True) as supports_mock:
            reference = mercadopago_checkout.build_external_reference(
                producto="nexar-tienda",
                plan_destino="PRO",
                tipo_solicitud="alta_licencia",
                activation_id="NXID-TEST-123",
            )

        self.assertEqual(reference, "ALTA|NXID-TEST-123|nexar-tienda|PRO")
        supports_mock.assert_called_once_with("PRO", producto="nexar-tienda")

    def test_create_checkout_preference_valida_checkout_con_producto_correcto(self):
        fake_response = mock.Mock(status_code=200)
        fake_response.content = b'{"init_point":"https://mp.test/init"}'
        fake_response.json.return_value = {"init_point": "https://mp.test/init"}
        with mock.patch.object(mercadopago_checkout, "plan_supports_checkout", return_value=True) as supports_mock, \
             mock.patch.object(mercadopago_checkout.requests, "post", return_value=fake_response):
            init_point = mercadopago_checkout.create_checkout_preference(
                producto="nexar-tienda",
                plan_destino="FULL",
                precio=19900,
                external_reference="NXR-TDA-TEST-001|nexar-tienda|FULL",
                license_key="NXR-TDA-TEST-001",
                email_titular="admin@test.com",
            )

        self.assertEqual(init_point, "https://mp.test/init")
        supports_mock.assert_called_once_with("FULL", producto="nexar-tienda")

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
