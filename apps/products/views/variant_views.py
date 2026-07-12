import json
import logging
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

# Your existing decorators
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    multipart_request_allowed,
    role_required,
)
from estore.utils.responses import APIResponse
from ..services.product_service import (
    ProductService,
    AdminProductService,
)
from ..services.wishlist_service import WishlistService
from ..schemas import validate_variant_create, validate_variant_update, serialize_variant
from ..models import ProductVariant
from apps.common.utils import sanitize_search_query
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


def _extract_indexed_form_values(data, field_name):
    """Collect FormData fields like image_alt_texts[0] into a list."""
    if isinstance(data.get(field_name), list):
        return data[field_name]

    indexed_values = []
    prefix = f"{field_name}["
    for key, value in data.items():
        if key.startswith(prefix) and key.endswith("]"):
            try:
                index = int(key[len(prefix):-1])
            except ValueError:
                continue
            indexed_values.append((index, value))

    return [value for _, value in sorted(indexed_values)]


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


def _log_variant_request(request, action, start_time, status_code, extra=None):
    """Helper to log variant requests consistently with app field"""
    duration_ms = (time.time() - start_time) * 1000
    user = request.user if hasattr(request, 'user') else None
    
    log_data = {
        "duration_ms": round(duration_ms, 2),
        "path": request.path,
        "method": request.method,
        "user_role": getattr(user, 'role', 'unknown') if user else 'anonymous',
        "user_id": str(user.id) if user and hasattr(user, 'id') else None,
    }
    if extra:
        log_data.update(extra)
    
    if status_code < 400:
        severity = LogSeverity.INFO
        description = "Variant request successful"
    elif status_code == 429:
        severity = LogSeverity.WARNING
        description = "Variant request rate limited"
    elif status_code < 500:
        severity = LogSeverity.WARNING
        description = "Variant request failed - invalid parameters"
    else:
        severity = LogSeverity.ERROR
        description = "Variant request failed with server error"
    
    log_action(
        logger=logger,
        severity=severity,
        action=action,
        description=description,
        status_code=status_code,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra=log_data
    )


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def admin_variant_list(request):
    """Admin: List all variants with product information, filters, and pagination"""
    start_time = time.time()
    action = "admin_variant_list"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin retrieving variant list",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = sanitize_search_query(request.GET.get("search", ""))
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

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "total_variants": total,
                "variants_returned": len(variants),
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
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.success(
            data={"variants": variants, "total": total, "pagination": pagination_meta},
            message="Variants retrieved successfully",
        )

    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        _log_variant_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Admin variant list error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='200/h', method='GET', block=True)
