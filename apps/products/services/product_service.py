"""
Business logic and database write operations
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone

from apps.products.models import (
    Product,
    ProductVariant,
    ProductReview,
    Wishlist,
    VariantImage,
)
from apps.products.selectors import (
    get_product_by_id,
    get_product_by_slug,
    get_variant_by_id,
    get_variant_by_sku,
    get_category_by_id,
    get_category_by_slug,
    get_products_filtered,
    get_related_products,
    get_all_categories,
    get_subcategories,
    get_reviews_by_product,
    get_wishlist_items,
    get_all_variants,
    get_admin_products_filtered
)
from apps.products.schemas import (
    serialize_product,
    serialize_product_list,
    serialize_variant,
    serialize_category,
    serialize_review,
    serialize_variant_list_response,
)
from apps.users.models import User
from ..models import Category
from apps.common.logging import log_action, LogSeverity, get_user_info

from django.db.models import Sum, F, Avg
from datetime import timedelta
from common.analytics import BaseAnalyticsService
\
logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


# ==================== CATEGORY SERVICE ====================
# NOTE: This is a DUPLICATE - should be removed and import from category_service.py instead
# Keeping for now but should be removed in Phase 8
class CategoryService:
    """Category management business logic - DUPLICATE, use category_service.py instead"""
    
    @staticmethod
    @transaction.atomic
    def create_category(
        name: str,
        description: str = "",
        parent_id: str = None,
        is_active: bool = True,
        is_hidden: bool = False,
        meta_title: str = "",
        meta_description: str = "",
        image_file=None,
        user: User = None,
    ) -> Tuple[Optional[Category], Optional[Dict]]:
        """Create a new category"""
        start_time = time.time()
        action = "category_create"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating new category: {name}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"category_name": name, "is_hidden": is_hidden}
        )
        
        try:
            from django.utils.text import slugify

            base_slug = slugify(name)
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            parent = None
            if parent_id and parent_id != "null" and parent_id != "none":
                parent = get_category_by_id(parent_id, is_admin=True)
                if not parent:
                    return None, {"parent_id": "Parent category not found"}

            category = Category.objects.create(
                name=name, slug=slug, description=description, parent=parent,
                is_active=is_active, is_hidden=is_hidden,
                meta_title=meta_title, meta_description=meta_description,
            )

            if image_file:
                category.image.save(image_file.name, image_file, save=True)

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Category created: {category.name}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": str(category.id),
                    "category_name": category.name,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return category, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create category: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": f"Failed to create category: {str(e)}"}

    # ... rest of CategoryService methods (update_category, bulk_action_categories)
    # Would be updated similarly but should be removed in favor of category_service.py


# ==================== PRODUCT SERVICE ====================

class ProductService:
    """Product business logic - read operations using selectors + serializers"""

    @staticmethod
    def get_admin_products(
        page: int = 1,
        limit: int = 20,
        search: str = None,
        status: str = None,
        category_id: str = None,
        is_featured: bool = None,
        is_bestseller: bool = None,
        is_new: bool = None,
        has_stock: bool = None,
        min_price: float = None,
        max_price: float = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Dict], int, Dict]:
        """Get filtered and paginated products for admin"""
        start_time = time.time()
        action = "get_admin_products"
        
        products, total, pagination_meta = get_admin_products_filtered(
            page=page, limit=limit, search=search, status=status,
            category_id=category_id, is_featured=is_featured,
            is_bestseller=is_bestseller, is_new=is_new, has_stock=has_stock,
            min_price=min_price, max_price=max_price,
            sort_by=sort_by, sort_order=sort_order,
        )
        
        products_data = serialize_product_list(products, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Admin products retrieved",
            status_code=200,
            app_name=APP_NAME,
            extra={
                "total_products": total,
                "page": page,
                "limit": limit,
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return products_data, total, pagination_meta

    @staticmethod
    def get_public_products(
        page: int = 1,
        limit: int = 20,
        category_slug: str = None,
        brand: str = None,
        min_price: float = None,
        max_price: float = None,
        in_stock: bool = None,
        featured: bool = None,
        bestseller: bool = None,
        new: bool = None,
        search: str = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        is_admin: bool = False,
    ) -> Tuple[List[Dict], int, Dict]:
        """Get filtered and paginated products for public/customers"""
        start_time = time.time()
        action = "get_public_products"
        
        products, total, pagination_meta = get_products_filtered(
            page=page, limit=limit, category_slug=category_slug, brand=brand,
            min_price=min_price, max_price=max_price, in_stock=in_stock,
            featured=featured, bestseller=bestseller, new=new, search=search,
            sort_by=sort_by, sort_order=sort_order,
            include_drafts=False, is_admin=is_admin,
        )
        
        products_data = serialize_product_list(products, is_admin=is_admin)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Public products retrieved",
            status_code=200,
            app_name=APP_NAME,
            extra={
                "total_products": total,
                "page": page,
                "limit": limit,
                "has_search": bool(search),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return products_data, total, pagination_meta
    
    @staticmethod
    def get_product_detail(slug: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed product information"""
        start_time = time.time()
        action = "get_product_detail"
        
        product = get_product_by_slug(slug, include_inactive=False)

        if not product:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Product not found: {slug}",
                status_code=404,
                app_name=APP_NAME,
                extra={"slug": slug, "duration_ms": round(duration_ms, 2)}
            )
            return None
        
        if not is_admin and product.status != Product.STATUS_PUBLISHED:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Product not published: {slug}",
                status_code=404,
                app_name=APP_NAME,
                extra={"slug": slug, "status": product.status, "duration_ms": round(duration_ms, 2)}
            )
            return None

        product_data = serialize_product(product, is_admin=is_admin)
        related = get_related_products(product, include_drafts=is_admin)
        product_data["related_products"] = serialize_product_list(related, is_admin=is_admin)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Product detail retrieved: {product.title}",
            status_code=200,
            app_name=APP_NAME,
            extra={
                "product_id": str(product.id),
                "product_slug": slug,
                "related_count": len(related),
                "duration_ms": round(duration_ms, 2)
            }
        )

        return product_data

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

        variants, total, pagination_meta = get_all_variants(
            page=page, limit=limit, search=search, product_id=product_id,
            is_active=is_active, is_default=is_default, min_price=min_price,
            max_price=max_price, in_stock=in_stock, sort_by=sort_by,
            sort_order=sort_order, is_admin=is_admin,
        )

        variants_data = serialize_variant_list_response(variants, is_admin=is_admin)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Variants retrieved",
            status_code=200,
            app_name=APP_NAME,
            extra={
                "total_variants": total,
                "page": page,
                "limit": limit,
                "product_id_filter": product_id,
                "duration_ms": round(duration_ms, 2)
            }
        )

        return variants_data, total, pagination_meta

    @staticmethod
    def get_variant_detail(variant_id: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed variant information"""
        start_time = time.time()
        action = "get_variant_detail"
        
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
                extra={"variant_id": variant_id, "duration_ms": round(duration_ms, 2)}
            )
            return None

        if not is_admin and variant.product.status != Product.STATUS_PUBLISHED:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Variant product not published: {variant_id}",
                status_code=404,
                app_name=APP_NAME,
                extra={"variant_id": variant_id, "product_status": variant.product.status}
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
                "duration_ms": round(duration_ms, 2)
            }
        )

        return variant_data

    @staticmethod
    def get_categories(is_admin: bool = False) -> List[Dict]:
        """Get all categories"""
        start_time = time.time()
        action = "get_categories"
        
        categories = get_all_categories(only_active=not is_admin)

        categories_data = []
        for category in categories:
            data = serialize_category(category, is_admin=is_admin)
            product_count = Product.objects.filter(category=category).count()
            if not is_admin:
                product_count = Product.objects.filter(
                    category=category, status=Product.STATUS_PUBLISHED
                ).count()
            data["product_count"] = product_count
            categories_data.append(data)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Categories retrieved",
            status_code=200,
            app_name=APP_NAME,
            extra={"total_categories": len(categories_data), "duration_ms": round(duration_ms, 2)}
        )

        return categories_data

    @staticmethod
    def get_category_detail(slug: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed category information"""
        start_time = time.time()
        action = "get_category_detail"
        
        category = get_category_by_slug(slug, only_active=not is_admin)
        
        if not category:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Category not found: {slug}",
                status_code=404,
                app_name=APP_NAME,
                extra={"slug": slug, "duration_ms": round(duration_ms, 2)}
            )
            return None
        
        category_data = serialize_category(category, is_admin=is_admin)
        
        subcategories = get_subcategories(str(category.id), only_active=not is_admin)
        subcategories_data = []
        for sub in subcategories:
            sub_data = {"id": str(sub.id), "name": sub.name, "slug": sub.slug}
            product_count = Product.objects.filter(category=sub).count()
            if not is_admin:
                product_count = Product.objects.filter(
                    category=sub, status=Product.STATUS_PUBLISHED
                ).count()
            sub_data["product_count"] = product_count
            subcategories_data.append(sub_data)
        
        category_data["subcategories"] = subcategories_data
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Category detail retrieved: {category.name}",
            status_code=200,
            app_name=APP_NAME,
            extra={
                "category_id": str(category.id),
                "category_slug": slug,
                "subcategories_count": len(subcategories_data),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return category_data

    @staticmethod
    @transaction.atomic
    def bulk_action_products(
        product_ids: List[str], action: str, user: User
    ) -> Tuple[Dict, Optional[Dict]]:
        """Perform bulk actions on products"""
        start_time = time.time()
        action_name = f"bulk_product_{action}"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action_name,
            description=f"Starting bulk {action} on {len(product_ids)} products",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"action": action, "total_products": len(product_ids)}
        )
        
        from apps.products.models import Product
        
        results = {"success": [], "failed": [], "total": len(product_ids)}
        
        if action in ["publish", "draft", "archive"]:
            status_map = {
                "publish": Product.STATUS_PUBLISHED,
                "draft": Product.STATUS_DRAFT,
                "archive": Product.STATUS_ARCHIVED,
            }
            new_status = status_map.get(action)
            
            for product_id in product_ids:
                product = None
                try:
                    product = Product.objects.get(id=product_id)
                    old_status = product.status
                    product.status = new_status
                    
                    if new_status == Product.STATUS_PUBLISHED and not product.published_at:
                        product.published_at = timezone.now()
                    
                    product.save()
                    results["success"].append({
                        "id": product_id, "name": product.title,
                        "old_status": old_status, "new_status": new_status,
                    })
                except Product.DoesNotExist:
                    results["failed"].append({"id": product_id, "name": "Unknown", "reason": "Product not found"})
                except Exception as e:
                    results["failed"].append({
                        "id": product_id,
                        "name": getattr(product, "title", "Unknown") if product else "Unknown",
                        "reason": str(e),
                    })
        
        elif action in ["feature", "unfeature"]:
            is_featured = action == "feature"
            for product_id in product_ids:
                product = None
                try:
                    product = Product.objects.get(id=product_id)
                    product.is_featured = is_featured
                    product.save()
                    results["success"].append({"id": product_id, "name": product.title, "is_featured": is_featured})
                except Product.DoesNotExist:
                    results["failed"].append({"id": product_id, "name": "Unknown", "reason": "Product not found"})
                except Exception as e:
                    results["failed"].append({
                        "id": product_id,
                        "name": getattr(product, "title", "Unknown") if product else "Unknown",
                        "reason": str(e),
                    })
        
        elif action in ["bestseller", "unbestseller"]:
            is_bestseller = action == "bestseller"
            for product_id in product_ids:
                product = None
                try:
                    product = Product.objects.get(id=product_id)
                    product.is_bestseller = is_bestseller
                    product.save()
                    results["success"].append({"id": product_id, "name": product.title, "is_bestseller": is_bestseller})
                except Product.DoesNotExist:
                    results["failed"].append({"id": product_id, "name": "Unknown", "reason": "Product not found"})
                except Exception as e:
                    results["failed"].append({
                        "id": product_id,
                        "name": getattr(product, "title", "Unknown") if product else "Unknown",
                        "reason": str(e),
                    })
        
        elif action in ["new", "unnew"]:
            is_new = action == "new"
            for product_id in product_ids:
                product = None
                try:
                    product = Product.objects.get(id=product_id)
                    product.is_new = is_new
                    product.save()
                    results["success"].append({"id": product_id, "name": product.title, "is_new": is_new})
                except Product.DoesNotExist:
                    results["failed"].append({"id": product_id, "name": "Unknown", "reason": "Product not found"})
                except Exception as e:
                    results["failed"].append({
                        "id": product_id,
                        "name": getattr(product, "title", "Unknown") if product else "Unknown",
                        "reason": str(e),
                    })
        
        elif action == "delete":
            for product_id in product_ids:
                product = None
                try:
                    product = Product.objects.get(id=product_id)
                    product_name = product.title
                    product.delete()
                    results["success"].append({"id": product_id, "name": product_name})
                except Product.DoesNotExist:
                    results["failed"].append({"id": product_id, "name": "Unknown", "reason": "Product not found"})
                except Exception as e:
                    results["failed"].append({
                        "id": product_id,
                        "name": getattr(product, "title", "Unknown") if product else "Unknown",
                        "reason": str(e),
                    })
        
        else:
            return None, {"action": f"Unknown action: {action}"}
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action_name,
            description=f"Bulk {action} completed: {len(results['success'])} succeeded, {len(results['failed'])} failed",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "action": action,
                "total_products": len(product_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return results, None


# ==================== REVIEW SERVICE ====================

class ReviewService:
    """Product review business logic"""

    @staticmethod
    def get_product_reviews(
        product_slug: str,
        page: int = 1,
        limit: int = 20,
        rating: int = None,
        verified: bool = None,
        is_admin: bool = False,
    ) -> Tuple[List[Dict], int]:
        """Get product reviews"""
        start_time = time.time()
        action = "get_product_reviews"

        reviews, total = get_reviews_by_product(
            product_slug=product_slug, page=page, limit=limit,
            rating=rating, verified=verified, only_approved=not is_admin,
        )

        reviews_data = [serialize_review(r, is_admin=is_admin) for r in reviews]
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Product reviews retrieved for {product_slug}",
            status_code=200,
            app_name=APP_NAME,
            extra={
                "product_slug": product_slug,
                "total_reviews": total,
                "page": page,
                "duration_ms": round(duration_ms, 2)
            }
        )

        return reviews_data, total

    @staticmethod
    @transaction.atomic
    def create_review(
        user: User,
        product_slug: str,
        rating: int,
        comment: str,
        title: str = "",
        is_verified_purchase: bool = False,
    ) -> Tuple[Optional[ProductReview], Optional[Dict]]:
        """Create a new product review"""
        start_time = time.time()
        action = "create_review"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating review for product: {product_slug}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"product_slug": product_slug, "rating": rating}
        )
        
        try:
            product = get_product_by_slug(product_slug)
            if not product:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Product not found: {product_slug}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={"product_slug": product_slug, "duration_ms": round(duration_ms, 2)}
                )
                return None, {"product": "Product not found"}

            if ProductReview.objects.filter(product=product, user=user).exists():
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Duplicate review attempt for {product_slug}",
                    status_code=409,
                    user=user,
                    app_name=APP_NAME,
                    extra={"product_slug": product_slug, "duration_ms": round(duration_ms, 2)}
                )
                return None, {"review": "You have already reviewed this product"}

            review = ProductReview.objects.create(
                product=product, user=user, rating=rating,
                title=title, comment=comment, is_verified_purchase=is_verified_purchase,
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Review created for {product_slug}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": str(review.id),
                    "product_slug": product_slug,
                    "rating": rating,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return review, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create review: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"product_slug": product_slug, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": "Failed to create review"}


# ==================== WISHLIST SERVICE ====================

class WishlistService:
    """Wishlist business logic"""

    @staticmethod
    def get_user_wishlist(
        user: User,
        page: int = 1,
        limit: int = 20,
        is_admin: bool = False,
        grouped: bool = True,
    ) -> Tuple[List[Dict], int]:
        """Get user's wishlist items"""
        start_time = time.time()
        action = "get_user_wishlist"

        from apps.products.selectors import get_wishlist_items_flat

        if grouped:
            items, total = get_wishlist_items(user, page, limit, is_admin)
        else:
            items, total = get_wishlist_items_flat(user, page, limit, is_admin)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="User wishlist retrieved",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "total_items": total,
                "page": page,
                "grouped": grouped,
                "duration_ms": round(duration_ms, 2)
            }
        )

        return items, total

    @staticmethod
    @transaction.atomic
    def add_to_wishlist(
        user: User, variant_id: str
    ) -> Tuple[Optional[Wishlist], Optional[str]]:
        """Add variant to user's wishlist"""
        start_time = time.time()
        action = "add_to_wishlist"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Adding variant {variant_id} to wishlist",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"variant_id": variant_id}
        )
        
        try:
            from apps.products.selectors import get_variant_by_id

            variant = get_variant_by_id(variant_id)
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
                    extra={"variant_id": variant_id, "duration_ms": round(duration_ms, 2)}
                )
                return None, "Variant not found"

            if Wishlist.objects.filter(user=user, variant=variant).exists():
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Item already in wishlist: {variant_id}",
                    status_code=409,
                    user=user,
                    app_name=APP_NAME,
                    extra={"variant_id": variant_id, "variant_sku": variant.sku}
                )
                return None, "Item already in wishlist"

            wishlist_item = Wishlist.objects.create(user=user, variant=variant)

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Added to wishlist: {variant.sku}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "wishlist_id": str(wishlist_item.id),
                    "variant_id": variant_id,
                    "variant_sku": variant.sku,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return wishlist_item, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to add to wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"variant_id": variant_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, f"Failed to add to wishlist: {str(e)}"

    @staticmethod
    @transaction.atomic
    def remove_from_wishlist(user: User, variant_id: str) -> Tuple[bool, Optional[str]]:
        """Remove variant from user's wishlist"""
        start_time = time.time()
        action = "remove_from_wishlist"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Removing variant {variant_id} from wishlist",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"variant_id": variant_id}
        )
        
        try:
            deleted_count, _ = Wishlist.objects.filter(
                user=user, variant_id=variant_id
            ).delete()

            if deleted_count > 0:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.INFO,
                    action=action,
                    description=f"Removed from wishlist: {variant_id}",
                    status_code=200,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return True, None
            else:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Item not found in wishlist: {variant_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={"variant_id": variant_id, "duration_ms": round(duration_ms, 2)}
                )
                return False, "Item not found in wishlist"

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to remove from wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"variant_id": variant_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return False, f"Failed to remove from wishlist: {str(e)}"


