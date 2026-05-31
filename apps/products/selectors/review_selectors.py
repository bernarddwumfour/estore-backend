"""
Review Selectors - Database read operations for reviews
No business logic - just queries
"""

from typing import  List, Dict, Any, Tuple
from django.db.models import Avg
from django.core.paginator import Paginator
from apps.products.models import ProductReview
from .product_selectors import get_product_by_slug


# ==================== REVIEW SELECTORS ====================

def get_reviews_by_product(
    product_slug: str,
    page: int = 1,
    limit: int = 20,
    rating: int = None,
    verified: bool = None,
    only_approved: bool = True,
) -> Tuple[List[ProductReview], int]:
    """Get reviews for a product"""
    product = get_product_by_slug(product_slug)
    if not product:
        return [], 0

    queryset = ProductReview.objects.filter(product=product)

    if only_approved:
        queryset = queryset.filter(is_approved=True)

    if rating:
        queryset = queryset.filter(rating=rating)

    if verified is not None:
        queryset = queryset.filter(is_verified_purchase=verified)

    queryset = queryset.order_by("-created_at")

    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)

    return list(page_obj), paginator.count


def get_product_rating_stats(product_id: str) -> Dict[str, Any]:
    """Get rating statistics for a product"""
    reviews = ProductReview.objects.filter(product_id=product_id, is_approved=True)

    if not reviews.exists():
        return {
            "average": 0,
            "total": 0,
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        }

    distribution = {}
    for i in range(1, 6):
        distribution[i] = reviews.filter(rating=i).count()

    return {
        "average": float(reviews.aggregate(Avg("rating"))["avg"] or 0),
        "total": reviews.count(),
        "distribution": distribution,
    }