from decimal import Decimal

from django.test import Client, TestCase

from apps.orders.models import Order
from apps.products.models import Product
from apps.products.tests.factories import make_product, make_variant, make_user
from apps.promotions.models import AffiliateCommission
from apps.promotions.services import DiscountCodeService
from apps.promotions.tests.factories import make_affiliate, make_discount_code


class CheckoutDiscountApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        product = make_product(status=Product.STATUS_PUBLISHED)
        self.variant = make_variant(
            product=product,
            price=Decimal("100.00"),
            stock=10,
            weight=Decimal("1.00"),
        )

    def _guest_payload(self, *, discount_code: str = ""):
        payload = {
            "items": [
                {
                    "is_bundle": False,
                    "variant_id": str(self.variant.id),
                    "quantity": 1,
                }
            ],
            "shipping_address": {
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+233000000000",
                "email": "jane@example.com",
                "address_line1": "123 Test Street",
                "city": "Accra",
                "state": "Greater Accra",
                "postal_code": "GA-123",
                "country": "GH",
            },
            "guest_info": {
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+233000000000",
            },
            "payment_method": "pod",
        }
        if discount_code:
            payload["discount_code"] = discount_code
        return payload

    def test_preview_discount_code_endpoint_returns_discounted_subtotal(self):
        make_discount_code(code="SAVE10", value="10.00")

        response = self.client.post(
            "/api/promotions/discount-codes/preview",
            data={
                "code": "save10",
                "items": [
                    {
                        "is_bundle": False,
                        "variant_id": str(self.variant.id),
                        "quantity": 1,
                    }
                ],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["code"], "SAVE10")
        self.assertEqual(body["data"]["discount_amount"], 10.0)
        self.assertEqual(body["data"]["subtotal_after_discount"], 90.0)

    def test_create_order_applies_affiliate_discount_and_records_pending_commission(self):
        affiliate = make_affiliate(user=make_user(), commission_rate="20.00")
        discount_code = make_discount_code(
            code="AFFDISC20",
            affiliate=affiliate,
            value="5.00",
        )

        response = self.client.post(
            "/api/orders/create",
            data=self._guest_payload(discount_code=discount_code.code),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])

        order = Order.objects.get(id=body["data"]["order"]["id"])
        self.assertEqual(order.discount_code_text, discount_code.code)
        self.assertEqual(order.discount_amount, Decimal("5.00"))
        self.assertEqual(order.affiliate_id, affiliate.id)
        self.assertEqual(order.affiliate_commission_amount, Decimal("19.00"))

        commission = AffiliateCommission.objects.get(order=order)
        self.assertEqual(commission.status, AffiliateCommission.STATUS_PENDING)

        affiliate.refresh_from_db()
        self.assertEqual(affiliate.pending_earnings, Decimal("0.00"))

    def test_create_order_accepts_affiliate_referral_code_in_discount_field(self):
        affiliate = make_affiliate(
            user=make_user(),
            referral_code="TRACKJANE",
            commission_rate="20.00",
        )
        discount_code = make_discount_code(
            code="AFFDISC25",
            affiliate=affiliate,
            value="5.00",
        )

        response = self.client.post(
            "/api/orders/create",
            data=self._guest_payload(discount_code=affiliate.referral_code),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        order = Order.objects.get(id=body["data"]["order"]["id"])

        self.assertEqual(order.entered_discount_code_text, affiliate.referral_code)
        self.assertEqual(order.discount_code_text, discount_code.code)
        self.assertEqual(order.affiliate_id, affiliate.id)

        commission = AffiliateCommission.objects.get(order=order)
        self.assertEqual(commission.discount_code_id, discount_code.id)


class OrderEmailTests(TestCase):
    def setUp(self):
        from apps.users.models import Address

        self.user = make_user()
        address = Address.objects.create(
            user=self.user,
            first_name="Jane",
            last_name="Doe",
            phone="+233000000000",
            email="jane@example.com",
            address_line1="123 Test Street",
            city="Accra",
            state="Greater Accra",
            postal_code="GA-123",
            country="GH",
        )
        self.order = Order.objects.create(
            user=self.user,
            payment_method=Order.PAYMENT_MOBILE_MONEY,
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("100.00"),
            shipping_cost=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            currency="GHS",
        )

    def test_process_successful_payment_sends_confirmation_once(self):
        from unittest.mock import patch

        from apps.orders.paystack_service import PaystackService

        gateway_data = {
            "status": "success",
            "amount": int(self.order.total * 100),
            "currency": "GHS",
            "metadata": {"order_id": str(self.order.id)},
            "authorization": {},
        }

        with patch.object(
            PaystackService, "verify_transaction", return_value=(gateway_data, None)
        ), patch("apps.orders.order_emails.send_templated_email") as mock_send:
            success, _ = PaystackService.process_successful_payment(
                "ref-once", str(self.order.id)
            )
            self.assertTrue(success)

            # Second verification of the same reference must not re-send
            success, result = PaystackService.process_successful_payment(
                "ref-once", str(self.order.id)
            )
            self.assertTrue(success)
            self.assertTrue(result.get("existing"))

        self.assertEqual(mock_send.call_count, 1)
        self.order.refresh_from_db()
        self.assertTrue(self.order.email_sent)
        self.assertEqual(self.order.payment_status, Order.PAYMENT_PAID)

    def test_email_failure_does_not_break_payment(self):
        from unittest.mock import patch

        from apps.orders.paystack_service import PaystackService

        gateway_data = {
            "status": "success",
            "amount": int(self.order.total * 100),
            "currency": "GHS",
            "metadata": {"order_id": str(self.order.id)},
            "authorization": {},
        }

        with patch.object(
            PaystackService, "verify_transaction", return_value=(gateway_data, None)
        ), patch(
            "apps.orders.order_emails.send_templated_email",
            side_effect=Exception("smtp down"),
        ):
            success, _ = PaystackService.process_successful_payment(
                "ref-fail", str(self.order.id)
            )

        self.assertTrue(success)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PAYMENT_PAID)
        self.assertFalse(self.order.email_sent)

    def test_shipment_transitions_send_shipping_and_delivered_emails(self):
        from unittest.mock import patch

        from apps.orders.models import Shipment

        self.order.payment_status = Order.PAYMENT_PAID
        self.order.save()

        with patch("apps.orders.order_emails.send_templated_email") as mock_send:
            shipment = Shipment.objects.create(
                order=self.order,
                status=Shipment.STATUS_SHIPPED,
                carrier="DHL",
                tracking_number="TRK1",
            )
            self.assertEqual(mock_send.call_count, 1)
            self.assertIn("Shipped", mock_send.call_args.kwargs["subject"])
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, Order.STATUS_SHIPPED)

            # Re-saving with the same status must not re-send
            shipment.save()
            self.assertEqual(mock_send.call_count, 1)

            shipment.status = Shipment.STATUS_DELIVERED
            shipment.save()
            self.assertEqual(mock_send.call_count, 2)
            self.assertIn("Delivered", mock_send.call_args.kwargs["subject"])
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, Order.STATUS_DELIVERED)


