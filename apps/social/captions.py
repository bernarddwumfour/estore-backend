"""
Social caption templates and image selection for products and promotions.

Pure helpers — no Zernio calls, no DB writes.
"""

import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

DESCRIPTION_MAX_LENGTH = 200


def _storefront_url(path: str) -> str:
    base = getattr(settings, 'STOREFRONT_BASE_URL', '').rstrip('/')
    return f"{base}{path}"


def _truncate(text: str, max_length: int = DESCRIPTION_MAX_LENGTH) -> str:
    text = (text or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def build_product_caption(product) -> str:
    """Templated caption for a published product."""
    lines = [f"✨ New arrival: {product.title}"]

    description = _truncate(product.description)
    if description:
        lines.append("")
        lines.append(description)

    variant = product.default_variant
    if variant:
        price = variant.discounted_price
        lines.append("")
        lines.append(f"From GHS {price}")

    lines.append("")
    lines.append(f"Shop now 👉 {_storefront_url(f'/products/{product.slug}')}")
    return "\n".join(lines)


def build_promotion_caption(promotion) -> str:
    """Templated caption for an activated promotion."""
    lines = [f"🔥 {promotion.name}"]

    description = _truncate(promotion.description)
    if description:
        lines.append("")
        lines.append(description)

    if promotion.bundle_price:
        lines.append("")
        lines.append(f"Bundle price: GHS {promotion.bundle_price}")

    if promotion.ends_at:
        lines.append(f"Ends {promotion.ends_at.strftime('%b %d, %Y')} — don't miss out!")

    lines.append("")
    lines.append(f"Grab the deal 👉 {_storefront_url(f'/promotions/{promotion.slug}')}")
    return "\n".join(lines)


def get_product_image_url(product) -> Optional[str]:
    """Main image of the default variant (Cloudinary URL), if any."""
    try:
        variant = product.default_variant
        if not variant:
            return None
        image = (
            variant.images.filter(is_active=True, image_type="main").first()
            or variant.images.filter(is_active=True).first()
        )
        return image.image.url if image else None
    except Exception as e:
        logger.warning(f"Could not resolve product image for social post: {str(e)}")
        return None


def get_promotion_image_url(promotion) -> Optional[str]:
    """Banner image of the promotion (Cloudinary URL), if any."""
    try:
        image = (
            promotion.images.filter(is_active=True, image_type="banner").first()
            or promotion.images.filter(is_active=True).first()
        )
        return image.image.url if image else None
    except Exception as e:
        logger.warning(f"Could not resolve promotion image for social post: {str(e)}")
        return None
