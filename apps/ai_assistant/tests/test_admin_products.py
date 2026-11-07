import json
from unittest.mock import patch

from django.test import TestCase
from langchain_core.messages import AIMessage, ToolMessage

from apps.ai_assistant.tools.admin import (
    get_admin_category, get_admin_product, get_admin_variant, get_inventory_health, list_admin_categories,
    list_admin_variants, search_admin_products,
)
from apps.products.tests.factories import make_category, make_product, make_variant
from apps.users.tests.factories import make_admin, make_staff, make_user
from apps.users.utils.token_utils import generate_jwt_token


class AdminProductToolTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.customer = make_user()
        self.admin_config = {"configurable": {"authenticated_user_id": str(self.admin.pk)}}
        self.customer_config = {"configurable": {"authenticated_user_id": str(self.customer.pk)}}
        self.category = make_category(is_active=False, is_hidden=True)
        self.product = make_product(category=self.category, status="draft")
        self.variant = make_variant(product=self.product, stock=0)

    def invoke(self, tool, args=None, config=None):
        return json.loads(tool.invoke(args or {}, config=config or self.admin_config))

    def test_admin_can_find_draft_product_and_variant(self):
        products = self.invoke(search_admin_products, {"search": self.product.title})
        self.assertEqual(products["data"]["total"], 1)
        self.assertEqual(products["data"]["products"][0]["id"], str(self.product.id))
        detail = self.invoke(get_admin_product, {"product_id": str(self.product.id)})
        self.assertEqual(detail["data"]["status"], "draft")
        variants = self.invoke(list_admin_variants, {"product_id": str(self.product.id)})
        self.assertEqual(variants["data"]["total"], 1)
        self.assertEqual(self.invoke(get_admin_variant, {"variant_id": str(self.variant.pk)})["data"]["sku"], self.variant.sku)

    def test_hidden_category_and_zero_stock_are_visible_to_admin(self):
        categories = self.invoke(list_admin_categories, {"search": self.category.name})
        self.assertEqual(categories["data"]["total"], 1)
        self.assertTrue(categories["data"]["categories"][0]["is_hidden"])
        self.assertTrue(self.invoke(get_admin_category, {"category_id": str(self.category.pk)})["data"]["is_hidden"])
        inventory = self.invoke(get_inventory_health)
        self.assertEqual(inventory["data"]["total_at_risk"], 1)
        self.assertEqual(inventory["data"]["items"][0]["sku"], self.variant.sku)

    def test_customer_cannot_invoke_any_admin_tool(self):
        for tool, args in [
            (search_admin_products, {}),
            (get_admin_product, {"product_id": str(self.product.id)}),
            (get_admin_variant, {"variant_id": str(self.variant.id)}),
            (list_admin_variants, {}),
            (list_admin_categories, {}),
            (get_admin_category, {"category_id": str(self.category.id)}),
            (get_inventory_health, {}),
        ]:
            with self.subTest(tool=tool.name):
                result = self.invoke(tool, args, self.customer_config)
                self.assertFalse(result["success"])
                self.assertNotIn(self.product.title, json.dumps(result))

    def test_staff_can_read_and_inactive_user_cannot(self):
        staff = make_staff()
        staff_config = {"configurable": {"authenticated_user_id": str(staff.pk)}}
        self.assertTrue(self.invoke(get_inventory_health, config=staff_config)["success"])
        staff.is_active = False
        staff.save(update_fields=["is_active"])
        self.assertFalse(self.invoke(get_inventory_health, config=staff_config)["success"])


class AdminChatAccessTests(TestCase):
    def test_customer_forbidden_and_staff_can_chat(self):
        customer = make_user()
        staff = make_staff()
        path = "/api/assistant/admin/chat/"
        payload = json.dumps({"message": "Which products are low on stock?"})
        customer_token = generate_jwt_token(customer)
        staff_token = generate_jwt_token(staff)
        with patch("apps.ai_assistant.services.admin_assistant_service.get_admin_graph") as graph:
            graph.return_value.invoke.return_value = {"messages": [AIMessage(content="One variant is low.")]}
            denied = self.client.post(path, payload, content_type="application/json",
                                      HTTP_AUTHORIZATION=f"Bearer {customer_token}")
            self.assertEqual(denied.status_code, 403)
            self.assertFalse(graph.called)
            allowed = self.client.post(path, payload, content_type="application/json",
                                       HTTP_AUTHORIZATION=f"Bearer {staff_token}")
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(allowed.json()["data"]["response"], "One variant is low.")

    def test_chat_returns_prepared_action_for_review(self):
        staff = make_staff()
        pending = {"action_id": "4a9d77db-4cd1-4215-a63e-4aa57d35b222",
                   "action": "update_product", "details": {"data": {"status": "draft"}}}
        with patch("apps.ai_assistant.services.admin_assistant_service.get_admin_graph") as graph:
            graph.return_value.invoke.return_value = {"messages": [
                ToolMessage(content=json.dumps({"success": True, "pending_action": pending}),
                            tool_call_id="call_1"),
                AIMessage(content="Please review this change."),
            ]}
            response = self.client.post(
                "/api/assistant/admin/chat/", json.dumps({"message": "Draft this product"}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(staff)}",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["pending_actions"], [pending])