class AdminOrderStatusApiTests(TestCase):
    """Regression: PUT /status must route shipped/delivered via shipments."""

    def setUp(self):
        from apps.users.models import Address
        from apps.users.utils.token_utils import generate_jwt_token

        self.admin = make_user(role="admin")
        self.token = generate_jwt_token(self.admin)
        self.client = Client()

        user = make_user()
        address = Address.objects.create(
            user=user,
            first_name="Jane",
            last_name="Doe",
            phone="+233000000000",
            email="jane@example.com",
            address_line1="123 Test Street",
            city="Accra",
            state="Greater Accra",
            postal_code="GA-123",
            country="GH",
        )
        self.order = Order.objects.create(
            user=user,
            payment_method=Order.PAYMENT_MOBILE_MONEY,
            payment_status=Order.PAYMENT_PAID,
            status=Order.STATUS_READY_FOR_SHIPPING,
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("50.00"),
            shipping_cost=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            currency="GHS",
        )

    def _put_status(self, status, **extra):
        import json as json_lib
        from unittest.mock import patch

        with patch("apps.orders.order_emails.send_templated_email"):
            return self.client.put(
                f"/api/orders/admin/orders/{self.order.id}/status",
                data=json_lib.dumps({"status": status, **extra}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )

    def test_shipped_creates_shipment_and_delivered_updates_it(self):
        response = self._put_status("shipped", carrier="DHL", tracking_number="TRK9")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_SHIPPED)
        self.assertEqual(self.order.shipment.tracking_number, "TRK9")

        response = self._put_status("delivered")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_DELIVERED)
        self.assertIsNotNone(self.order.shipment.delivered_at)

    def test_delivered_without_shipment_is_rejected(self):
        response = self._put_status("delivered")
        self.assertEqual(response.status_code, 422)

    def test_pipeline_jump_returns_conflict(self):
        self.order.status = Order.STATUS_PENDING
        self.order.save()
        # pending -> processing skips 'confirmed': conflict without skip_behavior
        response = self._put_status("processing")
        self.assertEqual(response.status_code, 409)
        response = self._put_status("processing", skip_behavior="complete")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_PROCESSING)
        self.assertIsNotNone(self.order.confirmed_at)


