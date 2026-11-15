from datetime import timedelta, time
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.services.models import BookingSettings, BookingHours, Service, ServiceOption
from apps.services.services.booking_service import available_slots, create_appointment
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from unittest import skipUnless


class BookingTests(TestCase):
    def test_only_one_overlapping_appointment(self):
        user = get_user_model().objects.create_user(email="booking@example.com", password="password123")
        day = (timezone.now() + timedelta(days=3)).date()
        BookingSettings.objects.create(enabled=True, timezone="UTC", slot_interval_minutes=30)
        BookingHours.objects.create(weekday=day.weekday(), opens_at=time(9), closes_at=time(17))
        service = Service.objects.create(title="Repair", slug="repair", status=Service.PUBLISHED)
        option = ServiceOption.objects.create(service=service, name="Standard", slug="standard", price=100, duration_minutes=60)
        slots = available_slots(option.pk, day)
        from datetime import datetime
        start = datetime.fromisoformat(slots[0])
        create_appointment(user, option.pk, start, "Customer", "0200000000")
        self.assertNotIn(slots[0], available_slots(option.pk, day))
        self.assertNotIn(slots[1], available_slots(option.pk, day))
        with self.assertRaises(ValueError):
            create_appointment(user, option.pk, start, "Customer", "0200000000")

    @patch("apps.users.decorators.auth.validate_jwt_token")
    def test_booking_endpoints_and_permissions(self, validate):
        user = get_user_model().objects.create_user(email="shopper@example.com", password="password123")
        admin = get_user_model().objects.create_user(email="staff@example.com", password="password123", role="admin")
        day = (timezone.now() + timedelta(days=3)).date()
        BookingSettings.objects.create(enabled=True, timezone="UTC")
        BookingHours.objects.create(weekday=day.weekday(), opens_at=time(9), closes_at=time(17))
        service = Service.objects.create(title="Repair", slug="repair", status=Service.PUBLISHED)
        option = ServiceOption.objects.create(service=service, name="Basic", slug="basic", price=100, duration_minutes=60)
        validate.return_value = (True, {"type": "access", "user_id": str(user.pk)})
        headers = {"HTTP_AUTHORIZATION": "Bearer test"}
        self.assertEqual(self.client.get('/api/services/admin/appointments', **headers).status_code, 403)
        response = self.client.get('/api/services/availability', {"date": day.isoformat(), "option_id": str(option.pk)})
        start = response.json()['data']['slots'][0]
        response = self.client.post('/api/services/appointments', data={"option_id": str(option.pk), "starts_at": start, "customer_name": "Customer", "customer_phone": "0200000000"}, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 201)
        appointment_id = response.json()['data']['appointment']['id']
        self.assertEqual(self.client.delete(f'/api/services/appointments/{appointment_id}', **headers).status_code, 200)
        validate.return_value = (True, {"type": "access", "user_id": str(admin.pk)})
        response = self.client.post('/api/services/admin/booking-exceptions', data={"date": day.isoformat(), "is_closed": True}, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(available_slots(option.pk, day), [])


@skipUnless(connection.vendor == "postgresql", "Row locking requires PostgreSQL")
class ConcurrentBookingTests(TransactionTestCase):
    def test_simultaneous_requests_only_allocate_one_appointment(self):
        user = get_user_model().objects.create_user(email="race@example.com", password="password123")
        day = (timezone.now() + timedelta(days=3)).date()
        BookingSettings.objects.create(enabled=True, timezone="UTC")
        BookingHours.objects.create(weekday=day.weekday(), opens_at=time(9), closes_at=time(17))
        service = Service.objects.create(title="Repair", slug="repair", status=Service.PUBLISHED)
        option = ServiceOption.objects.create(service=service, name="Basic", slug="basic", price=100, duration_minutes=60)
        from datetime import datetime
        start = datetime.fromisoformat(available_slots(option.pk, day)[0])
        barrier = Barrier(2)

        def book():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                create_appointment(get_user_model().objects.get(pk=user.pk), option.pk, start, "Customer", "0200000000")
                return "created"
            except ValueError:
                return "unavailable"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(lambda _: book(), range(2))), ["created", "unavailable"])
