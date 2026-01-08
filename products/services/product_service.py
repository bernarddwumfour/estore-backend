"""
products/services/product_service.py

Product business logic service - COMPLETE VERSION
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from django.db.models import Q
from django.db import transaction
from django.core.paginator import Paginator

from products.models import VariantImage
from ..models import Product, ProductVariant, Category, ProductReview, Wishlist
from users.models import User

logger = logging.getLogger(__name__)


class ProductService:
    """Product business logic"""

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
    ) -> Tuple[List[Dict], int, Dict]:
        """Get filtered and paginated products"""

        queryset = Product.objects.filter(status=Product.STATUS_PUBLISHED)
        
        descendant_categories= None

        if category_slug:
            descendant_categories = Category.get_descendants_from_slug(category_slug)
    
        if descendant_categories:
            # Get all descendant category IDs
            category_ids = [cat.id for cat in descendant_categories]
            queryset = queryset.filter(category_id__in=category_ids)
        
            
        if brand:
            queryset = queryset.filter(variants__attributes__brand=brand).distinct()

        if min_price is not None:
            queryset = queryset.filter(variants__price__gte=min_price).distinct()

        if max_price is not None:
            queryset = queryset.filter(variants__price__lte=max_price).distinct()

        if in_stock is True:
            queryset = queryset.filter(variants__stock__gt=0).distinct()
        elif in_stock is False:
            queryset = queryset.filter(variants__stock=0).distinct()

        if featured:
            queryset = queryset.filter(is_featured=True)

        if bestseller:
            queryset = queryset.filter(is_bestseller=True)

        if new:
            queryset = queryset.filter(is_new=True)

        # Search
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(slug__icontains=search)
            )

        # Sorting
        sort_mapping = {
            "price_asc": "variants__price",
            "price_desc": "-variants__price",
            "rating": "-average_rating",
            "newest": "-created_at",
            "name_asc": "title",
            "name_desc": "-title",
        }

        sort_field = sort_mapping.get(sort_by, "-created_at")
        queryset = queryset.order_by(sort_field).distinct()

        # Pagination
        paginator = Paginator(queryset, limit)
        page_obj = paginator.get_page(page)

        # Prepare response data
        products_data = []
        for product in page_obj:
            default_variant = product.default_variant

            products_data.append(
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
                                str(product.category.id) if product.category else None
                            ),
                            "name": product.category.name if product.category else None,
                            "slug": product.category.slug if product.category else None,
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
                            "sku": default_variant.sku if default_variant else None,
                            "id": default_variant.id if default_variant else None,
                            "price": (
                                float(default_variant.price)
                                if default_variant
                                else None
                            ),
                            "discounted_price": (
                                float(default_variant.discounted_price)
                                if default_variant
                                else None
                            ),
                            "stock": default_variant.stock if default_variant else 0,
                            "attributes": (
                                default_variant.attributes if default_variant else {}
                            ),
                            "images": [
                                {
                                    "url": img.image.url,
                                    "alt_text": img.alt_text,
                                    "type": img.image_type,
                                }
                                for img in default_variant.images.order_by("order")
                            ],
                        }
                        if default_variant
                        else None
                    ),
                    "created_at": product.created_at.isoformat(),
                }
            )

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

        return products_data, paginator.count, filters

    @staticmethod
    def get_product_detail(slug: str) -> Optional[Dict]:
        """Get detailed product information"""
        try:
            product = Product.objects.get(slug=slug, status=Product.STATUS_PUBLISHED)

            print(list(VariantImage.objects.values()))

            # Get all variants with images
            variants_data = []
            for variant in product.variants.filter(is_active=True):
                variants_data.append(
                    {
                        "id": str(variant.id),
                        "sku": variant.sku,
                        "attributes": variant.attributes,
                        "price": float(variant.price),
                        "discount_amount": float(variant.discount_amount),
                        "discounted_price": float(variant.discounted_price),
                        "discount_percentage": float(variant.discount_percentage),
                        "stock": variant.stock,
                        "is_default": variant.is_default,
                        "is_in_stock": variant.is_in_stock,
                        "is_low_stock": variant.is_low_stock,
                        "images": [
                            {
                                "url": img.image.url,
                                "alt_text": img.alt_text,
                                "type": img.image_type,
                            }
                            for img in variant.images.order_by("order")
                        ],
                        "dimensions": {
                            "weight": float(variant.weight) if variant.weight else None,
                            "height": float(variant.height) if variant.height else None,
                            "width": float(variant.width) if variant.width else None,
                            "depth": float(variant.depth) if variant.depth else None,
                        },
                    }
                )

            # Get related products (same category)
            related_products = []
            if product.category:
                related = Product.objects.filter(
                    category=product.category, status=Product.STATUS_PUBLISHED
                ).exclude(id=product.id)[:4]

                for related_product in related:
                    default_variant = related_product.default_variant
                    related_products.append(
                        {
                            "id": str(related_product.id),
                            "title": related_product.title,
                            "slug": related_product.slug,
                            "description": (
                                related_product.description[:200] + "..."
                                if len(related_product.description) > 200
                                else related_product.description
                            ),
                            "category": (
                                {
                                    "id": (
                                        str(related_product.category.id)
                                        if related_product.category
                                        else None
                                    ),
                                    "name": (
                                        related_product.category.name
                                        if related_product.category
                                        else None
                                    ),
                                    "slug": (
                                        related_product.category.slug
                                        if related_product.category
                                        else None
                                    ),
                                }
                                if related_product.category
                                else None
                            ),
                            "features": related_product.features,
                            "options": related_product.options,
                            "min_price": float(related_product.min_price),
                            "max_price": float(related_product.max_price),
                            "average_rating": float(related_product.average_rating),
                            "total_reviews": related_product.total_reviews,
                            "total_stock": related_product.total_stock,
                            "has_stock": related_product.has_stock,
                            "is_featured": related_product.is_featured,
                            "is_bestseller": related_product.is_bestseller,
                            "is_new": related_product.is_new,
                            "default_variant": (
                                {
                                    "sku": (
                                        default_variant.sku if default_variant else None
                                    ),
                                    "price": (
                                        float(default_variant.price)
                                        if default_variant
                                        else None
                                    ),
                                    "discounted_price": (
                                        float(default_variant.discounted_price)
                                        if default_variant
                                        else None
                                    ),
                                    "stock": (
                                        default_variant.stock if default_variant else 0
                                    ),
                                    "attributes": (
                                        default_variant.attributes
                                        if default_variant
                                        else {}
                                    ),
                                    "images": [
                                        {
                                            "url": img.image.url,
                                            "alt_text": img.alt_text,
                                            "type": img.image_type,
                                        }
                                        for img in default_variant.images.order_by(
                                            "order"
                                        )
                                    ],
                                }
                                if default_variant
                                else None
                            ),
                            "created_at": related_product.created_at.isoformat(),
                        }
                    )

            product_data = {
                "id": str(product.id),
                "title": product.title,
                "slug": product.slug,
                "description": product.description,
                "meta_title": product.meta_title,
                "meta_description": product.meta_description,
                "category": (
                    {
                        "id": str(product.category.id) if product.category else None,
                        "name": product.category.name if product.category else None,
                        "slug": product.category.slug if product.category else None,
                    }
                    if product.category
                    else None
                ),
                "features": product.features,
                "options": product.options,
                "average_rating": float(product.average_rating),
                "total_reviews": product.total_reviews,
                "is_featured": product.is_featured,
                "is_bestseller": product.is_bestseller,
                "is_new": product.is_new,
                "variants": variants_data,
                "related_products": related_products,
                "created_at": product.created_at.isoformat(),
                "published_at": (
                    product.published_at.isoformat() if product.published_at else None
                ),
            }

            return product_data

        except Product.DoesNotExist:
            return None

    @staticmethod
    def get_variant_detail(variant_id: str) -> Optional[Dict]:
        """Get detailed variant information"""
        try:
            variant = ProductVariant.objects.get(
                id=variant_id, is_active=True, product__status=Product.STATUS_PUBLISHED
            )

            variant_data = {
                "id": str(variant.id),
                "sku": variant.sku,
                "product": {
                    "id": str(variant.product.id),
                    "title": variant.product.title,
                    "slug": variant.product.slug,
                },
                "attributes": variant.attributes,
                "price": float(variant.price),
                "discount_amount": float(variant.discount_amount),
                "discounted_price": float(variant.discounted_price),
                "discount_percentage": float(variant.discount_percentage),
                "stock": variant.stock,
                "is_default": variant.is_default,
                "is_in_stock": variant.is_in_stock,
                "is_low_stock": variant.is_low_stock,
                "images": [
                    {
                        "id": str(img.id),
                        "url": img.image.url,
                        "alt_text": img.alt_text,
                        "type": img.image_type,
                        "order": img.order,
                    }
                    for img in variant.images.filter(is_active=True).order_by("order")
                ],
                "dimensions": {
                    "weight": float(variant.weight) if variant.weight else None,
                    "height": float(variant.height) if variant.height else None,
                    "width": float(variant.width) if variant.width else None,
                    "depth": float(variant.depth) if variant.depth else None,
                },
                "created_at": variant.created_at.isoformat(),
            }

            return variant_data

        except ProductVariant.DoesNotExist:
            return None

    @staticmethod
    def get_categories() -> List[Dict]:
        """Get all active categories"""
        categories = Category.objects.filter(is_active=True)

        categories_data = []
        for category in categories:
            # Count products in category
            product_count = Product.objects.filter(category=category).count()

            categories_data.append(
                {
                    "id": str(category.id),
                    "name": category.name,
                    "slug": category.slug,
                    "description": category.description,
                    "parent_id": str(category.parent.id) if category.parent else None,
                    "parent_name": category.parent.name if category.parent else None,
                    "image": category.image.url if category.image else None,
                    "product_count": product_count,
                    "full_path": category.full_path,
                }
            )

        return categories_data

    @staticmethod
    def get_category_detail(slug: str) -> Optional[Dict]:
        """Get detailed category information"""
        try:
            category = Category.objects.get(slug=slug, is_active=True)

            # Get subcategories
            subcategories = Category.objects.filter(parent=category, is_active=True)
            subcategories_data = [
                {
                    "id": str(sub.id),
                    "name": sub.name,
                    "slug": sub.slug,
                    "product_count": Product.objects.filter(
                        category=sub, status=Product.STATUS_PUBLISHED
                    ).count(),
                }
                for sub in subcategories
            ]

            category_data = {
                "id": str(category.id),
                "name": category.name,
                "slug": category.slug,
                "description": category.description,
                "parent": (
                    {
                        "id": str(category.parent.id),
                        "name": category.parent.name,
                        "slug": category.parent.slug,
                    }
                    if category.parent
                    else None
                ),
                "image": category.image.url if category.image else None,
                "subcategories": subcategories_data,
                "full_path": category.full_path,
                "meta_title": category.meta_title,
                "meta_description": category.meta_description,
            }

            return category_data

        except Category.DoesNotExist:
            return None


class ReviewService:
    """Product review business logic"""

    @staticmethod
    def get_product_reviews(
        product_slug: str,
        page: int = 1,
        limit: int = 20,
        rating: int = None,
        verified: bool = None,
    ) -> Tuple[List[Dict], int]:
        """Get product reviews"""
        try:
            product = Product.objects.get(slug=product_slug)
        except Product.DoesNotExist:
            return [], 0

        queryset = ProductReview.objects.filter(product=product, is_approved=True)

        if rating:
            queryset = queryset.filter(rating=rating)

        if verified is not None:
            queryset = queryset.filter(is_verified_purchase=verified)

        queryset = queryset.order_by("-created_at")

        paginator = Paginator(queryset, limit)
        page_obj = paginator.get_page(page)

        reviews_data = []
        for review in page_obj:
            # Get user display name
            user_display_name = ""
            if review.user.first_name and review.user.last_name:
                user_display_name = f"{review.user.first_name} {review.user.last_name}"
            else:
                user_display_name = review.user.email.split("@")[0]

            # Get user initials for avatar
            user_initials = ""
            if review.user.first_name and review.user.last_name:
                user_initials = (
                    f"{review.user.first_name[0]}{review.user.last_name[0]}".upper()
                )
            else:
                user_initials = review.user.email[0].upper()

            reviews_data.append(
                {
                    "id": str(review.id),
                    "user": {
                        "id": str(review.user.id),
                        "name": user_display_name,
                        "initials": user_initials,
                        "is_verified_purchase": review.is_verified_purchase,
                    },
                    "rating": review.rating,
                    "title": review.title,
                    "comment": review.comment,
                    "helpful_yes": review.helpful_yes,
                    "helpful_no": review.helpful_no,
                    "is_edited": review.is_edited,
                    "created_at": review.created_at.isoformat(),
                    "updated_at": review.updated_at.isoformat(),
                }
            )

        return reviews_data, paginator.count

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
            product = Product.objects.get(slug=product_slug)

            # Check if user already reviewed this product
            if ProductReview.objects.filter(product=product, user=user).exists():
                return None, {"review": "You have already reviewed this product"}

            # Validate rating
            if not 1 <= rating <= 5:
                return None, {"rating": "Rating must be between 1 and 5"}

            # Create review
            review = ProductReview.objects.create(
                product=product,
                user=user,
                rating=rating,
                title=title,
                comment=comment,
                is_verified_purchase=is_verified_purchase,
            )

            logger.info(
                f"Review created for product {product_slug} by user {user.email}"
            )
            return review, None

        except Product.DoesNotExist:
            return None, {"product": "Product not found"}
        except Exception as e:
            logger.error(f"Error creating review: {str(e)}")
            return None, {"general": "Failed to create review"}


class WishlistService:
    """Wishlist business logic"""

    @staticmethod
    def get_user_wishlist(
        user: User, page: int = 1, limit: int = 20
    ) -> Tuple[List[Dict], int]:
        """Get user's wishlist items"""
        wishlist_items = Wishlist.objects.filter(user=user)
        total = wishlist_items.count()

        # Paginate
        offset = (page - 1) * limit
        items = wishlist_items.order_by("-created_at")[offset : offset + limit]

        items_data = []
        for item in items:
            variant = item.variant

            # Get first image for variant
            image_url = None
            if variant.images.exists():
                image_url = variant.images.first().image.url

            items_data.append(
                {
                    "id": str(item.id),
                    "variant": {
                        "id": str(variant.id),
                        "sku": variant.sku,
                        "product_title": variant.product.title,
                        "product_slug": variant.product.slug,
                        "price": float(variant.price),
                        "discounted_price": float(variant.discounted_price),
                        "discount_percentage": float(variant.discount_percentage),
                        "stock": variant.stock,
                        "is_in_stock": variant.is_in_stock,
                        "image": image_url,
                    },
                    "added_at": item.created_at.isoformat(),
                }
            )

        return items_data, total

    @staticmethod
    @transaction.atomic
    def add_to_wishlist(user: User, variant_id: str) -> Tuple[bool, Optional[str]]:
        """Add variant to user's wishlist"""
        try:
            variant = ProductVariant.objects.get(id=variant_id, is_active=True)

            # Check if already in wishlist
            if Wishlist.objects.filter(user=user, variant=variant).exists():
                return False, "Item already in wishlist"

            # Add to wishlist
            Wishlist.objects.create(user=user, variant=variant)

            logger.info(f"Added {variant.sku} to wishlist for user {user.email}")
            return True, None

        except ProductVariant.DoesNotExist:
            return False, "Variant not found"
        except Exception as e:
            logger.error(f"Error adding to wishlist: {str(e)}")
            return False, "Failed to add to wishlist"

    @staticmethod
    @transaction.atomic
    def remove_from_wishlist(user: User, variant_id: str) -> Tuple[bool, Optional[str]]:
        """Remove variant from user's wishlist"""
        try:
            deleted_count, _ = Wishlist.objects.filter(
                user=user, variant_id=variant_id
            ).delete()

            if deleted_count > 0:
                logger.info(
                    f"Removed variant {variant_id} from wishlist for user {user.email}"
                )
                return True, None
            else:
                return False, "Item not found in wishlist"

        except Exception as e:
            logger.error(f"Error removing from wishlist: {str(e)}")
            return False, "Failed to remove from wishlist"

    @staticmethod
    def is_in_wishlist(user: User, variant_id: str) -> bool:
        """Check if variant is in user's wishlist"""
        return Wishlist.objects.filter(user=user, variant_id=variant_id).exists()


