import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from apps.users.decorators.auth import role_required
from estore.utils.responses import APIResponse
from apps.common.utils import sanitize_search_query
from apps.services.models import Service, ServiceCategory, ServiceImage, ServiceOption
from apps.services.schemas import serialize_category, serialize_option, serialize_image, serialize_service, _payload, _bool, _slug, _service_payload, _option_payload

logger = logging.getLogger(__name__)

def _admin(view):
    return role_required("admin", "staff")(view)

from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError
from django.utils import timezone
from apps.services.selectors.service_selectors import public_services, get_public_service, admin_services_queryset
from apps.services.services.service_service import create_service, update_service, archive_service

@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def service_list(request):
    qs = public_services()
    search = sanitize_search_query(request.GET.get("search", ""))
    if search: qs = qs.filter(Q(title__icontains=search) | Q(short_description__icontains=search) | Q(description__icontains=search))
    category = request.GET.get("category")
    if category: qs = qs.filter(category__slug=category, category__is_active=True, category__is_hidden=False)
    if request.GET.get("featured") is not None:
        try: qs = qs.filter(is_featured=_bool(request.GET.get("featured")))
        except ValueError as e: return APIResponse.bad_request(str(e))
    sort = request.GET.get("sort", "newest")
    ordering = {"newest": "-published_at", "name": "title", "featured": "-is_featured", "order": "sort_order"}.get(sort)
    if not ordering: return APIResponse.bad_request("Invalid sort value")
    try:
        page, limit = max(1, int(request.GET.get("page", 1))), min(100, max(1, int(request.GET.get("limit", 20))))
    except ValueError: return APIResponse.bad_request("Page and limit must be integers")
    paginator = Paginator(qs.order_by(ordering, "title"), limit)
    current = paginator.get_page(page)
    return APIResponse.success({"services": [serialize_service(s) for s in current.object_list], "total": paginator.count,
                                "pagination": {"page": current.number, "limit": limit, "total_pages": paginator.num_pages,
                                               "has_next": current.has_next(), "has_previous": current.has_previous()}}, "Services retrieved")


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def service_detail(request, slug):
    service = get_public_service(slug)
    if not service: return APIResponse.not_found("Service not found")
    return APIResponse.success({"service": serialize_service(service)}, "Service retrieved")


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_services(request):
    if request.method == "GET":
        status = request.GET.get("status")
        search = sanitize_search_query(request.GET.get("search", ""))
        qs = admin_services_queryset(status, search)
        try: page, limit = max(1, int(request.GET.get("page", 1))), min(100, max(1, int(request.GET.get("limit", 20))))
        except ValueError: return APIResponse.bad_request("Page and limit must be integers")
        paged = Paginator(qs.order_by("sort_order", "-created_at"), limit).get_page(page)
        return APIResponse.success({"services": [serialize_service(s, True) for s in paged.object_list], "total": paged.paginator.count,
                                    "pagination": {"page": paged.number, "limit": limit, "total_pages": paged.paginator.num_pages}}, "Services retrieved")
    try:
        data = _payload(request)
        options_data = data.pop("options", [])
        values = _service_payload(data)
        if values.get("status") == Service.PUBLISHED: values["published_at"] = timezone.now()
        service = create_service(values, options_data)
        return APIResponse.created({"service": serialize_service(service, True)}, "Service created")
    except ValueError as e: return APIResponse.validation_error({"service": str(e)})
    except IntegrityError: return APIResponse.conflict("A service with this slug already exists")
    except Exception:
        logger.exception("Service catalog operation failed")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="50/h", method=("PUT", "PATCH"), block=True)
@ratelimit(key="user", rate="20/h", method="DELETE", block=True)
def admin_service_detail(request, service_id):
    service = Service.objects.filter(pk=service_id).select_related("category").prefetch_related("options", "images").first()
    if not service: return APIResponse.not_found("Service not found")
    if request.method == "GET": return APIResponse.success({"service": serialize_service(service, True)}, "Service retrieved")
    if request.method == "DELETE":
        service = archive_service(service)
        return APIResponse.success({"service_id": str(service.id)}, "Service archived")
    try:
        values = _service_payload(_payload(request), service)
        service = update_service(service, values)
        return APIResponse.success({"service": serialize_service(service, True)}, "Service updated")
    except ValueError as e: return APIResponse.validation_error({"service": str(e)})
    except IntegrityError: return APIResponse.conflict("A service with this slug already exists")
    except Exception:
        logger.exception("Service catalog operation failed")
        return APIResponse.server_error()

