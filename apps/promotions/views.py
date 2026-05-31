"""
Promotion Views - API endpoints for promotions
"""

import logging
import time
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from .models import Promotion
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required, multipart_request_allowed
from apps.common.logging import log_action, LogSeverity, get_user_info
from apps.promotions.selectors import (
    get_active_promotions,
    get_promotion_by_slug,
    get_admin_promotions,
)
from apps.promotions.services import PromotionService
from apps.promotions.schemas import (
    validate_promotion_create,
    serialize_promotion,
    serialize_promotion_list,
)

logger = logging.getLogger(__name__)
APP_NAME = "promotions"


# ==================== PUBLIC ENDPOINTS ====================

@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='100/h', method='GET', block=True)
def promotion_list(request):
    """Public: Get list of active promotions"""
    start_time = time.time()
    action = "promotion_list"
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving active promotions",
        status_code=0,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        page = int(request.GET.get('page', 1))
        limit = min(int(request.GET.get('limit', 20)), 100)
        
        promotions, total, pagination_meta = get_active_promotions(page, limit)
        promotions_data = serialize_promotion_list(promotions, is_admin=False)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Active promotions retrieved: {total} total",
            status_code=200,
            request=request,
            app_name=APP_NAME,
            extra={
                "total_promotions": total,
                "promotions_returned": len(promotions_data),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(
            data={
                "promotions": promotions_data,
                "total": total,
                "pagination": pagination_meta
            },
            message="Promotions retrieved successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve promotions: {str(e)}",
            status_code=500,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='100/h', method='GET', block=True)
def promotion_detail(request, slug):
    """Public: Get promotion details by slug"""
    start_time = time.time()
    action = "promotion_detail"
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving promotion: {slug}",
        status_code=0,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "slug": slug}
    )
    
    try:
        promotion = get_promotion_by_slug(slug, is_admin=False)
        
        if not promotion:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion not found: {slug}",
                status_code=404,
                request=request,
                app_name=APP_NAME,
                extra={"slug": slug, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.not_found("Promotion not found")
        
        promotion_data = serialize_promotion(promotion, is_admin=False)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion retrieved: {promotion.name}",
            status_code=200,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion.id),
                "slug": slug,
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(data=promotion_data, message="Promotion retrieved successfully")
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve promotion: {str(e)}",
            status_code=500,
            request=request,
            app_name=APP_NAME,
            extra={"slug": slug, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


# ==================== ADMIN ENDPOINTS ====================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def admin_promotion_list(request):
    """Admin: Get all promotions with filters"""
    start_time = time.time()
    action = "admin_promotion_list"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin retrieving promotions",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        page = int(request.GET.get('page', 1))
        limit = min(int(request.GET.get('limit', 20)), 100)
        status = request.GET.get('status')
        search = request.GET.get('search', '').strip()
        sort_by = request.GET.get('sort_by', 'created_at')
        sort_order = request.GET.get('sort_order', 'desc')
        
        promotions, total, pagination_meta = get_admin_promotions(
            page=page,
            limit=limit,
            status=status,
            search=search if search else None,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        promotions_data = serialize_promotion_list(promotions, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Admin promotions retrieved: {total} total",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "total_promotions": total,
                "promotions_returned": len(promotions_data),
                "status_filter": status,
                "has_search": bool(search),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "promotions": promotions_data,
                "total": total,
                "pagination": pagination_meta
            },
            message="Promotions retrieved successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve promotions: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def admin_promotion_create(request):
    """Admin: Create a new promotion"""
    start_time = time.time()
    action = "admin_promotion_create"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - creating promotion",
        status_code=0,
        user=user,
        request=request,  # Pass the request object
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        # Parse data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = json.loads(request.POST.get('data', '{}'))
            image_files = request.FILES.getlist('images') if 'images' in request.FILES else []
        else:
            data = json.loads(request.body)
            image_files = []
        
        # Validate
        cleaned, errors = validate_promotion_create(data)
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description="Promotion validation failed",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(errors)
        
        # Create promotion
        promotion, errors = PromotionService.create_promotion(cleaned, image_files, user)
        
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description="Promotion creation failed",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(errors)
        
        promotion_data = serialize_promotion(promotion, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion created: {promotion.name}",
            status_code=201,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion.id),
                "name": promotion.name,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.created(
            data=promotion_data,
            message="Promotion created successfully"
        )
        
    except json.JSONDecodeError:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description="Invalid JSON data",
            status_code=400,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to create promotion: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()
    
    
@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_promotion_activate(request, promotion_id):
    """Admin: Activate a promotion"""
    start_time = time.time()
    action = "admin_promotion_activate"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - activating promotion: {promotion_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "promotion_id": str(promotion_id)}  # Convert UUID to string
    )
    
    try:
        success, error = PromotionService.activate_promotion(promotion_id, user)
        
        if not success:
            duration_ms = (time.time() - start_time) * 1000
            if error:
                error_message = error.get("general") or error.get("stock") or error.get("status") or error.get("promotion") or "Activation failed"
            else:
                error_message = "Activation failed"
            
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion activation failed: {error_message}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"promotion_id": str(promotion_id), "error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.bad_request(error_message)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion activated: {promotion_id}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion_id),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(message="Promotion activated successfully")
        
    except Promotion.DoesNotExist:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description=f"Promotion not found: {promotion_id}",
            status_code=404,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": str(promotion_id), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.not_found("Promotion not found")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to activate promotion: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": str(promotion_id), "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_promotion_pause(request, promotion_id):
    """Admin: Pause an active promotion"""
    start_time = time.time()
    action = "admin_promotion_pause"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - pausing promotion: {promotion_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "promotion_id": str(promotion_id)}
    )
    
    try:
        success, error = PromotionService.pause_promotion(promotion_id, user)
        
        if not success:
            duration_ms = (time.time() - start_time) * 1000
            if error:
                error_message = error.get("general") or error.get("status") or "Pause failed"
            else:
                error_message = "Pause failed"
            
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion pause failed: {error_message}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"promotion_id": str(promotion_id), "error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.bad_request(error_message)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion paused: {promotion_id}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion_id),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(message="Promotion paused successfully")
        
    except Promotion.DoesNotExist:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description=f"Promotion not found: {promotion_id}",
            status_code=404,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": str(promotion_id), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.not_found("Promotion not found")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to pause promotion: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": str(promotion_id), "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_promotion_refresh_stock(request, promotion_id):
    """Admin: Refresh stock availability for a promotion"""
    start_time = time.time()
    action = "admin_promotion_refresh_stock"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - refreshing promotion stock: {promotion_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "promotion_id": str(promotion_id)}
    )
    
    try:
        success, error = PromotionService.refresh_promotion_availability(promotion_id, user)
        
        if not success:
            duration_ms = (time.time() - start_time) * 1000
            if error:
                error_message = error.get("general") or "Refresh failed"
            else:
                error_message = "Refresh failed"
            
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion refresh failed: {error_message}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"promotion_id": str(promotion_id), "error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.bad_request(error_message)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion stock refreshed: {promotion_id}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion_id),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(message="Promotion stock refreshed successfully")
        
    except Promotion.DoesNotExist:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description=f"Promotion not found: {promotion_id}",
            status_code=404,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": str(promotion_id), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.not_found("Promotion not found")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to refresh promotion stock: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": str(promotion_id), "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()
 

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_promotion_bulk_action(request):
    """Admin: Perform bulk actions on promotions"""
    start_time = time.time()
    action = "admin_promotion_bulk_action"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - bulk action on promotions",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        from apps.promotions.schemas import validate_bulk_action, serialize_bulk_action_result
        
        # Validate request data
        cleaned, errors = validate_bulk_action(request.json_data)
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description="Bulk action validation failed",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(errors)
        
        # Execute bulk action
        results, error = PromotionService.bulk_action_promotions(
            promotion_ids=cleaned['promotion_ids'],
            action=cleaned['action'],
            user=request.user
        )
        
        if error:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Bulk action failed: {error}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(error)
        
        # Serialize and return response
        serialized_results = serialize_bulk_action_result(results)
        
        if serialized_results['failed_count'] == 0:
            message = f"Successfully {cleaned['action']}ed {serialized_results['success_count']} promotions"
        else:
            message = f"Processed {serialized_results['success_count']} successfully, {serialized_results['failed_count']} failed"
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Bulk action completed: {serialized_results['success_count']} succeeded",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "action": cleaned['action'],
                "total_promotions": len(cleaned['promotion_ids']),
                "success_count": serialized_results['success_count'],
                "failed_count": serialized_results['failed_count'],
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_results,
            message=message
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to execute bulk action: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()
    
    

