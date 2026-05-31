"""
Common Log Views - View and filter logs from all apps
"""

import logging
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required
from apps.common.logging import log_action, LogSeverity, get_user_info
from apps.common.models import SystemLog

logger = logging.getLogger(__name__)
APP_NAME = "common"


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def log_list(request):
    """
    Get filtered list of logs for admin UI.
    
    Query parameters:
    - app_name: Filter by app (products, orders, users, promotions, common)
    - page: Page number (default: 1)
    - limit: Items per page (default: 50, max: 200)
    - severity: Filter by severity (INFO, WARNING, ERROR, CRITICAL)
    - action: Filter by action name
    - status_code: Filter by HTTP status code
    - user_email: Filter by user email
    - start_date: Filter by start date (YYYY-MM-DD)
    - end_date: Filter by end date (YYYY-MM-DD)
    - search: Search in description and action
    """
    start_time = time.time()
    action = "log_list"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving logs",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        # Parse query parameters
        page = int(request.GET.get('page', 1))
        limit = min(int(request.GET.get('limit', 50)), 200)
        
        app_name = request.GET.get('app_name')
        severity = request.GET.get('severity')
        action_filter = request.GET.get('action')
        status_code = request.GET.get('status_code')
        user_email = request.GET.get('user_email')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        search = request.GET.get('search', '').strip()
        
        # Build queryset
        queryset = SystemLog.objects.all()
        
        # Apply filters
        if app_name:
            queryset = queryset.filter(app_name=app_name)
        
        if severity:
            queryset = queryset.filter(severity=severity)
        
        if action_filter:
            queryset = queryset.filter(action=action_filter)
        
        if status_code:
            try:
                status_code_int = int(status_code)
                queryset = queryset.filter(status_code=status_code_int)
            except ValueError:
                pass
        
        if user_email:
            queryset = queryset.filter(user_email__icontains=user_email)
        
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(action__icontains=search) |
                Q(user_email__icontains=search)
            )
        
        # Order by most recent first
        queryset = queryset.order_by('-created_at')
        
        # Get total count
        total = queryset.count()
        
        # Apply pagination
        paginator = Paginator(queryset, limit)
        
        try:
            logs_page = paginator.page(page)
        except PageNotAnInteger:
            logs_page = paginator.page(1)
            page = 1
        except EmptyPage:
            logs_page = paginator.page(paginator.num_pages)
            page = paginator.num_pages
        
        # Serialize logs
        logs_data = []
        for log in logs_page:
            logs_data.append({
                "id": str(log.id),
                "app_name": log.app_name,
                "action": log.action,
                "severity": log.severity,
                "description": log.description,
                "status_code": log.status_code,
                "user_email": log.user_email,
                "ip_address": log.ip_address,
                "path": log.path,
                "method": log.method,
                "extra_data": log.extra_data,
                "created_at": log.created_at.isoformat(),
            })
        
        # Pagination metadata
        total_pages = paginator.num_pages
        has_next = logs_page.has_next()
        has_previous = logs_page.has_previous()
        
        pagination_meta = {
            "current_page": page,
            "per_page": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_previous": has_previous,
            "next_page": page + 1 if has_next else None,
            "previous_page": page - 1 if has_previous else None,
        }
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Logs retrieved: {total} total",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "app_name_filter": app_name,
                "total_logs": total,
                "logs_returned": len(logs_data),
                "page": page,
                "limit": limit,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "logs": logs_data,
                "total": total,
                "pagination": pagination_meta
            },
            message="Logs retrieved successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve logs: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def log_detail(request, log_id):
    """
    Get a single log entry by ID.
    """
    start_time = time.time()
    action = "log_detail"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving log detail: {log_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "log_id": log_id}
    )
    
    try:
        log_entry = SystemLog.objects.get(id=log_id)
        
        log_data = {
            "id": str(log_entry.id),
            "app_name": log_entry.app_name,
            "action": log_entry.action,
            "severity": log_entry.severity,
            "description": log_entry.description,
            "status_code": log_entry.status_code,
            "user_email": log_entry.user_email,
            "ip_address": log_entry.ip_address,
            "path": log_entry.path,
            "method": log_entry.method,
            "extra_data": log_entry.extra_data,
            "created_at": log_entry.created_at.isoformat(),
        }
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Log detail retrieved: {log_id}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "log_id": log_id,
                "app_name": log_entry.app_name,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=log_data,
            message="Log detail retrieved successfully"
        )
        
    except SystemLog.DoesNotExist:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action=action,
            description=f"Log not found: {log_id}",
            status_code=404,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"log_id": log_id, "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.not_found(f"Log with id {log_id} not found")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve log detail: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"log_id": log_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='50/h', method='GET', block=True)
def log_stats(request):
    """
    Get statistics about logs for dashboard.
    
    Query parameters:
    - app_name: Filter by app (products, orders, users, etc.)
    - days: Number of days to analyze (default: 7)
    """
    start_time = time.time()
    action = "log_stats"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving log statistics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        days = int(request.GET.get('days', 7))
        app_name = request.GET.get('app_name')
        since = timezone.now() - timedelta(days=days)
        
        # Base queryset
        base_queryset = SystemLog.objects.filter(created_at__gte=since)
        
        if app_name:
            base_queryset = base_queryset.filter(app_name=app_name)
        
        # Total count
        total_logs = base_queryset.count()
        
        # Logs by app
        logs_by_app = dict(
            base_queryset.values('app_name')
            .annotate(count=Count('id'))
            .values_list('app_name', 'count')
        )
        
        # Logs by severity
        logs_by_severity = dict(
            base_queryset.values('severity')
            .annotate(count=Count('id'))
            .values_list('severity', 'count')
        )
        
        # Ensure all severity levels are present
        for severity in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            if severity not in logs_by_severity:
                logs_by_severity[severity] = 0
        
        # Logs by action (top 10)
        logs_by_action = list(
            base_queryset.values('action')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )
        
        # Error rate (4xx and 5xx responses)
        client_errors = base_queryset.filter(status_code__gte=400, status_code__lt=500).count()
        server_errors = base_queryset.filter(status_code__gte=500).count()
        error_rate = round(((client_errors + server_errors) / total_logs * 100), 2) if total_logs > 0 else 0
        
        # Daily log counts
        from django.db.models.functions import TruncDate
        daily_logs = list(
            base_queryset.annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Log statistics retrieved for last {days} days",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "app_name_filter": app_name,
                "days_analyzed": days,
                "total_logs": total_logs,
                "error_rate": error_rate,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "period_days": days,
                "app_name": app_name,
                "total_logs": total_logs,
                "error_rate": error_rate,
                "client_errors": client_errors,
                "server_errors": server_errors,
                "logs_by_app": logs_by_app,
                "logs_by_severity": logs_by_severity,
                "logs_by_action": logs_by_action,
                "daily_logs": daily_logs,
            },
            message="Log statistics retrieved successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve log stats: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def log_apps(request):
    """
    Get list of all apps that have logs.
    Useful for app filter dropdown.
    """
    start_time = time.time()
    action = "log_apps"
    user = request.user
    
    try:
        apps = SystemLog.objects.values('app_name')\
            .annotate(count=Count('id'))\
            .order_by('app_name')
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Log apps retrieved",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "total_apps": apps.count(),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(
            data={
                "apps": [
                    {"name": app['app_name'], "log_count": app['count']}
                    for app in apps
                ]
            },
            message="Log apps retrieved successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to retrieve log apps: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()