from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from apps.users.decorators.auth import role_required
from estore.utils.responses import APIResponse
from apps.common.utils import sanitize_search_query
from apps.services.models import Service, ServiceCategory, ServiceImage, ServiceOption
from apps.services.schemas import serialize_category, serialize_option, serialize_image, serialize_service, _payload, _bool, _slug, _service_payload, _option_payload

def _admin(view):
    return role_required("admin", "staff")(view)

from django.db import transaction
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.core.paginator import Paginator
from django.db.models import Q
from apps.services.services.service_service import create_option, update_option, delete_option

@csrf_exempt
@require_http_methods(["GET"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def admin_all_service_options(request):
    options = ServiceOption.objects.select_related("service")
    search = sanitize_search_query(request.GET.get("search", ""))
    if search:
        options = options.filter(Q(name__icontains=search) | Q(service__title__icontains=search))
    active = request.GET.get("is_active")
    if active in ("true", "false"):
        options = options.filter(is_active=active == "true")
    try:
        page = max(1, int(request.GET.get("page", 1)))
        limit = min(100, max(1, int(request.GET.get("limit", 20))))
    except ValueError:
        return APIResponse.bad_request("Page and limit must be integers")
    current = Paginator(options.order_by("service__title", "sort_order", "name"), limit).get_page(page)
    return APIResponse.success({
        "options": [
            {**serialize_option(option, True), "service": {
                "id": str(option.service_id), "title": option.service.title, "status": option.service.status,
            }} for option in current.object_list
        ],
        "total": current.paginator.count,
        "pagination": {"page": current.number, "limit": limit, "total_pages": current.paginator.num_pages},
    }, "Service options retrieved")

@csrf_exempt
@require_http_methods(["GET", "POST"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_service_options(request, service_id):
    service = Service.objects.filter(pk=service_id).first()
    if not service: return APIResponse.not_found("Service not found")
    if request.method == "GET":
        return APIResponse.success({"options": [serialize_option(o, True) for o in service.options.all()]}, "Service options retrieved")
    try:
        values = _option_payload(_payload(request), service)
        option = create_option(service, values)
        return APIResponse.created({"option": serialize_option(option, True)}, "Service option created")
    except ValueError as e: return APIResponse.validation_error({"option": str(e)})
    except IntegrityError: return APIResponse.conflict("Could not create service option")


@csrf_exempt
@require_http_methods(["PUT", "PATCH", "DELETE"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="80/h", method=(["PUT", "PATCH", "DELETE"]), block=True)
def admin_service_option_detail(request, service_id, option_id):
    option = ServiceOption.objects.filter(pk=option_id, service_id=service_id).first()
    if not option: return APIResponse.not_found("Service option not found")
    if request.method == "DELETE":
        try:
            delete_option(option)
            return APIResponse.no_content()
        except ValueError as e:
            return APIResponse.validation_error({"option": str(e)})
        except ProtectedError:
            return APIResponse.conflict("This option is used by an appointment and cannot be deleted")
    try:
        values = _option_payload(_payload(request), option.service, option)
        option = update_option(option, values)
        return APIResponse.success({"option": serialize_option(option, True)}, "Service option updated")
    except ValueError as e: return APIResponse.validation_error({"option": str(e)})
    except IntegrityError: return APIResponse.conflict("Could not update service option")

