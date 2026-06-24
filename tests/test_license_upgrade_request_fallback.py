import os
import unittest
from unittest import mock

import services.supabase_license_api as supabase_api


class UpgradeRequestFallbackTests(unittest.TestCase):
    def setUp(self):
        self.env_patcher = mock.patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://demo.supabase.co",
                "SUPABASE_KEY": "service-key",
            },
            clear=False,
        )
        self.env_patcher.start()
        os.environ.pop("SUPABASE_ANON_KEY", None)
        self.addCleanup(self.env_patcher.stop)

    def test_create_upgrade_request_reintenta_con_payload_compatible_para_alta_licencia(self):
        bad_response = mock.Mock(
            status_code=400,
            text='{"code":"PGRST204","message":"Could not find the \'origen\' column of \'solicitudes_upgrade\' in the schema cache"}',
        )
        ok_response = mock.Mock(status_code=201, text='[{"id":1}]')

        with mock.patch.object(supabase_api.requests, "post", side_effect=[bad_response, ok_response]) as post_mock:
            result = supabase_api.create_upgrade_request(
                {
                    "producto": "nexar-tienda",
                    "activation_id": "NXID-DEMO-456",
                    "nombre": "Admin Comercio",
                    "email": "admin@comercio.com",
                    "whatsapp": "264555000",
                    "tipo_solicitud": "alta_licencia",
                    "origen": "mi_plan",
                    "plan_actual": "DEMO",
                    "plan_destino": "FULL",
                    "machine_details": {"host": "demo"},
                }
            )

        self.assertTrue(result["ok"])
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(post_mock.call_args_list[0].args[0], "https://demo.supabase.co/rest/v1/solicitudes_upgrade")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["tipo_solicitud"], "alta_licencia")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["origen"], "mi_plan")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["plan_destino"], "FULL")
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["plan_solicitado"], "FULL")
        self.assertEqual(
            post_mock.call_args_list[0].kwargs["json"]["machine_details"]["request_context"]["origen"],
            "mi_plan",
        )
        self.assertNotIn("tipo_solicitud", post_mock.call_args_list[1].kwargs["json"])
        self.assertNotIn("origen", post_mock.call_args_list[1].kwargs["json"])
        self.assertNotIn("plan_destino", post_mock.call_args_list[1].kwargs["json"])
        self.assertEqual(post_mock.call_args_list[1].kwargs["json"]["plan_solicitado"], "FULL")

    def test_create_upgrade_request_conserva_codigo_vendedor_en_reintento_compatible(self):
        bad_response = mock.Mock(
            status_code=400,
            text='{"code":"PGRST204","message":"Could not find the \'origen\' column of \'solicitudes_upgrade\' in the schema cache"}',
        )
        ok_response = mock.Mock(status_code=201, text='[{"id":1}]')

        with mock.patch.object(supabase_api.requests, "post", side_effect=[bad_response, ok_response]) as post_mock:
            result = supabase_api.create_upgrade_request(
                {
                    "producto": "nexar-tienda",
                    "activation_id": "NXID-DEMO-456",
                    "nombre": "Admin Comercio",
                    "email": "admin@comercio.com",
                    "whatsapp": "264555000",
                    "tipo_solicitud": "alta_licencia",
                    "origen": "mi_plan",
                    "plan_actual": "DEMO",
                    "plan_destino": "FULL",
                    "codigo_vendedor": " vend123 ",
                    "machine_details": {"host": "demo"},
                }
            )

        self.assertTrue(result["ok"])
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(post_mock.call_args_list[0].kwargs["json"]["codigo_vendedor"], "VEND123")
        self.assertEqual(post_mock.call_args_list[1].kwargs["json"]["codigo_vendedor"], "VEND123")
