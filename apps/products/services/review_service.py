"""
Review Service - Business logic for product reviews
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.core.paginator import Paginator

from apps.products.models import ProductReview
from apps.products.selectors import get_product_by_slug, get_reviews_by_product
from apps.products.schemas import serialize_review
from apps.users.models import User
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
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
        """Get product reviews"""
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
            extra={
                "product_slug": product_slug,
                "rating": rating,
                "has_title": bool(title),
                "comment_length": len(comment) if comment else 0,
                "is_verified_purchase": is_verified_purchase
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

            # Check if user already reviewed this product
            existing_review = ProductReview.objects.filter(product=product, user=user).first()
            if existing_review:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Duplicate review attempt for {product_slug}",
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

            # Create review
            review = ProductReview.objects.create(
                product=product,
                user=user,
                rating=rating,
                title=title[:200] if title else "",
                comment=comment,
                is_verified_purchase=is_verified_purchase,
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
                    "product_id": str(product.id),
                    "rating": rating,
                    "is_verified_purchase": is_verified_purchase,
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
                description=f"Failed to create review for {product_slug}: {str(e)}",
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
    def approve_review(
        review_id: str, user: User
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Approve a single review (admin action)
        
        Args:
            review_id: ID of the review to approve
            user: Admin user performing the action
        
        Returns:
            Tuple of (success, error_dict)
        """
        start_time = time.time()
        action = "approve_review"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Approving review: {review_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"review_id": review_id}
        )
        
        try:
            review = ProductReview.objects.select_related('product').get(id=review_id)
            
            if review.is_approved:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Review already approved: {review_id}",
                    status_code=400,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "review_id": review_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return False, {"review": "Review is already approved"}
            
            review.is_approved = True
            review.save()
            
            # Update product rating cache
            review.update_product_rating()
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Review approved: {review_id}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": str(review.id),
                    "product_id": str(review.product.id),
                    "product_title": review.product.title,
                    "rating": review.rating,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return True, None
            
        except ProductReview.DoesNotExist:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Review not found: {review_id}",
                status_code=404,
                user=user,
                app_name=APP_NAME,
                extra={"review_id": review_id, "duration_ms": round(duration_ms, 2)}
            )
            return False, {"review": "Review not found"}
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to approve review {review_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": review_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            return False, {"general": "Failed to approve review"}

    @staticmethod
    @transaction.atomic
    def reject_review(
        review_id: str, user: User
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Reject a single review (admin action)
        
        Args:
            review_id: ID of the review to reject
            user: Admin user performing the action
        
        Returns:
            Tuple of (success, error_dict)
        """
        start_time = time.time()
        action = "reject_review"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Rejecting review: {review_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"review_id": review_id}
        )
        
        try:
            review = ProductReview.objects.select_related('product').get(id=review_id)
            
            if not review.is_approved:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Review already rejected: {review_id}",
                    status_code=400,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "review_id": review_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return False, {"review": "Review is already rejected"}
            
            review.is_approved = False
            review.save()
            
            # Update product rating cache
            review.update_product_rating()
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Review rejected: {review_id}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": str(review.id),
                    "product_id": str(review.product.id),
                    "product_title": review.product.title,
                    "rating": review.rating,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return True, None
            
        except ProductReview.DoesNotExist:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Review not found: {review_id}",
                status_code=404,
                user=user,
                app_name=APP_NAME,
                extra={"review_id": review_id, "duration_ms": round(duration_ms, 2)}
            )
            return False, {"review": "Review not found"}
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to reject review {review_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "review_id": review_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            return False, {"general": "Failed to reject review"}

    @staticmethod
    def get_pending_reviews(
        page: int = 1,
        limit: int = 20,
        is_admin: bool = True,
    ) -> Tuple[List[Dict], int]:
        """Get pending (unapproved) reviews for moderation"""
        start_time = time.time()
        action = "get_pending_reviews"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Retrieving pending reviews",
            status_code=0,
            app_name=APP_NAME,
            extra={"page": page, "limit": limit}
        )
        
        try:
            queryset = ProductReview.objects.filter(
                is_approved=False
            ).select_related('product', 'user').order_by('-created_at')
            
            paginator = Paginator(queryset, limit)
            page_obj = paginator.get_page(page)
            
            reviews_data = [serialize_review(r, is_admin=is_admin) for r in page_obj]
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Pending reviews retrieved",
                status_code=200,
                app_name=APP_NAME,
                extra={
                    "total_pending": paginator.count,
                    "reviews_returned": len(reviews_data),
                    "page": page,
                    "limit": limit,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            
            return reviews_data, paginator.count
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to retrieve pending reviews: {str(e)}",
                status_code=500,
                app_name=APP_NAME,
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            raise

    @staticmethod
    @transaction.atomic
    def bulk_moderate_reviews(
        review_ids: List[str], action: str, user: User
    ) -> Dict[str, Any]:
        """
        Bulk moderate multiple reviews (approve/reject)
        
        Args:
            review_ids: List of review IDs to moderate
            action: 'approve' or 'reject'
            user: Admin user performing the action
        
        Returns:
            Dict with success and failed lists
        """
        start_time = time.time()
        action_name = f"bulk_review_{action}"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action_name,
            description=f"Bulk {action} for {len(review_ids)} reviews",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "action": action,
                "total_reviews": len(review_ids),
                "review_ids": review_ids[:10]  # Log first 10 only
            }
        )
        
        results = {"success": [], "failed": [], "total": len(review_ids)}
        
        for review_id in review_ids:
            try:
                review = ProductReview.objects.select_related('product').get(id=review_id)
                
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
                review.update_product_rating()
                
                results["success"].append({
                    "id": str(review.id),
                    "product_title": review.product.title,
                    "rating": review.rating
                })
                
            except ProductReview.DoesNotExist:
                results["failed"].append({
                    "id": review_id,
                    "reason": "Review not found"
                })
            except Exception as e:
                results["failed"].append({
                    "id": review_id,
                    "reason": str(e)
                })
        
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
                "total_reviews": len(review_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "failed_reasons": list(set([f["reason"] for f in results["failed"]])),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return results