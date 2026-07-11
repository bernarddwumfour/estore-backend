"""
Review Selectors - Database read operations for product and order reviews
"""

from typing import List, Dict, Any, Tuple
from django.db.models import Q, Avg
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from itertools import chain
from apps.products.models import ProductReview, OrderReview
from .product_selectors import get_product_by_slug


def _order_review_queryset():
    return OrderReview.objects.select_related("order", "user").only(
        "id",
        "order_id",
        "user_id",
        "title",
        "comment",
        "overall_rating",
        "is_approved",
        "helpful_yes",
        "helpful_no",
        "admin_response",
        "admin_response_at",
        "created_at",
        "updated_at",
        "order__id",
        "order__order_number",
        "user__id",
        "user__email",
    )


def get_reviews_by_product(
    product_slug: str,
    page: int = 1,
    limit: int = 20,
    rating: int = None,
    verified: bool = None,
    only_approved: bool = True,
) -> Tuple[List[ProductReview], int]:
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
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return list(page_obj), paginator.count


def get_product_rating_stats(product_id: str) -> Dict[str, Any]:
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


def get_pending_product_reviews(
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[ProductReview], int]:
    queryset = ProductReview.objects.filter(
        is_approved=False
    ).select_related('product', 'user').order_by('-created_at')

    paginator = Paginator(queryset, limit)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return list(page_obj), paginator.count


def get_pending_order_reviews(
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[OrderReview], int]:
    queryset = _order_review_queryset().filter(
        is_approved=False
    ).order_by("-created_at")

    paginator = Paginator(queryset, limit)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return list(page_obj), paginator.count


def get_all_pending_reviews(
    page: int = 1,
    limit: int = 20,
) -> Tuple[List, int]:
    product_reviews = list(ProductReview.objects.filter(is_approved=False).select_related('product', 'user'))
    order_reviews = list(_order_review_queryset().filter(is_approved=False))

    all_reviews = list(chain(product_reviews, order_reviews))
    all_reviews.sort(key=lambda x: x.created_at, reverse=True)

    total = len(all_reviews)
    start = (page - 1) * limit
    end = start + limit
    paginated_reviews = all_reviews[start:end]

    return paginated_reviews, total


def get_reviews_by_order(
    order_id: str,
    page: int = 1,
    limit: int = 20,
    only_approved: bool = True,
) -> Tuple[List[OrderReview], int]:
    queryset = OrderReview.objects.filter(order_id=order_id)

    if only_approved:
        queryset = queryset.filter(is_approved=True)

    queryset = queryset.order_by("-created_at")

    paginator = Paginator(queryset, limit)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return list(page_obj), paginator.count


def get_all_product_reviews_admin(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    rating: int = None,
    verified: bool = None,
    product_id: str = None,
    user_id: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[ProductReview], int, Dict]:
    queryset = ProductReview.objects.select_related('product', 'user').all()
    
    if status == "approved":
        queryset = queryset.filter(is_approved=True)
    elif status == "pending":
        queryset = queryset.filter(is_approved=False)
    
    if rating:
        queryset = queryset.filter(rating=rating)
    
    if verified is not None:
        queryset = queryset.filter(is_verified_purchase=verified)
    
    if product_id:
        queryset = queryset.filter(product_id=product_id)
    
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    
    if search:
        queryset = queryset.filter(
            Q(product__title__icontains=search) |
            Q(user__email__icontains=search) |
            Q(comment__icontains=search) |
            Q(title__icontains=search)
        )
    
    sort_mapping = {
        "created_at": "created_at",
        "rating": "rating",
        "helpful_yes": "helpful_yes",
        "product_title": "product__title",
        "user_email": "user__email",
    }
    
    sort_field = sort_mapping.get(sort_by, "created_at")
    if sort_order == "desc":
        sort_field = f"-{sort_field}"
    
    queryset = queryset.order_by(sort_field)
    
    total = queryset.count()
    
    paginator = Paginator(queryset, limit)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
        page = 1
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "next_page": page + 1 if page_obj.has_next() else None,
        "previous_page": page - 1 if page_obj.has_previous() else None,
    }
    
    return list(page_obj), total, pagination_meta


