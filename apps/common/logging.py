"""
Structured logging utility for consistent log formatting
"""

import logging
import json
from typing import Optional, Dict, Any
from enum import Enum
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from django.utils.timezone import now


class LogSeverity(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def get_user_info(user: Any) -> str:
    """Extract user identifier from user object"""
    if not user:
        return "anonymous"
    if isinstance(user, AnonymousUser):
        return "anonymous"
    if hasattr(user, 'email') and user.email:
        return user.email
    if hasattr(user, 'id'):
        return str(user.id)
    return "unknown"


def get_client_ip(request: HttpRequest) -> Optional[str]:
    """Client IP for logging. Behind proxies (Render/Cloudflare) the
    X-Forwarded-For header is a comma-separated chain — the first entry is
    the client. The DB column is a single inet, so never store the chain."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


def get_request_info(request: HttpRequest) -> Dict[str, Any]:
    """Extract relevant info from request for logging"""
    info = {
        "method": request.method,
        "path": request.path,
        "ip": get_client_ip(request) or 'unknown',
    }
    
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if user_agent:
        info["user_agent"] = user_agent[:100]
    
    return info


def _infer_app_name(request=None, action=None):
    """Infer app name from request path or action"""
    if request:
        path = request.path
        if '/admin/products/' in path or '/products/' in path:
            return "products"
        elif '/admin/orders/' in path or '/orders/' in path:
            return "orders"
        elif '/admin/users/' in path or '/users/' in path:
            return "users"
        elif '/admin/promotions/' in path:
            return "promotions"
    
    if action:
        if action.startswith('analytics_') or action.startswith('product_') or action.startswith('variant_'):
            return "products"
        elif action.startswith('category_'):
            return "products"
        elif action.startswith('order_'):
            return "orders"
    
    return "unknown"


def log_action(
    logger: logging.Logger,
    severity: LogSeverity,
    action: str,
    description: str,
    status_code: int,
    user: Optional[Any] = None,
    request: Optional[HttpRequest] = None,
    extra: Optional[Dict[str, Any]] = None,
    app_name: Optional[str] = None,
) -> None:
    """
    Log a structured action with consistent formatting.
    
    Format includes app field for UI filtering:
    [SEVERITY] app=products | action=analytics_overview | status=200 | user=admin@x.com | ip=127.0.0.1 | desc=... | extra={...}
    """
    log_parts = []
    
    # Determine app name
    final_app_name = app_name or _infer_app_name(request, action)
    log_parts.append(f"app={final_app_name}")
    
    log_parts.extend([
        f"action={action}",
        f"status={status_code}",
        f"user={get_user_info(user)}",
    ])
    
    # Add request IP if available
    if request:
        log_parts.append(f"ip={get_client_ip(request) or 'unknown'}")
    
    log_parts.append(f"desc={description}")
    
    # Add timestamp for filtering
    timestamp = now().isoformat()
    log_parts.append(f"timestamp={timestamp}")
    
    if extra:
        # Convert extra dict to JSON string for easier parsing
        extra_str = json.dumps(extra, default=str)
        log_parts.append(f"extra={extra_str}")
    
    message = " | ".join(log_parts)
    
    log_method = {
        LogSeverity.DEBUG: logger.debug,
        LogSeverity.INFO: logger.info,
        LogSeverity.WARNING: logger.warning,
        LogSeverity.ERROR: logger.error,
        LogSeverity.CRITICAL: logger.critical,
    }.get(severity, logger.info)
    
    log_method(message)
    
    # Save to database asynchronously (non-blocking)
    _save_log_to_db_async(
        app_name=final_app_name,
        action=action,
        severity=severity.value,
        description=description,
        status_code=status_code,
        user=user,
        request=request,
        extra=extra,
    )


def _save_log_to_db_async(app_name, action, severity, description, status_code, user, request, extra):
    """
    Save log to database in a non-blocking way.
    Only save for completed requests (status_code > 0) and important logs.
    """
    # Only save for non-DEBUG logs or when status_code indicates issue
    if status_code == 0:  # Request start, don't save
        return
    
    # Don't save DEBUG logs to DB to reduce noise
    if severity == "DEBUG":
        return
    
    try:
        # Import here to avoid circular imports
        from apps.common.models import SystemLog
        from django.db import transaction

        # Get user info
        user_id = None
        user_email = None
        if user:
            user_id = str(user.id) if hasattr(user, 'id') else None
            user_email = user.email if hasattr(user, 'email') else None

        # Get request info
        ip_address = None
        path = None
        method = None
        if request:
            ip_address = get_client_ip(request)
            path = request.path
            method = request.method

        # Coerce non-JSON-native values (UUID, Decimal, datetime, ...) so the
        # JSONField write can never fail on serialization.
        safe_extra = {}
        if extra:
            try:
                safe_extra = json.loads(json.dumps(extra, default=str))
            except (TypeError, ValueError):
                safe_extra = {"_unserializable": str(extra)[:1000]}

        # Write inside a savepoint. Audit logging must NEVER be able to roll back
        # the caller's business transaction: if the INSERT fails while we are
        # already inside an atomic block, a bare failure would mark the whole
        # transaction broken. The nested atomic() confines any failure to this
        # savepoint so the caller's writes still commit.
        with transaction.atomic():
            SystemLog.objects.create(
                app_name=app_name[:50],
                action=action[:100],
                severity=severity,
                description=description[:1000],
                status_code=status_code,
                user_id=user_id,
                user_email=user_email,
                ip_address=ip_address,
                path=path[:500] if path else None,
                method=method[:10] if method else None,
                extra_data=safe_extra,
            )
    except Exception as db_error:
        # Silently fail - don't let DB errors break the main logging
        # Use print for debugging in development
        import sys
        print(f"Failed to save log to database: {db_error}", file=sys.stderr)