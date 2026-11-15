import json
from datetime import timedelta, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.ai_assistant.services.admin_product_action_service import AdminProductActionService
from apps.ai_assistant.services.appointment_action_service import confirm, get_review, prepare
from apps.ai_assistant.tools.admin.service_tools import search_admin_services
from apps.ai_assistant.tools.shopper.appointment_tools import list_my_appointments
from apps.services.models import Appointment, BookingHours, BookingSettings, Service, ServiceOption
from apps.services.services.booking_service import available_slots


class AppointmentAssistantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(email="shopper@example.com", password="password123")
        self.other = get_user_model().objects.create_user(email="other@example.com", password="password123")
        self.admin = get_user_model().objects.create_user(email="admin@example.com", password="password123", role="admin")
        day = (timezone.now() + timedelta(days=3)).date()
        BookingSettings.objects.create(enabled=True, timezone="UTC")
        BookingHours.objects.create(weekday=day.weekday(), opens_at=time(9), closes_at=time(17))
        self.service = Service.objects.create(title="Repair", slug="repair", status=Service.PUBLISHED)
        self.option = ServiceOption.objects.create(service=self.service, name="Basic", slug="basic", price=100, duration_minutes=60)
        self.start = available_slots(self.option.pk, day)[0]

    def test_review_is_owned_and_confirmation_rechecks_slot(self):
        data = {"option_id": str(self.option.pk), "starts_at": self.start, "customer_name": "Customer", "customer_phone": "0200000000"}
        first = prepare(self.user, "book", data)
        second = prepare(self.other, "book", data)
        token = first["review_path"].rsplit('/', 1)[-1]
        self.assertIsNone(get_review(self.other, token))
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(confirm(self.user, token)["status"], "pending")
        with self.assertRaises(ValueError): confirm(self.user, token)
        with self.assertRaises(ValueError): confirm(self.other, second["review_path"].rsplit('/', 1)[-1])
        self.assertEqual(Appointment.objects.count(), 1)

    def test_customer_cannot_access_another_appointment(self):
        data = {"option_id": str(self.option.pk), "starts_at": self.start, "customer_name": "Customer", "customer_phone": "0200000000"}
        token = prepare(self.user, "book", data)["review_path"].rsplit('/', 1)[-1]
        appointment = confirm(self.user, token)
        config = {"configurable": {"authenticated_user_id": str(self.other.pk)}}
        result = json.loads(list_my_appointments.invoke({"appointment_id": appointment["id"]}, config=config))
        self.assertFalse(result["success"])
        with self.assertRaises(ValueError): prepare(self.other, "cancel", {"appointment_id": appointment["id"]})

    def test_admin_changes_require_confirmation_and_role(self):
        user_config = {"configurable": {"authenticated_user_id": str(self.user.pk)}}
        self.assertFalse(json.loads(search_admin_services.invoke({}, config=user_config))["success"])
        pending, errors = AdminProductActionService.prepare(self.admin, "update_service", {"target_id": str(self.service.pk), "data": {"title": "New name"}})
        self.assertIsNone(errors)
        self.service.refresh_from_db()
        self.assertEqual(self.service.title, "Repair")
        result, errors = AdminProductActionService.confirm(self.other, pending["action_id"])
        self.assertIsNotNone(errors)
        result, errors = AdminProductActionService.confirm(self.admin, pending["action_id"])
        self.assertIsNone(errors)
        self.service.refresh_from_db()
        self.assertEqual(self.service.title, "New name")
