import json

from django.test import TestCase

from apps.ai_assistant.tools.guest import GUEST_TOOLS
from apps.ai_assistant.tools.shopper import SHOPPER_TOOLS
from apps.ai_assistant.tools.shopper.service_tools import (
    compare_services, get_service_details, list_service_categories, search_services,
)
from apps.services.models import Service, ServiceCategory, ServiceOption


class ServiceToolsTests(TestCase):
    def setUp(self):
        self.category = ServiceCategory.objects.create(name="Repairs", slug="repairs")
        self.service = Service.objects.create(title="Screen repair", slug="screen-repair", status=Service.PUBLISHED, category=self.category)
        ServiceOption.objects.create(service=self.service, name="Standard", slug="standard", pricing_type="from", price=100)
        ServiceOption.objects.create(service=self.service, name="Old", slug="old", price=10, is_active=False)
        Service.objects.create(title="Draft repair", slug="draft-repair", status=Service.DRAFT)
        hidden = ServiceCategory.objects.create(name="Hidden", slug="hidden", is_hidden=True)
        Service.objects.create(title="Hidden repair", slug="hidden-repair", status=Service.PUBLISHED, category=hidden)

    def test_search_returns_only_visible_services_and_active_options(self):
        result = json.loads(search_services.invoke({"query": "repair"}))
        self.assertEqual([s["slug"] for s in result["services"]], ["screen-repair"])
        self.assertEqual(result["services"][0]["options"][0]["pricing_type"], "from")
        self.assertEqual(len(result["services"][0]["options"]), 1)

    def test_details_categories_and_comparison_respect_visibility(self):
        self.assertFalse(json.loads(get_service_details.invoke({"slug": "hidden-repair"}))["success"])
        self.assertEqual(len(json.loads(list_service_categories.invoke({}))["categories"]), 1)
        result = json.loads(compare_services.invoke({"slugs": ["screen-repair", "draft-repair"]}))
        self.assertEqual(result["not_found"], ["draft-repair"])
        self.assertEqual(result["services"][0]["slug"], "screen-repair")

    def test_tools_registered_for_both_agents(self):
        names = {"search_services", "get_service_details", "list_service_categories", "compare_services"}
        for tools in (SHOPPER_TOOLS, GUEST_TOOLS):
            self.assertTrue(names.issubset({tool.name for tool in tools}))