def _make_address(user):
    from apps.users.models import Address

    return Address.objects.create(
        user=user,
        first_name="Jane",
        last_name="Doe",
        phone="+233000000000",
        email="jane@example.com",
        address_line1="123 Test Street",
        city="Accra",
        state="Greater Accra",
        postal_code="GA-123",
        country="GH",
    )


class PosCompletionTests(TestCase):
    """POS pickup orders complete automatically once paid."""

    def setUp(self):
        product = make_product(status=Product.STATUS_PUBLISHED)
        self.variant = make_variant(
            product=product,
            price=Decimal("40.00"),
            stock=10,
            weight=Decimal("1.00"),
        )
        self.staff = make_user(role="staff")
        self.items = [
            {"is_bundle": False, "variant_id": str(self.variant.id), "quantity": 2}
        ]

    def _create_pickup(self, payment_method):
        from apps.orders.order_service import OrderService

        order, error = OrderService.create_pos_pickup_order(
            customer=None,
            items=self.items,
            payment_method=payment_method,
            guest_info={
                "email": "walkin@example.com",
                "first_name": "Walk",
                "last_name": "In",
                "phone": "+233000000009",
            },
            created_by=self.staff,
        )
        self.assertIsNone(error)
        return order

    def test_pickup_paid_in_store_completes_at_creation(self):
        order = self._create_pickup("pos")
        self.assertTrue(order.is_pickup)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertIsNotNone(order.completed_at)
        self.assertIsNotNone(order.paid_at)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

    def test_pickup_pay_on_collect_stays_confirmed_then_completes_when_paid(self):
        from apps.orders.order_service import OrderService

        order = self._create_pickup("pod")
        self.assertTrue(order.is_pickup)
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)
        self.assertIsNone(order.completed_at)

        order, error = OrderService.update_payment_status(str(order.id), "paid")
        self.assertIsNone(error)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertIsNotNone(order.paid_at)

    def test_pickup_pay_on_collect_completes_via_record_charge(self):
        from apps.orders.transaction_service import TransactionService

        order = self._create_pickup("pod")
        txn, error = TransactionService.record_charge(
            order_id=str(order.id),
            transaction_id="POSCHG1",
            amount=order.total,
            payment_method="cash",
        )
        self.assertIsNone(error)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.completed_at)

    def test_pos_shipping_order_does_not_auto_complete(self):
        from apps.orders.order_service import OrderService

        # A registered customer: guest POS shipping needs a userless address,
        # which the Address model doesn't allow (tracked in TODOS.md).
        customer = make_user()
        order, error = OrderService.create_pos_shipping_order(
            customer=customer,
            items=self.items,
            shipping_address_data={
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+233000000000",
                "email": "jane@example.com",
                "address_line1": "123 Test Street",
                "city": "Accra",
                "state": "Greater Accra",
                "postal_code": "GA-123",
                "country": "GH",
            },
            payment_method="pos",
            guest_info={
                "email": "jane@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+233000000000",
            },
            created_by=self.staff,
        )
        self.assertIsNone(error)
        self.assertFalse(order.is_pickup)
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.assertIsNone(order.completed_at)


