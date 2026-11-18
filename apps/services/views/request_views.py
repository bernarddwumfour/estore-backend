import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.services.models import ServiceRequest
from apps.services.schemas.request_schemas import validate_service_request
from apps.services.schemas.service_schemas import _payload
from apps.services.selectors.service_selectors import get_public_service
from apps.services.services.request_service import create_service_request
from apps.users.decorators.auth import role_required
from estore.utils.responses import APIResponse


logger = logging.getLogger(__name__)


def serialize_request(item):
    return {
        "id": str(item.id),
        "service": item.service.title if item.service else item.custom_service_type,
        "device_model": item.device_model,
        "customer_name": item.customer_name,
        "customer_email": item.customer_email,
        "customer_phone": item.customer_phone,
        "issue_description": item.issue_description,
        "created_at": item.created_at.isoformat(),
    }


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate="10/h", method="POST", block=True)
def service_requests(request):
    try:
        data = _payload(request)
    except ValueError:
        return APIResponse.validation_error({"request": "Invalid JSON request"})
    values, errors = validate_service_request(data)
    if errors:
        return APIResponse.validation_error(errors)
    service = None
    if values["service_type"] != "other":
        service = get_public_service(values["service_type"])
        if not service:
            return APIResponse.validation_error({"service_type": "Service is unavailable"})
    try:
        item = create_service_request(values, service)
    except Exception:
        logger.exception("Could not save service request")
        return APIResponse.server_error()
    return APIResponse.created({"request": serialize_request(item)}, "Service request submitted")


@require_http_methods(["GET"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def admin_service_requests(request):
    items = ServiceRequest.objects.select_related("service")[:100]
    return APIResponse.success({"requests": [serialize_request(item) for item in items]}, "Service requests retrieved")
