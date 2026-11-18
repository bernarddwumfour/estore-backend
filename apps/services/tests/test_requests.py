import json

from django.test import TestCase

from apps.services.models import Service, ServiceRequest
from apps.services.schemas.request_schemas import validate_service_request


class ServiceRequestTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(title="Screen Repair", slug="screen-repair", status=Service.PUBLISHED)
        self.payload = {
            "service_type": "screen-repair",
            "device_model": "iPhone 15",
            "customer_name": "Ada Smith",
            "customer_email": "ada@example.com",
            "customer_phone": "0241234567",
            "issue_description": "Cracked display",
        }

    def test_submit_public_service_request(self):
        response = self.client.post("/api/services/requests", data=json.dumps(self.payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        item = ServiceRequest.objects.get()
        self.assertEqual(item.service, self.service)
        self.assertEqual(item.issue_description, "Cracked display")

    def test_reject_unpublished_service_without_creating_request(self):
        self.service.status = Service.DRAFT
        self.service.save()
        response = self.client.post("/api/services/requests", data=json.dumps(self.payload), content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertFalse(ServiceRequest.objects.exists())

    def test_other_service_requires_description(self):
        self.payload["service_type"] = "other"
        _, errors = validate_service_request(self.payload)
        self.assertIn("custom_service_type", errors)
        self.payload["custom_service_type"] = "Data recovery"
        response = self.client.post("/api/services/requests", data=json.dumps(self.payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ServiceRequest.objects.get().custom_service_type, "Data recovery")