class PaymentRecoveryTests(TestCase):
    """failed -> paid must re-reserve the stock that the failure released."""

    def setUp(self):
        from apps.orders.models import OrderItem

        product = make_product(status=Product.STATUS_PUBLISHED)
        self.variant = make_variant(
            product=product,
            price=Decimal("50.00"),
            stock=10,
            weight=Decimal("1.00"),
        )
        self.user = make_user()
        address = _make_address(self.user)
        self.order = Order.objects.create(
            user=self.user,
            payment_method=Order.PAYMENT_MOBILE_MONEY,
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("100.00"),
            shipping_cost=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("100.00"),
            currency="GHS",
        )
        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            product_title="Test product",
            product_slug="test-product",
            variant_attributes={},
            sku=self.variant.sku,
            unit_price=Decimal("50.00"),
            quantity=2,
        )
        # Mimic checkout's stock reservation
        self.variant.reduce_stock(2)

    def test_failed_then_paid_re_reserves_stock(self):
        from apps.orders.order_service import OrderService

        OrderService.mark_payment_failed(str(self.order.id), reason="abandoned")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)  # released on failure

        order, error = OrderService.update_payment_status(str(self.order.id), "paid")
        self.assertIsNone(error)
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)  # re-reserved

    def test_failed_then_paid_with_insufficient_stock_keeps_paid_and_flags_oversell(self):
        from apps.orders.order_service import OrderService

        OrderService.mark_payment_failed(str(self.order.id), reason="abandoned")
        # Someone else bought the released stock in the meantime.
        self.variant.refresh_from_db()
        self.variant.reduce_stock(9)

        order, error = OrderService.update_payment_status(str(self.order.id), "paid")
        self.assertIsNone(error)
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertIn("OVERSOLD", order.admin_note)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)  # untouched: conditional update refused

    def test_paid_twice_does_not_double_reserve(self):
        from apps.orders.order_service import OrderService

        OrderService.mark_payment_failed(str(self.order.id), reason="abandoned")
        OrderService.update_payment_status(str(self.order.id), "paid")
        OrderService.update_payment_status(str(self.order.id), "paid")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)


