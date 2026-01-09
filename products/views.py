"""
products/views.py

Product views using SHARED APIResponse from estore.utils
"""

import json
import logging
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q

# Use SHARED decorators from users (or create in products/decorators)
from users.decorators.auth import (
    json_request_required,
    jwt_required,
    multipart_request_allowed,
    role_required,
)
from estore.utils.responses import APIResponse  # SHARED RESPONSE
from .services.product_service import ProductService, ReviewService
from .models import Product, ProductVariant, Category, ProductReview, Wishlist
import os

logger = logging.getLogger(__name__)


# ==================== PUBLIC PRODUCT VIEWS ====================


@csrf_exempt
@require_http_methods(["GET"])
def product_list(request):
    """Get paginated product list with filtering"""
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        category_slug = request.GET.get("category")
        brand = request.GET.get("brand")
        min_price = request.GET.get("min_price")
        max_price = request.GET.get("max_price")
        in_stock = request.GET.get("in_stock")
        featured = request.GET.get("featured")
        bestseller = request.GET.get("bestseller")
        new = request.GET.get("new")
        search = request.GET.get("search", "").strip()
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        # Convert string parameters
        if min_price:
            min_price = float(min_price)
        if max_price:
            max_price = float(max_price)
        if in_stock:
            in_stock = in_stock.lower() == "true"
        if featured:
            featured = featured.lower() == "true"
        if bestseller:
            bestseller = bestseller.lower() == "true"
        if new:
            new = new.lower() == "true"

        # Get products from service
        products, total_count, filters = ProductService.get_products(
            page=page,
            limit=limit,
            category_slug=category_slug,
            brand=brand,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            featured=featured,
            bestseller=bestseller,
            new=new,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Return standardized list response
        return APIResponse.success(
            # items=products, total=total_count, page=page, limit=limit, filters=filters
            products,
            "Products Listed",
        )

    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def product_detail(request, slug):
    """Get detailed product information"""
    try:
        product_data = ProductService.get_product_detail(slug)

        if not product_data:
            return APIResponse.not_found("Product not found")

        return APIResponse.success(product_data)

    except Exception as e:
        logger.error(f"Product detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def variant_detail(request, variant_id):
    """Get detailed variant information"""
    try:
        variant_data = ProductService.get_variant_detail(variant_id)

        if not variant_data:
            return APIResponse.not_found("Variant not found")

        return APIResponse.success(variant_data)

    except Exception as e:
        logger.error(f"Variant detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def category_list(request):
    """Get all categories"""
    try:
        categories = ProductService.get_categories()
        return APIResponse.success(
            {"categories": categories}, "Categories retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Category list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def category_detail(request, slug):
    """Get detailed category information"""
    try:
        category_data = ProductService.get_category_detail(slug)

        if not category_data:
            return APIResponse.not_found("Category not found")

        return APIResponse.success(category_data)

    except Exception as e:
        logger.error(f"Category detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def product_reviews(request, slug):
    """Get product reviews"""
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        rating = request.GET.get("rating")
        verified = request.GET.get("verified")

        # Convert parameters
        if rating:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return APIResponse.bad_request("Rating must be between 1 and 5")

        if verified:
            verified = verified.lower() == "true"

        reviews, total = ReviewService.get_product_reviews(
            product_slug=slug, page=page, limit=limit, rating=rating, verified=verified
        )

        return APIResponse.success(
            # items=reviews,
            # total=total,
            # page=page,
            # limit=limit,
            # filters={"product_slug": slug},
            reviews,
            f"Review Listed for {slug}",
        )

    except ValueError as e:
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product reviews error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def product_search(request):
    """Search products"""
    try:
        query = request.GET.get("q", "").strip()
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))

        if not query or len(query) < 2:
            return APIResponse.bad_request("Search query must be at least 2 characters")

        # Use product service with search parameter
        products, total_count, filters = ProductService.get_products(
            page=page, limit=limit, search=query
        )

        return APIResponse.success(
            # items=products,
            # total=total_count,
            # page=page,
            # limit=limit,
            # filters={"query": query},
            products,
            f"Results for {query}",
        )

    except ValueError as e:
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product search error: {str(e)}")
        return APIResponse.server_error()


# ==================== AUTHENTICATED USER VIEWS ====================


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def wishlist_list(request):
    """Get or add to wishlist"""
    try:
        user = request.user

        if request.method == "GET":
            # Get user's wishlist
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))

            wishlist_items = Wishlist.objects.filter(user=user)
            total = wishlist_items.count()

            # Paginate
            offset = (page - 1) * limit
            items = wishlist_items.order_by("-created_at")[offset : offset + limit]

            items_data = []
            for item in items:
                variant = item.variant
                product = variant.product
                items_data.append(
                        {
                            "id": str(product.id),
                            "title": product.title,
                            "slug": product.slug,
                            "description": (
                                product.description[:200] + "..."
                                if len(product.description) > 200
                                else product.description
                            ),
                            "category": (
                                {
                                    "id": (
                                        str(product.category.id)
                                        if product.category
                                        else None
                                    ),
                                    "name": (
                                        product.category.name
                                        if product.category
                                        else None
                                    ),
                                    "slug": (
                                        product.category.slug
                                        if product.category
                                        else None
                                    ),
                                }
                                if product.category
                                else None
                            ),
                            "features": product.features,
                            "options": product.options,
                            "min_price": float(product.min_price),
                            "max_price": float(product.max_price),
                            "average_rating": float(product.average_rating),
                            "total_reviews": product.total_reviews,
                            "total_stock": product.total_stock,
                            "has_stock": product.has_stock,
                            "is_featured": product.is_featured,
                            "is_bestseller": product.is_bestseller,
                            "is_new": product.is_new,
                            "default_variant": (
                                {
                                    "sku": (
                                        variant.sku if variant else None
                                    ),
                                    "price": (
                                        float(variant.price)
                                        if variant
                                        else None
                                    ),
                                    "discounted_price": (
                                        float(variant.discounted_price)
                                        if variant
                                        else None
                                    ),
                                    "stock": (
                                        variant.stock if variant else 0
                                    ),
                                    "attributes": (
                                        variant.attributes
                                        if variant
                                        else {}
                                    ),
                                    "images": [
                                        {
                                            "url": img.image.url,
                                            "alt_text": img.alt_text,
                                            "type": img.image_type,
                                        }
                                        for img in variant.images.order_by(
                                            "order"
                                        )
                                    ],
                                }
                                if variant
                                else None
                            ),
                            "created_at": product.created_at.isoformat(),
                        }
                    )

            return APIResponse.success(
                {"items":items_data},"Wishlist Listed Successfully"
            )

        elif request.method == "POST":
            # Add to wishlist
            data = json.loads(request.body)

            if "variant_id" not in data:
                return APIResponse.bad_request("variant_id is required")

            try:
                variant = ProductVariant.objects.get(
                    id=data["variant_id"], is_active=True
                )
            except ProductVariant.DoesNotExist:
                return APIResponse.not_found("Variant not found")

            # Check if already in wishlist
            if Wishlist.objects.filter(user=user, variant=variant).exists():
                return APIResponse.conflict("Item already in wishlist")

            # Add to wishlist
            wishlist_item = Wishlist.objects.create(user=user, variant=variant)

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

        wishlist_item = get_object_or_404(Wishlist, user=user, variant_id=variant_id)
        wishlist_item.delete()

        return APIResponse.success(message="Removed from wishlist")

    except Exception as e:
        logger.error(f"Wishlist remove error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def create_review(request, slug):
    """Create product review"""
    try:
        user = request.user
        data = request.json_data

        # Get product
        product = get_object_or_404(Product, slug=slug)

        # Check if user already reviewed
        if ProductReview.objects.filter(product=product, user=user).exists():
            return APIResponse.conflict("You have already reviewed this product")

        # Validate required fields
        required_fields = ["rating", "comment"]
        errors = {}
        for field in required_fields:
            if field not in data:
                errors[field] = "This field is required"

        if errors:
            return APIResponse.validation_error(errors)

        # Validate rating
        rating = data["rating"]
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return APIResponse.bad_request("Rating must be an integer between 1 and 5")

        # Create review
        review = ProductReview.objects.create(
            product=product,
            user=user,
            rating=rating,
            title=data.get("title", ""),
            comment=data["comment"],
            is_verified_purchase=data.get("is_verified_purchase", False),
        )

        return APIResponse.created(
            data={"review_id": str(review.id)}, message="Review submitted successfully"
        )

    except Exception as e:
        logger.error(f"Create review error: {str(e)}")
        return APIResponse.server_error()


# ==================== ADMIN VIEWS ====================


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_product_list(request):
    """Admin: List all products (including drafts)"""
    try:
        if request.method == "GET":
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))
            status = request.GET.get("status")
            category = request.GET.get("category")
            search = request.GET.get("search", "").strip()

            queryset = Product.objects.all()

            if status:
                queryset = queryset.filter(status=status)

            if category:
                queryset = queryset.filter(category__slug=category)

            if search:
                queryset = queryset.filter(
                    Q(title__icontains=search)
                    | Q(slug__icontains=search)
                    | Q(description__icontains=search)
                )

            total = queryset.count()
            offset = (page - 1) * limit
            products = queryset.order_by("-created_at")[offset : offset + limit]

            products_data = []
            for product in products:
                products_data.append(
                    {
                        "id": str(product.id),
                        "title": product.title,
                        "slug": product.slug,
                        "status": product.status,
                        "category": product.category.name if product.category else None,
                        "variants_count": product.variants.count(),
                        "total_stock": product.total_stock,
                        "has_stock": product.has_stock,
                        "is_featured": product.is_featured,
                        "is_bestseller": product.is_bestseller,
                        "is_new": product.is_new,
                        "average_rating": float(product.average_rating),
                        "created_at": product.created_at.isoformat(),
                        "published_at": (
                            product.published_at.isoformat()
                            if product.published_at
                            else None
                        ),
                    }
                )

            return APIResponse.success(
                data={"products": products_data}, message="Products listed Successfully"
            )

    except Exception as e:
        logger.error(f"Admin product list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@jwt_required
@role_required("admin", "staff")
def admin_product_detail(request, product_id):
    """Admin: Get, update, or delete product"""
    try:
        product = get_object_or_404(Product, id=product_id)

        if request.method == "GET":
            # Return full product details for admin
            product_data = {
                "id": str(product.id),
                "title": product.title,
                "slug": product.slug,
                "description": product.description,
                "meta_title": product.meta_title,
                "meta_description": product.meta_description,
                "category": {
                    "id": str(product.category.id) if product.category else None,
                    "name": product.category.name if product.category else None,
                },
                "features": product.features,
                "options": product.options,
                "status": product.status,
                "is_featured": product.is_featured,
                "is_bestseller": product.is_bestseller,
                "is_new": product.is_new,
                "average_rating": float(product.average_rating),
                "total_reviews": product.total_reviews,
                "variants": [
                    {
                        "id": str(variant.id),
                        "sku": variant.sku,
                        "attributes": variant.attributes,
                        "price": float(variant.price),
                        "discount_amount": float(variant.discount_amount),
                        "stock": variant.stock,
                        "is_default": variant.is_default,
                        "is_active": variant.is_active,
                    }
                    for variant in product.variants.all()
                ],
                "created_at": product.created_at.isoformat(),
                "updated_at": product.updated_at.isoformat(),
                "published_at": (
                    product.published_at.isoformat() if product.published_at else None
                ),
            }

            return APIResponse.success(product_data)

        elif request.method == "PUT" or request.method == "PATCH":
            # TODO: Implement product update
            return APIResponse.bad_request("Product update not implemented yet")

        elif request.method == "DELETE":
            # Soft delete (change status to archived)
            product.status = Product.STATUS_ARCHIVED
            product.save()

            return APIResponse.success(message="Product archived successfully")

    except Exception as e:
        logger.error(f"Admin product detail error: {str(e)}")
        return APIResponse.server_error()


"""
Add these admin views to products/views.py
"""

# ==================== ADMIN PRODUCT MANAGEMENT ====================


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_product_create(request):
    """Admin: Create new product"""
    try:
        data = request.json_data

        from .services.product_service import AdminProductService

        product, errors = AdminProductService.create_product(data, request.user)

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(
            data={"product_id": str(product.id), "slug": product.slug},
            message="Product created successfully",
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin product create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_product_update(request, product_id):
    """Admin: Update product"""
    try:
        data = request.json_data

        from .services.product_service import AdminProductService

        product, errors = AdminProductService.update_product(
            product_id, data, request.user
        )

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.success(
            data={"product_id": str(product.id)}, message="Product updated successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin product update error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
def admin_variant_create(request, product_id):
    """Admin: Create product variant"""
    try:
        data = request.json_data
        files = request.files_data

        from .services.product_service import AdminProductService

        variant, errors = AdminProductService.create_variant(
            product_id, data, request.user, files
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

        from .services.product_service import AdminProductService

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

        from .services.product_service import AdminProductService

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
def admin_category_list(request):
    """Admin: List all categories (including inactive)"""
    try:
        categories = Category.objects.all().order_by("name")

        categories_data = []
        for category in categories:
            categories_data.append(
                {
                    "id": str(category.id),
                    "name": category.name,
                    "slug": category.slug,
                    "description": category.description,
                    "parent_id": str(category.parent.id) if category.parent else None,
                    "parent_name": (
                        category.parent.name if category.parent else "Parent Category"
                    ),
                    "is_active": category.is_active,
                    "product_count": Product.objects.filter(category=category).count(),
                    "created_at": category.created_at.isoformat(),
                }
            )

        return APIResponse.success({"categories": categories_data})

    except Exception as e:
        logger.error(f"Admin category list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
def admin_category_create(request):
    """Admin: Create category with optional image"""
    try:
        data = request.POST.dict()
        image_file = request.FILES.get("image")

        # Validate required fields
        if "name" not in data or not data["name"]:
            return APIResponse.bad_request("Category name is required")

        # Generate slug
        from django.utils.text import slugify

        slug = slugify(data["name"])

        # Ensure unique slug
        counter = 1
        original_slug = slug
        while Category.objects.filter(slug=slug).exists():
            slug = f"{original_slug}-{counter}"
            counter += 1

        # Get parent category if provided
        parent = None
        if "parent_id" in data and data["parent_id"]:
            try:
                parent = Category.objects.get(id=data["parent_id"])
            except Category.DoesNotExist:
                return APIResponse.not_found("Parent category not found")

        # Create category
        category = Category.objects.create(
            name=data["name"],
            slug=slug,
            description=data.get("description", ""),
            parent=parent,
            is_active=True if data.get("is_active") else False,
            meta_title=data.get("meta_title", ""),
            meta_description=data.get("meta_description", ""),
        )

        # Handle image upload if provided
        if image_file:
            try:
                # Validate image file
                if not image_file.content_type.startswith("image/"):
                    return APIResponse.bad_request("File must be an image")

                # Check file size (e.g., 5MB limit)
                if image_file.size > 5 * 1024 * 1024:
                    return APIResponse.bad_request("Image size must be less than 5MB")

                # Generate filename
                from django.utils import timezone

                timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
                filename = f"category_{category.slug}_{timestamp}{os.path.splitext(image_file.name)[1]}"

                # Save image using ImageField (if your Category model has image field)
                if hasattr(category, "image"):
                    category.image.save(filename, image_file, save=True)

                logger.info(f"Category image uploaded: {filename}")

            except Exception as e:
                logger.error(f"Error uploading category image: {str(e)}")

        logger.info(f"Category created by admin {request.user.email}: {category.name}")

        return APIResponse.created(
            data={
                "category_id": str(category.id),
                "slug": category.slug,
                "name": category.name,
                "has_image": bool(image_file),
            },
            message="Category created successfully",
        )

    except Exception as e:
        logger.error(f"Admin category create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH", "DELETE"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_category_update_delete(request, category_id):
    """Admin: Update or delete a category"""
    try:
        # Get category
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return APIResponse.not_found("Category not found")

        if request.method == "PUT" or request.method == "PATCH":
            data = request.json_data

            # Check if name is being updated
            if "name" in data and data["name"] != category.name:
                if not data["name"] or len(data["name"].strip()) < 2:
                    return APIResponse.bad_request(
                        "Category name must be at least 2 characters"
                    )

                # Generate new slug if name changes
                from django.utils.text import slugify

                new_slug = slugify(data["name"])

                # Ensure unique slug
                if new_slug != category.slug:
                    counter = 1
                    original_slug = new_slug
                    while (
                        Category.objects.filter(slug=new_slug)
                        .exclude(id=category.id)
                        .exists()
                    ):
                        new_slug = f"{original_slug}-{counter}"
                        counter += 1
                    category.slug = new_slug

                category.name = data["name"]

            # Update parent if provided
            if "parent_id" in data:
                if data["parent_id"] is None or data["parent_id"] == "":
                    category.parent = None
                else:
                    try:
                        parent = Category.objects.get(id=data["parent_id"])

                        # Prevent circular reference
                        if parent.id == category.id:
                            return APIResponse.bad_request(
                                "Category cannot be its own parent"
                            )

                        category.parent = parent
                    except Category.DoesNotExist:
                        return APIResponse.not_found("Parent category not found")

            # Update other fields
            if "description" in data:
                category.description = data.get("description", "")

            if "meta_title" in data:
                category.meta_title = data.get("meta_title", "")

            if "meta_description" in data:
                category.meta_description = data.get("meta_description", "")

            if "is_active" in data:
                category.is_active = data["is_active"]

            category.save()

            logger.info(
                f"Category updated by admin {request.user.email}: {category.name}"
            )

            return APIResponse.success(
                data={"category_id": str(category.id), "slug": category.slug},
                message="Category updated successfully",
            )

        elif request.method == "DELETE":
            # Check if category has children
            if category.children.exists():
                return APIResponse.bad_request(
                    "Cannot delete category with subcategories"
                )

            # Check if category has products
            if Product.objects.filter(category=category).exists():
                return APIResponse.bad_request("Cannot delete category with products")

            category_name = category.name
            category.delete()

            logger.info(
                f"Category deleted by admin {request.user.email}: {category_name}"
            )

            return APIResponse.success(message="Category deleted successfully")

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin category update/delete error: {str(e)}")
        return APIResponse.server_error()
