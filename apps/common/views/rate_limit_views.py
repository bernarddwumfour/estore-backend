
import logging
import time
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.logging import log_action, LogSeverity

logger = logging.getLogger(__name__)
APP_NAME = "common"


@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "DELETE", "PATCH"])
def rate_limit_exceeded(request, exception=None):
    """
    Custom response when rate limit is exceeded.
    Returns 429 Too Many Requests.
    """
    start_time = time.time()
    
    # Get user info
    user = getattr(request, 'user', None)
    user_email = user.email if user and hasattr(user, 'email') else 'anonymous'
    
    # Determine endpoint type from path
    path = request.path
    endpoint_type = "unknown"
    if 'analytics' in path:
        endpoint_type = "analytics"
    elif 'admin' in path:
        endpoint_type = "admin"
    elif 'wishlist' in path:
        endpoint_type = "wishlist"
    elif 'review' in path:
        endpoint_type = "reviews"
    elif 'products' in path:
        endpoint_type = "products"
    elif 'categories' in path:
        endpoint_type = "categories"
    
    # Log the rate limit event
    duration_ms = (time.time() - start_time) * 1000
    log_action(
        logger=logger,
        severity=LogSeverity.WARNING,
        action="rate_limit_exceeded",
        description=f"Rate limit exceeded for {endpoint_type} endpoint",
        status_code=429,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={
            "endpoint_type": endpoint_type,
            "path": path,
            "method": request.method,
            "user_email": user_email,
            "duration_ms": round(duration_ms, 2)
        }
    )
    
    response = JsonResponse({
        "error": "rate_limit_exceeded",
        "message": "Too many requests. Please try again later.",
        "status": 429
    }, status=429)
    
    return response