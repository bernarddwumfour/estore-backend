import json
import logging
from uuid import UUID

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.products.models import ProductVariant
from apps.products.services.wishlist_service import WishlistService


logger = logging.getLogger(__name__)
User = get_user_model()


class AddToWishlistInput(BaseModel):
    variant_id: str = Field(
        ...,
        description=(
            "Exact UUID of the product variant to save. "
            "Obtain it from verified product details. "
            "Never invent variant IDs."
        ),
    )


@tool(args_schema=AddToWishlistInput)
def add_to_wishlist(
    variant_id: str,
    config: RunnableConfig,
) -> str:
    """
    Add a verified product variant to the authenticated
    customer's wishlist.

    Requires an authenticated customer in the trusted
    LangGraph runtime configuration.
    """

    user_id = config.get("configurable", {}).get(
        "authenticated_user_id"
    )

    if not user_id:
        return json.dumps({
            "success": False,
            "error": "Authentication required.",
            "requires_authentication": True,
        })

    try:
        UUID(str(variant_id))
    except (ValueError, TypeError, AttributeError):
        return json.dumps({
            "success": False,
            "error": "Invalid product variant identifier.",
        })

    try:
        user = User.objects.filter(
            pk=user_id,
            is_active=True,
        ).first()

        if user is None:
            return json.dumps({
                "success": False,
                "error": "Authentication required.",
                "requires_authentication": True,
            })

        variant = (
            ProductVariant.objects
            .select_related("product")
            .filter(
                pk=variant_id,
                is_active=True,
                product__status="published",
            )
            .first()
        )

        if variant is None:
            return json.dumps({
                "success": False,
                "error": "Product variant is unavailable.",
            })

        if WishlistService.is_in_wishlist(user, variant_id):
            return json.dumps({
                "success": True,
                "already_exists": True,
                "message": "This variant is already in your wishlist.",
                "product": {
                    "id": str(variant.product_id),
                    "title": variant.product.title,
                    "variant_id": str(variant.id),
                    "attributes": variant.attributes,
                },
            })

        wishlist_item, error = WishlistService.add_to_wishlist(
            user=user,
            variant_id=variant_id,
        )

        if error:
            if "already" in error.lower():
                return json.dumps({
                    "success": True,
                    "already_exists": True,
                    "message": "This variant is already in your wishlist.",
                })

            return json.dumps({
                "success": False,
                "error": "Unable to add this variant to your wishlist.",
            })

        return json.dumps({
            "success": True,
            "already_exists": False,
            "message": "Added to wishlist successfully.",
            "wishlist_id": str(wishlist_item.id),
            "product": {
                "id": str(variant.product_id),
                "title": variant.product.title,
                "variant_id": str(variant.id),
                "attributes": variant.attributes,
                "price": float(variant.discounted_price),
            },
        })

    except Exception:
        logger.exception("AI wishlist operation failed")

        return json.dumps({
            "success": False,
            "error": "Wishlist service is temporarily unavailable.",
        })