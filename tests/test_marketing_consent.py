import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MarketingConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"
        for key in ("NEXAR_LICENSES_VALIDATION_URL", "NEXAR_LICENSES_SUPABASE_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
            os.environ.pop(key, None)

        import database
        import routes.main as routes_main

        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "marketing.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.routes = importlib.reload(routes_main)

    def _save(self, email, opt_in, sync_results=()):
        with mock.patch.object(self.routes, "_get_stable_activation_id", return_value=("HWID-1", {})), \
             mock.patch.object(self.routes, "get_license_product", return_value="nexar-tienda"), \
             mock.patch.object(self.routes, "sync_marketing_preference", side_effect=sync_results) as sync:
            result = self.routes._save_marketing_preference(email, opt_in)
        return result, sync

    def test_onboarding_unchecked_persists_without_subscription_request(self):
        with mock.patch.object(self.routes, "create_demo_request") as demo, \
             mock.patch.object(self.routes, "create_license_request") as license_request, \
             mock.patch.object(self.routes, "create_checkout_preference") as checkout:
            result, sync = self._save("owner@example.com", False)
        self.assertEqual(result, "saved")
        sync.assert_not_called()
        demo.assert_not_called()
        license_request.assert_not_called()
        checkout.assert_not_called()
        cfg = self.db.get_config()
        self.assertEqual(cfg["license_owner_email"], "")
        self.assertEqual(cfg["license_marketing_email"], "owner@example.com")
        self.assertEqual(cfg["license_marketing_opt_in"], "0")

    def test_onboarding_checked_valid_email_sends_confirmation_and_persists(self):
        result, sync = self._save("owner@example.com", True, [True])
        self.assertEqual(result, "pending_opt_in")
        self.assertEqual(sync.call_args.kwargs["email"], "owner@example.com")
        self.assertTrue(sync.call_args.kwargs["marketing_opt_in"])
        self.assertEqual(self.db.get_config()["license_marketing_opt_in"], "1")
        self.assertEqual(self.db.get_config()["license_marketing_email"], "owner@example.com")

    def test_checked_invalid_email_is_rejected(self):
        result, sync = self._save("not-an-email", True)
        self.assertEqual(result, "invalid")
        sync.assert_not_called()
        self.assertEqual(self.db.get_config()["license_marketing_opt_in"], "0")

    def test_onboarding_post_without_checkbox_ignores_persisted_opt_in(self):
        self.db.set_config({
            "license_marketing_email": "marketing@example.com",
            "license_marketing_opt_in": "1",
            "license_marketing_synced_email": "marketing@example.com",
            "license_marketing_synced_opt_in": "1",
        })

        profile = self.routes._get_activation_customer_profile(
            form_data={"email": "owner@example.com"},
        )
        result, sync = self._save("marketing@example.com", profile["marketing_opt_in"], [True])

        self.assertFalse(profile["marketing_opt_in"])
        self.assertEqual(result, "pending_opt_out")
        self.assertFalse(sync.call_args.kwargs["marketing_opt_in"])

    def test_checkout_profile_keeps_owner_email_separate_from_marketing(self):
        self.db.set_config({
            "license_owner_email": "holder@example.com",
            "license_marketing_email": "marketing@example.com",
        })

        profile = self.routes._get_activation_customer_profile()

        self.assertEqual(profile["email"], "holder@example.com")

    def test_holder_email_change_does_not_change_marketing_email(self):
        self.db.set_config({
            "license_owner_email": "old-holder@example.com",
            "license_marketing_email": "marketing@example.com",
            "license_marketing_opt_in": "1",
        })
        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.register_blueprint(self.routes.main_bp)

        with app.test_request_context(
            "/mi-plan/titular",
            method="POST",
            data={
                "titular_nombre": "Titular",
                "titular_email": "new-holder@example.com",
                "titular_telefono": "264555000",
                "titular_palabra_recuperacion": "",
            },
        ):
            self.routes.mi_plan_guardar_titular.__wrapped__()

        cfg = self.db.get_config()
        self.assertEqual(cfg["license_owner_email"], "new-holder@example.com")
        self.assertEqual(cfg["license_marketing_email"], "marketing@example.com")

    def test_marketing_consent_does_not_make_terms_optional(self):
        self.assertIn(
            "Debés aceptar los términos y condiciones para continuar.",
            self.routes._validate_activation_customer_profile({
                "titular_nombre": "Admin", "negocio": "Comercio", "email": "owner@example.com",
                "telefono": "264555000", "rubro": "tienda", "terms_accepted": False,
            })[1],
        )

    def test_opt_out_clears_email_and_requests_confirmation(self):
        self.db.set_config({
            "license_owner_email": "holder@example.com",
            "license_marketing_email": "owner@example.com",
            "license_marketing_opt_in": "1",
        })
        result, sync = self._save("", False, [True])
        self.assertEqual(result, "pending_opt_out")
        self.assertFalse(sync.call_args.kwargs["marketing_opt_in"])
        self.assertEqual(self.db.get_config()["license_marketing_email"], "")
        self.assertEqual(self.db.get_config()["license_owner_email"], "holder@example.com")

    def test_change_email_requests_cleanup_then_new_subscription(self):
        self.db.set_config({"license_marketing_email": "old@example.com", "license_marketing_opt_in": "1"})
        result, sync = self._save("new@example.com", True, [True, True])
        self.assertEqual(result, "pending_opt_in")
        self.assertEqual(
            [(call.kwargs["email"], call.kwargs["marketing_opt_in"]) for call in sync.call_args_list],
            [("old@example.com", False), ("new@example.com", True)],
        )

    def test_remote_failure_keeps_only_actual_cleanup_pending(self):
        self.db.set_config({"license_marketing_email": "old@example.com", "license_marketing_opt_in": "1"})
        result, sync = self._save("new@example.com", True, [False, False])
        self.assertEqual(result, "error")
        self.assertEqual(json.loads(self.db.get_config()["license_marketing_pending_cleanup_emails"]), ["old@example.com"])
        self.assertEqual(len(sync.call_args_list), 2)

    def test_multiple_cleanup_stops_at_first_failure_and_keeps_all_unsent(self):
        self.db.set_config({
            "license_marketing_email": "current@example.com",
            "license_marketing_opt_in": "1",
            "license_marketing_pending_cleanup_emails": '["a@example.com", "b@example.com", "c@example.com"]',
        })
        result, sync = self._save("current@example.com", True, [True, False, True])
        self.assertEqual(result, "error")
        self.assertEqual(
            [call.kwargs["email"] for call in sync.call_args_list],
            ["a@example.com", "b@example.com", "current@example.com"],
        )
        self.assertEqual(json.loads(self.db.get_config()["license_marketing_pending_cleanup_emails"]), ["b@example.com", "c@example.com"])

    def test_pending_confirmation_removes_delivered_cleanup_from_queue(self):
        self.db.set_config({
            "license_marketing_email": "old@example.com",
            "license_marketing_opt_in": "0",
            "license_marketing_pending_cleanup_email": "old@example.com",
        })
        result, _sync = self._save("", False, [True])
        self.assertEqual(result, "pending_opt_out")
        self.assertEqual(self.db.get_config()["license_marketing_pending_cleanup_emails"], "[]")

    def test_reactivation_cancels_unsent_cleanup_for_same_email(self):
        self.db.set_config({
            "license_marketing_email": "same@example.com",
            "license_marketing_opt_in": "0",
            "license_marketing_pending_cleanup_emails": '["same@example.com", "other@example.com"]',
        })
        result, sync = self._save("same@example.com", True, [True, True])
        self.assertEqual(result, "pending_opt_in")
        self.assertEqual(json.loads(self.db.get_config()["license_marketing_pending_cleanup_emails"]), [])
        self.assertEqual([call.kwargs["email"] for call in sync.call_args_list], ["other@example.com", "same@example.com"])

    def test_accepted_subscription_is_not_sent_again(self):
        self.db.set_config({
            "license_marketing_email": "same@example.com",
            "license_marketing_opt_in": "1",
            "license_marketing_synced_email": "same@example.com",
            "license_marketing_synced_opt_in": "1",
        })
        result, sync = self._save("same@example.com", True)
        self.assertEqual(result, "saved")
        sync.assert_not_called()

    def test_delivered_previous_cleanup_preserves_current_subscription(self):
        self.db.set_config({
            "license_marketing_email": "old@example.com",
            "license_marketing_opt_in": "1",
        })

        first_result, first_sync = self._save("new@example.com", True, [False, True])

        self.assertEqual(first_result, "error")
        self.assertEqual(
            json.loads(self.db.get_config()["license_marketing_pending_cleanup_emails"]),
            ["old@example.com"],
        )
        self.assertEqual(self.db.get_config()["license_marketing_synced_email"], "new@example.com")
        self.assertEqual(self.db.get_config()["license_marketing_synced_opt_in"], "1")
        self.assertEqual(
            [(call.kwargs["email"], call.kwargs["marketing_opt_in"]) for call in first_sync.call_args_list],
            [("old@example.com", False), ("new@example.com", True)],
        )

        second_result, second_sync = self._save("new@example.com", True, [True])

        self.assertEqual(second_result, "saved")
        self.assertEqual(self.db.get_config()["license_marketing_pending_cleanup_emails"], "[]")
        self.assertEqual(self.db.get_config()["license_marketing_synced_email"], "new@example.com")
        self.assertEqual(self.db.get_config()["license_marketing_synced_opt_in"], "1")
        self.assertEqual(
            [(call.kwargs["email"], call.kwargs["marketing_opt_in"]) for call in second_sync.call_args_list],
            [("old@example.com", False)],
        )

    def test_opt_out_retry_clears_synced_email_and_reactivation_resubscribes(self):
        self.db.set_config({
            "license_marketing_email": "old@example.com",
            "license_marketing_opt_in": "1",
            "license_marketing_synced_email": "old@example.com",
            "license_marketing_synced_opt_in": "1",
        })

        first_result, first_sync = self._save("", False, [False])

        self.assertEqual(first_result, "error")
        self.assertEqual(self.db.get_config()["license_marketing_email"], "")
        self.assertEqual(json.loads(self.db.get_config()["license_marketing_pending_cleanup_emails"]), ["old@example.com"])
        self.assertEqual(self.db.get_config()["license_marketing_synced_email"], "old@example.com")
        self.assertEqual(self.db.get_config()["license_marketing_synced_opt_in"], "1")
        self.assertFalse(first_sync.call_args.kwargs["marketing_opt_in"])

        retry_result, retry_sync = self._save("", False, [True])

        self.assertEqual(retry_result, "pending_opt_out")
        self.assertEqual(self.db.get_config()["license_marketing_pending_cleanup_emails"], "[]")
        self.assertEqual(self.db.get_config()["license_marketing_synced_email"], "")
        self.assertEqual(self.db.get_config()["license_marketing_synced_opt_in"], "0")
        self.assertFalse(retry_sync.call_args.kwargs["marketing_opt_in"])

        reactivation_result, reactivation_sync = self._save("old@example.com", True, [True])

        self.assertEqual(reactivation_result, "pending_opt_in")
        self.assertEqual(
            [(call.kwargs["email"], call.kwargs["marketing_opt_in"]) for call in reactivation_sync.call_args_list],
            [("old@example.com", True)],
        )

    def test_migrates_legacy_marketing_email_once_without_resending_synced_opt_in(self):
        self.db.set_config({
            "license_owner_email": "owner@example.com",
            "license_marketing_opt_in": "1",
            "license_marketing_synced_email": "owner@example.com",
            "license_marketing_synced_opt_in": "1",
        })

        result, sync = self._save("owner@example.com", True)

        self.assertEqual(result, "saved")
        sync.assert_not_called()
        self.assertEqual(self.db.get_config()["license_marketing_email"], "owner@example.com")

    def test_legacy_migration_does_not_overwrite_existing_marketing_email(self):
        self.db.set_config({
            "license_owner_email": "owner@example.com",
            "license_marketing_email": "marketing@example.com",
            "license_marketing_opt_in": "1",
        })

        self.routes._migrate_legacy_marketing_email()

        self.assertEqual(self.db.get_config()["license_marketing_email"], "marketing@example.com")

    def test_legacy_migration_requires_opt_in_and_stays_independent_from_owner(self):
        self.db.set_config({
            "license_owner_email": "owner@example.com",
            "license_marketing_opt_in": "0",
        })

        self.routes._migrate_legacy_marketing_email()

        self.assertEqual(self.db.get_config().get("license_marketing_email", ""), "")
        self.db.set_config({"license_marketing_opt_in": "1"})
        self.routes._migrate_legacy_marketing_email()
        self.db.set_config({"license_owner_email": "changed-owner@example.com"})
        self.assertEqual(self.db.get_config()["license_marketing_email"], "owner@example.com")


class MarketingConsentSupabaseTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co/rest/v1", "SUPABASE_ANON_KEY": "anon-key"}, clear=True)
    @mock.patch("services.supabase_license_api.requests.post")
    def test_backend_pending_confirmation_is_a_success(self, post):
        import services.supabase_license_api as api

        post.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={"ok": True, "pending_confirmation": True}))
        self.assertTrue(api.sync_marketing_preference(
            email="owner@example.com", marketing_opt_in=True, producto="nexar-tienda", activation_id="HWID-1"
        ))
        self.assertEqual(post.call_args.args[0], "https://example.supabase.co/functions/v1/newsletter-preference")

    @mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon-key"}, clear=True)
    @mock.patch("services.supabase_license_api.requests.post")
    def test_backend_response_without_confirmation_is_not_delivered(self, post):
        import services.supabase_license_api as api

        post.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={"ok": True}))
        self.assertFalse(api.sync_marketing_preference(
            email="owner@example.com", marketing_opt_in=False, producto="nexar-tienda"
        ))
