import json
from decimal import Decimal

from django.core.cache import cache
from django.test import Client, TestCase

from apps.common.models import GeneralConfig
from apps.common.schemas import validate_general_config_update
from apps.products.tests.factories import make_admin, make_user
from apps.users.utils.token_utils import generate_jwt_token


class GeneralConfigModelTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_singleton_and_defaults(self):
        config = GeneralConfig.get()
        again = GeneralConfig.get()
        self.assertEqual(config.pk, 1)
        self.assertEqual(again.pk, 1)
        self.assertEqual(GeneralConfig.objects.count(), 1)
        self.assertTrue(config.paystack_enabled)
        self.assertTrue(config.pod_enabled)
        self.assertEqual(config.pod_max_order_value, Decimal("500.00"))
        self.assertEqual(config.order_number_prefix, "ORD")
        self.assertEqual(config.currency, "GHS")
        self.assertTrue(config.notifications["order_confirmation"]["email"])
        self.assertFalse(config.notifications["order_confirmation"]["sms"])

    def test_cache_busted_on_save(self):
        self.assertTrue(GeneralConfig.get_cached().pod_enabled)
        config = GeneralConfig.get()
        config.pod_enabled = False
        config.save()
        self.assertFalse(GeneralConfig.get_cached().pod_enabled)

    def test_notification_enabled_fail_modes(self):
        config = GeneralConfig.get()
        # normal reads
        self.assertTrue(config.notification_enabled("order_shipped", "email"))
        self.assertFalse(config.notification_enabled("order_shipped", "sms"))
        # malformed config: email fails open, sms/whatsapp fail closed
        config.notifications = "garbage"
        self.assertTrue(config.notification_enabled("order_shipped", "email"))
        self.assertFalse(config.notification_enabled("order_shipped", "whatsapp"))
        # unknown event: same behavior
        config.notifications = {}
        self.assertTrue(config.notification_enabled("nonsense", "email"))
        self.assertFalse(config.notification_enabled("nonsense", "sms"))


class GeneralConfigValidatorTests(TestCase):
    def test_happy_partial_update(self):
        cleaned, errors = validate_general_config_update({
            "pod_enabled": False,
            "tax_rate": "12.5",
            "order_number_prefix": "acme",
            "currency": "usd",
            "notifications": {"order_shipped": {"email": False, "junk_channel": True}},
        })
        self.assertIsNone(errors)
        self.assertFalse(cleaned["pod_enabled"])
        self.assertEqual(cleaned["tax_rate"], Decimal("12.5"))
        self.assertEqual(cleaned["order_number_prefix"], "ACME")
        self.assertEqual(cleaned["currency"], "USD")
        self.assertFalse(cleaned["notifications"]["order_shipped"]["email"])
        # unknown channels dropped, other events keep defaults
        self.assertNotIn("junk_channel", cleaned["notifications"]["order_shipped"])
        self.assertTrue(cleaned["notifications"]["order_confirmation"]["email"])

    def test_rejections(self):
        cases = [
            ({"tax_rate": "abc"}, "tax_rate"),
            ({"tax_rate": "101"}, "tax_rate"),
            ({"min_order_value": "-5"}, "min_order_value"),
            ({"pod_max_quantity": "many"}, "pod_max_quantity"),
            ({"pod_enabled": "yes"}, "pod_enabled"),
            ({"default_payment_method": "bitcoin"}, "default_payment_method"),
            ({"order_number_prefix": "!!"}, "order_number_prefix"),
            ({"support_email": "not-an-email"}, "support_email"),
            ({"currency": "CEDIS"}, "currency"),
            ({"store_country": "GHA"}, "store_country"),
            ({"notifications": []}, "notifications"),
            ({}, "general"),
        ]
        for payload, field in cases:
            cleaned, errors = validate_general_config_update(payload)
            self.assertIsNone(cleaned, payload)
            self.assertIn(field, errors, payload)

    def test_paystack_bounds_cross_field(self):
        cleaned, errors = validate_general_config_update({"paystack_min_amount": "5000000"})
        self.assertIsNone(cleaned)
        self.assertIn("paystack_min_amount", errors)


class GeneralConfigEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin()
        self.user = make_user()

    def _auth(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_requires_auth_and_role(self):
        self.assertEqual(self.client.get("/api/common/admin/general/config").status_code, 401)
        self.assertEqual(
            self.client.get("/api/common/admin/general/config", **self._auth(self.user)).status_code,
            403,
        )

    def test_get_returns_defaults(self):
        response = self.client.get("/api/common/admin/general/config", **self._auth(self.admin))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["paystack_enabled"])
        self.assertEqual(data["pod_max_order_value"], "500.00")
        self.assertIn("order_confirmation", data["notifications"])

    def test_post_partial_update(self):
        response = self.client.post(
            "/api/common/admin/general/config",
            data=json.dumps({"guest_checkout_enabled": False, "store_name": "My Store"}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertFalse(data["guest_checkout_enabled"])
        self.assertEqual(data["store_name"], "My Store")
        config = GeneralConfig.get()
        self.assertFalse(config.guest_checkout_enabled)
        # untouched fields keep defaults
        self.assertTrue(config.paystack_enabled)

    def test_post_validation_error(self):
        response = self.client.post(
            "/api/common/admin/general/config",
            data=json.dumps({"tax_rate": "nope"}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 422)

    def test_post_bad_json(self):
        response = self.client.post(
            "/api/common/admin/general/config",
            data="{not json",
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 400)