@csrf_exempt
@require_http_methods(["PUT", "POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def admin_promotion_update(request, promotion_id):
    """Admin: Update an existing promotion"""
    start_time = time.time()
    action = "admin_promotion_update"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - updating promotion: {promotion_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "promotion_id": promotion_id}
    )
    
    try:
        # Parse data
        if request.content_type and 'multipart/form-data' in request.content_type:
            # For PUT with multipart, check for _method or just parse POST data
            data = json.loads(request.POST.get('data', '{}'))
            image_files = request.FILES.getlist('images') if 'images' in request.FILES else []
        else:
            data = json.loads(request.body)
            image_files = []
        
        # Validate
        cleaned, errors = validate_promotion_create(data)  # Reuse create validation
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description="Promotion validation failed",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(errors)
        
        # Add keep_image_ids if present
        if 'keep_image_ids' in data:
            cleaned['keep_image_ids'] = data['keep_image_ids']
        
        # Update promotion
        promotion, errors = PromotionService.update_promotion(promotion_id, cleaned, image_files, user)
        
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            error_message = errors.get("general") or errors.get("status") or errors.get("promotion") or "Update failed"
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion update failed: {error_message}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.bad_request(error_message)
        
        promotion_data = serialize_promotion(promotion, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion updated: {promotion.name}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion.id),
                "name": promotion.name,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=promotion_data,
            message="Promotion updated successfully"
        )
        
    except json.JSONDecodeError:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description="Invalid JSON data",
            status_code=400,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.bad_request("Invalid JSON data")
    except Promotion.DoesNotExist:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description=f"Promotion not found: {promotion_id}",
            status_code=404,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": promotion_id, "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.not_found("Promotion not found")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to update promotion: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": promotion_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()
    
    
@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def admin_promotion_detail(request, promotion_id):
    """Admin: Get single promotion details"""
    start_time = time.time()
    action = "admin_promotion_detail"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving promotion: {promotion_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "promotion_id": promotion_id}
    )
    
    try:
        promotion = Promotion.objects.get(id=promotion_id)
        promotion_data = serialize_promotion(promotion, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Promotion retrieved: {promotion.name}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "promotion_id": str(promotion.id),
                "name": promotion.name,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(data=promotion_data, message="Promotion retrieved successfully")
        
    except Promotion.DoesNotExist:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description=f"Promotion not found: {promotion_id}",
            status_code=404,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": promotion_id, "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.not_found("Promotion not found")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve promotion: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotion_id": promotion_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()