def get_all_order_reviews_admin(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    rating: int = None,
    order_id: str = None,
    user_id: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[OrderReview], int, Dict]:
    queryset = _order_review_queryset().all()
    
    if status == "approved":
        queryset = queryset.filter(is_approved=True)
    elif status == "pending":
        queryset = queryset.filter(is_approved=False)
    
    if rating:
        queryset = queryset.filter(overall_rating=rating)
    
    if order_id:
        queryset = queryset.filter(order_id=order_id)
    
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    
    if search:
        queryset = queryset.filter(
            Q(order__order_number__icontains=search) |
            Q(user__email__icontains=search) |
            Q(comment__icontains=search) |
            Q(title__icontains=search)
        )
    
    sort_mapping = {
        "created_at": "created_at",
        "rating": "overall_rating",
        "helpful_yes": "helpful_yes",
        "order_number": "order__order_number",
        "user_email": "user__email",
    }
    
    sort_field = sort_mapping.get(sort_by, "created_at")
    if sort_order == "desc":
        sort_field = f"-{sort_field}"
    
    queryset = queryset.order_by(sort_field)
    
    total = queryset.count()
    
    paginator = Paginator(queryset, limit)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
        page = 1
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "next_page": page + 1 if page_obj.has_next() else None,
        "previous_page": page - 1 if page_obj.has_previous() else None,
    }
    
    return list(page_obj), total, pagination_meta


def get_all_reviews_admin(
    review_type: str = "all",
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    rating: int = None,
    verified: bool = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List, int, Dict]:
    product_reviews = []
    order_reviews = []
    
    if review_type in ["product", "all"]:
        product_qs = ProductReview.objects.select_related('product', 'user').all()
        
        if status == "approved":
            product_qs = product_qs.filter(is_approved=True)
        elif status == "pending":
            product_qs = product_qs.filter(is_approved=False)
        
        if rating:
            product_qs = product_qs.filter(rating=rating)
        
        if verified is not None:
            product_qs = product_qs.filter(is_verified_purchase=verified)
        
        if search:
            product_qs = product_qs.filter(
                Q(product__title__icontains=search) |
                Q(user__email__icontains=search) |
                Q(comment__icontains=search)
            )
        
        if sort_by == "rating":
            sort_field = "rating" if sort_order == "asc" else "-rating"
        elif sort_by == "helpful_yes":
            sort_field = "helpful_yes" if sort_order == "asc" else "-helpful_yes"
        else:
            sort_field = "created_at" if sort_order == "asc" else "-created_at"
        
        product_reviews = list(product_qs.order_by(sort_field))
    
    if review_type in ["order", "all"]:
        order_qs = _order_review_queryset().all()
        
        if status == "approved":
            order_qs = order_qs.filter(is_approved=True)
        elif status == "pending":
            order_qs = order_qs.filter(is_approved=False)
        
        if rating:
            order_qs = order_qs.filter(overall_rating=rating)
        
        if search:
            order_qs = order_qs.filter(
                Q(order__order_number__icontains=search) |
                Q(user__email__icontains=search) |
                Q(comment__icontains=search)
            )
        
        if sort_by == "rating":
            sort_field = "overall_rating" if sort_order == "asc" else "-overall_rating"
        elif sort_by == "helpful_yes":
            sort_field = "helpful_yes" if sort_order == "asc" else "-helpful_yes"
        else:
            sort_field = "created_at" if sort_order == "asc" else "-created_at"
        
        order_reviews = list(order_qs.order_by(sort_field))
    
    all_reviews = list(chain(product_reviews, order_reviews))
    
    if sort_by == "created_at":
        reverse = sort_order == "desc"
        all_reviews.sort(key=lambda x: x.created_at, reverse=reverse)
    
    total = len(all_reviews)
    
    start = (page - 1) * limit
    end = start + limit
    paginated_reviews = all_reviews[start:end]
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": (total + limit - 1) // limit if total > 0 else 0,
        "has_next": end < total,
        "has_previous": page > 1,
        "next_page": page + 1 if end < total else None,
        "previous_page": page - 1 if page > 1 else None,
    }
    
    return paginated_reviews, total, pagination_meta


def get_order_review_stats(order_id: str) -> Dict[str, Any]:
    reviews = OrderReview.objects.filter(order_id=order_id, is_approved=True)

    if not reviews.exists():
        return {
            "average_rating": 0,
            "total_reviews": 0,
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        }

    distribution = {}
    for i in range(1, 6):
        distribution[i] = reviews.filter(overall_rating=i).count()

    return {
        "average_rating": float(reviews.aggregate(Avg("overall_rating"))["avg"] or 0),
        "total_reviews": reviews.count(),
        "distribution": distribution,
    }
