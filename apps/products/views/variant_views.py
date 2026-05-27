import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Your existing decorators
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    multipart_request_allowed,
    role_required,
)
from estore.utils.responses import APIResponse  # Your existing response class
from ..services.product_service import (
    ProductService,
    ReviewService,
    WishlistService,
    AdminProductService,
    CategoryService,
)
from ..schemas import (
    
    validate_variant_create
)
from ..models import ProductVariant

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_list(request):
    """Admin: List all variants with product information, filters, and pagination"""
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        product_id = request.GET.get("product_id")
        is_active = request.GET.get("is_active")
        is_default = request.GET.get("is_default")
        min_price = request.GET.get("min_price")
        max_price = request.GET.get("max_price")
        in_stock = request.GET.get("in_stock")
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        # Convert boolean parameters
        if is_active and is_active != "":
            is_active = is_active.lower() == "true"
        else:
            is_active = None

        if is_default and is_default != "":
            is_default = is_default.lower() == "true"
        else:
            is_default = None

        if in_stock and in_stock != "":
            in_stock = in_stock.lower() == "true"
        else:
            in_stock = None

        if min_price:
            min_price = float(min_price)
        if max_price:
            max_price = float(max_price)

        # Get variants with filters and pagination
        variants, total, pagination_meta = ProductService.get_all_variants(
            page=page,
            limit=limit,
            search=search if search else None,
            product_id=product_id if product_id else None,
            is_active=is_active,
            is_default=is_default,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            sort_by=sort_by,
            sort_order=sort_order,
            is_admin=True,
        )

        return APIResponse.success(
            data={"variants": variants, "total": total, "pagination": pagination_meta},
            message="Variants retrieved successfully",
        )

    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Admin variant list error: {str(e)}")
        import traceback

        traceback.print_exc()
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def variant_detail(request, variant_id):
    """Get detailed variant information"""
    try:
        is_admin = _is_admin(request)
        variant_data = ProductService.get_variant_detail(variant_id, is_admin=is_admin)

        if not variant_data:
            return APIResponse.not_found("Variant not found")

        return APIResponse.success(variant_data)

    except Exception as e:
        logger.error(f"Variant detail error: {str(e)}")
        return APIResponse.server_error()


# apps/products/views.py - Add bulk action for variants


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_variant_bulk_action(request):
    """Admin: Perform bulk actions on variants"""
    try:
        data = request.json_data
        action = data.get("action")
        variant_ids = data.get("variant_ids", [])

        if not variant_ids:
            return APIResponse.bad_request("No variant IDs provided")

        if not action:
            return APIResponse.bad_request("No action specified")

        results = {"success": [], "failed": [], "total": len(variant_ids)}

        if action in ["activate", "deactivate", "set_default", "unset_default"]:
            for variant_id in variant_ids:
                try:
                    variant = ProductVariant.objects.get(id=variant_id)

                    if action == "activate":
                        variant.is_active = True
                    elif action == "deactivate":
                        variant.is_active = False
                    elif action == "set_default":
                        # First, unset any existing default variant for this product
                        ProductVariant.objects.filter(
                            product=variant.product, is_default=True
                        ).update(is_default=False)
                        variant.is_default = True
                    elif action == "unset_default":
                        variant.is_default = False

                    variant.save()
                    results["success"].append(
                        {
                            "id": variant_id,
                            "sku": variant.sku,
                        }
                    )
                except ProductVariant.DoesNotExist:
                    results["failed"].append(
                        {"id": variant_id, "reason": "Variant not found"}
                    )
                except Exception as e:
                    results["failed"].append({"id": variant_id, "reason": str(e)})

        elif action == "delete":
            for variant_id in variant_ids:
                try:
                    variant = ProductVariant.objects.get(id=variant_id)
                    variant.delete()
                    results["success"].append({"id": variant_id, "sku": variant.sku})
                except ProductVariant.DoesNotExist:
                    results["failed"].append(
                        {"id": variant_id, "reason": "Variant not found"}
                    )
                except Exception as e:
                    results["failed"].append({"id": variant_id, "reason": str(e)})

        else:
            return APIResponse.bad_request(f"Unknown action: {action}")

        return APIResponse.success(
            data=results,
            message=f"Processed {len(results['success'])} out of {results['total']} variants",
        )

    except Exception as e:
        logger.error(f"Admin variant bulk action error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def wishlist_list(request):
    """Get or add to wishlist"""
    try:
        user = request.user
        is_admin = _is_admin(request)

        if request.method == "GET":
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))
            grouped = (
                request.GET.get("grouped", "true").lower() == "true"
            )  # Allow client to choose

            items, total = WishlistService.get_user_wishlist(
                user, page, limit, is_admin=is_admin, grouped=grouped
            )

            return APIResponse.success(
                data={
                    "items": items,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "grouped": grouped,
                },
                message="Wishlist retrieved successfully",
            )

        elif request.method == "POST":
            data = json.loads(request.body)

            if "variant_id" not in data:
                return APIResponse.bad_request("variant_id is required")

            wishlist_item, error = WishlistService.add_to_wishlist(
                user, data["variant_id"]
            )

            if error:
                if "already" in error.lower():
                    return APIResponse.conflict(error)
                return APIResponse.bad_request(error)

            return APIResponse.created(
                data={"wishlist_id": str(wishlist_item.id)}, message="Added to wishlist"
            )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Wishlist error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