class ShipmentServiceTests(TestCase):
    def setUp(self):
        from unittest.mock import patch

        patcher = patch("apps.orders.order_emails.send_templated_email")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.user = make_user()
        self.admin = make_user(role="admin")
        address = _make_address(self.user)
        self.order = Order.objects.create(
            user=self.user,
            payment_method=Order.PAYMENT_MOBILE_MONEY,
            payment_status=Order.PAYMENT_PAID,
            status=Order.STATUS_CONFIRMED,
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("100.00"),
            shipping_cost=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("110.00"),
            currency="GHS",
        )

    def _ship(self, shipment, **kwargs):
        from apps.orders.models import Shipment
        from apps.orders.shipment_service import ShipmentService

        return ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id),
            status=Shipment.STATUS_SHIPPED,
            created_by=self.admin,
            **kwargs,
        )

    def test_create_shipment_is_pending_and_advances_order_to_ready(self):
        from apps.orders.models import Shipment
        from apps.orders.shipment_service import ShipmentService

        shipment, error = ShipmentService.create_shipment(
            order_id=str(self.order.id),
            shipping_cost=Decimal("25.00"),
            created_by=self.admin,
        )
        self.assertIsNone(error)
        self.assertEqual(shipment.status, Shipment.STATUS_PENDING)
        self.assertIsNone(shipment.shipped_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_READY_FOR_SHIPPING)
        self.assertIsNotNone(self.order.ready_for_shipping_at)
        self.assertIsNone(self.order.shipped_at)
        self.assertEqual(self.order.shipping_cost, Decimal("25.00"))
        self.assertEqual(self.order.total, Decimal("125.00"))

    def test_ready_for_shipping_auto_creates_pending_shipment(self):
        from apps.orders.models import Shipment, ShipmentTracking
        from apps.orders.order_service import OrderService

        order, error = OrderService.update_order_status(
            order_id=str(self.order.id),
            status=Order.STATUS_READY_FOR_SHIPPING,
            skip_behavior="skip",
            user=self.admin,
        )
        self.assertIsNone(error)
        shipment = order.shipment
        self.assertEqual(shipment.status, Shipment.STATUS_PENDING)
        self.assertTrue(
            ShipmentTracking.objects.filter(
                shipment=shipment, status=Shipment.STATUS_PENDING
            ).exists()
        )

        # Re-running the transition must not try to create a duplicate
        order, error = OrderService.update_order_status(
            order_id=str(self.order.id),
            status=Order.STATUS_READY_FOR_SHIPPING,
            user=self.admin,
        )
        self.assertIsNone(error)
        self.assertEqual(Shipment.objects.filter(order=order).count(), 1)

    def test_mark_shipped_from_pending_syncs_order(self):
        from apps.orders.models import Shipment, ShipmentTracking
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        shipment, error = self._ship(
            shipment, tracking_number="TRK100", carrier="DHL"
        )
        self.assertIsNone(error)
        self.assertEqual(shipment.status, Shipment.STATUS_SHIPPED)
        self.assertIsNotNone(shipment.shipped_at)
        self.assertEqual(shipment.carrier, "DHL")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_SHIPPED)
        self.assertIsNotNone(self.order.shipped_at)
        self.assertTrue(
            ShipmentTracking.objects.filter(
                shipment=shipment, status=Shipment.STATUS_SHIPPED
            ).exists()
        )

    def test_mark_shipped_allows_empty_tracking_details(self):
        from apps.orders.models import Shipment
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        shipment, error = self._ship(shipment)
        self.assertIsNone(error)
        self.assertEqual(shipment.status, Shipment.STATUS_SHIPPED)

    def test_mark_shipped_requires_payment_unless_cod(self):
        from apps.orders.shipment_service import ShipmentService

        self.order.payment_status = Order.PAYMENT_PENDING
        self.order.save()
        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        shipment, error = self._ship(shipment)
        self.assertIsNotNone(error)
        self.assertIn("payment", error)

        self.order.payment_method = Order.PAYMENT_CASH_ON_DELIVERY
        self.order.save()
        shipment, error = self._ship(self.order.shipment)
        self.assertIsNone(error)

    def test_pending_shipment_cannot_be_delivered_or_reverted_to(self):
        from apps.orders.models import Shipment
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        _, error = ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id), status=Shipment.STATUS_DELIVERED
        )
        self.assertIsNotNone(error)

        self._ship(shipment)
        _, error = ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id), status=Shipment.STATUS_PENDING
        )
        self.assertIsNotNone(error)

    def test_cancelling_pending_shipment_cancels_order(self):
        from apps.orders.models import Shipment
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        shipment, error = ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id),
            status=Shipment.STATUS_CANCELLED,
            created_by=self.admin,
        )
        self.assertIsNone(error)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CANCELLED)

    def test_create_shipment_rejected_for_pending_or_pickup_orders(self):
        from apps.orders.shipment_service import ShipmentService

        self.order.status = Order.STATUS_PENDING
        self.order.save()
        shipment, error = ShipmentService.create_shipment(order_id=str(self.order.id))
        self.assertIsNotNone(error)

        self.order.status = Order.STATUS_CONFIRMED
        self.order.is_pickup = True
        self.order.save()
        shipment, error = ShipmentService.create_shipment(order_id=str(self.order.id))
        self.assertIsNotNone(error)

    def test_update_shipment_status_guards_transitions(self):
        from apps.orders.models import Shipment, ShipmentTracking
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        self._ship(shipment)

        # delivered from shipped: OK, syncs order and writes a tracking row
        shipment, error = ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id),
            status=Shipment.STATUS_DELIVERED,
            created_by=self.admin,
        )
        self.assertIsNone(error)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_DELIVERED)
        self.assertTrue(
            ShipmentTracking.objects.filter(
                shipment=shipment, status=Shipment.STATUS_DELIVERED
            ).exists()
        )

        # delivered -> shipped is a demotion: rejected
        shipment, error = ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id),
            status=Shipment.STATUS_SHIPPED,
            created_by=self.admin,
        )
        self.assertIsNotNone(error)

    def test_update_shipment_tracking_only_without_status(self):
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        shipment, error = ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id),
            status=None,
            tracking_number="TRK200",
            carrier="UPS",
            created_by=self.admin,
        )
        self.assertIsNone(error)
        self.assertEqual(shipment.tracking_number, "TRK200")
        self.assertEqual(shipment.carrier, "UPS")
        # A tracking-only update must not dispatch the shipment
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_READY_FOR_SHIPPING)

    def test_delivered_shipment_does_not_demote_completed_order(self):
        from apps.orders.models import Shipment
        from apps.orders.shipment_service import ShipmentService

        shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )
        self._ship(shipment)
        ShipmentService.update_shipment_status(
            shipment_id=str(shipment.id), status=Shipment.STATUS_DELIVERED
        )
        self.order.refresh_from_db()
        self.order.status = Order.STATUS_COMPLETED
        self.order.save()

        # Re-saving the delivered shipment must not pull the order back
        shipment.refresh_from_db()
        shipment.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_COMPLETED)


