import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.common.models import GeneralConfig
from apps.orders.models import Order
from apps.orders.order_emails import send_order_confirmation_email
from apps.orders.order_service import OrderService
from apps.orders.payment_config import PaymentConfigService
from apps.orders.schemas.order_schemas import validate_order_create
from apps.orders.tests.factories import (
    make_product,
    make_user,
    make_variant,
    shipping_address_data,
)


def set_config(**overrides) -> GeneralConfig:
    config = GeneralConfig.get()
    for field, value in overrides.items():
        setattr(config, field, value)
    config.save()
    return config


def make_published_variant(**kwargs):
    product = make_product(status="published")
    return make_variant(product=product, **kwargs)


class PaymentConfigConsumerTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()
        self.user = make_user()
        self.variant = make_published_variant(price=Decimal("100.00"), stock=10)

    def _create(self, **kwargs):
        return OrderService.create_order(
            user=self.user,
            items=[{"variant_id": str(self.variant.id), "quantity": 1,
                    "price": float(self.variant.price)}],
            shipping_address_data=shipping_address_data(),
            payment_method=kwargs.pop("payment_method", "paystack"),
            **kwargs,
        )

    def test_disabled_method_rejected_at_order_creation(self):
        set_config(pod_enabled=False)
        order, error = self._create(payment_method="pod")
        self.assertIsNone(order)
        self.assertIn("payment_method", error)

        set_config(pod_enabled=True, paystack_enabled=False)
        order, error = self._create(payment_method="paystack")
        self.assertIsNone(order)
        self.assertIn("payment_method", error)

    def test_cash_on_delivery_rejected_by_schema(self):
        cleaned, errors = validate_order_create({
            "items": [{"variant_id": str(self.variant.id), "quantity": 1}],
            "shipping_address": shipping_address_data(),
            "payment_method": "cash_on_delivery",
        })
        self.assertIsNotNone(errors)
        self.assertIn("payment_method", errors)

    def test_pod_eligibility_uses_config_limits(self):
        order, error = self._create(payment_method="paystack")
        self.assertIsNone(error)

        set_config(pod_max_order_value=Decimal("50.00"))
        eligible, reason = PaymentConfigService.check_pod_eligibility(order)
        self.assertFalse(eligible)
        self.assertIn("50.00", reason)

        set_config(pod_max_order_value=Decimal("500.00"), pod_enabled=False)
        eligible, reason = PaymentConfigService.check_pod_eligibility(order)
        self.assertFalse(eligible)
        self.assertIn("disabled", reason)

    def test_default_method_from_config(self):
        order, _ = self._create(payment_method="paystack")
        set_config(default_payment_method="pod")
        methods = PaymentConfigService.get_available_payment_methods(order)
        self.assertEqual(methods["default_method"], "pod")

    def test_min_order_value_enforced(self):
        set_config(min_order_value=Decimal("500.00"))
        before = Order.objects.count()
        order, error = self._create()
        self.assertIsNone(order)
        self.assertIn("items", error)
        self.assertEqual(Order.objects.count(), before)

    def test_tax_rate_applied(self):
        set_config(tax_rate=Decimal("10.00"))
        order, error = self._create()
        self.assertIsNone(error)
        order.refresh_from_db()
        self.assertEqual(order.tax_amount, Decimal("10.00"))  # 10% of 100
        # total = subtotal + shipping + tax
        self.assertEqual(order.total, order.subtotal + order.shipping_cost + Decimal("10.00"))

    def test_tax_inclusive_adds_nothing(self):
        set_config(tax_rate=Decimal("15.00"), tax_inclusive=True)
        order, error = self._create()
        self.assertIsNone(error)
        order.refresh_from_db()
        self.assertEqual(order.tax_amount, Decimal("0.00"))
        self.assertEqual(order.total, order.subtotal + order.shipping_cost)

    def test_order_number_prefix_from_config(self):
        set_config(order_number_prefix="ACME")
        order, error = self._create()
        self.assertIsNone(error)
        self.assertTrue(order.order_number.startswith("ACME"))

    def test_currency_default_from_config(self):
        set_config(currency="USD")
        order, error = self._create(currency="")
        self.assertIsNone(error)
        self.assertEqual(order.currency, "USD")


class GuestCheckoutGateTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()
        self.client = Client()
        self.variant = make_published_variant(price=Decimal("100.00"), stock=5)

    def _guest_payload(self):
        return {
            "items": [{"variant_id": str(self.variant.id), "quantity": 1,
                       "price": float(self.variant.price)}],
            "shipping_address": shipping_address_data(),
            "payment_method": "pod",
            "guest_info": {
                "email": "guest@example.com",
                "first_name": "Guest", "last_name": "Buyer",
                "phone": "+233200000001",
            },
        }

    def test_guest_checkout_disabled(self):
        set_config(guest_checkout_enabled=False)
        response = self.client.post(
            "/api/orders/create",
            data=json.dumps(self._guest_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("disabled", response.json()["message"])

    def test_guest_checkout_enabled_still_works(self):
        response = self.client.post(
            "/api/orders/create",
            data=json.dumps(self._guest_payload()),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (200, 201))


class CheckoutMetaEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()
        self.client = Client()

    def test_meta_public_and_reflects_config(self):
        response = self.client.get("/api/orders/checkout/meta")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([m["id"] for m in data["payment_methods"]], ["paystack", "pod"])
        self.assertEqual(data["default_payment_method"], "paystack")
        self.assertTrue(data["guest_checkout_enabled"])

        set_config(pod_enabled=False, tax_rate=Decimal("15.00"),
                   min_order_value=Decimal("50.00"), guest_checkout_enabled=False)
        data = self.client.get("/api/orders/checkout/meta").json()["data"]
        self.assertEqual([m["id"] for m in data["payment_methods"]], ["paystack"])
        self.assertEqual(data["tax_rate"], "15.00")
        self.assertFalse(data["tax_inclusive"])

        set_config(tax_inclusive=True)
        data = self.client.get("/api/orders/checkout/meta").json()["data"]
        self.assertTrue(data["tax_inclusive"])
        self.assertEqual(data["min_order_value"], "50.00")
        self.assertFalse(data["guest_checkout_enabled"])

    def test_default_falls_back_when_disabled(self):
        set_config(default_payment_method="pod", pod_enabled=False)
        data = self.client.get("/api/orders/checkout/meta").json()["data"]
        self.assertEqual(data["default_payment_method"], "paystack")


class AutoCancelUnpaidTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()
        self.user = make_user()
        self.variant = make_published_variant(price=Decimal("100.00"), stock=10)

    def _create_order(self, payment_method="paystack"):
        order, error = OrderService.create_order(
            user=self.user,
            items=[{"variant_id": str(self.variant.id), "quantity": 2,
                    "price": float(self.variant.price)}],
            shipping_address_data=shipping_address_data(),
            payment_method=payment_method,
        )
        assert error is None, error
        return order

    def _backdate(self, order, hours):
        Order.objects.filter(id=order.id).update(
            created_at=timezone.now() - timezone.timedelta(hours=hours)
        )

    def test_disabled_is_noop(self):
        order = self._create_order()
        self._backdate(order, 48)
        cancelled, failed = OrderService.cancel_stale_unpaid_orders()
        self.assertEqual((cancelled, failed), (0, 0))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_cancels_stale_and_restores_stock(self):
        set_config(auto_cancel_unpaid_hours=24)
        stale = self._create_order()
        self._backdate(stale, 48)
        recent = self._create_order()
        pod = self._create_order(payment_method="pod")
        self._backdate(pod, 48)

        self.variant.refresh_from_db()
        stock_before = self.variant.stock

        cancelled, failed = OrderService.cancel_stale_unpaid_orders()
        self.assertEqual(cancelled, 1)
        self.assertEqual(failed, 0)

        stale.refresh_from_db()
        recent.refresh_from_db()
        pod.refresh_from_db()
        self.assertEqual(stale.status, Order.STATUS_CANCELLED)
        self.assertEqual(recent.status, Order.STATUS_PENDING)
        # POD orders are unpaid-by-design and must never be auto-cancelled
        self.assertNotEqual(pod.status, Order.STATUS_CANCELLED)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, stock_before + 2)


class EmailGateTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()
        user = make_user()
        variant = make_published_variant(price=Decimal("100.00"), stock=5)
        self.order, error = OrderService.create_order(
            user=user,
            items=[{"variant_id": str(variant.id), "quantity": 1,
                    "price": float(variant.price)}],
            shipping_address_data=shipping_address_data(),
            payment_method="paystack",
        )
        assert error is None, error

    def test_confirmation_email_gated_by_config(self):
        notifications = GeneralConfig.get().notifications
        notifications["order_confirmation"]["email"] = False
        set_config(notifications=notifications)

        with patch("apps.orders.order_emails.send_templated_email") as mock_send:
            sent = send_order_confirmation_email(self.order)

        self.assertFalse(sent)
        mock_send.assert_not_called()
        self.order.refresh_from_db()
        self.assertFalse(self.order.email_sent)

    def test_confirmation_email_sends_when_enabled(self):
        with patch("apps.orders.order_emails.send_templated_email") as mock_send:
            sent = send_order_confirmation_email(self.order)

        self.assertTrue(sent)
        mock_send.assert_called_once()
        self.order.refresh_from_db()
        self.assertTrue(self.order.email_sent)

    def test_store_name_in_subject(self):
        set_config(store_name="Kusi Electronics")
        with patch("apps.orders.order_emails.send_templated_email") as mock_send:
            send_order_confirmation_email(self.order)
        subject = mock_send.call_args.kwargs["subject"]
        self.assertIn("Kusi Electronics", subject)