def wishlist_remove(request, variant_id):
    """Remove from wishlist"""
    try:
        user = request.user

        success, error = WishlistService.remove_from_wishlist(user, variant_id)

        if not success:
            return APIResponse.not_found(error)

        return APIResponse.success(message="Removed from wishlist")

    except Exception as e:
        logger.error(f"Wishlist remove error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
def admin_variant_create(request, product_id):
    """Admin: Create product variant with images"""
    try:
        data = request.json_data if hasattr(request, "json_data") else {}
        files = request.files_data if hasattr(request, "files_data") else request.FILES

        # Handle boolean field
        if "is_default" in data:
            data["is_default"] = data["is_default"] in ["true", "True", True, "1", 1]

        # Validate input with admin privileges
        cleaned, errors = validate_variant_create(data, is_admin=True)
        if errors:
            return APIResponse.validation_error(errors)

        variant, errors = AdminProductService.create_variant(
            product_id=product_id, data=cleaned, user=request.user, image_files=files
        )

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(
            data={"variant_id": str(variant.id), "sku": variant.sku},
            message="Variant created successfully",
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin variant create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_variant_update(request, variant_id):
    """Admin: Update product variant"""
    try:
        data = request.json_data

        variant, errors = AdminProductService.update_variant(
            variant_id, data, request.user
        )

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.success(
            data={"variant_id": str(variant.id)}, message="Variant updated successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin variant update error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_image_upload(request, variant_id):
    """Admin: Upload variant image"""
    try:
        if "image" not in request.FILES:
            return APIResponse.bad_request("No image file provided")

        image_file = request.FILES["image"]
        image_type = request.POST.get("image_type", "gallery")
        alt_text = request.POST.get("alt_text", "")

        # Validate file type
        allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        import os

        ext = os.path.splitext(image_file.name)[1].lower()
        if ext not in allowed_extensions:
            return APIResponse.bad_request(
                f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )

        # Validate file size (max 5MB)
        if image_file.size > 5 * 1024 * 1024:
            return APIResponse.bad_request("Image file too large. Maximum size is 5MB")

        image, errors = AdminProductService.add_variant_image(
            variant_id=variant_id,
            image_file=image_file,
            image_type=image_type,
            alt_text=alt_text,
            user=request.user,
        )

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(
            data={"image_id": str(image.id), "url": image.image.url},
            message="Image uploaded successfully",
        )

    except Exception as e:
        logger.error(f"Admin image upload error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_detail(request, variant_id):
    """Admin: Get single variant details"""
    try:
        from apps.products.selectors import get_variant_by_id
        from apps.products.schemas import serialize_variant

        variant = get_variant_by_id(variant_id, require_active=False)
        if not variant:
            return APIResponse.not_found("Variant not found")

        variant_data = serialize_variant(variant, is_admin=True, include_images=True)
        variant_data["product"] = {
            "id": str(variant.product.id),
            "title": variant.product.title,
            "slug": variant.product.slug,
        }

        return APIResponse.success(
            data=variant_data, message="Variant retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Admin variant detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_delete(request, variant_id):
    """Admin: Delete product variant"""
    try:
        from apps.products.selectors import get_variant_by_id

        variant = get_variant_by_id(variant_id, require_active=False)
        if not variant:
            return APIResponse.not_found("Variant not found")

        variant.delete()

        logger.info(f"Variant deleted by admin {request.user.email}: {variant.sku}")

        return APIResponse.success(message="Variant deleted successfully")

    except Exception as e:
        logger.error(f"Admin variant delete error: {str(e)}")
        return APIResponse.server_error()
