"""Unit tests for AdminProductService.create_product business logic."""

import uuid

from django.test import TestCase

from apps.products.models import Product
from apps.products.services.product_service import AdminProductService
from .factories import make_admin, make_category, make_product


class CreateProductTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.category = make_category()

    def _data(self, **overrides):
        data = {
            "title": f"Product {uuid.uuid4().hex[:6]}",
            "description": "A description",
            "category_id": str(self.category.id),
        }
        data.update(overrides)
        return data

    def test_create_basic_defaults_to_draft(self):
        product, error = AdminProductService.create_product(self._data(), self.admin)
        self.assertIsNone(error)
        self.assertIsNotNone(product)
        self.assertEqual(product.status, Product.STATUS_DRAFT)
        self.assertIsNone(product.published_at)

    def test_create_published_sets_published_at(self):
        product, error = AdminProductService.create_product(
            self._data(status=Product.STATUS_PUBLISHED), self.admin
        )
        self.assertIsNone(error)
        self.assertEqual(product.status, Product.STATUS_PUBLISHED)
        self.assertIsNotNone(product.published_at)

    def test_create_missing_category_rejected(self):
        product, error = AdminProductService.create_product(
            self._data(category_id=str(uuid.uuid4())), self.admin
        )
        self.assertIsNone(product)
        self.assertIn("category_id", error)

    def test_slug_uniqueness_on_duplicate_title(self):
        make_product(title="Same Title", slug="same-title", category=self.category)
        product, error = AdminProductService.create_product(
            self._data(title="Same Title"), self.admin
        )
        self.assertIsNone(error)
        self.assertEqual(product.slug, "same-title-1")
