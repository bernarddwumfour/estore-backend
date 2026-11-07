import json

from django.core.cache import cache
from django.test import TestCase

from apps.ai_assistant.tools.admin import (
    bulk_admin_categories, bulk_admin_products, bulk_admin_variants, create_admin_category,
    create_admin_product, create_admin_variant, update_admin_product,
    update_admin_category, update_admin_variant,
)
from apps.products.models import Category, Product, ProductVariant
from apps.products.tests.factories import make_category, make_product, make_variant
from apps.users.tests.factories import make_admin, make_staff, make_user
from apps.users.utils.token_utils import generate_jwt_token


class AdminProductActionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_admin()
        self.other_staff = make_staff()
        self.customer = make_user()
        self.category = make_category()
        self.config = {"configurable": {"authenticated_user_id": str(self.admin.pk)}}

    def prepare(self, tool, args):
        result = json.loads(tool.invoke(args, config=self.config))
        self.assertTrue(result["success"], result)
        return result["pending_action"]

    def confirm(self, pending, user=None):
        user = user or self.admin
        return self.client.post(
            pending["confirmation_path"],
            HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(user)}",
        )

    def test_product_create_requires_confirmation_and_is_single_use(self):
        pending = self.prepare(create_admin_product, {
            "title": "Admin Agent Item", "description": "A product", "category_id": str(self.category.pk)
        })
        self.assertFalse(Product.objects.filter(title="Admin Agent Item").exists())
        self.assertEqual(self.confirm(pending, self.customer).status_code, 403)
        self.assertEqual(self.confirm(pending, self.other_staff).status_code, 400)
        self.assertFalse(Product.objects.filter(title="Admin Agent Item").exists())
        self.assertEqual(self.confirm(pending).status_code, 200)
        self.assertTrue(Product.objects.filter(title="Admin Agent Item", status="draft").exists())
        self.assertEqual(self.confirm(pending).status_code, 400)

    def test_variant_stock_and_product_status_changes(self):
        product = make_product(category=self.category, status="draft")
        pending_variant = self.prepare(create_admin_variant, {
            "product_id": str(product.pk), "sku": "AGENT-1", "price": 120,
            "cost_price": 70, "stock": 4
        })
        self.assertFalse(ProductVariant.objects.filter(sku="AGENT-1").exists())
        self.assertEqual(self.confirm(pending_variant).status_code, 200)
        variant = ProductVariant.objects.get(sku="AGENT-1")
        self.assertEqual(variant.cost_price, 70)
        pending_stock = self.prepare(update_admin_variant, {
            "variant_id": str(variant.pk), "changes": {"stock": 9}
        })
        self.assertEqual(self.confirm(pending_stock).status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 9)
        pending_product = self.prepare(update_admin_product, {
            "product_id": str(product.pk), "changes": {"status": "archived"}
        })
        self.assertEqual(self.confirm(pending_product).status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.status, "archived")

    def test_category_and_bulk_actions(self):
        pending_category = self.prepare(create_admin_category, {"name": "Agent Category"})
        self.assertEqual(self.confirm(pending_category).status_code, 200)
        category = Category.objects.get(name="Agent Category")
        pending_update = self.prepare(update_admin_category, {
            "category_id": str(category.pk), "changes": {"is_hidden": True}
        })
        self.assertEqual(self.confirm(pending_update).status_code, 200)
        category.refresh_from_db()
        self.assertTrue(category.is_hidden)
        pending_category_bulk = self.prepare(bulk_admin_categories, {
            "ids": [str(category.pk)], "action": "deactivate"
        })
        self.assertEqual(self.confirm(pending_category_bulk).status_code, 200)
        category.refresh_from_db()
        self.assertFalse(category.is_active)
        product = make_product(category=self.category)
        pending_bulk = self.prepare(bulk_admin_products, {
            "ids": [str(product.pk)], "action": "archive"
        })
        self.assertEqual(self.confirm(pending_bulk).status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.status, "archived")
        variant = make_variant(product=product)
        pending_variant = self.prepare(bulk_admin_variants, {
            "ids": [str(variant.pk)], "action": "deactivate"
        })
        self.assertEqual(self.confirm(pending_variant).status_code, 200)
        variant.refresh_from_db()
        self.assertFalse(variant.is_active)

    def test_customer_cannot_prepare_changes(self):
        result = json.loads(create_admin_category.invoke(
            {"name": "Forbidden"},
            config={"configurable": {"authenticated_user_id": str(self.customer.pk)}},
        ))
        self.assertFalse(result["success"])
