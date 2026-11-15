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

import os
from apps.services.services.service_service import create_image, delete_image
from django.db import IntegrityError

@csrf_exempt
@require_http_methods(["GET", "POST"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def admin_service_images(request, service_id):
    service = Service.objects.filter(pk=service_id).first()
    if not service: return APIResponse.not_found("Service not found")
    if request.method == "GET":
        return APIResponse.success({"images": [serialize_image(i) for i in service.images.all()]}, "Service images retrieved")
    image_file = request.FILES.get("image")
    if not image_file: return APIResponse.bad_request("No image file provided")
    try:
        from PIL import Image
        with Image.open(image_file) as uploaded:
            uploaded.verify()
        image_file.seek(0)
    except Exception:
        return APIResponse.bad_request("Invalid image file")
    ext = os.path.splitext(image_file.name)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"): return APIResponse.bad_request("Unsupported image type")
    if image_file.size > 5 * 1024 * 1024: return APIResponse.bad_request("Image file too large. Maximum size is 5MB")
    image_type = request.POST.get("image_type", "gallery")
    if image_type not in dict(ServiceImage.IMAGE_TYPES): return APIResponse.bad_request("Invalid image_type")
    try:
        order = int(request.POST.get("order", 0))
        if order < 0: return APIResponse.bad_request("Order cannot be negative")
    except ValueError: return APIResponse.bad_request("Order must be an integer")
    image = create_image(service, image_file, image_type, request.POST.get("alt_text", "")[:250], order)
    return APIResponse.created({"image": serialize_image(image)}, "Service image uploaded")


@csrf_exempt
@require_http_methods(["DELETE"])
@_admin
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="80/h", method="DELETE", block=True)
def admin_service_image_delete(request, service_id, image_id):
    image = ServiceImage.objects.filter(pk=image_id, service_id=service_id).first()
    if not image: return APIResponse.not_found("Service image not found")
    delete_image(image); return APIResponse.no_content()