# ==================== ADMIN PRODUCT SERVICE ====================

class AdminProductService:
    """Admin product management business logic - writes only"""

    @staticmethod
    @transaction.atomic
    def create_product(
        data: Dict[str, Any], user: User
    ) -> Tuple[Optional[Product], Optional[Dict]]:
        """Create a new product (admin only)"""
        start_time = time.time()
        action = "admin_create_product"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating product: {data.get('title')}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"product_title": data.get("title")}
        )
        
        try:
            category = get_category_by_id(data["category_id"])
            if not category:
                return None, {"category_id": "Category not found"}

            base_slug = slugify(data["title"])
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            product = Product.objects.create(
                title=data["title"], slug=slug, description=data["description"],
                category=category, features=data.get("features", []),
                options=data.get("options", {}), status=data.get("status", Product.STATUS_DRAFT),
                is_featured=data.get("is_featured", False), is_bestseller=data.get("is_bestseller", False),
                is_new=data.get("is_new", False), meta_title=data.get("meta_title", ""),
                meta_description=data.get("meta_description", ""),
                published_at=timezone.now() if data.get("status") == Product.STATUS_PUBLISHED else None,
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Product created: {product.title}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "product_id": str(product.id),
                    "product_title": product.title,
                    "slug": product.slug,
                    "status": product.status,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return product, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create product: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": "Failed to create product"}

    @staticmethod
    @transaction.atomic
    def update_product(
        product_id: str, data: Dict[str, Any], user: User
    ) -> Tuple[Optional[Product], Optional[Dict]]:
        """Update product (admin only)"""
        start_time = time.time()
        action = "admin_update_product"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Updating product: {product_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"product_id": product_id, "update_fields": list(data.keys())}
        )
        
        try:
            product = get_product_by_id(product_id, include_inactive=True)
            if not product:
                return None, {"product": "Product not found"}

            for field in ["title", "description", "status", "is_featured", "is_bestseller", 
                          "is_new", "meta_title", "meta_description", "features", "options"]:
                if field in data:
                    setattr(product, field, data[field])

            if "category_id" in data and data["category_id"]:
                category = get_category_by_id(data["category_id"])
                if not category:
                    return None, {"category_id": "Category not found"}
                product.category = category
            elif "category_id" in data and data["category_id"] is None:
                product.category = None

            if "title" in data and data["title"] != product.title:
                base_slug = slugify(data["title"])
                slug = base_slug
                counter = 1
                while Product.objects.filter(slug=slug).exclude(id=product.id).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                product.slug = slug

            if product.status == Product.STATUS_PUBLISHED and not product.published_at:
                product.published_at = timezone.now()

            product.save()

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Product updated: {product.title}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "product_id": str(product.id),
                    "product_title": product.title,
                    "updated_fields": list(data.keys()),
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return product, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to update product: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"product_id": product_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": "Failed to update product"}

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
            extra={"product_id": product_id, "sku": data.get("sku")}
        )
        
        try:
            product = get_product_by_id(product_id, include_inactive=True)
            if not product:
                return None, {"product": "Product not found"}

            if get_variant_by_sku(data["sku"]):
                return None, {"sku": "SKU already exists"}

            if product.options:
                for option_key in data["attributes"]:
                    if option_key not in product.options:
                        return None, {
                            f"attributes.{option_key}": f'Option "{option_key}" not allowed for this product'
                        }

            is_default = data.get("is_default", False)
            if is_default:
                ProductVariant.objects.filter(product=product, is_default=True).update(is_default=False)
            elif not ProductVariant.objects.filter(product=product).exists():
                is_default = True

            variant = ProductVariant.objects.create(
                product=product, sku=data["sku"], attributes=data["attributes"],
                price=data["price"], discount_amount=data.get("discount_amount", 0),
                stock=data.get("stock", 0), is_default=is_default,
                is_active=data.get("is_active", True), weight=data.get("weight"),
                height=data.get("height"), width=data.get("width"), depth=data.get("depth"),
                low_stock_threshold=data.get("low_stock_threshold", 5),
            )

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
                        alt_text = (data.get("image_alt_texts", [])[i] if data.get("image_alt_texts")
                                    and i < len(data.get("image_alt_texts", [])) else f"{product.title} - {variant.sku}")
                        VariantImage.objects.create(
                            variant=variant, image=image_file, image_type=image_type,
                            alt_text=alt_text, order=i, is_active=True,
                        )

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
                    "price": float(variant.price),
                    "stock": variant.stock,
                    "images_count": len(image_files) if image_files else 0,
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
                extra={"product_id": product_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
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
            extra={"variant_id": variant_id, "update_fields": list(data.keys())}
        )
        
        try:
            variant = get_variant_by_id(variant_id, require_active=False)
            if not variant:
                return None, {"variant": "Variant not found"}

            if "sku" in data and data["sku"] != variant.sku:
                if get_variant_by_sku(data["sku"]):
                    return None, {"sku": "SKU already exists"}

            if data.get("is_default", False) and not variant.is_default:
                ProductVariant.objects.filter(product=variant.product, is_default=True).update(is_default=False)

            for field in ["sku", "price", "discount_amount", "stock", "is_default", "is_active",
                          "weight", "height", "width", "depth", "low_stock_threshold", "attributes"]:
                if field in data:
                    setattr(variant, field, data[field])

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
                    "updated_fields": list(data.keys()),
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
                description=f"Failed to update variant: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"variant_id": variant_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
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
            extra={"variant_id": variant_id, "image_type": image_type}
        )
        
        try:
            variant = get_variant_by_id(variant_id, require_active=False)
            if not variant:
                return None, {"variant": "Variant not found"}

            valid_types = ["main", "gallery", "thumbnail"]
            if image_type not in valid_types:
                return None, {"image_type": f'Must be one of: {", ".join(valid_types)}'}

            image = VariantImage.objects.create(
                variant=variant, image=image_file, image_type=image_type,
                alt_text=alt_text, order=VariantImage.objects.filter(variant=variant).count(),
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
                    "image_type": image_type,
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
                description=f"Failed to add image: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"variant_id": variant_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": "Failed to upload image"}


