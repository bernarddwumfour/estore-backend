"""Model-level tests: Promotion and PromotionItem computed properties."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.promotions.models import Promotion, DiscountCode
from .factories import (
    make_promotion,
    make_promotion_item,
    make_variant,
    make_affiliate,
    make_discount_code,
)


class PromotionPropertyTests(TestCase):
    def test_is_currently_active_true_for_active_in_window(self):
        promo = make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(promo.is_currently_active)

    def test_is_currently_active_false_when_not_active_status(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        self.assertFalse(promo.is_currently_active)

    def test_is_currently_active_false_before_start(self):
        promo = make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(promo.is_currently_active)

    def test_is_currently_active_false_after_end(self):
        promo = make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() - timedelta(days=5),
            ends_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(promo.is_currently_active)

    def test_is_currently_active_true_with_no_end_date(self):
        promo = make_promotion(
            status=Promotion.STATUS_ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=None,
        )
        self.assertTrue(promo.is_currently_active)

    def test_original_total_sums_price_times_quantity(self):
        promo = make_promotion(bundle_price="120.00")
        v1 = make_variant(price=Decimal("100.00"), stock=10)
        v2 = make_variant(price=Decimal("50.00"), stock=10)
        make_promotion_item(promo, v1, quantity=2, original_price="100.00")
        make_promotion_item(promo, v2, quantity=1, original_price="50.00")
        self.assertEqual(promo.original_total, 250.00)

    def test_savings_amount(self):
        promo = make_promotion(bundle_price="200.00")
        v1 = make_variant(price=Decimal("150.00"), stock=10)
        make_promotion_item(promo, v1, quantity=2, original_price="150.00")
        # original 300 - bundle 200 = 100
        self.assertEqual(promo.savings_amount, 100.00)

    def test_has_stock_true_when_all_items_sufficient(self):
        promo = make_promotion()
        v1 = make_variant(price=Decimal("10.00"), stock=5)
        make_promotion_item(promo, v1, quantity=3)
        self.assertTrue(promo.has_stock)

    def test_has_stock_false_when_any_item_short(self):
        promo = make_promotion()
        v1 = make_variant(price=Decimal("10.00"), stock=2)
        make_promotion_item(promo, v1, quantity=5)
        self.assertFalse(promo.has_stock)

    def test_unavailable_items_lists_short_items(self):
        promo = make_promotion()
        short = make_variant(price=Decimal("10.00"), stock=1)
        ok = make_variant(price=Decimal("10.00"), stock=10)
        make_promotion_item(promo, short, quantity=5)
        make_promotion_item(promo, ok, quantity=1)
        unavailable = promo.unavailable_items
        self.assertEqual(len(unavailable), 1)
        self.assertEqual(unavailable[0]["sku"], short.sku)
        self.assertEqual(unavailable[0]["required"], 5)
        self.assertEqual(unavailable[0]["available"], 1)


class PromotionItemPropertyTests(TestCase):
    def test_has_sufficient_stock(self):
        v = make_variant(stock=4)
        item = make_promotion_item(variant=v, quantity=4)
        self.assertTrue(item.has_sufficient_stock)
        item2 = make_promotion_item(variant=make_variant(stock=2), quantity=3)
        self.assertFalse(item2.has_sufficient_stock)

    def test_item_gross_profit_paid(self):
        v = make_variant(price=Decimal("100.00"), stock=10)
        item = make_promotion_item(
            variant=v, quantity=2, original_price="100.00", cost_price_snapshot="60.00"
        )
        # (100 - 60) * 2 = 80
        self.assertEqual(item.item_gross_profit, 80.00)

    def test_item_gross_profit_free_is_negative_cost(self):
        v = make_variant(price=Decimal("100.00"), stock=10)
        item = make_promotion_item(
            variant=v, quantity=2, original_price="100.00",
            cost_price_snapshot="60.00", is_free=True,
        )
        # free: 0 - cost*qty = -120
        self.assertEqual(item.item_gross_profit, -120.00)

    def test_item_margin_percentage(self):
        v = make_variant(price=Decimal("100.00"), stock=10)
        item = make_promotion_item(
            variant=v, quantity=1, original_price="100.00", cost_price_snapshot="40.00"
        )
        # profit 60 / revenue 100 = 60%
        self.assertEqual(item.item_margin_percentage, 60.00)

    def test_item_margin_percentage_free_is_zero(self):
        item = make_promotion_item(
            quantity=1, original_price="100.00", cost_price_snapshot="40.00", is_free=True
        )
        self.assertEqual(item.item_margin_percentage, 0)

    def test_refresh_availability_updates_flag(self):
        v = make_variant(stock=1)
        item = make_promotion_item(variant=v, quantity=5)  # is_available computed False at build
        v.stock = 10
        v.save(update_fields=["stock"])
        item.variant.refresh_from_db()
        item.refresh_availability()
        item.refresh_from_db()
        self.assertTrue(item.is_available)


class DiscountCodeModelTests(TestCase):
    def test_code_is_normalized_to_uppercase(self):
        code = make_discount_code(code="save10")
        self.assertEqual(code.code, "SAVE10")

    def test_is_currently_active_false_for_inactive_affiliate(self):
        affiliate = make_affiliate(is_active=False)
        code = make_discount_code(code=affiliate.referral_code, affiliate=affiliate)
        self.assertFalse(code.is_currently_active)

    def test_is_currently_active_true_for_active_affiliate_code(self):
        affiliate = make_affiliate()
        code = make_discount_code(code=affiliate.referral_code, affiliate=affiliate)
        self.assertTrue(code.is_currently_active)
