"""
Variant Service - Business logic for variant management
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction

from apps.products.models import ProductVariant, VariantImage, Product
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
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


class VariantService:
    """Variant business logic - read operations"""

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
        start_time = time.time()
        action = "get_all_variants"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Retrieving variants with filters",
            status_code=0,
            app_name=APP_NAME,
            extra={
                "page": page,
                "limit": limit,
                "product_id_filter": product_id,
                "has_search": bool(search),
                "is_active_filter": is_active,
                "is_default_filter": is_default,
                "has_price_filter": bool(min_price or max_price),
                "in_stock_filter": in_stock,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "is_admin": is_admin
            }
        )

        try:
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

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Variants retrieved successfully",
                status_code=200,
                app_name=APP_NAME,
                extra={
                    "total_variants": total,
                    "variants_returned": len(variants_data),
                    "page": page,
                    "limit": limit,
                    "duration_ms": round(duration_ms, 2)
                }
            )

            return variants_data, total, pagination_meta

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to retrieve variants: {str(e)}",
                status_code=500,
                app_name=APP_NAME,
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            raise

    @staticmethod
    def get_variant_detail(variant_id: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed variant information"""
        start_time = time.time()
        action = "get_variant_detail"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Retrieving variant detail: {variant_id}",
            status_code=0,
            app_name=APP_NAME,
            extra={"variant_id": variant_id, "is_admin": is_admin}
        )
        
        try:
            variant = get_variant_by_id(variant_id, require_active=not is_admin)
            
            if not variant:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Variant not found: {variant_id}",
                    status_code=404,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None
            
            # Check product status for non-admins
            if not is_admin and variant.product.status != Product.STATUS_PUBLISHED:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Variant product not published: {variant_id}",
                    status_code=404,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "product_status": variant.product.status,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None
            
            variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)
            variant_data["product"] = {
                "id": str(variant.product.id),
                "title": variant.product.title,
                "slug": variant.product.slug,
            }
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description=f"Variant detail retrieved: {variant.sku}",
                status_code=200,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "sku": variant.sku,
                    "product_id": str(variant.product.id),
                    "product_title": variant.product.title,
                    "is_active": variant.is_active,
                    "stock": variant.stock,
                    "price": float(variant.price),
                    "duration_ms": round(duration_ms, 2)
                }
            )
            
            return variant_data

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to retrieve variant {variant_id}: {str(e)}",
                status_code=500,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            raise