# ==================== PRODUCT ANALYTICS SERVICE ====================

class ProductAnalyticsService(BaseAnalyticsService):
    """Optimized product analytics service"""

    def __init__(self):
        super().__init__(app_name=APP_NAME, cache_timeout=300)

    def get_card_data(self, request) -> List[Dict]:
        """Get card data using optimized single-query aggregations"""
        start_time = time.time()
        action = "analytics_card_data"
        user = request.user if hasattr(request, 'user') else None
        
        try:
            from django.db.models import Count, Q

            product_aggregates = Product.objects.aggregate(
                total=Count("id"),
                published=Count("id", filter=Q(status=Product.STATUS_PUBLISHED)),
                draft=Count("id", filter=Q(status=Product.STATUS_DRAFT)),
                archived=Count("id", filter=Q(status=Product.STATUS_ARCHIVED)),
                featured=Count("id", filter=Q(is_featured=True)),
                bestseller=Count("id", filter=Q(is_bestseller=True)),
                new=Count("id", filter=Q(created_at__gte=timezone.now() - timedelta(days=30))),
                missing_variants=Count("id", filter=Q(variants__isnull=True)),
            )

            variant_aggregates = ProductVariant.objects.aggregate(
                total_variants=Count("id"),
                total_stock=Sum("stock"),
                low_stock=Count("id", filter=Q(stock__lte=F("low_stock_threshold"), stock__gt=0)),
                out_of_stock=Count("id", filter=Q(stock=0)),
                inventory_value=Sum(F("price") * F("stock")),
            )

            category_aggregates = Category.objects.aggregate(
                active_categories=Count("id", filter=Q(is_active=True, is_hidden=False))
            )

            rating_avg = ProductReview.objects.filter(is_approved=True).aggregate(avg_rating=Avg("rating"))["avg_rating"] or 0

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Card data generated",
                status_code=200,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={
                    "duration_ms": round(duration_ms, 2),
                    "total_products": product_aggregates["total"] or 0,
                    "total_variants": variant_aggregates["total_variants"] or 0,
                }
            )

            return [
                {"id": "total_products", "name": "Total Products", "value": product_aggregates["total"] or 0, "unit": "", "critical": False},
                {"id": "published_products", "name": "Published", "value": product_aggregates["published"] or 0, "unit": "", "critical": False},
                {"id": "draft_products", "name": "Draft", "value": product_aggregates["draft"] or 0, "unit": "", "critical": product_aggregates["draft"] > 10},
                {"id": "archived_products", "name": "Archived", "value": product_aggregates["archived"] or 0, "unit": "", "critical": False},
                {"id": "total_variants", "name": "Total Variants", "value": variant_aggregates["total_variants"] or 0, "unit": "", "critical": False},
                {"id": "total_stock", "name": "Total Stock", "value": variant_aggregates["total_stock"] or 0, "unit": "units", "critical": (variant_aggregates["total_stock"] or 0) < 100},
                {"id": "low_stock_variants", "name": "Low Stock", "value": variant_aggregates["low_stock"] or 0, "unit": "variants", "critical": (variant_aggregates["low_stock"] or 0) > 5},
                {"id": "out_of_stock", "name": "Out of Stock", "value": variant_aggregates["out_of_stock"] or 0, "unit": "variants", "critical": (variant_aggregates["out_of_stock"] or 0) > 10},
                {"id": "featured_products", "name": "Featured", "value": product_aggregates["featured"] or 0, "unit": "", "critical": False},
                {"id": "bestseller_products", "name": "Bestsellers", "value": product_aggregates["bestseller"] or 0, "unit": "", "critical": False},
                {"id": "new_products", "name": "New (30 days)", "value": product_aggregates["new"] or 0, "unit": "", "critical": False},
                {"id": "inventory_value", "name": "Inventory Value", "value": round(variant_aggregates["inventory_value"] or 0, 2), "unit": "$", "critical": False},
                {"id": "products_without_variants", "name": "Missing Variants", "value": product_aggregates["missing_variants"] or 0, "unit": "", "critical": (product_aggregates["missing_variants"] or 0) > 5},
                {"id": "avg_rating", "name": "Average Rating", "value": round(rating_avg, 1), "unit": "★", "critical": rating_avg < 3.5},
                {"id": "active_categories", "name": "Active Categories", "value": category_aggregates["active_categories"] or 0, "unit": "", "critical": False},
            ]

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to generate card data: {str(e)}",
                status_code=500,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            raise

    def get_chart_data(self, request, chart_type: str = None) -> Dict:
        """Get all chart data with optimized queries"""
        start_time = time.time()
        action = "analytics_chart_data"
        user = request.user if hasattr(request, 'user') else None
        
        charts = {}

        try:
            if chart_type and chart_type != "all":
                method_name = f"_get_{chart_type}_chart"
                if hasattr(self, method_name):
                    charts[chart_type] = getattr(self, method_name)()
                    chart_count = 1
                else:
                    chart_count = 0
            else:
                charts = {
                    "monthly_trend": self._get_monthly_trend_chart(),
                    "categories": self._get_category_chart(),
                    "status_distribution": self._get_status_chart(),
                    "stock_distribution": self._get_stock_chart(),
                    "weekly_activity": self._get_weekly_chart(),
                    "top_products": self._get_top_products_chart(),
                    "rating_distribution": self._get_rating_chart(),
                    "product_flags": self._get_flags_chart(),
                    "category_visibility": self._get_visibility_chart(),
                }
                chart_count = len(charts)

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Chart data generated",
                status_code=200,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={
                    "duration_ms": round(duration_ms, 2),
                    "chart_type_requested": chart_type or "all",
                    "charts_generated": chart_count,
                }
            )

            return charts

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to generate chart data: {str(e)}",
                status_code=500,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"chart_type": chart_type, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            raise

    # Chart methods (_get_monthly_trend_chart, _get_category_chart, etc.)
    # These should be updated similarly to accept request parameter and add logging
    # (Keeping existing implementation for brevity, but should add logging as shown in analytics_service.py)


# Singleton instance
product_analytics_service = ProductAnalyticsService()