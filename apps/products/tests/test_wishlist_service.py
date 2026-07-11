"""Unit tests for WishlistService business logic."""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.products.models import Wishlist
from apps.products.services.wishlist_service import WishlistService
from .factories import make_user, make_product, make_variant


class WishlistServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product()
        self.variant = make_variant(self.product, stock=5)

    def test_add_to_wishlist(self):
        item, error = WishlistService.add_to_wishlist(self.user, str(self.variant.id))
        self.assertIsNone(error)
        self.assertIsNotNone(item)
        self.assertTrue(Wishlist.objects.filter(user=self.user, variant=self.variant).exists())

    def test_add_duplicate_rejected(self):
        WishlistService.add_to_wishlist(self.user, str(self.variant.id))
        item, error = WishlistService.add_to_wishlist(self.user, str(self.variant.id))
        self.assertIsNone(item)
        self.assertEqual(error, "Item already in wishlist")

    def test_add_missing_variant(self):
        item, error = WishlistService.add_to_wishlist(self.user, str(uuid.uuid4()))
        self.assertIsNone(item)
        self.assertEqual(error, "Variant not found")

    def test_remove_from_wishlist(self):
        WishlistService.add_to_wishlist(self.user, str(self.variant.id))
        ok, error = WishlistService.remove_from_wishlist(self.user, str(self.variant.id))
        self.assertTrue(ok)
        self.assertIsNone(error)
        self.assertFalse(Wishlist.objects.filter(user=self.user, variant=self.variant).exists())

    def test_remove_not_in_wishlist(self):
        ok, error = WishlistService.remove_from_wishlist(self.user, str(self.variant.id))
        self.assertFalse(ok)
        self.assertEqual(error, "Item not found in wishlist")

    def test_is_in_wishlist(self):
        self.assertFalse(WishlistService.is_in_wishlist(self.user, str(self.variant.id)))
        WishlistService.add_to_wishlist(self.user, str(self.variant.id))
        self.assertTrue(WishlistService.is_in_wishlist(self.user, str(self.variant.id)))

    def test_clear_wishlist(self):
        WishlistService.add_to_wishlist(self.user, str(self.variant.id))
        other = make_variant(self.product, sku="other")
        WishlistService.add_to_wishlist(self.user, str(other.id))
        count, error = WishlistService.clear_wishlist(self.user)
        self.assertIsNone(error)
        self.assertEqual(count, 2)
        self.assertEqual(Wishlist.objects.filter(user=self.user).count(), 0)

    def test_clear_empty_wishlist(self):
        count, error = WishlistService.clear_wishlist(self.user)
        self.assertEqual(count, 0)
        self.assertIsNone(error)

    def test_wishlist_summary(self):
        in_stock = make_variant(self.product, sku="ins", stock=10, discount_amount=Decimal("5.00"))
        out_stock = make_variant(self.product, sku="out", stock=0)
        WishlistService.add_to_wishlist(self.user, str(in_stock.id))
        WishlistService.add_to_wishlist(self.user, str(out_stock.id))

        summary = WishlistService.get_wishlist_summary(self.user)
        self.assertEqual(summary["total_items"], 2)
        self.assertEqual(summary["in_stock_count"], 1)
        self.assertEqual(summary["out_of_stock_count"], 1)
        self.assertEqual(summary["on_discount_count"], 1)
        self.assertEqual(summary["total_potential_savings"], 5.0)
