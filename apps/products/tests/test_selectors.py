"""Unit tests for products selectors (read queries / visibility rules)."""

import uuid

from django.test import TestCase

from apps.products.models import Product
from apps.products.selectors.category_selectors import (
    get_category_by_id,
    get_category_by_slug,
    get_all_categories,
    get_subcategories,
)
from apps.products.selectors.product_selectors import get_product_by_slug
from apps.products.selectors.variant_selectors import (
    get_variant_by_id,
    get_variant_by_sku,
)
from .factories import make_category, make_product, make_variant


class CategorySelectorTests(TestCase):
    def test_get_by_id_hides_hidden_from_customers(self):
        hidden = make_category(is_hidden=True)
        self.assertIsNone(get_category_by_id(str(hidden.id), is_admin=False))
        self.assertIsNotNone(get_category_by_id(str(hidden.id), is_admin=True))

    def test_get_by_id_invalid_uuid_returns_none(self):
        self.assertIsNone(get_category_by_id("not-a-uuid"))

    def test_get_by_slug_respects_active_and_hidden(self):
        make_category(slug="visible", is_active=True, is_hidden=False)
        self.assertIsNotNone(get_category_by_slug("visible"))

        make_category(slug="inactive", is_active=False)
        self.assertIsNone(get_category_by_slug("inactive", only_active=True))
        self.assertIsNotNone(get_category_by_slug("inactive", only_active=False))

    def test_get_all_categories_pagination_metadata(self):
        for i in range(5):
            make_category(name=f"C{i}", slug=f"c{i}")
        categories, total, meta = get_all_categories(page=1, limit=2)
        self.assertEqual(total, 5)
        self.assertEqual(len(categories), 2)
        self.assertEqual(meta["total_pages"], 3)
        self.assertTrue(meta["has_next"])
        self.assertFalse(meta["has_previous"])
        self.assertEqual(meta["current_page"], 1)

    def test_get_all_categories_search(self):
        make_category(name="Electronics", slug="electronics")
        make_category(name="Groceries", slug="groceries")
        categories, total, _ = get_all_categories(search="electro")
        self.assertEqual(total, 1)
        self.assertEqual(categories[0].name, "Electronics")

    def test_get_all_categories_excludes_hidden_for_customer(self):
        make_category(slug="pub", is_hidden=False)
        make_category(slug="sec", is_hidden=True)
        _, total_customer, _ = get_all_categories(is_admin=False)
        _, total_admin, _ = get_all_categories(is_admin=True)
        self.assertEqual(total_customer, 1)
        self.assertEqual(total_admin, 2)

    def test_get_subcategories(self):
        parent = make_category()
        make_category(parent=parent, name="sub-a")
        make_category(parent=parent, name="sub-b")
        subs = get_subcategories(str(parent.id))
        self.assertEqual(len(subs), 2)

    def test_get_subcategories_missing_parent(self):
        self.assertEqual(get_subcategories(str(uuid.uuid4())), [])


class ProductSelectorTests(TestCase):
    def test_get_product_by_slug_only_published(self):
        make_product(slug="live", status=Product.STATUS_PUBLISHED)
        make_product(slug="hidden", status=Product.STATUS_DRAFT)
        self.assertIsNotNone(get_product_by_slug("live"))
        self.assertIsNone(get_product_by_slug("hidden"))
        self.assertIsNotNone(get_product_by_slug("hidden", include_inactive=True))

    def test_get_product_by_slug_missing(self):
        self.assertIsNone(get_product_by_slug("nope"))


class VariantSelectorTests(TestCase):
    def test_get_variant_by_id_require_active(self):
        active = make_variant(is_active=True)
        inactive = make_variant(is_active=False, sku="inact")
        self.assertIsNotNone(get_variant_by_id(str(active.id)))
        self.assertIsNone(get_variant_by_id(str(inactive.id), require_active=True))
        self.assertIsNotNone(get_variant_by_id(str(inactive.id), require_active=False))

    def test_get_variant_by_id_invalid_uuid(self):
        self.assertIsNone(get_variant_by_id("bad-id"))

    def test_get_variant_by_sku(self):
        variant = make_variant(sku="FIND-ME")
        self.assertEqual(get_variant_by_sku("FIND-ME"), variant)
        self.assertIsNone(get_variant_by_sku("MISSING"))
