"""
Variant Service - Business logic for variant management
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction

from apps.products.models import ProductVariant, VariantImage
from apps.products.selectors import (
    get_product_by_id,
    get_variant_by_id,
    get_variant_by_sku,
    get_all_variants,
)
from apps.products.schemas import (
    serialize_variant,
    serialize_variant_list_response,
)
from apps.users.models import User

logger = logging.getLogger(__name__)


class VariantService:
    """Variant business logic"""

    @staticmethod
    def get_all_variants(
        page: int = 1,
        limit: int = 20,
        search: str = None,
        product_id: str = None,
        is_active: bool = None,
        is_default: bool = None,
        min_price: float = None,
        max_price: float = None,
        in_stock: bool = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        is_admin: bool = False,
    ) -> Tuple[List[Dict], int, Dict]:
        """Get all variants with filtering and pagination"""

        variants, total, pagination_meta = get_all_variants(
            page=page,
            limit=limit,
            search=search,
            product_id=product_id,
            is_active=is_active,
            is_default=is_default,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            sort_by=sort_by,
            sort_order=sort_order,
            is_admin=is_admin,
        )

        variants_data = serialize_variant_list_response(variants, is_admin=is_admin)

        return variants_data, total, pagination_meta

    @staticmethod
    def get_variant_detail(variant_id: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed variant information"""
        variant = get_variant_by_id(variant_id, require_active=not is_admin)

        if not variant:
            return None

        # Check product status for non-admins
        if not is_admin and variant.product.status != ProductVariant.product.STATUS_PUBLISHED:
            return None

        variant_data = serialize_variant(
            variant, is_admin=is_admin, include_images=True
        )
        variant_data["product"] = {
            "id": str(variant.product.id),
            "title": variant.product.title,
            "slug": variant.product.slug,
        }

        return variant_data


class AdminVariantService:
    """Admin variant management business logic - writes only"""

    @staticmethod
    @transaction.atomic
    def create_variant(
        product_id: str, data: Dict[str, Any], user: User, image_files: List = None
    ) -> Tuple[Optional[ProductVariant], Optional[Dict]]:
        """Create product variant with optional images (admin only)"""
        try:
            product = get_product_by_id(product_id, include_inactive=True)
            if not product:
                return None, {"product": "Product not found"}

            # Check SKU uniqueness
            if get_variant_by_sku(data["sku"]):
                return None, {"sku": "SKU already exists"}

            # Validate attributes match product options
            if product.options:
                for option_key in data["attributes"]:
                    if option_key not in product.options:
                        return None, {
                            f"attributes.{option_key}": f'Option "{option_key}" not allowed for this product'
                        }

            # Handle default variant
            is_default = data.get("is_default", False)
            if is_default:
                ProductVariant.objects.filter(product=product, is_default=True).update(
                    is_default=False
                )
            elif not ProductVariant.objects.filter(product=product).exists():
                is_default = True

            # Create variant
            variant = ProductVariant.objects.create(
                product=product,
                sku=data["sku"],
                attributes=data["attributes"],
                price=data["price"],
                discount_amount=data.get("discount_amount", 0),
                stock=data.get("stock", 0),
                is_default=is_default,
                is_active=data.get("is_active", True),
                weight=data.get("weight"),
                height=data.get("height"),
                width=data.get("width"),
                depth=data.get("depth"),
                low_stock_threshold=data.get("low_stock_threshold", 5),
            )

            # Add images if provided
            if image_files:
                actual_image_files = []
                if hasattr(image_files, "getlist"):
                    if "images" in image_files:
                        actual_image_files = image_files.getlist("images")
                    else:
                        for key in image_files.keys():
                            actual_image_files.extend(image_files.getlist(key))
                elif isinstance(image_files, list):
                    actual_image_files = image_files
                else:
                    actual_image_files = [image_files]

                for i, image_file in enumerate(actual_image_files):
                    if image_file:
                        image_type = "main" if i == 0 else "gallery"
                        alt_text = (
                            data.get("image_alt_texts", [])[i]
                            if data.get("image_alt_texts")
                            and i < len(data.get("image_alt_texts", []))
                            else f"{product.title} - {variant.sku}"
                        )

                        VariantImage.objects.create(
                            variant=variant,
                            image=image_file,
                            image_type=image_type,
                            alt_text=alt_text,
                            order=i,
                            is_active=True,
                        )

            logger.info(f"Variant created by admin {user.email}: {variant.sku}")
            return variant, None

        except Exception as e:
            logger.error(f"Admin variant creation error: {str(e)}")
            return None, {"general": f"Failed to create variant: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def update_variant(
        variant_id: str, data: Dict[str, Any], user: User
    ) -> Tuple[Optional[ProductVariant], Optional[Dict]]:
        """Update product variant (admin only)"""
        try:
            variant = get_variant_by_id(variant_id, require_active=False)
            if not variant:
                return None, {"variant": "Variant not found"}

            # Validate SKU uniqueness if changed
            if "sku" in data and data["sku"] != variant.sku:
                if get_variant_by_sku(data["sku"]):
                    return None, {"sku": "SKU already exists"}

            # Handle default variant
            if data.get("is_default", False) and not variant.is_default:
                ProductVariant.objects.filter(
                    product=variant.product, is_default=True
                ).update(is_default=False)

            # Update fields
            for field in [
                "sku",
                "price",
                "discount_amount",
                "stock",
                "is_default",
                "is_active",
                "weight",
                "height",
                "width",
                "depth",
                "low_stock_threshold",
                "attributes",
            ]:
                if field in data:
                    setattr(variant, field, data[field])

            variant.save()

            logger.info(f"Variant updated by admin {user.email}: {variant.sku}")
            return variant, None

        except Exception as e:
            logger.error(f"Admin variant update error: {str(e)}")
            return None, {"general": "Failed to update variant"}

    @staticmethod
    @transaction.atomic
    def add_variant_image(
        variant_id: str,
        image_file,
        image_type: str = "gallery",
        alt_text: str = "",
        user: User = None,
    ) -> Tuple[Optional[VariantImage], Optional[Dict]]:
        """Add image to product variant (admin only)"""
        try:
            variant = get_variant_by_id(variant_id, require_active=False)
            if not variant:
                return None, {"variant": "Variant not found"}

            # Validate image type
            valid_types = ["main", "gallery", "thumbnail"]
            if image_type not in valid_types:
                return None, {"image_type": f'Must be one of: {", ".join(valid_types)}'}

            # Create image
            image = VariantImage.objects.create(
                variant=variant,
                image=image_file,
                image_type=image_type,
                alt_text=alt_text,
                order=VariantImage.objects.filter(variant=variant).count(),
            )

            if user:
                logger.info(
                    f"Image added to variant {variant.sku} by admin {user.email}"
                )

            return image, None

        except Exception as e:
            logger.error(f"Admin image upload error: {str(e)}")
            return None, {"general": "Failed to upload image"}