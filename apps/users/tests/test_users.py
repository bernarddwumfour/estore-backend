import json

from django.test import Client, TestCase
from django.contrib.auth import get_user_model

from apps.promotions.models import DiscountCode
from apps.promotions.tests.factories import make_affiliate, make_discount_code, make_user
from apps.users.utils.token_utils import generate_jwt_token

User = get_user_model()


class UserCreationTest(TestCase):

    def test_create_customer(self):
        customer = User.objects.create_customer(
            email="customer@example.com",
            password="testpass123",
            first_name="John",
            last_name="Doe"
        )

        self.assertEqual(customer.role, User.ROLE_CUSTOMER)
        self.assertTrue(customer.is_customer())
        self.assertFalse(customer.is_admin())

    def test_create_staff(self):
        staff = User.objects.create_staff(
            email="staff@example.com",
            password="testpass123",
        )

        self.assertEqual(staff.role, User.ROLE_STAFF)
        self.assertTrue(staff.is_staff_member())
        self.assertTrue(staff.is_staff)

    def test_create_admin(self):
        admin = User.objects.create_admin(
            email="admin@example.com",
            password="testpass123"
        )

        self.assertTrue(admin.is_admin())
        self.assertTrue(admin.is_superuser)


class AffiliateAdminApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_staff(
            email="staff-affiliates@example.com",
            password="testpass123",
        )
        self.admin = User.objects.create_admin(
            email="admin-affiliates@example.com",
            password="testpass123",
        )

    def _auth_headers(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_staff_can_make_affiliate_by_email_with_selected_discount_code(self):
        user = make_user(email="new-affiliate@example.com")
        discount_code = make_discount_code(code="AFFSELECT", created_by=self.admin)

        response = self.client.post(
            "/api/users/admin/affiliates/make-by-email",
            data=json.dumps({
                "email": user.email,
                "discount_code_id": str(discount_code.id),
                "referral_code": "NEWAFF01",
            }),
            content_type="application/json",
            **self._auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["email"], user.email)
        self.assertEqual(body["data"]["referral_code"], "NEWAFF01")
        discount_code.refresh_from_db()
        self.assertEqual(discount_code.affiliate.user, user)

    def test_make_affiliate_rejects_referral_code_that_matches_discount_code(self):
        user = make_user(email="conflict-affiliate@example.com")
        discount_code = make_discount_code(code="TAKENREF", created_by=self.admin)

        response = self.client.post(
            "/api/users/admin/affiliates/make-by-email",
            data=json.dumps({
                "email": user.email,
                "discount_code_id": str(discount_code.id),
                "referral_code": "takenref",
            }),
            content_type="application/json",
            **self._auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("referral_code", response.json()["errors"])

    def test_staff_can_toggle_affiliate_status_and_discount_code_status(self):
        affiliate = make_affiliate(user=make_user(email="toggle-affiliate@example.com"))
        discount_code = make_discount_code(
            code="TOGGLE10",
            affiliate=affiliate,
            created_by=self.admin,
        )

        response = self.client.post(
            f"/api/users/admin/affiliates/{affiliate.user_id}/status",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
            **self._auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 200)
        affiliate.refresh_from_db()
        discount_code.refresh_from_db()
        self.assertFalse(affiliate.is_active)
        self.assertFalse(discount_code.is_active)

    def test_staff_can_list_affiliates(self):
        make_affiliate(user=make_user(email="listed-affiliate@example.com"))

        response = self.client.get(
            "/api/users/admin/affiliates",
            **self._auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertGreaterEqual(body["data"]["total"], 1)

    def test_make_affiliate_requires_discount_code_selection(self):
        user = make_user(email="missing-code@example.com")

        response = self.client.post(
            "/api/users/admin/affiliates/make-by-email",
            data=json.dumps({"email": user.email}),
            content_type="application/json",
            **self._auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("discount_code_id", response.json()["errors"])


class AffiliateCommissionAdminApiTests(TestCase):
    """Creating an affiliate with a commission rate/basis and editing it later."""

    def setUp(self):
        import json as json_lib

        from django.test import Client

        from apps.products.tests.factories import make_user
        from apps.promotions.models import DiscountCode
        from apps.users.utils.token_utils import generate_jwt_token

        self.json = json_lib
        self.client = Client()
        self.admin = make_user(role="admin")
        self.token = generate_jwt_token(self.admin)
        self.customer = make_user()
        self.discount_code = DiscountCode.objects.create(
            code="COMMISH10",
            name="Commission Test",
            discount_type=DiscountCode.TYPE_PERCENTAGE,
            value="10.00",
            is_active=True,
        )

    def _post(self, url, payload, token=None):
        return self.client.post(
            url,
            data=self.json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}",
        )

    def _make_by_email(self, **extra):
        return self._post(
            "/api/users/admin/affiliates/make-by-email",
            {
                "email": self.customer.email,
                "discount_code_id": str(self.discount_code.id),
                **extra,
            },
        )

    def test_make_affiliate_with_rate_and_basis(self):
        from apps.users.models import Affiliate

        response = self._make_by_email(commission_rate=12.5, commission_basis="profit")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["commission_rate"], 12.5)
        self.assertEqual(data["commission_basis"], "profit")

        affiliate = Affiliate.objects.get(user=self.customer)
        self.assertEqual(float(affiliate.commission_rate), 12.5)
        self.assertEqual(affiliate.commission_basis, Affiliate.BASIS_PROFIT)

    def test_make_affiliate_defaults_when_commission_omitted(self):
        from apps.users.models import Affiliate

        response = self._make_by_email()
        self.assertEqual(response.status_code, 200)
        affiliate = Affiliate.objects.get(user=self.customer)
        self.assertEqual(float(affiliate.commission_rate), 2.0)
        self.assertEqual(affiliate.commission_basis, Affiliate.BASIS_SALE_AMOUNT)

    def test_invalid_rate_and_basis_rejected(self):
        response = self._make_by_email(commission_rate=150)
        self.assertEqual(response.status_code, 422)
        response = self._make_by_email(commission_basis="revenue")
        self.assertEqual(response.status_code, 422)

    def test_update_commission_endpoint(self):
        from apps.users.models import Affiliate

        self._make_by_email(commission_rate=5)
        response = self.client.put(
            f"/api/users/admin/affiliates/{self.customer.id}/commission",
            data=self.json.dumps({"commission_rate": 7.5, "commission_basis": "profit"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 200)
        affiliate = Affiliate.objects.get(user=self.customer)
        self.assertEqual(float(affiliate.commission_rate), 7.5)
        self.assertEqual(affiliate.commission_basis, Affiliate.BASIS_PROFIT)

        # Empty payload rejected
        response = self.client.put(
            f"/api/users/admin/affiliates/{self.customer.id}/commission",
            data=self.json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 422)

    def test_update_commission_requires_admin(self):
        from apps.products.tests.factories import make_user
        from apps.users.utils.token_utils import generate_jwt_token

        self._make_by_email()
        outsider_token = generate_jwt_token(make_user())
        response = self.client.put(
            f"/api/users/admin/affiliates/{self.customer.id}/commission",
            data=self.json.dumps({"commission_rate": 50}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {outsider_token}",
        )
        self.assertEqual(response.status_code, 403)