class ShipmentUpdateApiTests(TestCase):
    """Regression: the update-status response must serialize tracking rows
    (returning raw ShipmentTracking objects 500'd with 'not JSON serializable')."""

    def setUp(self):
        import json as json_lib
        from unittest.mock import patch

        from apps.users.utils.token_utils import generate_jwt_token
        from apps.orders.shipment_service import ShipmentService

        patcher = patch("apps.orders.order_emails.send_templated_email")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.json = json_lib

        self.admin = make_user(role="admin")
        self.token = generate_jwt_token(self.admin)
        self.client = Client()

        user = make_user()
        address = _make_address(user)
        self.order = Order.objects.create(
            user=user,
            payment_method=Order.PAYMENT_MOBILE_MONEY,
            payment_status=Order.PAYMENT_PAID,
            status=Order.STATUS_READY_FOR_SHIPPING,
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("50.00"),
            shipping_cost=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("50.00"),
            currency="GHS",
        )
        self.shipment, _ = ShipmentService.create_shipment(
            order_id=str(self.order.id), created_by=self.admin
        )

    def _put(self, payload):
        return self.client.put(
            f"/api/orders/admin/shipments/{self.shipment.id}/update-status",
            data=self.json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

    def test_mark_shipped_returns_serialized_tracking_history(self):
        response = self._put({"shipment_status": "shipped", "carrier": "DHL"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["shipment"]["status"], "shipped")
        history = data["tracking_history"]
        self.assertIsInstance(history, list)
        self.assertTrue(history)
        for row in history:
            self.assertIn("status", row)
            self.assertIn("created_at", row)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_SHIPPED)

    def test_mark_delivered_via_api(self):
        self._put({"shipment_status": "shipped"})
        response = self._put({"shipment_status": "delivered"})
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_DELIVERED)
