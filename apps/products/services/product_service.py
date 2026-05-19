# apps/products/services/product_service.py
"""
Business logic and database write operations
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone

from apps.products.models import Product, ProductVariant, ProductReview, Wishlist, VariantImage
from apps.products.selectors import (
    get_product_by_id, get_product_by_slug, get_variant_by_id, get_variant_by_sku,
    get_category_by_id, get_category_by_slug, get_products_filtered,get_related_products,get_all_categories,get_subcategories,get_reviews_by_product,get_wishlist_items
)
from apps.products.schemas import (
    serialize_product, serialize_product_list, serialize_variant, 
    serialize_category, serialize_review
)
from users.models import User
from ..models import Category

from django.db.models import Count, Sum, Q, F, Avg
from datetime import timedelta
from common.analytics import BaseAnalyticsService, AggregatedMetrics
from common.chart_configs import ChartConfig, ColorPalette

logger = logging.getLogger(__name__)

# apps/products/services/product_service.py - Update CategoryService

# apps/products/services/product_service.py - Update CategoryService

class CategoryService:
    """Category management business logic"""
    
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
        try:
            from django.utils.text import slugify
            
            # Generate unique slug
            base_slug = slugify(name)
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            # Get parent if provided
            parent = None
            if parent_id and parent_id != 'null' and parent_id != 'none':
                parent = get_category_by_id(parent_id, is_admin=True)
                if not parent:
                    return None, {"parent_id": "Parent category not found"}
            
            # Create category
            category = Category.objects.create(
                name=name,
                slug=slug,
                description=description,
                parent=parent,
                is_active=is_active,
                is_hidden=is_hidden,
                meta_title=meta_title,
                meta_description=meta_description,
            )
            
            # Handle image upload
            if image_file:
                category.image.save(image_file.name, image_file, save=True)
            
            if user:
                logger.info(f"Category created by admin {user.email}: {category.name}")
            
            return category, None
            
        except Exception as e:
            logger.error(f"Category creation error: {str(e)}")
            return None, {"general": f"Failed to create category: {str(e)}"}
    
    @staticmethod
    @transaction.atomic
    def update_category(
        category_id: str,
        data: Dict[str, Any],
        image_file=None,
        remove_image: bool = False,
        user: User = None,
    ) -> Tuple[Optional[Category], Optional[Dict]]:
        """Update an existing category"""
        try:
            from django.utils.text import slugify
            
            category = get_category_by_id(category_id, is_admin=True)
            if not category:
                return None, {"category": "Category not found"}
            
            # Update name and slug
            if "name" in data and data["name"] != category.name:
                category.name = data["name"]
                base_slug = slugify(data["name"])
                slug = base_slug
                counter = 1
                while Category.objects.filter(slug=slug).exclude(id=category.id).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                category.slug = slug
            
            # Update parent
            if "parent_id" in data:
                if data["parent_id"] is None or data["parent_id"] == 'null' or data["parent_id"] == 'none':
                    category.parent = None
                else:
                    parent = get_category_by_id(data["parent_id"], is_admin=True)
                    if not parent:
                        return None, {"parent_id": "Parent category not found"}
                    if parent.id == category.id:
                        return None, {"parent_id": "Category cannot be its own parent"}
                    category.parent = parent
            
            # Update other fields
            for field in ["description", "is_active", "is_hidden", "meta_title", "meta_description"]:
                if field in data:
                    setattr(category, field, data[field])
            
            category.save()
            
            # Handle image
            if remove_image and category.image:
                category.image.delete(save=False)
                category.image = None
                category.save()
            elif image_file:
                if category.image:
                    category.image.delete(save=False)
                category.image.save(image_file.name, image_file, save=True)
            
            if user:
                logger.info(f"Category updated by admin {user.email}: {category.name}")
            
            return category, None
            
        except Exception as e:
            logger.error(f"Category update error: {str(e)}")
            return None, {"general": f"Failed to update category: {str(e)}"}
        
    @staticmethod
    @transaction.atomic
    def bulk_action_categories(
        category_ids: List[str],
        action: str,
        user: User = None
    ) -> Tuple[Dict, Optional[Dict]]:
        """
        Perform bulk actions on categories
        
        Returns:
            Tuple of (results dict, error dict)
            results: {
                'success': [{'id': str, 'name': str}],
                'failed': [{'id': str, 'name': str, 'reason': str}],
                'total': int
            }
        """
        from apps.products.models import Category, Product
        
        results = {
            'success': [],
            'failed': [],
            'total': len(category_ids)
        }
        
        if action == 'delete':
            for category_id in category_ids:
                try:
                    category = Category.objects.get(id=category_id)
                    
                    # Check for subcategories
                    if category.children.exists():
                        results['failed'].append({
                            'id': category_id,
                            'name': category.name,
                            'reason': 'Has subcategories'
                        })
                        continue
                    
                    # Check for products
                    if Product.objects.filter(category=category).exists():
                        results['failed'].append({
                            'id': category_id,
                            'name': category.name,
                            'reason': 'Has products'
                        })
                        continue
                    
                    category_name = category.name
                    category.delete()
                    results['success'].append({
                        'id': category_id,
                        'name': category_name
                    })
                    
                except Category.DoesNotExist:
                    results['failed'].append({
                        'id': category_id,
                        'name': 'Unknown',
                        'reason': 'Not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': category_id,
                        'name': getattr(category, 'name', 'Unknown'),
                        'reason': str(e)
                    })
        
        elif action in ['activate', 'deactivate', 'hide', 'unhide']:
            for category_id in category_ids:
                try:
                    category = Category.objects.get(id=category_id)
                    
                    if action == 'activate':
                        category.is_active = True
                    elif action == 'deactivate':
                        category.is_active = False
                    elif action == 'hide':
                        category.is_hidden = True
                    elif action == 'unhide':
                        category.is_hidden = False
                    
                    category.save()
                    results['success'].append({
                        'id': category_id,
                        'name': category.name
                    })
                    
                except Category.DoesNotExist:
                    results['failed'].append({
                        'id': category_id,
                        'name': 'Unknown',
                        'reason': 'Not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': category_id,
                        'name': getattr(category, 'name', 'Unknown'),
                        'reason': str(e)
                    })
        
        else:
            return None, {"action": f"Unknown action: {action}"}
        
        if user:
            logger.info(f"Bulk {action} action performed by {user.email}: {len(results['success'])} succeeded, {len(results['failed'])} failed")
        
        return results, None
        
        
class ProductService:
    """Product business logic - read operations using selectors + serializers"""
   
    @staticmethod
    @staticmethod
    def get_products(
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
        status: str = None,  # Add status parameter
    ) -> Tuple[List[Dict], int, Dict]:
        """Get filtered and paginated products"""
        
        products, total = get_products_filtered(
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
            include_drafts=is_admin,
            is_admin=is_admin,
            status=status,  # Pass status to selector
        )
        
        products_data = serialize_product_list(products, is_admin=is_admin)
        
        # Build filters metadata
        filters = {}
        if category_slug:
            filters["category"] = category_slug
        if brand:
            filters["brand"] = brand
        if min_price is not None:
            filters["min_price"] = min_price
        if max_price is not None:
            filters["max_price"] = max_price
        if in_stock is not None:
            filters["in_stock"] = in_stock
        if status:
            filters["status"] = status
        
        return products_data, total, filters
   
    @staticmethod
    def get_product_detail(slug: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed product information"""
        product = get_product_by_slug(slug, include_inactive=is_admin)
        
        if not product:
            return None
        
        # Check if accessible to non-admin
        if not is_admin and product.status != Product.STATUS_PUBLISHED:
            return None
        
        product_data = serialize_product(product, is_admin=is_admin, include_variants=True)
        
        # Add related products
        related = get_related_products(product, include_drafts=is_admin)
        product_data["related_products"] = serialize_product_list(related, is_admin=is_admin)
        
        return product_data
    
    @staticmethod
    def get_variant_detail(variant_id: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed variant information"""
        variant = get_variant_by_id(variant_id, require_active=not is_admin)
        
        if not variant:
            return None
        
        # Check product status for non-admins
        if not is_admin and variant.product.status != Product.STATUS_PUBLISHED:
            return None
        
        variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)
        variant_data["product"] = {
            "id": str(variant.product.id),
            "title": variant.product.title,
            "slug": variant.product.slug,
        }
        
        return variant_data
    
    @staticmethod
    def get_categories(is_admin: bool = False) -> List[Dict]:
        """Get all categories"""
        categories = get_all_categories(only_active=not is_admin)
        
        categories_data = []
        for category in categories:
            data = serialize_category(category, is_admin=is_admin)
            # Add product count
            product_count = Product.objects.filter(category=category).count()
            if not is_admin:
                product_count = Product.objects.filter(category=category, status=Product.STATUS_PUBLISHED).count()
            data["product_count"] = product_count
            categories_data.append(data)
        
        return categories_data
    
    @staticmethod
    def get_category_detail(slug: str, is_admin: bool = False) -> Optional[Dict]:
        """Get detailed category information"""
        category = get_category_by_slug(slug, only_active=not is_admin)
        
        if not category:
            return None
        
        category_data = serialize_category(category, is_admin=is_admin)
        
        # Get subcategories
        subcategories = get_subcategories(str(category.id), only_active=not is_admin)
        subcategories_data = []
        for sub in subcategories:
            sub_data = {
                "id": str(sub.id),
                "name": sub.name,
                "slug": sub.slug,
            }
            # Count products in subcategory
            product_count = Product.objects.filter(category=sub).count()
            if not is_admin:
                product_count = Product.objects.filter(category=sub, status=Product.STATUS_PUBLISHED).count()
            sub_data["product_count"] = product_count
            subcategories_data.append(sub_data)
        
        category_data["subcategories"] = subcategories_data
        
        return 
    
    @staticmethod
    @transaction.atomic
    def bulk_action_products(
        product_ids: List[str],
        action: str,
        user: User
    ) -> Tuple[Dict, Optional[Dict]]:
        """
        Perform bulk actions on products
        
        Returns:
            Tuple of (results dict, error dict)
        """
        from apps.products.models import Product
        
        results = {
            'success': [],
            'failed': [],
            'total': len(product_ids)
        }
        
        if action in ['publish', 'draft', 'archive']:
            status_map = {
                'publish': Product.STATUS_PUBLISHED,
                'draft': Product.STATUS_DRAFT,
                'archive': Product.STATUS_ARCHIVED
            }
            new_status = status_map.get(action)
            
            for product_id in product_ids:
                try:
                    product = Product.objects.get(id=product_id)
                    old_status = product.status
                    product.status = new_status
                    
                    if new_status == Product.STATUS_PUBLISHED and not product.published_at:
                        from django.utils import timezone
                        product.published_at = timezone.now()
                    
                    product.save()
                    results['success'].append({
                        'id': product_id,
                        'name': product.title,
                        'old_status': old_status,
                        'new_status': new_status
                    })
                except Product.DoesNotExist:
                    results['failed'].append({
                        'id': product_id,
                        'name': 'Unknown',
                        'reason': 'Product not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': product_id,
                        'name': getattr(product, 'title', 'Unknown'),
                        'reason': str(e)
                    })
        
        elif action in ['feature', 'unfeature']:
            is_featured = action == 'feature'
            
            for product_id in product_ids:
                try:
                    product = Product.objects.get(id=product_id)
                    product.is_featured = is_featured
                    product.save()
                    results['success'].append({
                        'id': product_id,
                        'name': product.title,
                        'is_featured': is_featured
                    })
                except Product.DoesNotExist:
                    results['failed'].append({
                        'id': product_id,
                        'name': 'Unknown',
                        'reason': 'Product not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': product_id,
                        'name': getattr(product, 'title', 'Unknown'),
                        'reason': str(e)
                    })
        
        elif action in ['bestseller', 'unbestseller']:
            is_bestseller = action == 'bestseller'
            
            for product_id in product_ids:
                try:
                    product = Product.objects.get(id=product_id)
                    product.is_bestseller = is_bestseller
                    product.save()
                    results['success'].append({
                        'id': product_id,
                        'name': product.title,
                        'is_bestseller': is_bestseller
                    })
                except Product.DoesNotExist:
                    results['failed'].append({
                        'id': product_id,
                        'name': 'Unknown',
                        'reason': 'Product not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': product_id,
                        'name': getattr(product, 'title', 'Unknown'),
                        'reason': str(e)
                    })
        
        elif action in ['new', 'unnew']:
            is_new = action == 'new'
            
            for product_id in product_ids:
                try:
                    product = Product.objects.get(id=product_id)
                    product.is_new = is_new
                    product.save()
                    results['success'].append({
                        'id': product_id,
                        'name': product.title,
                        'is_new': is_new
                    })
                except Product.DoesNotExist:
                    results['failed'].append({
                        'id': product_id,
                        'name': 'Unknown',
                        'reason': 'Product not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': product_id,
                        'name': getattr(product, 'title', 'Unknown'),
                        'reason': str(e)
                    })
        
        elif action == 'delete':
            for product_id in product_ids:
                try:
                    product = Product.objects.get(id=product_id)
                    product_name = product.title
                    product.delete()
                    results['success'].append({
                        'id': product_id,
                        'name': product_name
                    })
                except Product.DoesNotExist:
                    results['failed'].append({
                        'id': product_id,
                        'name': 'Unknown',
                        'reason': 'Product not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'id': product_id,
                        'name': getattr(product, 'title', 'Unknown'),
                        'reason': str(e)
                    })
        
        else:
            return None, {"action": f"Unknown action: {action}"}
        
        logger.info(f"Bulk {action} action performed by admin {user.email}: {len(results['success'])} succeeded, {len(results['failed'])} failed")
        
        return results, None


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
        
        reviews, total = get_reviews_by_product(
            product_slug=product_slug,
            page=page,
            limit=limit,
            rating=rating,
            verified=verified,
            only_approved=not is_admin,
        )
        
        reviews_data = [serialize_review(r, is_admin=is_admin) for r in reviews]
        
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
        try:
            product = get_product_by_slug(product_slug)
            if not product:
                return None, {"product": "Product not found"}
            
            # Check if user already reviewed this product
            if ProductReview.objects.filter(product=product, user=user).exists():
                return None, {"review": "You have already reviewed this product"}
            
            # Create review
            review = ProductReview.objects.create(
                product=product,
                user=user,
                rating=rating,
                title=title,
                comment=comment,
                is_verified_purchase=is_verified_purchase,
            )
            
            logger.info(f"Review created for product {product_slug} by user {user.email}")
            return review, None
            
        except Exception as e:
            logger.error(f"Error creating review: {str(e)}")
            return None, {"general": "Failed to create review"}



class WishlistService:
    """Wishlist business logic"""
    
    @staticmethod
    def get_user_wishlist(
        user: User, page: int = 1, limit: int = 20, is_admin: bool = False, grouped: bool = True
    ) -> Tuple[List[Dict], int]:
        """Get user's wishlist items"""
        
        from apps.products.selectors import  get_wishlist_items_flat
        
        if grouped:
            # Grouped by product (multiple variants under one product)
            return get_wishlist_items(user, page, limit, is_admin)
        else:
            # Flat list (each variant as separate item)
            return get_wishlist_items_flat(user, page, limit, is_admin)
    
    @staticmethod
    @transaction.atomic
    def add_to_wishlist(user: User, variant_id: str) -> Tuple[Optional[Wishlist], Optional[str]]:
        """Add variant to user's wishlist"""
        try:
            from apps.products.selectors import get_variant_by_id
            
            variant = get_variant_by_id(variant_id)
            if not variant:
                return None, "Variant not found"
            
            # Check if already in wishlist
            if Wishlist.objects.filter(user=user, variant=variant).exists():
                return None, "Item already in wishlist"
            
            # Add to wishlist
            wishlist_item = Wishlist.objects.create(user=user, variant=variant)
            
            logger.info(f"Added {variant.sku} to wishlist for user {user.email}")
            return wishlist_item, None
            
        except Exception as e:
            logger.error(f"Wishlist add error: {str(e)}")
            return None, f"Failed to add to wishlist: {str(e)}"
    
    @staticmethod
    @transaction.atomic
    def remove_from_wishlist(user: User, variant_id: str) -> Tuple[bool, Optional[str]]:
        """Remove variant from user's wishlist"""
        try:
            deleted_count, _ = Wishlist.objects.filter(user=user, variant_id=variant_id).delete()
            
            if deleted_count > 0:
                logger.info(f"Removed variant {variant_id} from wishlist for user {user.email}")
                return True, None
            else:
                return False, "Item not found in wishlist"
                
        except Exception as e:
            logger.error(f"Wishlist remove error: {str(e)}")
            return False, f"Failed to remove from wishlist: {str(e)}"


class AdminProductService:
    """Admin product management business logic - writes only"""
    
    @staticmethod
    @transaction.atomic
    def create_product(data: Dict[str, Any], user: User) -> Tuple[Optional[Product], Optional[Dict]]:
        """Create a new product (admin only)"""
        try:
            # Validate category exists
            category = get_category_by_id(data["category_id"])
            if not category:
                return None, {"category_id": "Category not found"}
            
            # Generate slug from title
            base_slug = slugify(data["title"])
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            # Create product
            product = Product.objects.create(
                title=data["title"],
                slug=slug,
                description=data["description"],
                category=category,
                features=data.get("features", []),
                options=data.get("options", {}),
                status=data.get("status", Product.STATUS_DRAFT),
                is_featured=data.get("is_featured", False),
                is_bestseller=data.get("is_bestseller", False),
                is_new=data.get("is_new", False),
                meta_title=data.get("meta_title", ""),
                meta_description=data.get("meta_description", ""),
                published_at=timezone.now() if data.get("status") == Product.STATUS_PUBLISHED else None,
            )
            
            logger.info(f"Product created by admin {user.email}: {product.title}")
            return product, None
            
        except Exception as e:
            logger.error(f"Admin product creation error: {str(e)}")
            return None, {"general": "Failed to create product"}
    
    @staticmethod
    @transaction.atomic
    def update_product(product_id: str, data: Dict[str, Any], user: User) -> Tuple[Optional[Product], Optional[Dict]]:
        """Update product (admin only)"""
        try:
            product = get_product_by_id(product_id, include_inactive=True)
            if not product:
                return None, {"product": "Product not found"}
            
            # Update fields
            for field in ["title", "description", "status", "is_featured", "is_bestseller", "is_new", "meta_title", "meta_description", "features", "options"]:
                if field in data:
                    setattr(product, field, data[field])
            
            # Update category if provided
            if "category_id" in data and data["category_id"]:
                category = get_category_by_id(data["category_id"])
                if not category:
                    return None, {"category_id": "Category not found"}
                product.category = category
            elif "category_id" in data and data["category_id"] is None:
                product.category = None
            
            # Update slug if title changed
            if "title" in data and data["title"] != product.title:
                base_slug = slugify(data["title"])
                slug = base_slug
                counter = 1
                while Product.objects.filter(slug=slug).exclude(id=product.id).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                product.slug = slug
            
            # Update published_at if status changed to published
            if product.status == Product.STATUS_PUBLISHED and not product.published_at:
                product.published_at = timezone.now()
            
            product.save()
            
            logger.info(f"Product updated by admin {user.email}: {product.title}")
            return product, None
            
        except Exception as e:
            logger.error(f"Admin product update error: {str(e)}")
            return None, {"general": "Failed to update product"}
    
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
                        return None, {f"attributes.{option_key}": f'Option "{option_key}" not allowed for this product'}
            
            # Handle default variant
            is_default = data.get("is_default", False)
            if is_default:
                ProductVariant.objects.filter(product=product, is_default=True).update(is_default=False)
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
                        alt_text = data.get("image_alt_texts", [])[i] if data.get("image_alt_texts") and i < len(data.get("image_alt_texts", [])) else f"{product.title} - {variant.sku}"
                        
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
    def update_variant(variant_id: str, data: Dict[str, Any], user: User) -> Tuple[Optional[ProductVariant], Optional[Dict]]:
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
                ProductVariant.objects.filter(product=variant.product, is_default=True).update(is_default=False)
            
            # Update fields
            for field in ["sku", "price", "discount_amount", "stock", "is_default", "is_active", "weight", "height", "width", "depth", "low_stock_threshold", "attributes"]:
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
                logger.info(f"Image added to variant {variant.sku} by admin {user.email}")
            
            return image, None
            
        except Exception as e:
            logger.error(f"Admin image upload error: {str(e)}")
            return None, {"general": "Failed to upload image"}
        
        
class ProductAnalyticsService(BaseAnalyticsService):
    """Optimized product analytics service"""
    
    def __init__(self):
        super().__init__(app_name='products', cache_timeout=300)
    
    def get_card_data(self, request) -> List[Dict]:
        """Get card data using optimized single-query aggregations"""
        
        # Single query for all product counts
        from django.db.models import Count, Q
        
        product_aggregates = Product.objects.aggregate(
            total=Count('id'),
            published=Count('id', filter=Q(status=Product.STATUS_PUBLISHED)),
            draft=Count('id', filter=Q(status=Product.STATUS_DRAFT)),
            archived=Count('id', filter=Q(status=Product.STATUS_ARCHIVED)),
            featured=Count('id', filter=Q(is_featured=True)),
            bestseller=Count('id', filter=Q(is_bestseller=True)),
            new=Count('id', filter=Q(
                created_at__gte=timezone.now() - timedelta(days=30)
            )),
            missing_variants=Count('id', filter=Q(variants__isnull=True))
        )
        
        # Single query for variant metrics
        variant_aggregates = ProductVariant.objects.aggregate(
            total_variants=Count('id'),
            total_stock=Sum('stock'),
            low_stock=Count('id', filter=Q(stock__lte=F('low_stock_threshold'), stock__gt=0)),
            out_of_stock=Count('id', filter=Q(stock=0)),
            inventory_value=Sum(F('price') * F('stock'))
        )
        
        # Single query for category metrics
        category_aggregates = Category.objects.aggregate(
            active_categories=Count('id', filter=Q(is_active=True, is_hidden=False))
        )
        
        # Rating average
        rating_avg = ProductReview.objects.filter(is_approved=True).aggregate(
            avg_rating=Avg('rating')
        )['avg_rating'] or 0
        
        return [
            {"id": "total_products", "name": "Total Products", "value": product_aggregates['total'] or 0, "unit": "", "critical": False},
            {"id": "published_products", "name": "Published", "value": product_aggregates['published'] or 0, "unit": "", "critical": False},
            {"id": "draft_products", "name": "Draft", "value": product_aggregates['draft'] or 0, "unit": "", "critical": product_aggregates['draft'] > 10},
            {"id": "archived_products", "name": "Archived", "value": product_aggregates['archived'] or 0, "unit": "", "critical": False},
            {"id": "total_variants", "name": "Total Variants", "value": variant_aggregates['total_variants'] or 0, "unit": "", "critical": False},
            {"id": "total_stock", "name": "Total Stock", "value": variant_aggregates['total_stock'] or 0, "unit": "units", "critical": (variant_aggregates['total_stock'] or 0) < 100},
            {"id": "low_stock_variants", "name": "Low Stock", "value": variant_aggregates['low_stock'] or 0, "unit": "variants", "critical": (variant_aggregates['low_stock'] or 0) > 5},
            {"id": "out_of_stock", "name": "Out of Stock", "value": variant_aggregates['out_of_stock'] or 0, "unit": "variants", "critical": (variant_aggregates['out_of_stock'] or 0) > 10},
            {"id": "featured_products", "name": "Featured", "value": product_aggregates['featured'] or 0, "unit": "", "critical": False},
            {"id": "bestseller_products", "name": "Bestsellers", "value": product_aggregates['bestseller'] or 0, "unit": "", "critical": False},
            {"id": "new_products", "name": "New (30 days)", "value": product_aggregates['new'] or 0, "unit": "", "critical": False},
            {"id": "inventory_value", "name": "Inventory Value", "value": round(variant_aggregates['inventory_value'] or 0, 2), "unit": "$", "critical": False},
            {"id": "products_without_variants", "name": "Missing Variants", "value": product_aggregates['missing_variants'] or 0, "unit": "", "critical": (product_aggregates['missing_variants'] or 0) > 5},
            {"id": "avg_rating", "name": "Average Rating", "value": round(rating_avg, 1), "unit": "★", "critical": rating_avg < 3.5},
            {"id": "active_categories", "name": "Active Categories", "value": category_aggregates['active_categories'] or 0, "unit": "", "critical": False},
        ]
    
    def get_chart_data(self, request, chart_type: str = None) -> Dict:
        """Get all chart data with optimized queries"""
        
        charts = {}
        
        # Only fetch requested chart type if specified
        if chart_type and chart_type != 'all':
            method_name = f"_get_{chart_type}_chart"
            if hasattr(self, method_name):
                charts[chart_type] = getattr(self, method_name)()
        else:
            # Fetch all charts (use caching)
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
        
        return charts
    
    def _get_monthly_trend_chart(self) -> Dict:
        """Get monthly product creation trend using time series aggregation"""
        six_months_ago = timezone.now() - timedelta(days=180)
        
        time_series = AggregatedMetrics.get_time_series(
            queryset=Product.objects.filter(created_at__gte=six_months_ago),
            date_field='created_at',
            group_by='month',
            value_field='id',
            aggregation='count'
        )
        
        data = [
            {
                "month": item['period'].strftime("%b") if item['period'] else "Unknown",
                "products": item['value'],
                "full_date": item['period'].isoformat() if item['period'] else None
            }
            for item in time_series
        ]
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.AREA,
                title="Product Creation Trend",
                description="Number of products created per month",
                data_key="products",
                color="hsl(var(--chart-1))"
            )
        )
    
    def _get_category_chart(self) -> Dict:
        """Get products by category - optimized with single query"""
        categories = Category.objects.filter(
            is_hidden=False
        ).annotate(
            product_count=Count('products', filter=Q(products__status=Product.STATUS_PUBLISHED))
        ).filter(product_count__gt=0).order_by('-product_count')[:10]
        
        data = [
            {"category": cat.name, "products": cat.product_count}
            for cat in categories
        ]
        
        # Add colors
        data = ColorPalette.add_colors_to_data(data, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Products by Category",
                description="Top categories by product count",
                data_key="products"
            )
        )
    
    def _get_status_chart(self) -> Dict:
        """Get product status distribution - from cached aggregates"""
        status_counts = Product.objects.aggregate(
            published=Count('id', filter=Q(status=Product.STATUS_PUBLISHED)),
            draft=Count('id', filter=Q(status=Product.STATUS_DRAFT)),
            archived=Count('id', filter=Q(status=Product.STATUS_ARCHIVED))
        )
        
        data = [
            {"status": "Published", "count": status_counts['published'] or 0},
            {"status": "Draft", "count": status_counts['draft'] or 0},
            {"status": "Archived", "count": status_counts['archived'] or 0},
        ]
        
        data = ColorPalette.add_colors_to_data(data, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.PIE,
                title="Product Status",
                description="Distribution by publication status",
                data_key="count"
            )
        )
    
    def _get_stock_chart(self) -> Dict:
        """Get stock distribution - optimized with conditional aggregation"""
        total_variants = ProductVariant.objects.count() or 1
        
        stock_stats = ProductVariant.objects.aggregate(
            in_stock=Count('id', filter=Q(stock__gt=10)),
            low_stock=Count('id', filter=Q(stock__lte=10, stock__gt=0)),
            out_of_stock=Count('id', filter=Q(stock=0))
        )
        
        data = [
            {
                "status": "In Stock (>10)",
                "count": stock_stats['in_stock'] or 0,
                "percentage": round((stock_stats['in_stock'] or 0) / total_variants * 100, 1)
            },
            {
                "status": "Low Stock (1-10)",
                "count": stock_stats['low_stock'] or 0,
                "percentage": round((stock_stats['low_stock'] or 0) / total_variants * 100, 1)
            },
            {
                "status": "Out of Stock",
                "count": stock_stats['out_of_stock'] or 0,
                "percentage": round((stock_stats['out_of_stock'] or 0) / total_variants * 100, 1)
            }
        ]
        
        data = ColorPalette.add_colors_to_data(data, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.DONUT,
                title="Stock Distribution",
                description="Variants by stock availability",
                data_key="count"
            )
        )
    
    def _get_weekly_chart(self) -> Dict:
        """Get weekly activity - last 7 days"""
        seven_days_ago = timezone.now() - timedelta(days=7)
        
        daily_activity = Product.objects.filter(
            created_at__gte=seven_days_ago
        ).extra(
            {'day': "DATE(created_at)"}
        ).values('day').annotate(
            created=Count('id'),
            published=Count('id', filter=Q(status=Product.STATUS_PUBLISHED))
        ).order_by('day')
        
        # Create a dict for quick lookup
        activity_dict = {item['day']: item for item in daily_activity}
        
        # Generate last 7 days
        data = []
        for i in range(7):
            day = (timezone.now() - timedelta(days=6-i)).date()
            day_activity = activity_dict.get(day, {})
            data.append({
                "day": day.strftime("%a"),
                "created": day_activity.get('created', 0),
                "published": day_activity.get('published', 0)
            })
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config={
                "title": "Weekly Activity",
                "description": "Last 7 days product activity",
                "type": ChartConfig.BAR,
                "config": {
                    "created": {"label": "Created", "color": "hsl(var(--chart-1))"},
                    "published": {"label": "Published", "color": "hsl(var(--chart-2))"}
                }
            }
        )
    
    def _get_top_products_chart(self) -> Dict:
        """Get top products by inventory value - limited to 10"""
        top_products = ProductVariant.objects.values(
            'product__id', 'product__title'
        ).annotate(
            total_value=Sum(F('price') * F('stock'))
        ).order_by('-total_value')[:10]
        
        data = [
            {"product": item['product__title'][:30], "value": round(float(item['total_value'] or 0), 2)}
            for item in top_products
        ]
        
        data = ColorPalette.add_colors_to_data(data, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Top Products by Value",
                description="Highest inventory value products",
                data_key="value"
            )
        )
    
    def _get_rating_chart(self) -> Dict:
        """Get rating distribution"""
        ratings = []
        for rating in range(1, 6):
            count = ProductReview.objects.filter(
                rating=rating, is_approved=True
            ).count()
            ratings.append({
                "rating": f"{rating} ★",
                "count": count
            })
        
        ratings = ColorPalette.add_colors_to_data(ratings, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=ratings,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Customer Ratings",
                description="Distribution of product reviews",
                data_key="count"
            )
        )
    
    def _get_flags_chart(self) -> Dict:
        """Get products by flag status"""
        flag_counts = Product.objects.aggregate(
            featured=Count('id', filter=Q(is_featured=True)),
            bestseller=Count('id', filter=Q(is_bestseller=True)),
            new=Count('id', filter=Q(is_new=True))
        )
        
        data = [
            {"flag": "Featured", "count": flag_counts['featured'] or 0},
            {"flag": "Bestseller", "count": flag_counts['bestseller'] or 0},
            {"flag": "New Arrival", "count": flag_counts['new'] or 0}
        ]
        
        data = ColorPalette.add_colors_to_data(data, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Product Highlights",
                description="Products with special flags",
                data_key="count"
            )
        )
    
    def _get_visibility_chart(self) -> Dict:
        """Get category visibility distribution"""
        visibility_counts = Category.objects.aggregate(
            visible=Count('id', filter=Q(is_hidden=False, is_active=True)),
            hidden=Count('id', filter=Q(is_hidden=True))
        )
        
        data = [
            {"status": "Visible", "count": visibility_counts['visible'] or 0},
            {"status": "Hidden", "count": visibility_counts['hidden'] or 0}
        ]
        
        data = ColorPalette.add_colors_to_data(data, key='fill')
        
        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.PIE,
                title="Category Visibility",
                description="Hidden vs visible categories",
                data_key="count"
            )
        )


# Singleton instance
product_analytics_service = ProductAnalyticsService()
