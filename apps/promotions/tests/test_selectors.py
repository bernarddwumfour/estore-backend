"""Selector (read-query) tests for the promotions app."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.promotions.models import Promotion
from apps.promotions.selectors import (
    get_active_promotions,
    get_promotion_by_slug,
    get_admin_promotions,
    get_promotions_containing_variant,
    get_promotion_item_by_variant,
)
from .factories import (
    make_promotion,
    make_promotion_item,
    make_variant,
    make_active_promotion_with_items,
)


class GetActivePromotionsTests(TestCase):
    def test_returns_only_active(self):
        make_promotion(status=Promotion.STATUS_ACTIVE)
        make_promotion(status=Promotion.STATUS_DRAFT)
        promos, total, meta = get_active_promotions(page=1, limit=20)
        self.assertEqual(total, 1)
        self.assertEqual(len(promos), 1)

    def test_excludes_ended_by_date(self):
        make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() - timedelta(days=5),
            ends_at=timezone.now() - timedelta(days=1),
        )
        promos, total, meta = get_active_promotions()
        self.assertEqual(total, 0)

    def test_pagination_meta(self):
        for _ in range(3):
            make_promotion(status=Promotion.STATUS_ACTIVE)
        promos, total, meta = get_active_promotions(page=1, limit=2)
        self.assertEqual(total, 3)
        self.assertEqual(len(promos), 2)
        self.assertTrue(meta["has_next"])
        self.assertEqual(meta["total_pages"], 2)


class GetPromotionBySlugTests(TestCase):
    def test_public_returns_active_started(self):
        promo = make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
        )
        found = get_promotion_by_slug(promo.slug, is_admin=False)
        self.assertIsNotNone(found)

    def test_public_hides_draft(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        self.assertIsNone(get_promotion_by_slug(promo.slug, is_admin=False))

    def test_public_hides_not_yet_started(self):
        promo = make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() + timedelta(days=2),
        )
        self.assertIsNone(get_promotion_by_slug(promo.slug, is_admin=False))

    def test_admin_sees_draft(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        self.assertIsNotNone(get_promotion_by_slug(promo.slug, is_admin=True))

    def test_missing_slug_returns_none(self):
        self.assertIsNone(get_promotion_by_slug("does-not-exist", is_admin=True))


class GetAdminPromotionsTests(TestCase):
    def test_status_filter(self):
        make_promotion(status=Promotion.STATUS_ACTIVE)
        make_promotion(status=Promotion.STATUS_DRAFT)
        promos, total, meta = get_admin_promotions(status=Promotion.STATUS_DRAFT)
        self.assertEqual(total, 1)
        self.assertEqual(promos[0].status, Promotion.STATUS_DRAFT)

    def test_search_by_name(self):
        make_promotion(name="Summer Sale", slug="summer-sale")
        make_promotion(name="Winter Clearance", slug="winter-clearance")
        promos, total, meta = get_admin_promotions(search="summer")
        self.assertEqual(total, 1)
        self.assertEqual(promos[0].name, "Summer Sale")

    def test_sort_by_bundle_price_asc(self):
        make_promotion(name="A", slug="a", bundle_price="300.00")
        make_promotion(name="B", slug="b", bundle_price="100.00")
        promos, total, meta = get_admin_promotions(sort_by="bundle_price", sort_order="asc")
        self.assertEqual(promos[0].bundle_price, Decimal("100.00"))


class GetPromotionsContainingVariantTests(TestCase):
    def test_returns_active_promotions_with_variant(self):
        promo = make_active_promotion_with_items(
            variant_specs=((Decimal("10.00"), 10, 1),)
        )
        variant = promo.items.first().variant
        results = get_promotions_containing_variant(str(variant.id))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, promo.id)

    def test_excludes_draft(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        v = make_variant(stock=10)
        make_promotion_item(promo, v, quantity=1)
        self.assertEqual(get_promotions_containing_variant(str(v.id)), [])


class GetPromotionItemByVariantTests(TestCase):
    def test_found(self):
        promo = make_promotion()
        v = make_variant(stock=10)
        item = make_promotion_item(promo, v, quantity=1)
        found = get_promotion_item_by_variant(str(promo.id), str(v.id))
        self.assertEqual(found.id, item.id)

    def test_missing_returns_none(self):
        promo = make_promotion()
        v = make_variant(stock=10)
        self.assertIsNone(get_promotion_item_by_variant(str(promo.id), str(v.id)))
