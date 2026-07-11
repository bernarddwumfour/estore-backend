"""
Unit tests for products app models — properties, methods, constraints, and the
concurrency-safe stock operations.
"""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from apps.products.models import Category, Product, ProductVariant
from .factories import (
    make_category,
    make_product,
    make_variant,
    make_user,
    make_review,
)


class CategoryModelTests(TestCase):
    def test_str(self):
        cat = make_category(name="Electronics")
        self.assertEqual(str(cat), "Electronics")

    def test_full_path_nested(self):
        root = make_category(name="Electronics")
        mid = make_category(name="Audio", parent=root)
        leaf = make_category(name="Headphones", parent=mid)
        self.assertEqual(leaf.full_path, "Electronics > Audio > Headphones")
        self.assertEqual(root.full_path, "Electronics")

    def test_get_all_descendants_includes_self(self):
        root = make_category(name="Root")
        child_a = make_category(name="A", parent=root)
        child_b = make_category(name="B", parent=root)
        grandchild = make_category(name="A1", parent=child_a)

        descendants = root.get_all_descendants()
        self.assertIn(root, descendants)
        self.assertIn(child_a, descendants)
        self.assertIn(child_b, descendants)
        self.assertIn(grandchild, descendants)
        self.assertEqual(len(descendants), 4)

    def test_get_descendant_ids(self):
        root = make_category()
        child = make_category(parent=root)
        ids = root.get_descendant_ids()
        self.assertCountEqual(ids, [root.id, child.id])

    def test_get_descendants_from_slug_active(self):
        root = make_category(slug="root-cat", is_active=True)
        make_category(parent=root)
        result = Category.get_descendants_from_slug("root-cat")
        self.assertEqual(len(result), 2)

    def test_get_descendants_from_slug_missing_returns_empty(self):
        self.assertEqual(Category.get_descendants_from_slug("does-not-exist"), [])

    def test_name_uniqueness_enforced(self):
        make_category(name="Dup", slug="dup-1")
        with self.assertRaises(IntegrityError):
            make_category(name="Dup", slug="dup-2")


class ProductModelTests(TestCase):
    def test_str(self):
        product = make_product(title="Cool Phone")
        self.assertEqual(str(product), "Cool Phone")

    def test_published_at_set_on_publish(self):
        product = make_product(status=Product.STATUS_DRAFT)
        self.assertIsNone(product.published_at)
        product.status = Product.STATUS_PUBLISHED
        product.save()
        self.assertIsNotNone(product.published_at)

    def test_published_at_not_overwritten(self):
        product = make_product(status=Product.STATUS_PUBLISHED)
        first = product.published_at
        self.assertIsNotNone(first)
        product.title = "Renamed"
        product.save()
        self.assertEqual(product.published_at, first)

    def test_price_aggregates_across_variants(self):
        product = make_product()
        make_variant(product, price=Decimal("50.00"))
        make_variant(product, price=Decimal("150.00"))
        self.assertEqual(product.min_price, Decimal("50.00"))
        self.assertEqual(product.max_price, Decimal("150.00"))

    def test_price_with_no_variants_is_zero(self):
        product = make_product()
        self.assertEqual(product.min_price, 0)
        self.assertEqual(product.max_price, 0)

    def test_total_stock_and_has_stock(self):
        product = make_product()
        make_variant(product, stock=3)
        make_variant(product, stock=7)
        self.assertEqual(product.total_stock, 10)
        self.assertTrue(product.has_stock)

    def test_has_stock_false_when_all_zero(self):
        product = make_product()
        make_variant(product, stock=0)
        self.assertFalse(product.has_stock)

    def test_default_variant_prefers_flagged(self):
        product = make_product()
        make_variant(product, is_default=False, sku="v-a")
        default = make_variant(product, is_default=True, sku="v-b")
        self.assertEqual(product.default_variant, default)


