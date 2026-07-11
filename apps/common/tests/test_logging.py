from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

import estore.utils.resend_mailer  # noqa: F401  (loads the module so mock.patch can resolve it)
from estore.utils.email_util import send_email, send_templated_email

# override_settings can't be used in this project: Django 4.2's setting_changed
# receiver imports django.contrib.staticfiles, which isn't installed. Patch the
# settings object directly instead.


def patch_setting(name, value):
    return patch.object(settings, name, value, create=True)


class SendEmailTests(SimpleTestCase):
    def test_falls_back_to_console_without_api_key(self):
        with patch_setting("RESEND_API_KEY", ""), patch(
            "estore.utils.resend_mailer.resend.Emails.send"
        ) as mock_send:
            result = send_email("user@example.com", "Hi", "Body")
        self.assertTrue(result)
        mock_send.assert_not_called()

    def test_sends_via_resend_with_expected_payload(self):
        with patch_setting("RESEND_API_KEY", "re_test"), patch_setting(
            "DEFAULT_FROM_EMAIL", "no-reply@example.com"
        ), patch_setting("DEFAULT_FROM_NAME", "Test Store"), patch(
            "estore.utils.resend_mailer.resend.Emails.send"
        ) as mock_send:
            mock_send.return_value = {"id": "email_123"}
            result = send_email(
                "user@example.com", "Hi", "Body text", html_message="<p>Body</p>"
            )

        self.assertTrue(result)
        params = mock_send.call_args[0][0]
        self.assertEqual(params["from"], "Test Store <no-reply@example.com>")
        self.assertEqual(params["to"], ["user@example.com"])
        self.assertEqual(params["subject"], "Hi")
        self.assertEqual(params["html"], "<p>Body</p>")
        self.assertEqual(params["text"], "Body text")

    def test_provider_error_returns_false_without_raising(self):
        with patch_setting("RESEND_API_KEY", "re_test"), patch_setting(
            "DEFAULT_FROM_EMAIL", "no-reply@example.com"
        ), patch(
            "estore.utils.resend_mailer.resend.Emails.send",
            side_effect=Exception("provider down"),
        ):
            result = send_email("user@example.com", "Hi", "Body")
        self.assertFalse(result)

    def test_templated_email_sync_renders_and_sends(self):
        with patch_setting("RESEND_API_KEY", ""):
            result = send_templated_email(
                "user@example.com",
                "Verify",
                "verify_email.html",
                context={"verification_url": "https://x/verify", "expiry_hours": 24},
                recipient_name="Jane",
                async_send=False,
            )
        self.assertTrue(result)


class EmailTemplateRenderTests(SimpleTestCase):
    """Every template renders with representative context."""

    def test_auth_templates_render(self):
        base = {"site_name": "Test Store", "recipient_name": "Jane"}
        html = render_to_string(
            "emails/verify_email.html",
            {**base, "verification_url": "https://x/verify?t=1", "expiry_hours": 24},
        )
        self.assertIn("https://x/verify?t=1", html)

        html = render_to_string(
            "emails/password_reset.html", {**base, "reset_url": "https://x/reset?t=1"}
        )
        self.assertIn("https://x/reset?t=1", html)

        html = render_to_string(
            "emails/password_changed.html",
            {**base, "timestamp": "2026-07-05 10:00:00 UTC", "ip_address": "1.2.3.4"},
        )
        self.assertIn("1.2.3.4", html)

    def test_order_templates_render(self):
        base = {"site_name": "Test Store", "recipient_name": "Jane"}

        class FakeItem:
            product_title = "Widget"
            quantity = 2
            total_price = "20.00"

        class FakeOrder:
            order_number = "ORD123"
            created_at = None
            currency = "GHS"
            subtotal = "20.00"
            shipping_cost = "5.00"
            discount_amount = 0
            total = "25.00"

        html = render_to_string(
            "emails/order_confirmation.html",
            {
                **base,
                "order": FakeOrder(),
                "items": [FakeItem()],
                "receipt_url": "https://pay/receipt",
                "payment_method": "paystack",
            },
        )
        self.assertIn("ORD123", html)
        self.assertIn("Widget", html)

        class FakeShipment:
            carrier = "DHL"
            tracking_number = "TRK1"
            tracking_url = "https://track/TRK1"
            estimated_delivery = None

        html = render_to_string(
            "emails/shipping_update.html",
            {**base, "order": FakeOrder(), "shipment": FakeShipment()},
        )
        self.assertIn("TRK1", html)

        html = render_to_string(
            "emails/order_delivered.html", {**base, "order": FakeOrder()}
        )
        self.assertIn("ORD123", html)


class ClientIpTests(SimpleTestCase):
    def test_forwarded_chain_returns_first_ip(self):
        from django.test import RequestFactory
        from apps.common.logging import get_client_ip

        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="18.207.165.154, 172.68.245.48, 10.29.200.106"
        )
        self.assertEqual(get_client_ip(request), "18.207.165.154")

    def test_falls_back_to_remote_addr(self):
        from django.test import RequestFactory
        from apps.common.logging import get_client_ip

        request = RequestFactory().get("/")
        self.assertEqual(get_client_ip(request), "127.0.0.1")
