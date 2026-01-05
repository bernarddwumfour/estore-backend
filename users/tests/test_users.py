from django.test import TestCase
from django.contrib.auth import get_user_model

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
            employee_id="EMP001"
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
