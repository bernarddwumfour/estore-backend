"""
Test data factories/helpers for the promotions app test-suite.

Plain builder functions (no external deps). They reuse the products factories
for users/variants and add promotion-specific builders so each test stays
focused on the behaviour under test rather than fixture setup.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.products.tests.factories import (  # noqa: F401  (re-exported for convenience)
    make_user,
    make_admin,
    make_category,
    make_product,
    make_variant,
)
from apps.promotions.models import Promotion, PromotionItem, DiscountCode
from apps.users.models.affiliate import Affiliate


def make_promotion(
    *,
    name: str = "Bundle Deal",
    bundle_price="150.00",
    status: str = Promotion.STATUS_DRAFT,
    starts_at=None,
    ends_at=None,
    created_by=None,
    **kwargs,
) -> Promotion:
    """Build a Promotion. Slug defaults to a unique value derived from name."""
    slug = kwargs.pop("slug", None) or f"{name.lower().replace(' ', '-')}-{timezone.now().timestamp()}"
    starts_at = starts_at or (timezone.now() - timedelta(days=1))
    return Promotion.objects.create(
        name=name,
        slug=slug,
        description=kwargs.pop("description", "A test bundle."),
        bundle_price=Decimal(str(bundle_price)),
        status=status,
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=created_by,
        **kwargs,
    )


def make_promotion_item(
    promotion: Promotion = None,
    variant=None,
    *,
    quantity: int = 1,
    original_price=None,
    cost_price_snapshot="0.00",
    is_free: bool = False,
    **kwargs,
) -> PromotionItem:
    """Build a PromotionItem, snapshotting the variant price when not given."""
    promotion = promotion or make_promotion()
    variant = variant or make_variant()
    if original_price is None:
        original_price = variant.price
    return PromotionItem.objects.create(
        promotion=promotion,
        variant=variant,
        quantity=quantity,
        original_price=Decimal(str(original_price)),
        cost_price_snapshot=Decimal(str(cost_price_snapshot)),
        is_free=is_free,
        is_available=variant.stock >= quantity,
        **kwargs,
    )


def make_active_promotion_with_items(
    *,
    bundle_price="150.00",
    variant_specs=((Decimal("100.00"), 10, 1),),  # (price, stock, qty)
    created_by=None,
) -> Promotion:
    """Active promotion with one or more in-stock items — the common case."""
    promo = make_promotion(
        bundle_price=bundle_price,
        status=Promotion.STATUS_ACTIVE,
        created_by=created_by,
    )
    for price, stock, qty in variant_specs:
        variant = make_variant(price=Decimal(str(price)), stock=stock)
        make_promotion_item(promo, variant, quantity=qty, original_price=price)
    return promo


def make_affiliate(*, user=None, referral_code: str = None, commission_rate="10.00", **kwargs) -> Affiliate:
    user = user or make_user()
    referral_code = referral_code or f"AFF{timezone.now().strftime('%H%M%S%f')[-8:]}"
    return Affiliate.objects.create(
        user=user,
        referral_code=referral_code,
        commission_rate=Decimal(str(commission_rate)),
        is_active=kwargs.pop("is_active", True),
        is_approved=kwargs.pop("is_approved", True),
        **kwargs,
    )


def make_discount_code(
    *,
    code: str = "SAVE10",
    name: str = "Save 10",
    discount_type: str = DiscountCode.TYPE_PERCENTAGE,
    value="10.00",
    min_subtotal="0.00",
    max_discount_amount=None,
    affiliate=None,
    is_active: bool = True,
    starts_at=None,
    ends_at=None,
    **kwargs,
) -> DiscountCode:
    return DiscountCode.objects.create(
        code=code,
        name=name,
        discount_type=discount_type,
        value=Decimal(str(value)),
        min_subtotal=Decimal(str(min_subtotal)),
        max_discount_amount=(
            Decimal(str(max_discount_amount)) if max_discount_amount is not None else None
        ),
        affiliate=affiliate,
        is_active=is_active,
        starts_at=starts_at,
        ends_at=ends_at,
        **kwargs,
    )