class AdminVariantService:
    """Admin variant management business logic - writes only"""

    @staticmethod
    @transaction.atomic
    def create_variant(
        product_id: str, data: Dict[str, Any], user: User, image_files: List = None
    ) -> Tuple[Optional[ProductVariant], Optional[Dict]]:
        """Create product variant with optional images (admin only)"""
        start_time = time.time()
        action = "admin_create_variant"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating variant for product: {product_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "product_id": product_id,
                "sku": data.get("sku"),
                "price": data.get("price"),
                "stock": data.get("stock", 0),
                "is_default": data.get("is_default", False),
                "has_images": bool(image_files)
            }
        )
        
        try:
            product = get_product_by_id(product_id, include_inactive=True)
            if not product:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Product not found: {product_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "product_id": product_id,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, {"product": "Product not found"}

            # Check SKU uniqueness
            if get_variant_by_sku(data["sku"]):
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"SKU already exists: {data['sku']}",
                    status_code=400,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "sku": data["sku"],
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None, {"sku": "SKU already exists"}

            # Validate attributes match product options
            if product.options:
                for option_key in data["attributes"]:
                    if option_key not in product.options:
                        duration_ms = (time.time() - start_time) * 1000
                        log_action(
                            logger=logger,
                            severity=LogSeverity.WARNING,
                            action=action,
                            description=f"Invalid attribute key: {option_key}",
                            status_code=400,
                            user=user,
                            app_name=APP_NAME,
                            extra={
                                "option_key": option_key,
                                "allowed_options": list(product.options.keys()),
                                "duration_ms": round(duration_ms, 2)
                            }
                        )
                        return None, {
                            f"attributes.{option_key}": f'Option "{option_key}" not allowed for this product'
                        }

            # Handle default variant
            is_default = data.get("is_default", False)
            if is_default:
                previous_default = ProductVariant.objects.filter(product=product, is_default=True).first()
                ProductVariant.objects.filter(product=product, is_default=True).update(is_default=False)
                previous_default_sku = previous_default.sku if previous_default else None
            elif not ProductVariant.objects.filter(product=product).exists():
                is_default = True
                previous_default_sku = None

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
            images_created = 0
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
                        images_created += 1

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Variant created: {variant.sku}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": str(variant.id),
                    "sku": variant.sku,
                    "product_id": product_id,
                    "product_title": product.title,
                    "price": float(variant.price),
                    "stock": variant.stock,
                    "is_default": variant.is_default,
                    "previous_default_sku": previous_default_sku if is_default else None,
                    "images_created": images_created,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return variant, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create variant: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "product_id": product_id,
                    "sku": data.get("sku"),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, {"general": f"Failed to create variant: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def update_variant(
        variant_id: str, data: Dict[str, Any], user: User
    ) -> Tuple[Optional[ProductVariant], Optional[Dict]]:
        """Update product variant (admin only)"""
        start_time = time.time()
        action = "admin_update_variant"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Updating variant: {variant_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "variant_id": variant_id,
                "update_fields": list(data.keys())
            }
        )
        
        try:
            variant = get_variant_by_id(variant_id, require_active=False)
            if not variant:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Variant not found: {variant_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None, {"variant": "Variant not found"}

            old_values = {
                "sku": variant.sku,
                "price": float(variant.price),
                "stock": variant.stock,
                "is_default": variant.is_default,
                "is_active": variant.is_active,
            }

            # Validate SKU uniqueness if changed
            if "sku" in data and data["sku"] != variant.sku:
                if get_variant_by_sku(data["sku"]):
                    duration_ms = (time.time() - start_time) * 1000
                    log_action(
                        logger=logger,
                        severity=LogSeverity.WARNING,
                        action=action,
                        description=f"SKU already exists: {data['sku']}",
                        status_code=400,
                        user=user,
                        app_name=APP_NAME,
                        extra={
                            "sku": data["sku"],
                            "duration_ms": round(duration_ms, 2)
                        }
                    )
                    return None, {"sku": "SKU already exists"}

            # Handle default variant
            previous_default_sku = None
            if data.get("is_default", False) and not variant.is_default:
                previous_default = ProductVariant.objects.filter(
                    product=variant.product, is_default=True
                ).first()
                if previous_default:
                    previous_default_sku = previous_default.sku
                    previous_default.is_default = False
                    previous_default.save()
                    log_action(
                        logger=logger,
                        severity=LogSeverity.DEBUG,
                        action=action,
                        description="Removed default flag from previous default variant",
                        status_code=0,
                        user=user,
                        app_name=APP_NAME,
                        extra={
                            "previous_default_sku": previous_default_sku,
                            "variant_id": variant_id
                        }
                    )

            # Update fields
            updated_fields = []
            for field in [
                "sku", "price", "discount_amount", "stock", "is_default",
                "is_active", "weight", "height", "width", "depth",
                "low_stock_threshold", "attributes"
            ]:
                if field in data:
                    old_value = getattr(variant, field)
                    new_value = data[field]
                    if old_value != new_value:
                        setattr(variant, field, new_value)
                        updated_fields.append(field)

            variant.save()

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Variant updated: {variant.sku}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": str(variant.id),
                    "sku": variant.sku,
                    "product_id": str(variant.product.id),
                    "product_title": variant.product.title,
                    "old_sku": old_values["sku"],
                    "new_sku": variant.sku if "sku" in data else old_values["sku"],
                    "old_price": old_values["price"],
                    "new_price": float(variant.price) if "price" in data else old_values["price"],
                    "old_stock": old_values["stock"],
                    "new_stock": variant.stock if "stock" in data else old_values["stock"],
                    "was_default": old_values["is_default"],
                    "is_default": variant.is_default,
                    "was_active": old_values["is_active"],
                    "is_active": variant.is_active,
                    "previous_default_sku": previous_default_sku,
                    "updated_fields": updated_fields,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return variant, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to update variant {variant_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
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
        start_time = time.time()
        action = "admin_add_variant_image"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Adding image to variant: {variant_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "variant_id": variant_id,
                "image_type": image_type,
                "file_name": image_file.name if image_file else None,
                "file_size_kb": round(image_file.size / 1024, 2) if image_file else None
            }
        )
        
        try:
            variant = get_variant_by_id(variant_id, require_active=False)
            if not variant:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Variant not found: {variant_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None, {"variant": "Variant not found"}

            # Validate image type
            valid_types = ["main", "gallery", "thumbnail"]
            if image_type not in valid_types:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Invalid image type: {image_type}",
                    status_code=400,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "image_type": image_type,
                        "valid_types": valid_types,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None, {"image_type": f'Must be one of: {", ".join(valid_types)}'}

            existing_images_count = VariantImage.objects.filter(variant=variant).count()
            
            # Create image
            image = VariantImage.objects.create(
                variant=variant,
                image=image_file,
                image_type=image_type,
                alt_text=alt_text,
                order=existing_images_count,
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Image added to variant: {variant.sku}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "image_id": str(image.id),
                    "variant_id": variant_id,
                    "variant_sku": variant.sku,
                    "product_title": variant.product.title,
                    "image_type": image_type,
                    "image_order": existing_images_count,
                    "has_alt_text": bool(alt_text),
                    "file_name": image_file.name,
                    "file_size_kb": round(image_file.size / 1024, 2),
                    "total_images_after": existing_images_count + 1,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return image, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to add image to variant {variant_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, {"general": "Failed to upload image"}

    @staticmethod
    @transaction.atomic
    def delete_variant_image(
        image_id: str, user: User
    ) -> Tuple[bool, Optional[Dict]]:
        """Delete a variant image (admin only)"""
        start_time = time.time()
        action = "admin_delete_variant_image"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Deleting image: {image_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"image_id": image_id}
        )
        
        try:
            image = VariantImage.objects.select_related('variant__product').get(id=image_id)
            variant_sku = image.variant.sku
            product_title = image.variant.product.title
            image_type = image.image_type
            image_order = image.order
            
            image.delete()
            
            # Reorder remaining images
            remaining_images = VariantImage.objects.filter(variant=image.variant).order_by('order')
            for idx, img in enumerate(remaining_images):
                if img.order != idx:
                    img.order = idx
                    img.save()
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Image deleted from variant: {variant_sku}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "image_id": image_id,
                    "variant_id": str(image.variant.id),
                    "variant_sku": variant_sku,
                    "product_title": product_title,
                    "deleted_image_type": image_type,
                    "deleted_image_order": image_order,
                    "remaining_images": remaining_images.count(),
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return True, None
            
        except VariantImage.DoesNotExist:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Image not found: {image_id}",
                status_code=404,
                user=user,
                app_name=APP_NAME,
                extra={"image_id": image_id, "duration_ms": round(duration_ms, 2)}
            )
            return False, {"image": "Image not found"}
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to delete image {image_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "image_id": image_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            return False, {"general": "Failed to delete image"}