def variant_detail(request, variant_id):
    """Get detailed variant information"""
    start_time = time.time()
    action = "variant_detail"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving variant detail for ID: {variant_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "variant_id": variant_id}
    )
    
    try:
        is_admin = _is_admin(request)
        variant_data = ProductService.get_variant_detail(variant_id, is_admin=is_admin)

        if not variant_data:
            _log_variant_request(
                request, action, start_time, 404,
                extra={"variant_id": variant_id, "reason": "Variant not found"}
            )
            return APIResponse.not_found("Variant not found")

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "variant_id": variant_id,
                "sku": variant_data.get("sku"),
                "product_title": variant_data.get("product", {}).get("title"),
                "is_admin_access": is_admin,
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.success(variant_data)

    except Exception as e:
        logger.error(f"Variant detail error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"variant_id": variant_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_variant_bulk_action(request):
    """Admin: Perform bulk actions on variants"""
    start_time = time.time()
    action = "admin_variant_bulk_action"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin bulk action on variants",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = request.json_data
        action_type = data.get("action")
        variant_ids = data.get("variant_ids", [])

        if not variant_ids:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"error": "No variant IDs provided"}
            )
            return APIResponse.bad_request("No variant IDs provided")

        if not action_type:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"error": "No action specified"}
            )
            return APIResponse.bad_request("No action specified")

        results = {"success": [], "failed": [], "total": len(variant_ids)}

        if action_type in ["activate", "deactivate", "set_default", "unset_default"]:
            for variant_id in variant_ids:
                try:
                    variant = ProductVariant.objects.get(id=variant_id)

                    if action_type == "activate":
                        variant.is_active = True
                    elif action_type == "deactivate":
                        variant.is_active = False
                    elif action_type == "set_default":
                        # First, unset any existing default variant for this product
                        ProductVariant.objects.filter(
                            product=variant.product, is_default=True
                        ).update(is_default=False)
                        variant.is_default = True
                    elif action_type == "unset_default":
                        variant.is_default = False

                    variant.save()
                    results["success"].append({
                        "id": variant_id,
                        "sku": variant.sku,
                    })
                except ProductVariant.DoesNotExist:
                    results["failed"].append({
                        "id": variant_id,
                        "reason": "Variant not found"
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": variant_id,
                        "reason": str(e)
                    })

        elif action_type == "delete":
            for variant_id in variant_ids:
                try:
                    variant = ProductVariant.objects.get(id=variant_id)
                    sku = variant.sku
                    variant.delete()
                    results["success"].append({
                        "id": variant_id,
                        "sku": sku
                    })
                except ProductVariant.DoesNotExist:
                    results["failed"].append({
                        "id": variant_id,
                        "reason": "Variant not found"
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": variant_id,
                        "reason": str(e)
                    })

        else:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"error": f"Unknown action: {action_type}"}
            )
            return APIResponse.bad_request(f"Unknown action: {action_type}")

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "action": action_type,
                "total_variants": len(variant_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.success(
            data=results,
            message=f"Processed {len(results['success'])} out of {results['total']} variants",
        )

    except Exception as e:
        logger.error(f"Admin variant bulk action error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
@ratelimit(key='user', rate='100/h', method='GET', block=True)
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def wishlist_list(request):
    """Get or add to wishlist"""
    start_time = time.time()
    action = f"wishlist_{request.method.lower()}"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - wishlist {request.method} operation",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "method": request.method}
    )
    
    try:
        is_admin = _is_admin(request)

        if request.method == "GET":
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))
            grouped = request.GET.get("grouped", "true").lower() == "true"

            if limit > 100:
                limit = 100
            if limit < 1:
                limit = 20

            items, total = WishlistService.get_user_wishlist(
                user, page, limit, is_admin=is_admin, grouped=grouped
            )

            _log_variant_request(
                request, action, start_time, 200,
                extra={
                    "total_items": total,
                    "items_returned": len(items),
                    "page": page,
                    "limit": limit,
                    "grouped": grouped,
                    "requested_by": get_user_info(user)
                }
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
                _log_variant_request(
                    request, action, start_time, 400,
                    extra={"error": "variant_id is required"}
                )
                return APIResponse.bad_request("variant_id is required")

            wishlist_item, error = WishlistService.add_to_wishlist(
                user, data["variant_id"]
            )

            if error:
                if "already" in error.lower():
                    _log_variant_request(
                        request, action, start_time, 409,
                        extra={"variant_id": data["variant_id"], "reason": "Already in wishlist"}
                    )
                    return APIResponse.conflict(error)
                
                _log_variant_request(
                    request, action, start_time, 400,
                    extra={"variant_id": data["variant_id"], "error": error}
                )
                return APIResponse.bad_request(error)

            _log_variant_request(
                request, action, start_time, 201,
                extra={
                    "wishlist_id": str(wishlist_item.id),
                    "variant_id": data["variant_id"],
                    "variant_sku": wishlist_item.variant.sku if wishlist_item.variant else None,
                    "requested_by": get_user_info(user)
                }
            )

            return APIResponse.created(
                data={"wishlist_id": str(wishlist_item.id)},
                message="Added to wishlist"
            )

    except json.JSONDecodeError:
        _log_variant_request(request, action, start_time, 400, extra={"error": "Invalid JSON data"})
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Wishlist error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@ratelimit(key='user', rate='30/h', method='DELETE', block=True)
def wishlist_remove(request, variant_id):
    """Remove from wishlist"""
    start_time = time.time()
    action = "wishlist_remove"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - removing from wishlist, variant: {variant_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "variant_id": variant_id}
    )
    
    try:
        success, error = WishlistService.remove_from_wishlist(user, variant_id)

        if not success:
            _log_variant_request(
                request, action, start_time, 404,
                extra={"variant_id": variant_id, "reason": error}
            )
            return APIResponse.not_found(error)

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "variant_id": variant_id,
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.success(message="Removed from wishlist")

    except Exception as e:
        logger.error(f"Wishlist remove error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"variant_id": variant_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def admin_variant_create(request, product_id):
    """Admin: Create product variant with images"""
    start_time = time.time()
    action = "admin_variant_create"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin creating variant for product: {product_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "product_id": product_id}
    )
    
    try:
        data = request.json_data if hasattr(request, "json_data") else {}
        files = request.files_data if hasattr(request, "files_data") else request.FILES

        # Handle boolean field
        if "is_default" in data:
            data["is_default"] = data["is_default"] in ["true", "True", True, "1", 1]

        # Validate input with admin privileges
        cleaned, errors = validate_variant_create(data, is_admin=True)
        if errors:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"product_id": product_id, "errors": errors}
            )
            return APIResponse.validation_error(errors)

        variant, errors = AdminProductService.create_variant(
            product_id=product_id, data=cleaned, user=request.user, image_files=files
        )

        if errors:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"product_id": product_id, "errors": errors}
            )
            return APIResponse.validation_error(errors)

        _log_variant_request(
            request, action, start_time, 201,
            extra={
                "variant_id": str(variant.id),
                "sku": variant.sku,
                "product_id": product_id,
                "price": float(variant.price),
                "stock": variant.stock,
                "is_default": variant.is_default,
                "has_images": bool(files),
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.created(
            data={"variant_id": str(variant.id), "sku": variant.sku},
            message="Variant created successfully",
        )

    except json.JSONDecodeError:
        _log_variant_request(request, action, start_time, 400, extra={"error": "Invalid JSON data"})
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin variant create error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"product_id": product_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
@ratelimit(key='user', rate='50/h', method='PUT', block=True)
def admin_variant_update(request, variant_id):
    """Admin: Update product variant"""
    start_time = time.time()
    action = "admin_variant_update"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin updating variant: {variant_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "variant_id": variant_id}
    )
    
    try:
        data = request.json_data if hasattr(request, "json_data") else {}
        files = request.files_data if hasattr(request, "files_data") else None

        cleaned, errors = validate_variant_update(data, is_admin=True)
        if errors:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "errors": errors}
            )
            return APIResponse.validation_error(errors)

        if "remove_images" in data and isinstance(data["remove_images"], list):
            cleaned["remove_images"] = data["remove_images"]

        image_alt_texts = _extract_indexed_form_values(data, "image_alt_texts")
        if image_alt_texts:
            cleaned["image_alt_texts"] = image_alt_texts

        has_update_fields = any(key != "image_alt_texts" for key in cleaned.keys())
        if not has_update_fields and not files:
            errors = {"variant": "No update fields provided"}
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "errors": errors}
            )
            return APIResponse.validation_error(errors)

        variant, errors = AdminProductService.update_variant(
            variant_id, cleaned, request.user, image_files=files
        )

        if errors:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "errors": errors}
            )
            return APIResponse.validation_error(errors)

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "variant_id": str(variant.id),
                "sku": variant.sku,
                "updated_fields": list(cleaned.keys()),
                "requested_by": get_user_info(user)
            }
        )

        variant_data = serialize_variant(variant, is_admin=True, include_images=True)
        variant_data["product"] = {
            "id": str(variant.product.id),
            "title": variant.product.title,
            "slug": variant.product.slug,
        }

        return APIResponse.success(
            data={"variant_id": str(variant.id), "variant": variant_data},
            message="Variant updated successfully"
        )

    except json.JSONDecodeError:
        _log_variant_request(request, action, start_time, 400, extra={"error": "Invalid JSON data"})
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin variant update error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"variant_id": variant_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_variant_image_upload(request, variant_id):
    """Admin: Upload variant image"""
    start_time = time.time()
    action = "admin_variant_image_upload"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - uploading image for variant: {variant_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "variant_id": variant_id}
    )
    
    try:
        if "image" not in request.FILES:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "error": "No image file provided"}
            )
            return APIResponse.bad_request("No image file provided")

        image_file = request.FILES["image"]
        image_type = request.POST.get("image_type", "gallery")
        alt_text = request.POST.get("alt_text", "")

        # Validate file type
        allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        import os

        ext = os.path.splitext(image_file.name)[1].lower()
        if ext not in allowed_extensions:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "error": f"Invalid file type: {ext}"}
            )
            return APIResponse.bad_request(
                f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )

        # Validate file size (max 5MB)
        if image_file.size > 5 * 1024 * 1024:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "error": f"File too large: {image_file.size} bytes"}
            )
            return APIResponse.bad_request("Image file too large. Maximum size is 5MB")

        image, errors = AdminProductService.add_variant_image(
            variant_id=variant_id,
            image_file=image_file,
            image_type=image_type,
            alt_text=alt_text,
            user=request.user,
        )

        if errors:
            _log_variant_request(
                request, action, start_time, 400,
                extra={"variant_id": variant_id, "errors": errors}
            )
            return APIResponse.validation_error(errors)

        _log_variant_request(
            request, action, start_time, 201,
            extra={
                "image_id": str(image.id),
                "variant_id": variant_id,
                "image_type": image_type,
                "file_size_kb": round(image_file.size / 1024, 2),
                "has_alt_text": bool(alt_text),
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.created(
            data={"image_id": str(image.id), "url": image.image.url},
            message="Image uploaded successfully",
        )

    except Exception as e:
        logger.error(f"Admin image upload error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"variant_id": variant_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def admin_variant_detail(request, variant_id):
    """Admin: Get single variant details"""
    start_time = time.time()
    action = "admin_variant_detail"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin retrieving variant detail: {variant_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "variant_id": variant_id}
    )
    
    try:
        from apps.products.selectors import get_variant_by_id
        from apps.products.schemas import serialize_variant

        variant = get_variant_by_id(variant_id, require_active=False)
        if not variant:
            _log_variant_request(
                request, action, start_time, 404,
                extra={"variant_id": variant_id, "reason": "Variant not found"}
            )
            return APIResponse.not_found("Variant not found")

        variant_data = serialize_variant(variant, is_admin=True, include_images=True)
        variant_data["product"] = {
            "id": str(variant.product.id),
            "title": variant.product.title,
            "slug": variant.product.slug,
        }

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "variant_id": str(variant.id),
                "sku": variant.sku,
                "product_id": str(variant.product.id),
                "product_title": variant.product.title,
                "is_active": variant.is_active,
                "stock": variant.stock,
                "price": float(variant.price),
                "images_count": variant.images.count(),
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.success(
            data=variant_data, message="Variant retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Admin variant detail error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"variant_id": variant_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='20/h', method='DELETE', block=True)
def admin_variant_delete(request, variant_id):
    """Admin: Delete product variant"""
    start_time = time.time()
    action = "admin_variant_delete"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin deleting variant: {variant_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "variant_id": variant_id}
    )
    
    try:
        from apps.products.selectors import get_variant_by_id

        variant = get_variant_by_id(variant_id, require_active=False)
        if not variant:
            _log_variant_request(
                request, action, start_time, 404,
                extra={"variant_id": variant_id, "reason": "Variant not found"}
            )
            return APIResponse.not_found("Variant not found")

        sku = variant.sku
        product_title = variant.product.title
        variant.delete()

        _log_variant_request(
            request, action, start_time, 200,
            extra={
                "variant_id": variant_id,
                "sku": sku,
                "product_title": product_title,
                "requested_by": get_user_info(user)
            }
        )

        return APIResponse.success(message="Variant deleted successfully")

    except Exception as e:
        logger.error(f"Admin variant delete error: {str(e)}", exc_info=True)
        _log_variant_request(request, action, start_time, 500, extra={"variant_id": variant_id, "error": str(e)})
        return APIResponse.server_error()
