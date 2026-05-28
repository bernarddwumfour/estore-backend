"""
Statistics Views - User statistics endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required
from apps.users.selectors import get_user_statistics as get_user_stats
from apps.users.schemas import serialize_user_statistics

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def user_statistics(request):
    """Admin: Get user statistics for dashboard"""
    try:
        stats = get_user_stats()

        return APIResponse.success(
            data=serialize_user_statistics(stats),
            message="User statistics retrieved successfully"
        )

    except Exception as e:
        logger.error(f"User statistics error: {str(e)}")
        return APIResponse.server_error()