"""Service/business-logic tests for PromotionService."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.promotions.models import Promotion, PromotionItem, AffiliateCommission, DiscountCode
from apps.promotions.services import PromotionService, DiscountCodeService
from apps.orders.models import Order
from apps.users.models import Address
from .factories import (
    make_admin,
    make_variant,
    make_promotion,
    make_promotion_item,
    make_active_promotion_with_items,
    make_affiliate,
    make_discount_code,
    make_user,
)


def _create_data(variants, *, name="New Bundle", bundle_price="100.00"):
    return {
        "name": name,
        "bundle_price": Decimal(bundle_price),
        "starts_at": timezone.now(),
        "ends_at": None,
        "description": "",
        "meta_title": "",
        "meta_description": "",
        "items": [
            {"variant_id": str(v.id), "quantity": q, "is_free": False}
            for v, q in variants
        ],
    }


class CreatePromotionTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_create_success_persists_promotion_and_items(self):
        v1 = make_variant(price=Decimal("60.00"), stock=10)
        v2 = make_variant(price=Decimal("40.00"), stock=10)
        data = _create_data([(v1, 1), (v2, 2)])
        promo, errors = PromotionService.create_promotion(data, None, self.admin)
        self.assertIsNone(errors)
        self.assertIsNotNone(promo)
        self.assertTrue(Promotion.objects.filter(id=promo.id).exists())
        self.assertEqual(promo.items.count(), 2)
        self.assertEqual(promo.status, Promotion.STATUS_DRAFT)
        self.assertEqual(promo.created_by, self.admin)

    def test_create_snapshots_price_and_cost(self):
        v = make_variant(price=Decimal("99.00"), stock=5, cost_price=Decimal("55.00"))
        promo, errors = PromotionService.create_promotion(_create_data([(v, 1)]), None, self.admin)
        self.assertIsNone(errors)
        item = promo.items.first()
        self.assertEqual(item.original_price, Decimal("99.00"))
        self.assertEqual(item.cost_price_snapshot, Decimal("55.00"))

    def test_create_generates_unique_slug(self):
        v = make_variant(stock=5)
        d1 = _create_data([(v, 1)], name="Same Name")
        d2 = _create_data([(make_variant(stock=5), 1)], name="Same Name")
        p1, _ = PromotionService.create_promotion(d1, None, self.admin)
        p2, _ = PromotionService.create_promotion(d2, None, self.admin)
        self.assertNotEqual(p1.slug, p2.slug)

    def test_create_with_invalid_variant_rolls_back(self):
        # Regression: a bad variant_id must not leave a half-created promotion.
        data = _create_data([(make_variant(stock=5), 1)])
        data["items"].append({"variant_id": "00000000-0000-0000-0000-000000000000", "quantity": 1})
        before = Promotion.objects.count()
        promo, errors = PromotionService.create_promotion(data, None, self.admin)
        self.assertIsNotNone(errors)
        self.assertIsNone(promo)
        self.assertEqual(Promotion.objects.count(), before)


class ActivatePauseTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_activate_draft(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        ok, err = PromotionService.activate_promotion(str(promo.id), self.admin)
        self.assertTrue(ok)
        promo.refresh_from_db()
        self.assertEqual(promo.status, Promotion.STATUS_ACTIVE)

    def test_activate_already_active_fails(self):
        promo = make_promotion(status=Promotion.STATUS_ACTIVE)
        ok, err = PromotionService.activate_promotion(str(promo.id), self.admin)
        self.assertFalse(ok)
        self.assertIn("status", err)

    def test_activate_missing(self):
        ok, err = PromotionService.activate_promotion(
            "00000000-0000-0000-0000-000000000000", self.admin
        )
        self.assertFalse(ok)
        self.assertIn("promotion", err)

    def test_pause_active(self):
        promo = make_promotion(status=Promotion.STATUS_ACTIVE)
        ok, err = PromotionService.pause_promotion(str(promo.id), self.admin)
        self.assertTrue(ok)
        promo.refresh_from_db()
        self.assertEqual(promo.status, Promotion.STATUS_PAUSED)

    def test_pause_non_active_fails(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        ok, err = PromotionService.pause_promotion(str(promo.id), self.admin)
        self.assertFalse(ok)
        self.assertIn("status", err)


class DeductStockTests(TestCase):
    def test_deduct_reduces_stock(self):
        promo = make_active_promotion_with_items(
            variant_specs=((Decimal("10.00"), 10, 3),)
        )
        variant = promo.items.first().variant
        ok, err = PromotionService.deduct_stock_for_promotion(str(promo.id))
        self.assertTrue(ok)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 7)

    def test_deduct_insufficient_stock_fails(self):
        promo = make_promotion(status=Promotion.STATUS_ACTIVE)
        v = make_variant(price=Decimal("10.00"), stock=1)
        make_promotion_item(promo, v, quantity=5)
        ok, err = PromotionService.deduct_stock_for_promotion(str(promo.id))
        self.assertFalse(ok)
        self.assertIn("Insufficient stock", err)
        v.refresh_from_db()
        self.assertEqual(v.stock, 1)  # unchanged

    def test_deduct_on_inactive_promotion_fails(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        make_promotion_item(promo, make_variant(stock=10), quantity=1)
        ok, err = PromotionService.deduct_stock_for_promotion(str(promo.id))
        self.assertFalse(ok)
        self.assertEqual(err, "Promotion is not active")


class RefreshAvailabilityTests(TestCase):
    def test_refresh_pauses_when_item_unavailable(self):
        promo = make_promotion(status=Promotion.STATUS_ACTIVE)
        v = make_variant(price=Decimal("10.00"), stock=10)
        item = make_promotion_item(promo, v, quantity=2)
        # drain stock below requirement
        v.stock = 1
        v.save(update_fields=["stock"])
        ok, err = PromotionService.refresh_promotion_availability(str(promo.id))
        self.assertTrue(ok)
        promo.refresh_from_db()
        item.refresh_from_db()
        self.assertFalse(item.is_available)
        self.assertEqual(promo.status, Promotion.STATUS_PAUSED)


class BulkActionTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_bulk_activate_mixed(self):
        ok_promo = make_promotion(status=Promotion.STATUS_DRAFT)
        make_promotion_item(ok_promo, make_variant(stock=10), quantity=1)
        already = make_promotion(status=Promotion.STATUS_ACTIVE)
        results, err = PromotionService.bulk_action_promotions(
            [str(ok_promo.id), str(already.id)], "activate", self.admin
        )
        self.assertIsNone(err)
        self.assertEqual(len(results["success"]), 1)
        self.assertEqual(len(results["failed"]), 1)

    def test_bulk_activate_blocked_by_stock(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT)
        make_promotion_item(promo, make_variant(stock=1), quantity=5)
        results, err = PromotionService.bulk_action_promotions(
            [str(promo.id)], "activate", self.admin
        )
        self.assertEqual(len(results["failed"]), 1)
        promo.refresh_from_db()
        self.assertEqual(promo.status, Promotion.STATUS_DRAFT)

    def test_bulk_delete_only_draft_or_ended(self):
        draft = make_promotion(status=Promotion.STATUS_DRAFT)
        active = make_promotion(status=Promotion.STATUS_ACTIVE)
        results, err = PromotionService.bulk_action_promotions(
            [str(draft.id), str(active.id)], "delete", self.admin
        )
        self.assertEqual(len(results["success"]), 1)
        self.assertEqual(len(results["failed"]), 1)
        self.assertFalse(Promotion.objects.filter(id=draft.id).exists())
        self.assertTrue(Promotion.objects.filter(id=active.id).exists())

    def test_bulk_unknown_action(self):
        results, err = PromotionService.bulk_action_promotions(["x"], "frobnicate", self.admin)
        self.assertIsNone(results)
        self.assertIn("action", err)


class UpdatePromotionTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_update_draft_changes_fields_and_items(self):
        promo = make_promotion(status=Promotion.STATUS_DRAFT, name="Old")
        make_promotion_item(promo, make_variant(stock=10), quantity=1)
        new_variant = make_variant(price=Decimal("30.00"), stock=10)
        data = {
            "name": "New",
            "bundle_price": Decimal("75.00"),
            "starts_at": timezone.now(),
            "items": [{"variant_id": str(new_variant.id), "quantity": 2, "is_free": False}],
        }
        updated, errors = PromotionService.update_promotion(str(promo.id), data, None, self.admin)
        self.assertIsNone(errors)
        updated.refresh_from_db()
        self.assertEqual(updated.name, "New")
        self.assertEqual(updated.bundle_price, Decimal("75.00"))
        self.assertEqual(updated.items.count(), 1)
        self.assertEqual(updated.items.first().variant_id, new_variant.id)

    def test_update_active_is_blocked(self):
        promo = make_promotion(status=Promotion.STATUS_ACTIVE)
        data = {
            "name": "Nope",
            "bundle_price": Decimal("10.00"),
            "starts_at": timezone.now(),
            "items": [{"variant_id": str(make_variant(stock=5).id), "quantity": 1}],
        }
        updated, errors = PromotionService.update_promotion(str(promo.id), data, None, self.admin)
        self.assertIsNone(updated)
        self.assertIn("status", errors)


class DiscountCodeServiceTests(TestCase):
    def test_validate_percentage_discount_code(self):
        code = make_discount_code(code="SAVE10", value="10.00")
        resolved, details, error = DiscountCodeService.validate_discount_code(
            code.code,
            Decimal("200.00"),
        )
        self.assertIsNone(error)
        self.assertEqual(resolved.id, code.id)
        self.assertEqual(details["discount_amount"], Decimal("20.00"))
        self.assertFalse(details["is_affiliate_code"])

    def test_validate_affiliate_code_uses_discounted_subtotal_for_commission(self):
        affiliate = make_affiliate(commission_rate="12.50")
        code = make_discount_code(code="AFFDISC12", affiliate=affiliate, value="5.00")
        resolved, details, error = DiscountCodeService.validate_discount_code(
            code.code,
            Decimal("300.00"),
        )
        self.assertIsNone(error)
        self.assertEqual(resolved.id, code.id)
        self.assertEqual(details["discount_amount"], Decimal("15.00"))
        self.assertEqual(details["commissionable_amount"], Decimal("285.00"))
        self.assertEqual(details["commission_amount"], Decimal("35.63"))

    def test_validate_referral_code_resolves_assigned_discount_code(self):
        affiliate = make_affiliate(referral_code="REFONLY01", commission_rate="10.00")
        code = make_discount_code(code="SAVEAFF5", affiliate=affiliate, value="5.00")

        resolved, details, error = DiscountCodeService.validate_discount_code(
            affiliate.referral_code,
            Decimal("300.00"),
        )

        self.assertIsNone(error)
        self.assertEqual(resolved.id, code.id)
        self.assertEqual(details["entered_code"], affiliate.referral_code)
        self.assertEqual(details["code"], code.code)
        self.assertTrue(details["resolved_from_referral_code"])
        self.assertEqual(details["affiliate_referral_code"], affiliate.referral_code)

    def test_sync_order_commission_accrues_when_order_paid(self):
        affiliate = make_affiliate(commission_rate="10.00")
        code = make_discount_code(code="SYNCAFF1", affiliate=affiliate, value="5.00")
        user = make_user()
        address = Address.objects.create(
            user=user,
            address_type="shipping",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="+233000000000",
            address_line1="123 Street",
            city="Accra",
            state="Greater Accra",
            postal_code="GA-123",
            country="GH",
        )
        order = Order.objects.create(
            user=user,
            guest_email=user.email,
            guest_first_name="Jane",
            guest_last_name="Doe",
            guest_phone="+233000000000",
            order_number="ORDTESTSYNC1",
            status=Order.STATUS_PENDING,
            payment_status=Order.PAYMENT_PENDING,
            payment_method="paystack",
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("200.00"),
            shipping_cost=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("10.00"),
            discount_code=code,
            discount_code_text=code.code,
            affiliate=affiliate,
            affiliate_commission_amount=Decimal("19.00"),
            total=Decimal("200.00"),
        )
        AffiliateCommission.objects.create(
            affiliate=affiliate,
            order=order,
            discount_code=code,
            commission_rate=Decimal("10.00"),
            commissionable_amount=Decimal("190.00"),
            commission_amount=Decimal("19.00"),
        )

        order.payment_status = Order.PAYMENT_PAID
        order.save(update_fields=["payment_status"])
        DiscountCodeService.sync_order_commission(order, reason="paid")

        affiliate.refresh_from_db()
        order.affiliate_commission.refresh_from_db()
        self.assertEqual(order.affiliate_commission.status, AffiliateCommission.STATUS_ACCRUED)
        self.assertEqual(affiliate.pending_earnings, Decimal("19.00"))

    def test_sync_order_commission_reverses_accrued_commission(self):
        affiliate = make_affiliate(commission_rate="10.00", pending_earnings="19.00", total_earnings="19.00")
        code = make_discount_code(code="SYNCAFF2", affiliate=affiliate, value="5.00")
        user = make_user()
        address = Address.objects.create(
            user=user,
            address_type="shipping",
            first_name="Jane",
            last_name="Doe",
            email="jane2@example.com",
            phone="+233000000001",
            address_line1="123 Street",
            city="Accra",
            state="Greater Accra",
            postal_code="GA-123",
            country="GH",
        )
        order = Order.objects.create(
            user=user,
            guest_email=user.email,
            guest_first_name="Jane",
            guest_last_name="Doe",
            guest_phone="+233000000001",
            order_number="ORDTESTSYNC2",
            status=Order.STATUS_CANCELLED,
            payment_status=Order.PAYMENT_FAILED,
            payment_method="paystack",
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("200.00"),
            shipping_cost=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("10.00"),
            discount_code=code,
            discount_code_text=code.code,
            affiliate=affiliate,
            affiliate_commission_amount=Decimal("19.00"),
            total=Decimal("200.00"),
        )
        AffiliateCommission.objects.create(
            affiliate=affiliate,
            order=order,
            discount_code=code,
            commission_rate=Decimal("10.00"),
            commissionable_amount=Decimal("190.00"),
            commission_amount=Decimal("19.00"),
            status=AffiliateCommission.STATUS_ACCRUED,
        )

        DiscountCodeService.sync_order_commission(order, reason="cancelled")

        affiliate.refresh_from_db()
        order.affiliate_commission.refresh_from_db()
        self.assertEqual(order.affiliate_commission.status, AffiliateCommission.STATUS_REVERSED)
        self.assertEqual(affiliate.pending_earnings, Decimal("0.00"))


class SyncOrderCommissionIdempotencyTests(TestCase):
    """The status flips are conditional UPDATEs: earnings move exactly once."""

    def _make_commission_order(
        self,
        *,
        order_number,
        status=Order.STATUS_CONFIRMED,
        payment_status=Order.PAYMENT_PAID,
        commission_status=AffiliateCommission.STATUS_PENDING,
        pending_earnings="0.00",
    ):
        affiliate = make_affiliate(
            commission_rate="10.00",
            pending_earnings=pending_earnings,
            total_earnings=pending_earnings,
        )
        code = make_discount_code(
            code=f"IDEM{order_number[-4:]}", affiliate=affiliate, value="5.00"
        )
        user = make_user()
        address = Address.objects.create(
            user=user,
            address_type="shipping",
            first_name="Jane",
            last_name="Doe",
            email=user.email,
            phone="+233000000002",
            address_line1="123 Street",
            city="Accra",
            state="Greater Accra",
            postal_code="GA-123",
            country="GH",
        )
        order = Order.objects.create(
            user=user,
            guest_email=user.email,
            guest_first_name="Jane",
            guest_last_name="Doe",
            guest_phone="+233000000002",
            order_number=order_number,
            status=status,
            payment_status=payment_status,
            payment_method="paystack",
            shipping_address=address,
            billing_address=address,
            subtotal=Decimal("200.00"),
            shipping_cost=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("10.00"),
            discount_code=code,
            discount_code_text=code.code,
            affiliate=affiliate,
            affiliate_commission_amount=Decimal("19.00"),
            total=Decimal("200.00"),
        )
        AffiliateCommission.objects.create(
            affiliate=affiliate,
            order=order,
            discount_code=code,
            commission_rate=Decimal("10.00"),
            commissionable_amount=Decimal("190.00"),
            commission_amount=Decimal("19.00"),
            status=commission_status,
        )
        return order, affiliate

    def test_double_sync_accrues_earnings_only_once(self):
        order, affiliate = self._make_commission_order(order_number="ORDIDEM0001")

        DiscountCodeService.sync_order_commission(order, reason="paid")
        DiscountCodeService.sync_order_commission(order, reason="paid again")

        affiliate.refresh_from_db()
        order.affiliate_commission.refresh_from_db()
        self.assertEqual(order.affiliate_commission.status, AffiliateCommission.STATUS_ACCRUED)
        self.assertEqual(affiliate.pending_earnings, Decimal("19.00"))
        self.assertEqual(affiliate.total_earnings, Decimal("19.00"))

    def test_reversed_commission_recovers_when_order_is_paid_again(self):
        order, affiliate = self._make_commission_order(
            order_number="ORDIDEM0002",
            commission_status=AffiliateCommission.STATUS_REVERSED,
        )

        DiscountCodeService.sync_order_commission(order, reason="re-paid after failure")

        affiliate.refresh_from_db()
        order.affiliate_commission.refresh_from_db()
        self.assertEqual(order.affiliate_commission.status, AffiliateCommission.STATUS_ACCRUED)
        self.assertIsNone(order.affiliate_commission.reversed_at)
        self.assertEqual(affiliate.pending_earnings, Decimal("19.00"))

    def test_pending_to_reversed_does_not_touch_earnings(self):
        order, affiliate = self._make_commission_order(
            order_number="ORDIDEM0003",
            status=Order.STATUS_CANCELLED,
            payment_status=Order.PAYMENT_FAILED,
            commission_status=AffiliateCommission.STATUS_PENDING,
            pending_earnings="7.00",
        )

        DiscountCodeService.sync_order_commission(order, reason="cancelled before payment")

        affiliate.refresh_from_db()
        order.affiliate_commission.refresh_from_db()
        self.assertEqual(order.affiliate_commission.status, AffiliateCommission.STATUS_REVERSED)
        self.assertEqual(affiliate.pending_earnings, Decimal("7.00"))
        self.assertEqual(affiliate.total_earnings, Decimal("7.00"))


class ProfitBasisCommissionTests(TestCase):
    """Commission basis 'profit': rate applies to (price − cost)×qty − discount."""

    def _validate(self, *, basis, cost_price, discount_value="20.00", quantity=2):
        from apps.products.tests.factories import make_variant
        from apps.users.models import Affiliate

        affiliate = make_affiliate(commission_rate="10.00")
        affiliate.commission_basis = basis
        affiliate.save(update_fields=["commission_basis"])
        code = make_discount_code(
            code=f"PROF{cost_price.replace('.', '')}",
            affiliate=affiliate,
            discount_type=DiscountCode.TYPE_FIXED,
            value=discount_value,
        )
        variant = make_variant(price=Decimal("100.00"), cost_price=Decimal(cost_price))
        items = [
            {
                "variant": variant,
                "quantity": quantity,
                "unit_price": variant.discounted_price,
            }
        ]
        subtotal = variant.discounted_price * quantity
        return DiscountCodeService.validate_discount_code(code.code, subtotal, items=items)

    def test_profit_basis_commission_is_rate_of_margin_after_discount(self):
        from apps.users.models import Affiliate

        # 2 × (100 − 60) = 80 margin, − 20 discount = 60 basis → 10% = 6.00
        discount_code, details, error = self._validate(
            basis=Affiliate.BASIS_PROFIT, cost_price="60.00"
        )
        self.assertIsNone(error)
        self.assertEqual(details["commissionable_amount"], Decimal("60.00"))
        self.assertEqual(details["commission_amount"], Decimal("6.00"))

    def test_profit_basis_floors_at_zero_when_discount_exceeds_margin(self):
        from apps.users.models import Affiliate

        # 2 × (100 − 95) = 10 margin, − 20 discount → floored to 0
        discount_code, details, error = self._validate(
            basis=Affiliate.BASIS_PROFIT, cost_price="95.00"
        )
        self.assertIsNone(error)
        self.assertEqual(details["commissionable_amount"], Decimal("0.00"))
        self.assertEqual(details["commission_amount"], Decimal("0.00"))

    def test_sale_amount_basis_is_unchanged(self):
        from apps.users.models import Affiliate

        # 200 subtotal − 20 discount = 180 basis → 10% = 18.00 (cost irrelevant)
        discount_code, details, error = self._validate(
            basis=Affiliate.BASIS_SALE_AMOUNT, cost_price="60.00"
        )
        self.assertIsNone(error)
        self.assertEqual(details["commissionable_amount"], Decimal("180.00"))
        self.assertEqual(details["commission_amount"], Decimal("18.00"))
