import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from apps.users.decorators.auth import role_required
from estore.utils.responses import APIResponse
from apps.common.utils import sanitize_search_query
from apps.services.models import Service, ServiceCategory, ServiceImage, ServiceOption
from apps.services.schemas import serialize_category, serialize_option, serialize_image, serialize_service, _payload, _bool, _slug, _service_payload, _option_payload, category_payload

logger = logging.getLogger(__name__)

def _admin(view):
    return role_required("admin", "staff")(view)

from django.db.models import Q
from django.db import IntegrityError
from apps.services.selectors.service_selectors import public_categories
from apps.services.services.service_service import create_category, update_category, delete_category
from apps.services.services.service_service import validate_category_image

@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def category_list(request):
    search = sanitize_search_query(request.GET.get("search", ""))
    qs = public_categories(search)
    return APIResponse.success({"categories": [serialize_category(c) for c in qs]}, "Service categories retrieved")


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def category_detail(request, slug):
    category = ServiceCategory.objects.filter(slug=slug, is_active=True, is_hidden=False).first()
    if not category: return APIResponse.not_found("Service category not found")
    return APIResponse.success({"category": serialize_category(category)}, "Service category retrieved")


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_service_categories(request):
    if request.method == "GET":
        qs = ServiceCategory.objects.select_related("parent").order_by("sort_order", "name")
        if request.GET.get("status") != "all": qs = qs.filter(is_active=True)
        return APIResponse.success({"categories": [serialize_category(c, True) for c in qs]}, "Service categories retrieved")
    try:
        data = _payload(request)
        validate_category_image(request.FILES.get("image"))
        category = create_category(category_payload(data), request.FILES.get("image"))
        return APIResponse.created({"category": serialize_category(category, True)}, "Service category created")
    except (ValueError, ServiceCategory.DoesNotExist) as e: return APIResponse.validation_error({"category": str(e)})
    except IntegrityError: return APIResponse.conflict("Category name or slug already exists")
    except Exception:
        logger.exception("Service catalog operation failed")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="80/h", method=(["PUT", "PATCH", "DELETE"]), block=True)
def admin_service_category_detail(request, category_id):
    category = ServiceCategory.objects.filter(pk=category_id).first()
    if not category: return APIResponse.not_found("Service category not found")
    if request.method == "GET": return APIResponse.success({"category": serialize_category(category, True)}, "Category retrieved")
    if request.method == "DELETE":
        if category.services.exists() or category.children.exists(): return APIResponse.conflict("Move or remove its services and child categories first")
        delete_category(category); return APIResponse.no_content()
    try:
        data = _payload(request)
        image_file = request.FILES.get("image")
        validate_category_image(image_file)
        category = update_category(category, category_payload(data, category), image_file)
        return APIResponse.success({"category": serialize_category(category, True)}, "Category updated")
    except (ValueError, IntegrityError): return APIResponse.validation_error({"category": "Invalid or duplicate category values"})

