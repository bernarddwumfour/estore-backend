"""
Review Service - Business logic for product reviews
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction

from apps.products.models import ProductReview
from apps.products.selectors import get_product_by_slug, get_reviews_by_product
from apps.products.schemas import serialize_review
from apps.users.models import User

logger = logging.getLogger(__name__)


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

            logger.info(
                f"Review created for product {product_slug} by user {user.email}"
            )
            return review, None

        except Exception as e:
            logger.error(f"Error creating review: {str(e)}")
            return None, {"general": "Failed to create review"}