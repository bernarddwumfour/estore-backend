"""Validator and serializer tests for the promotions schemas."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.promotions.schemas import (
    validate_promotion_create,
    validate_bulk_action,
    serialize_promotion,
    serialize_promotion_item,
    serialize_bulk_action_result,
)
from .factories import (
    make_active_promotion_with_items,
    make_promotion,
    make_promotion_item,
    make_variant,
)


def _valid_payload(**overrides):
    payload = {
        "name": "Holiday Bundle",
        "bundle_price": "150.00",
        "starts_at": (timezone.now()).isoformat(),
        "items": [{"variant_id": "some-id", "quantity": 2}],
    }
    payload.update(overrides)
    return payload


class ValidatePromotionCreateTests(TestCase):
    def test_valid_payload(self):
        cleaned, errors = validate_promotion_create(_valid_payload())
        self.assertIsNone(errors)
        self.assertEqual(cleaned["name"], "Holiday Bundle")
        self.assertEqual(cleaned["bundle_price"], Decimal("150.00"))
        self.assertEqual(len(cleaned["items"]), 1)

    def test_missing_name(self):
        cleaned, errors = validate_promotion_create(_valid_payload(name="  "))
        self.assertIsNone(cleaned)
        self.assertIn("name", errors)

    def test_missing_bundle_price_is_400_not_crash(self):
        # Regression: Decimal(str(None)) raises InvalidOperation (not ValueError);
        # must surface as a field error, never bubble to a 500.
        payload = _valid_payload()
        del payload["bundle_price"]
        cleaned, errors = validate_promotion_create(payload)
        self.assertIsNone(cleaned)
        self.assertIn("bundle_price", errors)

    def test_garbage_bundle_price_is_field_error(self):
        cleaned, errors = validate_promotion_create(_valid_payload(bundle_price="abc"))
        self.assertIsNone(cleaned)
        self.assertIn("bundle_price", errors)

    def test_negative_bundle_price(self):
        cleaned, errors = validate_promotion_create(_valid_payload(bundle_price="-5"))
        self.assertIsNone(cleaned)
        self.assertIn("bundle_price", errors)

    def test_missing_items(self):
        cleaned, errors = validate_promotion_create(_valid_payload(items=[]))
        self.assertIsNone(cleaned)
        self.assertIn("items", errors)

    def test_item_with_bad_quantity(self):
        payload = _valid_payload(items=[{"variant_id": "x", "quantity": 0}])
        cleaned, errors = validate_promotion_create(payload)
        self.assertIsNone(cleaned)
        self.assertIn("items[0]", errors)

    def test_item_missing_variant_id(self):
        payload = _valid_payload(items=[{"quantity": 1}])
        cleaned, errors = validate_promotion_create(payload)
        self.assertIsNone(cleaned)
        self.assertIn("items[0]", errors)

    def test_missing_starts_at(self):
        payload = _valid_payload()
        del payload["starts_at"]
        cleaned, errors = validate_promotion_create(payload)
        self.assertIsNone(cleaned)
        self.assertIn("starts_at", errors)

    def test_ends_before_starts_is_rejected(self):
        # Regression: a bundle must not end before it begins.
        now = timezone.now()
        payload = _valid_payload(
            starts_at=now.isoformat(),
            ends_at=(now - timedelta(days=1)).isoformat(),
        )
        cleaned, errors = validate_promotion_create(payload)
        self.assertIsNone(cleaned)
        self.assertIn("ends_at", errors)

    def test_ends_after_starts_is_accepted(self):
        now = timezone.now()
        payload = _valid_payload(
            starts_at=now.isoformat(),
            ends_at=(now + timedelta(days=1)).isoformat(),
        )
        cleaned, errors = validate_promotion_create(payload)
        self.assertIsNone(errors)


class ValidateBulkActionTests(TestCase):
    def test_valid(self):
        cleaned, errors = validate_bulk_action(
            {"action": "activate", "promotion_ids": ["a", "b"]}
        )
        self.assertIsNone(errors)
        self.assertEqual(cleaned["action"], "activate")
        self.assertEqual(cleaned["promotion_ids"], ["a", "b"])

    def test_invalid_action(self):
        cleaned, errors = validate_bulk_action(
            {"action": "explode", "promotion_ids": ["a"]}
        )
        self.assertIsNone(cleaned)
        self.assertIn("action", errors)

    def test_missing_ids(self):
        cleaned, errors = validate_bulk_action({"action": "pause", "promotion_ids": []})
        self.assertIsNone(cleaned)
        self.assertIn("promotion_ids", errors)


class SerializeTests(TestCase):
    def test_serialize_item_public_hides_cost(self):
        v = make_variant(price=Decimal("100.00"), stock=10)
        item = make_promotion_item(
            variant=v, quantity=1, original_price="100.00", cost_price_snapshot="60.00"
        )
        public = serialize_promotion_item(item, is_admin=False)
        self.assertNotIn("cost_price_snapshot", public)
        self.assertNotIn("item_gross_profit", public)
        self.assertEqual(public["original_price"], 100.0)

    def test_serialize_item_admin_includes_cost(self):
        v = make_variant(price=Decimal("100.00"), stock=10)
        item = make_promotion_item(
            variant=v, quantity=1, original_price="100.00", cost_price_snapshot="60.00"
        )
        admin = serialize_promotion_item(item, is_admin=True)
        self.assertIn("cost_price_snapshot", admin)
        self.assertEqual(admin["current_stock"], 10)

    def test_serialize_promotion_splits_free_and_paid(self):
        promo = make_promotion(bundle_price="80.00", status="active")
        paid_v = make_variant(price=Decimal("100.00"), stock=10)
        free_v = make_variant(price=Decimal("20.00"), stock=10)
        make_promotion_item(promo, paid_v, quantity=1, original_price="100.00")
        make_promotion_item(promo, free_v, quantity=1, original_price="20.00", is_free=True)
        data = serialize_promotion(promo, is_admin=False)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(len(data["free_items"]), 1)
        self.assertNotIn("status", data)  # admin-only

    def test_serialize_promotion_admin_financials(self):
        promo = make_active_promotion_with_items(
            bundle_price="150.00", variant_specs=((Decimal("100.00"), 10, 2),)
        )
        data = serialize_promotion(promo, is_admin=True)
        self.assertIn("bundle_cost", data)
        self.assertIn("bundle_gross_profit", data)
        self.assertIn("status", data)

    def test_serialize_bulk_action_result_counts(self):
        results = {
            "success": [{"id": "1", "name": "A"}],
            "failed": [{"id": "2", "name": "B", "reason": "Already active"}],
            "total": 2,
        }
        out = serialize_bulk_action_result(results)
        self.assertEqual(out["success_count"], 1)
        self.assertEqual(out["failed_count"], 1)
        self.assertEqual(out["total"], 2)