class SearchService:
    """Product search business logic"""

    @staticmethod
    def search_products(
        query: str,
        page: int = 1,
        limit: int = 20,
        category_slug: str = None,
        min_price: float = None,
        max_price: float = None,
        in_stock: bool = None,
    ) -> Tuple[List[Dict], int, Dict]:
        """Search products with filters"""

        # Base queryset
        queryset = Product.objects.filter(status=Product.STATUS_PUBLISHED)

        # Search query
        if query and len(query) >= 2:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(slug__icontains=query)
                | Q(variants__sku__icontains=query)
                | Q(variants__attributes__icontains=query)
            ).distinct()

        # Additional filters
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        if min_price is not None:
            queryset = queryset.filter(variants__price__gte=min_price).distinct()

        if max_price is not None:
            queryset = queryset.filter(variants__price__lte=max_price).distinct()

        if in_stock is True:
            queryset = queryset.filter(variants__stock__gt=0).distinct()
        elif in_stock is False:
            queryset = queryset.filter(variants__stock=0).distinct()

        # Order by relevance (simple implementation)
        queryset = queryset.order_by("-is_featured", "-average_rating", "-created_at")

        # Pagination
        paginator = Paginator(queryset, limit)
        page_obj = paginator.get_page(page)

        # Prepare response data
        products_data = []
        for product in page_obj:
            default_variant = product.default_variant

            products_data.append(
                {
                    "id": str(product.id),
                    "title": product.title,
                    "slug": product.slug,
                    "description": (
                        product.description[:150] + "..."
                        if len(product.description) > 150
                        else product.description
                    ),
                    "category": product.category.name if product.category else None,
                    "min_price": float(product.min_price),
                    "max_price": float(product.max_price),
                    "average_rating": float(product.average_rating),
                    "has_stock": product.has_stock,
                    "default_variant": (
                        {
                            "sku": default_variant.sku if default_variant else None,
                            "price": (
                                float(default_variant.price)
                                if default_variant
                                else None
                            ),
                            "discounted_price": (
                                float(default_variant.discounted_price)
                                if default_variant
                                else None
                            ),
                            "image": (
                                default_variant.images.first().image.url
                                if default_variant and default_variant.images.first()
                                else None
                            ),
                        }
                        if default_variant
                        else None
                    ),
                }
            )

        # Build filters metadata
        filters = {"query": query}
        if category_slug:
            filters["category"] = category_slug
        if min_price is not None:
            filters["min_price"] = min_price
        if max_price is not None:
            filters["max_price"] = max_price
        if in_stock is not None:
            filters["in_stock"] = in_stock

        return products_data, paginator.count, filters


