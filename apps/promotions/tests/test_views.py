import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.promotions.models import DiscountCode
from apps.promotions.tests.factories import make_affiliate, make_discount_code
from apps.users.utils.token_utils import generate_jwt_token

User = get_user_model()


class DiscountCodeAdminApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_admin(
            email="admin-discount@example.com",
            password="testpass123",
        )
        self.staff = User.objects.create_staff(
            email="staff-discount@example.com",
            password="testpass123",
        )

    def _auth_headers(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_staff_can_list_discount_codes(self):
        make_discount_code(code="LIST10", created_by=self.admin)

        response = self.client.get(
            "/api/promotions/admin/discount-codes",
            **self._auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertGreaterEqual(body["data"]["total"], 1)

    def test_admin_can_create_discount_code(self):
        response = self.client.post(
            "/api/promotions/admin/discount-codes/create",
            data=json.dumps({
                "code": "WELCOME15",
                "name": "Welcome Discount",
                "discount_type": DiscountCode.TYPE_PERCENTAGE,
                "value": "15.00",
                "min_subtotal": "50.00",
                "description": "New customer discount",
            }),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(DiscountCode.objects.filter(code="WELCOME15").exists())

    def test_admin_can_update_discount_code(self):
        discount_code = make_discount_code(code="UPDATE10", created_by=self.admin)

        response = self.client.put(
            f"/api/promotions/admin/discount-codes/{discount_code.id}/update",
            data=json.dumps({
                "name": "Updated Discount",
                "value": "12.50",
            }),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )

        self.assertEqual(response.status_code, 200)
        discount_code.refresh_from_db()
        self.assertEqual(discount_code.name, "Updated Discount")
        self.assertEqual(str(discount_code.value), "12.50")

    def test_admin_can_toggle_discount_code_status(self):
        affiliate = make_affiliate()
        discount_code = make_discount_code(
            code="AFFSTATUS",
            affiliate=affiliate,
            is_active=True,
            created_by=self.admin,
        )

        response = self.client.post(
            f"/api/promotions/admin/discount-codes/{discount_code.id}/status",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )

        self.assertEqual(response.status_code, 200)
        discount_code.refresh_from_db()
        self.assertFalse(discount_code.is_active)

    def test_admin_cannot_create_discount_code_using_affiliate_referral_code(self):
        affiliate = make_affiliate(referral_code="REFLOCK01")

        response = self.client.post(
            "/api/promotions/admin/discount-codes/create",
            data=json.dumps({
                "code": affiliate.referral_code,
                "name": "Conflict Discount",
                "discount_type": DiscountCode.TYPE_PERCENTAGE,
                "value": "10.00",
            }),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("code", response.json()["errors"])


class AffiliateDashboardApiTests(TestCase):
    """GET /api/promotions/affiliate/dashboard — an affiliate's own orders,
    earnings summary, and month filtering."""

    def setUp(self):
        from decimal import Decimal

        from django.utils import timezone

        from apps.orders.models import Order
        from apps.promotions.models import AffiliateCommission
        from apps.users.models import Address

        self.client = Client()
        self.affiliate = make_affiliate(commission_rate="10.00")
        self.token = generate_jwt_token(self.affiliate.user)
        code = make_discount_code(code="DASH10", affiliate=self.affiliate, value="5.00")

        customer = make_affiliate().user  # any registered user works as buyer
        address = Address.objects.create(
            user=customer,
            address_type="shipping",
            first_name="Jane",
            last_name="Doe",
            email=customer.email,
            phone="+233000000002",
            address_line1="123 Street",
            city="Accra",
            state="Greater Accra",
            postal_code="GA-123",
            country="GH",
        )

        # Two commissions in different months (order created_at drives the filter)
        for i, (status, month_offset) in enumerate(
            [(AffiliateCommission.STATUS_ACCRUED, 0), (AffiliateCommission.STATUS_PENDING, 1)]
        ):
            order = Order.objects.create(
                user=customer,
                order_number=f"ORDDASH000{i}",
                status=Order.STATUS_CONFIRMED,
                payment_status=Order.PAYMENT_PAID,
                payment_method="paystack",
                shipping_address=address,
                billing_address=address,
                subtotal=Decimal("200.00"),
                shipping_cost=Decimal("10.00"),
                tax_amount=Decimal("0.00"),
                discount_amount=Decimal("10.00"),
                discount_code=code,
                affiliate=self.affiliate,
                total=Decimal("200.00"),
                currency="GHS",
            )
            if month_offset:
                shifted = timezone.now() - timezone.timedelta(days=35)
                Order.objects.filter(pk=order.pk).update(created_at=shifted)
            AffiliateCommission.objects.create(
                affiliate=self.affiliate,
                order=order,
                discount_code=code,
                commission_rate=Decimal("10.00"),
                commissionable_amount=Decimal("190.00"),
                commission_amount=Decimal("19.00"),
                status=status,
            )

    def _get(self, token=None, **params):
        from urllib.parse import urlencode

        qs = f"?{urlencode(params)}" if params else ""
        return self.client.get(
            f"/api/promotions/affiliate/dashboard{qs}",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}",
        )

    def test_returns_summary_and_commissions(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["affiliate"]["referral_code"], self.affiliate.referral_code)
        self.assertEqual(data["summary"]["order_count"], 2)
        self.assertEqual(data["summary"]["earned"], 19.0)
        self.assertEqual(data["summary"]["pending"], 19.0)
        self.assertEqual(len(data["commissions"]), 2)
        row = data["commissions"][0]
        for key in ("order_number", "order_total", "commission_amount", "status", "order_date"):
            self.assertIn(key, row)

    def test_month_filter_limits_results(self):
        from django.utils import timezone

        now = timezone.now()
        response = self._get(year=now.year, month=now.month)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["summary"]["order_count"], 1)
        self.assertEqual(len(data["commissions"]), 1)
        self.assertEqual(data["commissions"][0]["status"], "accrued")

    def test_non_affiliate_is_rejected(self):
        from apps.products.tests.factories import make_user

        outsider = make_user()
        response = self._get(token=generate_jwt_token(outsider))
        self.assertEqual(response.status_code, 403)

    def test_invalid_month_is_rejected(self):
        response = self._get(month=13)
        self.assertEqual(response.status_code, 422)
