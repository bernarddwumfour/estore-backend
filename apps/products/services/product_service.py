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
\
logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


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
                        from apps.social.services import SocialPostService
                        SocialPostService.queue_for_approval("product", product)

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

            if product.status == Product.STATUS_PUBLISHED:
                from apps.social.services import SocialPostService
                SocialPostService.queue_for_approval("product", product)

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
                from apps.social.services import SocialPostService
                SocialPostService.queue_for_approval("product", product)

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
        variant_id: str, data: Dict[str, Any], user: User, image_files: List = None
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

            if "attributes" in data and variant.product.options:
                for option_key in data["attributes"]:
                    if option_key not in variant.product.options:
                        return None, {
                            f"attributes.{option_key}": f'Option "{option_key}" not allowed for this product'
                        }

            candidate_price = data.get("price", variant.price)
            candidate_discount_amount = data.get(
                "discount_amount", variant.discount_amount
            )
            if candidate_discount_amount > candidate_price:
                return None, {"discount_amount": "Cannot exceed price"}

            if data.get("is_default", False) and not variant.is_default:
                ProductVariant.objects.filter(product=variant.product, is_default=True).update(is_default=False)

            for field in ["sku", "price", "discount_amount", "stock", "is_default", "is_active",
                          "weight", "height", "width", "depth", "low_stock_threshold",
                          "attributes", "cost_price"]:
                if field in data:
                    setattr(variant, field, data[field])

            variant.save()

            remove_image_ids = data.get("remove_images") or []
            if remove_image_ids:
                VariantImage.objects.filter(
                    variant=variant, id__in=remove_image_ids
                ).delete()

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

                alt_texts = data.get("image_alt_texts", [])
                if not isinstance(alt_texts, list):
                    alt_texts = []

                next_order = VariantImage.objects.filter(variant=variant).count()
                for i, image_file in enumerate(actual_image_files):
                    if image_file:
                        image_type = "main" if next_order == 0 and i == 0 else "gallery"
                        alt_text = (
                            alt_texts[i]
                            if i < len(alt_texts) and alt_texts[i]
                            else f"{variant.product.title} - {variant.sku}"
                        )
                        VariantImage.objects.create(
                            variant=variant,
                            image=image_file,
                            image_type=image_type,
                            alt_text=alt_text,
                            order=next_order + i,
                            is_active=True,
                        )
                        images_created += 1

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
                    "removed_images_count": len(remove_image_ids),
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


