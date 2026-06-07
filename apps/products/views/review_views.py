"""
Review Views - API endpoints for product and order reviews
"""

import logging
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from estore.utils.responses import APIResponse
from ..services.review_service import ReviewService, AdminReviewService
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    role_required,
)
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

APP_NAME = "products"


def _log_review_request(request, action, start_time, status_code, extra=None):
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
        description = "Review request successful"
    elif status_code == 429:
        severity = LogSeverity.WARNING
        description = "Review request rate limited"
    elif status_code < 500:
        severity = LogSeverity.WARNING
        description = "Review request failed - invalid parameters"
    else:
        severity = LogSeverity.ERROR
        description = "Review request failed with server error"
    
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
@ratelimit(key='ip', rate='200/h', method='GET', block=True)
def product_reviews_list(request, slug):
    start_time = time.time()
    action = "product_reviews_list"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving reviews for product: {slug}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "slug": slug}
    )
    
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        rating = request.GET.get("rating")
        verified = request.GET.get("verified")
        
        if rating:
            rating = int(rating)
        if verified:
            verified = verified.lower() == "true"
        
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        reviews, total = ReviewService.get_product_reviews(
            product_slug=slug,
            page=page,
            limit=limit,
            rating=rating,
            verified=verified,
            is_admin=False,
        )
        
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        
        print("Product Reviews")
        
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "slug": slug,
                "total_reviews": total,
                "reviews_returned": len(reviews),
                "page": page,
                "limit": limit,
                "rating_filter": rating,
                "verified_filter": verified,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "reviews": reviews,
                "pagination": {
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                }
            },
            message="Product reviews retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        _log_review_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product reviews list error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def product_review_create(request, slug):
    start_time = time.time()
    action = "product_review_create"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - creating product review for slug: {slug}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "slug": slug}
    )
    
    try:
        data = request.json_data
        
        rating = data.get('rating')
        comment = data.get('comment')
        title = data.get('title', '')
        
        if not rating or not comment:
            _log_review_request(
                request, action, start_time, 400,
                extra={"error": "Rating and comment required", "slug": slug}
            )
            return APIResponse.bad_request("Rating and comment are required")
        
        if rating < 1 or rating > 5:
            _log_review_request(
                request, action, start_time, 400,
                extra={"error": "Invalid rating", "rating": rating}
            )
            return APIResponse.bad_request("Rating must be between 1 and 5")
        
        review, error = ReviewService.create_product_review(
            user=request.user,
            product_slug=slug,
            rating=rating,
            comment=comment,
            title=title,
        )
        
        if error:
            _log_review_request(
                request, action, start_time, 400,
                extra={"error": error, "slug": slug, "rating": rating}
            )
            return APIResponse.bad_request(error.get('review') or error.get('product') or "Failed to create review")
        
        from ..schemas.review_schemas import serialize_review
        
        _log_review_request(
            request, action, start_time, 201,
            extra={
                "slug": slug,
                "review_id": str(review.id),
                "rating": rating,
                "has_title": bool(title),
                "comment_length": len(comment),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.created(
            data=serialize_review(review),
            message="Review created successfully"
        )
        
    except Exception as e:
        logger.error(f"Product review create error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key='user', rate='100/h', method='POST', block=True)
def product_review_helpful(request, review_id):
    start_time = time.time()
    action = "product_review_helpful"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - marking product review helpful: {review_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "review_id": review_id}
    )
    
    try:
        data = request.json_data
        is_helpful = data.get('is_helpful', True)
        
        success, error = ReviewService.mark_product_review_helpful(
            review_id=review_id,
            user=request.user,
            is_helpful=is_helpful,
        )
        
        if not success:
            _log_review_request(
                request, action, start_time, 400,
                extra={"review_id": review_id, "error": error, "is_helpful": is_helpful}
            )
            return APIResponse.bad_request(error or "Failed to mark review")
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_id": review_id,
                "is_helpful": is_helpful,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            message="Review marked as helpful" if is_helpful else "Review marked as not helpful"
        )
        
    except Exception as e:
        logger.error(f"Product review helpful error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def order_review_create(request, order_id):
    start_time = time.time()
    action = "order_review_create"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - creating order review for order: {order_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "order_id": order_id}
    )
    
    try:
        data = request.json_data
        
        overall_rating = data.get('overall_rating')
        comment = data.get('comment')
        title = data.get('title', '')
        shipping_rating = data.get('shipping_rating')
        packaging_rating = data.get('packaging_rating')
        delivery_speed_rating = data.get('delivery_speed_rating')
        customer_service_rating = data.get('customer_service_rating')
        images = data.get('images', [])
        
        if not overall_rating or not comment:
            _log_review_request(
                request, action, start_time, 400,
                extra={"error": "Overall rating and comment required", "order_id": order_id}
            )
            return APIResponse.bad_request("Overall rating and comment are required")
        
        if overall_rating < 1 or overall_rating > 5:
            _log_review_request(
                request, action, start_time, 400,
                extra={"error": "Invalid overall rating", "overall_rating": overall_rating}
            )
            return APIResponse.bad_request("Overall rating must be between 1 and 5")
        
        review, error = ReviewService.create_order_review(
            user=request.user,
            order_id=order_id,
            overall_rating=overall_rating,
            comment=comment,
            title=title,
            shipping_rating=shipping_rating,
            packaging_rating=packaging_rating,
            delivery_speed_rating=delivery_speed_rating,
            customer_service_rating=customer_service_rating,
            images=images,
        )
        
        if error:
            _log_review_request(
                request, action, start_time, 400,
                extra={"error": error, "order_id": order_id, "overall_rating": overall_rating}
            )
            return APIResponse.bad_request(error.get('review') or error.get('order') or "Failed to create review")
        
        from ..schemas.review_schemas import serialize_order_review
        
        _log_review_request(
            request, action, start_time, 201,
            extra={
                "order_id": order_id,
                "review_id": str(review.id),
                "overall_rating": overall_rating,
                "has_title": bool(title),
                "comment_length": len(comment),
                "has_images": bool(images),
                "images_count": len(images) if images else 0,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.created(
            data=serialize_order_review(review),
            message="Order review created successfully"
        )
        
    except Exception as e:
        logger.error(f"Order review create error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@ratelimit(key='user', rate='200/h', method='GET', block=True)
def order_review_detail(request, review_id):
    start_time = time.time()
    action = "order_review_detail"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving order review: {review_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "review_id": review_id}
    )
    
    try:
        from ..models import OrderReview
        from ..schemas.review_schemas import serialize_order_review
        
        review = OrderReview.objects.filter(id=review_id).first()
        
        if not review:
            _log_review_request(
                request, action, start_time, 404,
                extra={"review_id": review_id, "reason": "Review not found"}
            )
            return APIResponse.not_found("Review not found")
        
        is_admin = getattr(request.user, 'role', 'customer') in ['admin', 'staff']
        if not is_admin and review.user_id != request.user.id:
            _log_review_request(
                request, action, start_time, 403,
                extra={"review_id": review_id, "user_id": str(request.user.id), "review_user_id": str(review.user_id)}
            )
            return APIResponse.forbidden("You don't have permission to view this review")
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_id": review_id,
                "order_id": str(review.order_id),
                "overall_rating": review.overall_rating,
                "is_approved": review.is_approved,
                "is_admin_access": is_admin,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialize_order_review(review, is_admin=is_admin),
            message="Order review retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Order review detail error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key='user', rate='100/h', method='POST', block=True)
def order_review_helpful(request, review_id):
    start_time = time.time()
    action = "order_review_helpful"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - marking order review helpful: {review_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "review_id": review_id}
    )
    
    try:
        data = request.json_data
        is_helpful = data.get('is_helpful', True)
        
        success, error = ReviewService.mark_order_review_helpful(
            review_id=review_id,
            user=request.user,
            is_helpful=is_helpful,
        )
        
        if not success:
            _log_review_request(
                request, action, start_time, 400,
                extra={"review_id": review_id, "error": error, "is_helpful": is_helpful}
            )
            return APIResponse.bad_request(error or "Failed to mark review")
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_id": review_id,
                "is_helpful": is_helpful,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            message="Review marked as helpful" if is_helpful else "Review marked as not helpful"
        )
        
    except Exception as e:
        logger.error(f"Order review helpful error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def user_reviews(request):
    start_time = time.time()
    action = "user_reviews"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving user reviews",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        review_type = request.GET.get("type", "all")
        
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        from ..selectors.review_selectors import get_reviews_by_user
        
        reviews, total = get_reviews_by_user(
            user_id=str(request.user.id),
            review_type=review_type,
            page=page,
            limit=limit,
            only_approved=True,
        )
        
        from ..schemas.review_schemas import serialize_review, serialize_order_review
        
        serialized_reviews = []
        for review in reviews:
            if hasattr(review, 'product'):
                serialized_reviews.append(serialize_review(review))
            else:
                serialized_reviews.append(serialize_order_review(review))
        
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_type_filter": review_type,
                "total_reviews": total,
                "reviews_returned": len(serialized_reviews),
                "product_reviews_count": sum(1 for r in reviews if hasattr(r, 'product')),
                "order_reviews_count": sum(1 for r in reviews if not hasattr(r, 'product')),
                "page": page,
                "limit": limit,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "reviews": serialized_reviews,
                "pagination": {
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                }
            },
            message="User reviews retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        _log_review_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"User reviews error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def admin_reviews_list(request):
    start_time = time.time()
    action = "admin_reviews_list"
    user = request.user
    
    print("Admin Reviews")
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin retrieving all reviews",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        review_type = request.GET.get("type", "all")
        status = request.GET.get("status", "all")
        rating = request.GET.get("rating")
        verified = request.GET.get("verified")
        search = request.GET.get("search", "")
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        if rating:
            rating = int(rating)
        
        if verified:
            verified = verified.lower() == "true"
        
        status_filter = None if status == "all" else status
        
        reviews, total, pagination_meta = AdminReviewService.get_all_reviews(
            review_type=review_type,
            page=page,
            limit=limit,
            search=search if search else None,
            status=status_filter,
            rating=rating,
            verified=verified,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_type_filter": review_type,
                "status_filter": status,
                "rating_filter": rating,
                "verified_filter": verified,
                "has_search": bool(search),
                "total_reviews": total,
                "reviews_returned": len(reviews),
                "page": page,
                "limit": limit,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "reviews": reviews,
                "pagination": pagination_meta
            },
            message="Reviews retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        _log_review_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Admin reviews list error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='POST', block=True)
def admin_review_approve(request, review_id):
    start_time = time.time()
    action = "admin_review_approve"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin approving review: {review_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "review_id": review_id}
    )
    
    try:
        review_type = request.GET.get("type", "product")
        
        if review_type == "product":
            success, error = AdminReviewService.approve_product_review(
                review_id=review_id,
                user=request.user,
            )
        else:
            success, error = AdminReviewService.approve_order_review(
                review_id=review_id,
                user=request.user,
            )
        
        if not success:
            _log_review_request(
                request, action, start_time, 400,
                extra={"review_id": review_id, "review_type": review_type, "error": error}
            )
            error_msg = error.get('review') or error.get('general') or "Failed to approve review"
            return APIResponse.bad_request(error_msg)
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_id": review_id,
                "review_type": review_type,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            message="Review approved successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin review approve error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='POST', block=True)