class AdminProductService:
    """Admin product management business logic"""

    @staticmethod
    @transaction.atomic
    def create_product(
        data: Dict[str, Any], user: User
    ) -> Tuple[Optional[Product], Optional[Dict]]:
        """Create a new product (admin only)"""
        try:
            # Validate required fields
            required_fields = ["title", "description", "category_id"]
            errors = {}
            for field in required_fields:
                if field not in data or not data[field]:
                    errors[field] = "This field is required"

            if errors:
                return None, errors

            # Validate category exists
            try:
                category = Category.objects.get(id=data["category_id"])
            except Category.DoesNotExist:
                return None, {"category_id": "Category not found"}

            # Generate slug from title
            from django.utils.text import slugify

            slug = slugify(data["title"])

            # Ensure slug is unique
            counter = 1
            original_slug = slug
            while Product.objects.filter(slug=slug).exists():
                slug = f"{original_slug}-{counter}"
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
            )

            logger.info(
                f"Product created by admin {user.email}: {product.title} (ID: {product.id})"
            )
            return product, None

        except Exception as e:
            logger.error(f"Admin product creation error: {str(e)}")
            return None, {"general": "Failed to create product"}

    @staticmethod
    @transaction.atomic
    def update_product(
        product_id: str, data: Dict[str, Any], user: User
    ) -> Tuple[Optional[Product], Optional[Dict]]:
        """Update product (admin only)"""
        try:
            product = Product.objects.get(id=product_id)

            # Update fields
            update_fields = [
                "title",
                "description",
                "status",
                "is_featured",
                "is_bestseller",
                "is_new",
                "meta_title",
                "meta_description",
                "features",
                "options",
            ]

            updated = False

            for field in update_fields:
                if field in data:
                    setattr(product, field, data[field])
                    updated = True

            # Update category if provided
            if "category_id" in data and data["category_id"]:
                try:
                    category = Category.objects.get(id=data["category_id"])
                    product.category = category
                    updated = True
                except Category.DoesNotExist:
                    return None, {"category_id": "Category not found"}

            if updated:
                product.save()
                logger.info(
                    f"Product updated by admin {user.email}: {product.title} (ID: {product.id})"
                )

            return product, None

        except Product.DoesNotExist:
            return None, {"product": "Product not found"}
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
            product = Product.objects.get(id=product_id)

            # Validate required fields
            required_fields = ["sku", "price", "attributes"]
            errors = {}
            for field in required_fields:
                if field not in data or not data[field]:
                    errors[field] = "This field is required"

            if errors:
                return None, errors

            # Check SKU uniqueness
            if ProductVariant.objects.filter(sku=data["sku"]).exists():
                return None, {"sku": "SKU already exists"}

            # Validate attributes match product options
            if product.options:
                for option_key in data["attributes"]:
                    if option_key not in product.options:
                        return None, {
                            f"attributes.{option_key}": f'Option "{option_key}" not allowed for this product'
                        }
                    
            default_variant =  ProductVariant.objects.get(product=product,is_default=True)
            if(default_variant):
                print("Product has a default variant")
                if data["is_default"]:
                    default_variant.is_default = False
                    default_variant.save()
            else:
                data["is_default"] = True


            # Create variant
            variant = ProductVariant.objects.create(
                product=product,
                sku=data["sku"],
                attributes=data["attributes"],
                price=data["price"],
                discount_amount=data.get("discount_amount", 0),
                stock=data.get("stock", 0),
                is_default=True if data.get("is_default") == "true" else False,
                weight=data.get("weight"),
                height=data.get("height"),
                width=data.get("width"),
                depth=data.get("depth"),
                low_stock_threshold=data.get("low_stock_threshold", 5),
            )

            # Add images if provided
            if image_files:
                print(f"Image files type: {type(image_files)}")
                print(f"Image files structure: {image_files}")

                # Extract files from MultiValueDict
                actual_image_files = []
                if hasattr(image_files, "getlist"):
                    # It's a MultiValueDict (like request.FILES)
                    if "images" in image_files:
                        actual_image_files = image_files.getlist("images")
                    else:
                        # Try to get any file list if key is different
                        for key in image_files.keys():
                            actual_image_files.extend(image_files.getlist(key))
                elif isinstance(image_files, list):
                    # Already a list
                    actual_image_files = image_files
                else:
                    # Single file or other structure
                    actual_image_files = [image_files]

                print(f"Actual images to process count: {len(actual_image_files)}")

                if actual_image_files:
                    created_images_count = 0
                    for i, image_file in enumerate(actual_image_files):
                        try:
                            # Skip if image_file is None or empty
                            if not image_file:
                                print(
                                    f"Skipping image at index {i} - file is empty or None"
                                )
                                continue

                            # Debug: Print image file info
                            print(f"Processing image {i}:")
                            print(f"  Type: {type(image_file)}")
                            print(f"  Class: {image_file.__class__.__name__}")
                            if hasattr(image_file, "name"):
                                print(f"  Name: {image_file.name}")
                            if hasattr(image_file, "size"):
                                print(f"  Size: {image_file.size} bytes")

                            # Determine image type
                            if i == 0:
                                image_type = "main"  # First image is main
                            else:
                                image_type = "gallery"

                            # Handle alt text
                            alt_text = None
                            if "image_alt_texts" in data and isinstance(
                                data["image_alt_texts"], list
                            ):
                                alt_text_list = data["image_alt_texts"]
                                if i < len(alt_text_list) and alt_text_list[i]:
                                    alt_text = alt_text_list[i]

                            # Use default alt text if not provided
                            if not alt_text:
                                alt_text = (
                                    f"{product.title} - {variant.sku} - Image {i+1}"
                                )

                            print(f"Creating VariantImage with alt_text: {alt_text}")

                            # Create image
                            VariantImage.objects.create(
                                variant=variant,
                                image=image_file,
                                image_type=image_type,
                                alt_text=alt_text,
                                order=i,
                                is_active=True,
                            )
                            created_images_count += 1
                            print(f"Successfully created image {i}")

                        except Exception as img_error:
                            print(f"Error creating image {i}: {str(img_error)}")
                            import traceback

                            print(f"Traceback: {traceback.format_exc()}")
                            logger.error(
                                f"Failed to add image {i} to variant {variant.sku}: {str(img_error)}",
                                exc_info=True,
                            )
                            # Continue with other images if one fails

                    print(
                        f"Total images created: {created_images_count}/{len(actual_image_files)}"
                    )
                else:
                    print("No actual image files found after extraction")
            else:
                print("No image files provided")

            logger.info(
                f"Variant created by admin {user.email}: {variant.sku} for product {product.title} with {created_images_count if 'created_images_count' in locals() else 0} images"
            )
            return variant, None

        except Product.DoesNotExist:
            return None, {"product": "Product not found"}
        except Exception as e:
            logger.error(f"Admin variant creation error: {str(e)}", exc_info=True)
            return None, {"general": f"Failed to create variant: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def update_variant(
        variant_id: str, data: Dict[str, Any], user: User
    ) -> Tuple[Optional[ProductVariant], Optional[Dict]]:
        """Update product variant (admin only)"""
        try:
            variant = ProductVariant.objects.get(id=variant_id)

            # Update fields
            update_fields = [
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
            ]

            updated = False

            for field in update_fields:
                if field in data:
                    setattr(variant, field, data[field])
                    updated = True

            # Validate SKU uniqueness if changed
            if "sku" in data and data["sku"] != variant.sku:
                if (
                    ProductVariant.objects.filter(sku=data["sku"])
                    .exclude(id=variant.id)
                    .exists()
                ):
                    return None, {"sku": "SKU already exists"}

            if updated:
                variant.save()
                logger.info(f"Variant updated by admin {user.email}: {variant.sku}")

            return variant, None

        except ProductVariant.DoesNotExist:
            return None, {"variant": "Variant not found"}
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
            variant = ProductVariant.objects.get(id=variant_id)

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
                order=VariantImage.objects.filter(
                    variant=variant
                ).count(),  # Auto-order
            )

            if user:
                logger.info(
                    f"Image added to variant {variant.sku} by admin {user.email}"
                )

            return image, None

        except ProductVariant.DoesNotExist:
            return None, {"variant": "Variant not found"}
        except Exception as e:
            logger.error(f"Admin image upload error: {str(e)}")
            return None, {"general": "Failed to upload image"}
