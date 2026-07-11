"""
Review Service - Business logic for product and order reviews
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.core.paginator import Paginator
from django.utils import timezone

from apps.products.models import ProductReview, OrderReview, ProductReviewHelpful, OrderReviewHelpful
from apps.products.selectors import get_product_by_slug
from apps.products.selectors.review_selectors import (
    get_pending_product_reviews,
    get_pending_order_reviews,
    get_all_pending_reviews,
    get_all_reviews_admin,
)
from apps.products.schemas.review_schemas import (
    serialize_review,
    serialize_order_review,
    serialize_admin_review_list,
)
from apps.users.models import User
from apps.common.logging import log_action, LogSeverity, get_user_info
from apps.orders.selectors import get_order_by_id
from apps.orders.models import Order, OrderItem

logger = logging.getLogger(__name__)

APP_NAME = "products"


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
        start_time = time.time()
        action = "get_product_reviews"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Retrieving reviews for product: {product_slug}",
            status_code=0,
            app_name=APP_NAME,
            extra={
                "product_slug": product_slug,
                "page": page,
                "limit": limit,
                "rating_filter": rating,
                "verified_filter": verified,
                "is_admin": is_admin
            }
        )

        try:
            from apps.products.selectors import get_reviews_by_product
            
            reviews, total = get_reviews_by_product(
                product_slug=product_slug,
                page=page,
                limit=limit,
                rating=rating,
                verified=verified,
                only_approved=not is_admin,
            )

            reviews_data = [serialize_review(r, is_admin=is_admin) for r in reviews]

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description=f"Reviews retrieved for {product_slug}",
                status_code=200,
                app_name=APP_NAME,
                extra={
                    "product_slug": product_slug,
                    "total_reviews": total,
                    "reviews_returned": len(reviews_data),
                    "page": page,
                    "limit": limit,
                    "duration_ms": round(duration_ms, 2)
                }
            )

            return reviews_data, total

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to retrieve reviews for {product_slug}: {str(e)}",
                status_code=500,
                app_name=APP_NAME,
                extra={
                    "product_slug": product_slug,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            raise

    @staticmethod
    def _check_product_verified_purchase(user_id: str, product_id: str) -> bool:
        from apps.orders.models import Order, OrderItem
        
        return OrderItem.objects.filter(
            variant__product_id=product_id,
            order__user_id=user_id,
            order__payment_status=Order.PAYMENT_PAID,
            order__status__in=['delivered', 'completed']
        ).exists()

    @staticmethod
    def _check_order_verified_purchase(user_id: str, order_id: str) -> bool:
        from apps.orders.models import Order
        
        return Order.objects.filter(
            id=order_id,
            user_id=user_id,
            payment_status=Order.PAYMENT_PAID,
            status__in=['delivered', 'completed']
        ).exists()

    @staticmethod
    @transaction.atomic
    def create_product_review(
        user: User,
        product_slug: str,
        rating: int,
        comment: str,
        title: str = "",
        is_verified_purchase: bool = False,
    ) -> Tuple[Optional[ProductReview], Optional[Dict]]:
        start_time = time.time()
        action = "create_product_review"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating product review for: {product_slug}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "product_slug": product_slug,
                "rating": rating,
                "has_title": bool(title),
                "comment_length": len(comment) if comment else 0,
            }
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
                    extra={
                        "product_slug": product_slug,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, {"product": "Product not found"}

            existing_review = ProductReview.objects.filter(product=product, user=user).first()
            if existing_review:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Duplicate product review attempt for {product_slug}",
                    status_code=409,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "product_slug": product_slug,
                        "product_id": str(product.id),
                        "existing_review_id": str(existing_review.id),
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, {"review": "You have already reviewed this product"}

            is_verified = ReviewService._check_product_verified_purchase(str(user.id), str(product.id))

            review = ProductReview.objects.create(
                product=product,
                user=user,
                rating=rating,
                title=title[:200] if title else "",
                comment=comment,
                is_verified_purchase=is_verified,
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Product review created for {product_slug}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": str(review.id),
                    "product_slug": product_slug,
                    "product_id": str(product.id),
                    "rating": rating,
                    "is_verified_purchase": is_verified,
                    "comment_length": len(comment),
                    "has_title": bool(title),
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
                description=f"Failed to create product review for {product_slug}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "product_slug": product_slug,
                    "rating": rating,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, {"general": "Failed to create review"}

    @staticmethod
    @transaction.atomic
    def create_order_review(
        user: User,
        order_id: str,
        overall_rating: int,
        comment: str,
        title: str = "",
        shipping_rating: Optional[int] = None,
        packaging_rating: Optional[int] = None,
        delivery_speed_rating: Optional[int] = None,
        customer_service_rating: Optional[int] = None,
        images: List[str] = None,
    ) -> Tuple[Optional[OrderReview], Optional[Dict]]:
        start_time = time.time()
        action = "create_order_review"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating order review for order: {order_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "order_id": order_id,
                "overall_rating": overall_rating,
                "has_title": bool(title),
                "comment_length": len(comment) if comment else 0,
                "has_images": bool(images)
            }
        )
        
        try:
            order = get_order_by_id(order_id)
            if not order:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Order not found: {order_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "order_id": order_id,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, {"order": "Order not found"}

            if order.user_id != user.id:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"User does not own order: {order_id}",
                    status_code=403,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "order_id": order_id,
                        "order_user_id": str(order.user_id),
                        "requesting_user_id": str(user.id),
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, {"order": "You can only review your own orders"}

            existing_review = OrderReview.objects.filter(order=order, user=user).first()
            if existing_review:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Duplicate order review attempt for {order_id}",
                    status_code=409,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "order_id": order_id,
                        "existing_review_id": str(existing_review.id),
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, {"review": "You have already reviewed this order"}

            review = OrderReview.objects.create(
                order=order,
                user=user,
                overall_rating=overall_rating,
                shipping_rating=shipping_rating,
                packaging_rating=packaging_rating,
                delivery_speed_rating=delivery_speed_rating,
                customer_service_rating=customer_service_rating,
                title=title[:200] if title else "",
                comment=comment,
                images=images or [],
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Order review created for order {order.order_number}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": str(review.id),
                    "order_id": order_id,
                    "order_number": order.order_number,
                    "overall_rating": overall_rating,
                    "has_images": bool(images),
                    "images_count": len(images) if images else 0,
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
                description=f"Failed to create order review for {order_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "order_id": order_id,
                    "overall_rating": overall_rating,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, {"general": "Failed to create order review"}

    @staticmethod
    @transaction.atomic
    def mark_product_review_helpful(
        review_id: str,
        user: User,
        is_helpful: bool = True
    ) -> Tuple[bool, Optional[str]]:
        try:
            review = ProductReview.objects.get(id=review_id)
            
            existing_vote = ProductReviewHelpful.objects.filter(
                review=review, user=user
            ).first()
            
            if existing_vote:
                return False, "You have already voted on this review"
            
            ProductReviewHelpful.objects.create(
                review=review,
                user=user,
                is_helpful=is_helpful
            )
            
            if is_helpful:
                review.helpful_yes += 1
            else:
                review.helpful_no += 1
            review.save()
            
            return True, None
            
        except ProductReview.DoesNotExist:
            return False, "Review not found"
        except Exception as e:
            return False, f"Failed to mark review: {str(e)}"

    @staticmethod
    @transaction.atomic
    def mark_order_review_helpful(
        review_id: str,
        user: User,
        is_helpful: bool = True
    ) -> Tuple[bool, Optional[str]]:
        try:
            review = OrderReview.objects.get(id=review_id)
            
            existing_vote = OrderReviewHelpful.objects.filter(
                review=review, user=user
            ).first()
            
            if existing_vote:
                return False, "You have already voted on this review"
            
            OrderReviewHelpful.objects.create(
                review=review,
                user=user,
                is_helpful=is_helpful
            )
            
            if is_helpful:
                review.helpful_yes += 1
            else:
                review.helpful_no += 1
            review.save()
            
            return True, None
            
        except OrderReview.DoesNotExist:
            return False, "Review not found"
        except Exception as e:
            return False, f"Failed to mark review: {str(e)}"


class AdminReviewService:
    """Admin review management business logic"""

    @staticmethod
    def get_all_reviews(
        review_type: str = "all",
        page: int = 1,
        limit: int = 20,
        search: str = None,
        status: str = None,
        rating: int = None,
        verified: bool = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Dict], int, Dict]:
        try:
            reviews, total, pagination_meta = get_all_reviews_admin(
                review_type=review_type,
                page=page,
                limit=limit,
                search=search,
                status=status,
                rating=rating,
                verified=verified,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            
            reviews_data = [serialize_admin_review_list(r) for r in reviews]
            
            return reviews_data, total, pagination_meta
            
        except Exception as e:
            logger.error(f"Failed to retrieve all reviews: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def approve_product_review(
        review_id: str,
        user: User
    ) -> Tuple[bool, Optional[Dict]]:
        try:
            review = ProductReview.objects.select_related('product').get(id=review_id)
            
            if review.is_approved:
                return False, {"review": "Review is already approved"}
            
            review.is_approved = True
            review.save()
            
            review.update_product_rating()
            
            return True, None
            
        except ProductReview.DoesNotExist:
            return False, {"review": "Review not found"}
        except Exception as e:
            return False, {"general": "Failed to approve review"}

    @staticmethod
    @transaction.atomic
    def reject_product_review(
        review_id: str,
        user: User
    ) -> Tuple[bool, Optional[Dict]]:
        try:
            review = ProductReview.objects.select_related('product').get(id=review_id)
            
            if not review.is_approved:
                return False, {"review": "Review is already rejected"}
            
            review.is_approved = False
            review.save()
            
            review.update_product_rating()
            
            return True, None
            
        except ProductReview.DoesNotExist:
            return False, {"review": "Review not found"}
        except Exception as e:
            return False, {"general": "Failed to reject review"}

    @staticmethod
    @transaction.atomic
    def approve_order_review(
        review_id: str,
        user: User
    ) -> Tuple[bool, Optional[Dict]]:
        try:
            review = OrderReview.objects.select_related("order").only(
                "id",
                "is_approved",
                "order__id",
                "order__order_number",
            ).get(id=review_id)
            
            if review.is_approved:
                return False, {"review": "Review is already approved"}
            
            review.is_approved = True
            review.save()
            
            return True, None
            
        except OrderReview.DoesNotExist:
            return False, {"review": "Review not found"}
        except Exception as e:
            return False, {"general": "Failed to approve review"}

    @staticmethod
    @transaction.atomic
    def reject_order_review(
        review_id: str,
        user: User
    ) -> Tuple[bool, Optional[Dict]]:
        try:
            review = OrderReview.objects.select_related("order").only(
                "id",
                "is_approved",
                "order__id",
                "order__order_number",
            ).get(id=review_id)
            
            if not review.is_approved:
                return False, {"review": "Review is already rejected"}
            
            review.is_approved = False
            review.save()
            
            return True, None
            
        except OrderReview.DoesNotExist:
            return False, {"review": "Review not found"}
        except Exception as e:
            return False, {"general": "Failed to reject review"}

    @staticmethod
    @transaction.atomic
    def add_admin_response(
        review_id: str,
        response: str,
        user: User,
        review_type: str = "order"
    ) -> Tuple[bool, Optional[Dict]]:
        try:
            if review_type == "order":
                review = OrderReview.objects.get(id=review_id)
                review.admin_response = response
                review.admin_response_at = timezone.now()
                review.save()
            else:
                return False, {"error": "Admin responses are only supported for order reviews"}
            
            return True, None
            
        except OrderReview.DoesNotExist:
            return False, {"review": "Review not found"}
        except Exception as e:
            return False, {"general": "Failed to add response"}

    @staticmethod
    @transaction.atomic
    def bulk_moderate_reviews(
        review_ids: List[str],
        action: str,
        user: User,
        review_type: str = "product"
    ) -> Dict[str, Any]:
        results = {"success": [], "failed": [], "total": len(review_ids)}
        
        if review_type == "product":
            Model = ProductReview
        else:
            Model = OrderReview
        
        for review_id in review_ids:
            try:
                if review_type == "product":
                    review = Model.objects.select_related().get(id=review_id)
                else:
                    review = Model.objects.select_related("order").only(
                        "id",
                        "overall_rating",
                        "is_approved",
                        "order__id",
                        "order__order_number",
                    ).get(id=review_id)
                
                if action == "approve":
                    if review.is_approved:
                        results["failed"].append({
                            "id": review_id,
                            "reason": "Already approved"
                        })
                        continue
                    review.is_approved = True
                elif action == "reject":
                    if not review.is_approved:
                        results["failed"].append({
                            "id": review_id,
                            "reason": "Already rejected"
                        })
                        continue
                    review.is_approved = False
                else:
                    results["failed"].append({
                        "id": review_id,
                        "reason": f"Invalid action: {action}"
                    })
                    continue
                
                review.save()
                
                if review_type == "product":
                    review.update_product_rating()
                
                results["success"].append({
                    "id": str(review.id),
                    "title": review.product.title if review_type == "product" else f"Order {review.order.order_number}",
                    "rating": review.rating if review_type == "product" else review.overall_rating
                })
                
            except Model.DoesNotExist:
                results["failed"].append({
                    "id": review_id,
                    "reason": "Review not found"
                })
            except Exception as e:
                results["failed"].append({
                    "id": review_id,
                    "reason": str(e)
                })
        
        return results