class ProductVariantModelTests(TestCase):
    def test_str(self):
        product = make_product(title="Headphones")
        variant = make_variant(product, sku="HP-BLK")
        self.assertEqual(str(variant), "HP-BLK - Headphones")

    def test_discounted_price_and_percentage(self):
        variant = make_variant(price=Decimal("200.00"), discount_amount=Decimal("50.00"))
        self.assertEqual(variant.discounted_price, Decimal("150.00"))
        self.assertEqual(variant.discount_percentage, Decimal("25"))

    def test_discount_percentage_zero_when_no_discount(self):
        variant = make_variant(price=Decimal("100.00"), discount_amount=Decimal("0"))
        self.assertEqual(variant.discount_percentage, 0)

    def test_is_in_stock(self):
        self.assertTrue(make_variant(stock=1).is_in_stock)
        self.assertFalse(make_variant(stock=0).is_in_stock)

    def test_is_low_stock_boundary(self):
        variant = make_variant(stock=5, low_stock_threshold=5)
        self.assertTrue(variant.is_low_stock)
        variant_ok = make_variant(stock=6, low_stock_threshold=5)
        self.assertFalse(variant_ok.is_low_stock)
        variant_out = make_variant(stock=0, low_stock_threshold=5)
        self.assertFalse(variant_out.is_low_stock)  # 0 is out-of-stock, not "low"

    def test_profit_properties(self):
        variant = make_variant(
            price=Decimal("100.00"),
            discount_amount=Decimal("0"),
            cost_price=Decimal("60.00"),
            stock=10,
        )
        self.assertEqual(variant.gross_profit, Decimal("40.00"))
        self.assertEqual(variant.margin_percentage, 40.0)
        self.assertAlmostEqual(variant.markup_percentage, 66.6666, places=2)
        self.assertEqual(variant.inventory_cost_value, Decimal("600.00"))
        self.assertEqual(variant.potential_revenue, Decimal("1000.00"))
        self.assertEqual(variant.potential_profit, Decimal("400.00"))

    def test_margin_and_markup_guard_against_zero(self):
        free = make_variant(price=Decimal("0"), discount_amount=Decimal("0"), cost_price=Decimal("0"))
        self.assertEqual(free.margin_percentage, 0.0)
        self.assertEqual(free.markup_percentage, 0.0)

    def test_sku_uniqueness(self):
        make_variant(sku="DUP-SKU")
        with self.assertRaises(IntegrityError):
            make_variant(sku="DUP-SKU")

    def test_only_one_default_variant_per_product(self):
        product = make_product()
        v1 = make_variant(product, is_default=True, sku="d-1")
        v2 = make_variant(product, is_default=True, sku="d-2")
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertFalse(v1.is_default)
        self.assertTrue(v2.is_default)
        self.assertEqual(
            ProductVariant.objects.filter(product=product, is_default=True).count(), 1
        )


class StockOperationTests(TestCase):
    def test_reduce_stock_happy_path(self):
        variant = make_variant(stock=10)
        variant.reduce_stock(4)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 6)

    def test_reduce_stock_exact(self):
        variant = make_variant(stock=5)
        variant.reduce_stock(5)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 0)

    def test_reduce_stock_insufficient_raises_and_keeps_stock(self):
        variant = make_variant(stock=3)
        with self.assertRaises(ValueError):
            variant.reduce_stock(4)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 3)

    def test_increase_stock(self):
        variant = make_variant(stock=2)
        variant.increase_stock(8)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 10)

    def test_reduce_stock_is_atomic_conditional_update(self):
        """A stale in-memory copy must not be able to oversell: the conditional
        UPDATE guards on the *database* value, not the cached one."""
        variant = make_variant(stock=5)
        stale = ProductVariant.objects.get(pk=variant.pk)  # second handle, stock=5

        variant.reduce_stock(5)  # DB now 0
        with self.assertRaises(ValueError):
            stale.reduce_stock(1)  # stale thinks 5 left, DB says 0 -> rejected

        variant.refresh_from_db()
        self.assertEqual(variant.stock, 0)


class ProductReviewModelTests(TestCase):
    def test_str(self):
        product = make_product(title="Gadget")
        user = make_user(email="rev@example.com")
        review = make_review(product=product, user=user)
        self.assertIn("Gadget", str(review))
        self.assertIn("rev@example.com", str(review))

    def test_unique_review_per_user_product(self):
        product = make_product()
        user = make_user()
        make_review(product=product, user=user)
        with self.assertRaises(IntegrityError):
            make_review(product=product, user=user)

    def test_approved_review_updates_product_rating_cache(self):
        product = make_product()
        make_review(product=product, user=make_user(), rating=4, is_approved=True)
        make_review(product=product, user=make_user(), rating=2, is_approved=True)
        product.refresh_from_db()
        self.assertEqual(product.total_reviews, 2)
        self.assertEqual(product.average_rating, Decimal("3.00"))