def admin_review_reject(request, review_id):
    start_time = time.time()
    action = "admin_review_reject"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin rejecting review: {review_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "review_id": review_id}
    )
    
    try:
        review_type = request.GET.get("type", "product")
        
        if review_type == "product":
            success, error = AdminReviewService.reject_product_review(
                review_id=review_id,
                user=request.user,
            )
        else:
            success, error = AdminReviewService.reject_order_review(
                review_id=review_id,
                user=request.user,
            )
        
        if not success:
            _log_review_request(
                request, action, start_time, 400,
                extra={"review_id": review_id, "review_type": review_type, "error": error}
            )
            error_msg = error.get('review') or error.get('general') or "Failed to reject review"
            return APIResponse.bad_request(error_msg)
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_id": review_id,
                "review_type": review_type,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            message="Review rejected successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin review reject error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def admin_reviews_bulk_action(request):
    start_time = time.time()
    action_name = "admin_reviews_bulk_action"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action_name,
        description="Request started - admin bulk action on reviews",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = request.json_data
        review_ids = data.get('review_ids', [])
        action = data.get('action')
        review_type = data.get('type', 'product')
        
        if not review_ids:
            _log_review_request(
                request, action_name, start_time, 400,
                extra={"error": "No review IDs provided"}
            )
            return APIResponse.bad_request("No review IDs provided")
        
        if action not in ['approve', 'reject']:
            _log_review_request(
                request, action_name, start_time, 400,
                extra={"error": "Invalid action", "action": action}
            )
            return APIResponse.bad_request("Invalid action. Must be 'approve' or 'reject'")
        
        results = AdminReviewService.bulk_moderate_reviews(
            review_ids=review_ids,
            action=action,
            user=request.user,
            review_type=review_type,
        )
        
        _log_review_request(
            request, action_name, start_time, 200,
            extra={
                "review_type": review_type,
                "action": action,
                "total_reviews": len(review_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "requested_by": get_user_info(user)
            }
        )
        
        message = f"Bulk {action} completed: {len(results['success'])} succeeded, {len(results['failed'])} failed"
        
        return APIResponse.success(
            data=results,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Admin bulk review action error: {str(e)}", exc_info=True)
        _log_review_request(request, action_name, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def admin_order_review_response(request, review_id):
    start_time = time.time()
    action = "admin_order_review_response"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin adding response to order review: {review_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "review_id": review_id}
    )
    
    try:
        data = request.json_data
        response_text = data.get('response')
        
        if not response_text:
            _log_review_request(
                request, action, start_time, 400,
                extra={"review_id": review_id, "error": "Response text required"}
            )
            return APIResponse.bad_request("Response text is required")
        
        success, error = AdminReviewService.add_admin_response(
            review_id=review_id,
            response=response_text,
            user=request.user,
            review_type="order",
        )
        
        if not success:
            _log_review_request(
                request, action, start_time, 400,
                extra={"review_id": review_id, "error": error}
            )
            error_msg = error.get('review') or error.get('general') or "Failed to add response"
            return APIResponse.bad_request(error_msg)
        
        _log_review_request(
            request, action, start_time, 200,
            extra={
                "review_id": review_id,
                "response_length": len(response_text),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            message="Admin response added successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin order review response error: {str(e)}", exc_info=True)
        _log_review_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()