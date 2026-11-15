import json
from decimal import Decimal, InvalidOperation
from django.utils.text import slugify
from apps.services.models import Service, ServiceCategory, ServiceImage, ServiceOption

def _url(field):
    try:
        return field.url if field else None
    except (ValueError, OSError):
        return None


def serialize_category(category, admin=False):
    result = {"id": str(category.id), "name": category.name, "slug": category.slug,
              "description": category.description, "image": _url(category.image)}
    if admin:
        result.update(parent_id=str(category.parent_id) if category.parent_id else None,
                      is_hidden=category.is_hidden, is_active=category.is_active, sort_order=category.sort_order,
                      meta_title=category.meta_title, meta_description=category.meta_description,
                      created_at=category.created_at.isoformat(), updated_at=category.updated_at.isoformat())
    return result


def serialize_option(option, admin=False):
    result = {"id": str(option.id), "name": option.name, "slug": option.slug, "description": option.description,
              "pricing_type": option.pricing_type, "price": str(option.price) if option.price is not None else None,
              "duration_minutes": option.duration_minutes}
    if admin:
        result.update(is_default=option.is_default, is_active=option.is_active, sort_order=option.sort_order,
                      created_at=option.created_at.isoformat(), updated_at=option.updated_at.isoformat())
    return result


def serialize_image(image):
    return {"id": str(image.id), "url": _url(image.image), "image_type": image.image_type,
            "alt_text": image.alt_text, "order": image.order}


def serialize_service(service, admin=False):
    options = service.options.all() if admin else getattr(service, "public_options", None) if hasattr(service, "public_options") else service.options.filter(is_active=True)
    images = service.images.all() if admin else getattr(service, "public_images", None) if hasattr(service, "public_images") else service.images.filter(is_active=True)
    result = {"id": str(service.id), "title": service.title, "slug": service.slug,
              "short_description": service.short_description, "description": service.description,
              "category": serialize_category(service.category, admin) if service.category else None,
              "features": service.features, "is_featured": service.is_featured,
              "options": [serialize_option(o, admin) for o in options],
              "images": [serialize_image(i) for i in images]}
    if admin:
        result.update(status=service.status, sort_order=service.sort_order,
                      meta_title=service.meta_title, meta_description=service.meta_description,
                      created_at=service.created_at.isoformat(), updated_at=service.updated_at.isoformat(),
                      published_at=service.published_at.isoformat() if service.published_at else None)
    return result


def _payload(request):
    if request.content_type and "multipart/form-data" in request.content_type:
        return request.POST.dict()
    if request.content_type != "application/json":
        raise ValueError("Content-Type must be application/json or multipart/form-data")
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError("Request body must be an object")
        return data
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON data")


def _bool(value, default=False):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if str(value).lower() in ("true", "1", "yes", "on"):
        return True
    if str(value).lower() in ("false", "0", "no", "off"):
        return False
    raise ValueError("Expected a boolean value")


def _slug(model, value, fallback, exclude_id=None):
    base = slugify(value or fallback)[:210] or "service"
    candidate, suffix = base, 2
    qs = model.objects.all()
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    while qs.filter(slug=candidate).exists():
        candidate = f"{base[:200]}-{suffix}"
        suffix += 1
    return candidate


def _service_payload(data, instance=None):
    allowed = {"title", "slug", "short_description", "description", "category_id", "features", "status",
               "is_featured", "sort_order", "meta_title", "meta_description"}
    values = {key: data[key] for key in allowed if key in data}
    title = str(values.get("title", instance.title if instance else "")).strip()
    if not title:
        raise ValueError("Title is required")
    if len(title) > 200:
        raise ValueError("Title must be 200 characters or fewer")
    values["title"] = title
    if "slug" in values or not instance or title != instance.title:
        values["slug"] = _slug(Service, values.get("slug") or title, title, instance.id if instance else None)
    if "category_id" in values and values["category_id"]:
        try:
            values["category"] = ServiceCategory.objects.get(pk=values.pop("category_id"))
        except (ServiceCategory.DoesNotExist, ValueError):
            raise ValueError("Category was not found")
    elif "category_id" in values:
        values.pop("category_id")
        values["category"] = None
    if "features" in values and not isinstance(values["features"], list):
        raise ValueError("Features must be a list of strings")
    if "features" in values and not all(isinstance(x, str) for x in values["features"]):
        raise ValueError("Features must be a list of strings")
    if "status" in values and values["status"] not in dict(Service.STATUS_CHOICES):
        raise ValueError("Status must be draft, published, or archived")
    if "is_featured" in values:
        values["is_featured"] = _bool(values["is_featured"])
    if "sort_order" in values:
        values["sort_order"] = int(values["sort_order"])
        if values["sort_order"] < 0: raise ValueError("Sort order cannot be negative")
    for field, limit in (("short_description", 300), ("meta_title", 200)):
        if field in values and len(str(values[field] or "")) > limit:
            raise ValueError(f"{field} must be {limit} characters or fewer")
    for key in ("short_description", "description", "meta_title", "meta_description"):
        if key in values: values[key] = str(values[key] or "").strip()
    return values


def _option_payload(data, service, instance=None):
    name = str(data.get("name", instance.name if instance else "")).strip()
    if not name: raise ValueError("Option name is required")
    if len(name) > 120: raise ValueError("Option name must be 120 characters or fewer")
    if len(str(data.get("description", instance.description if instance else "") or "")) > 300: raise ValueError("Description must be 300 characters or fewer")
    pricing = data.get("pricing_type", instance.pricing_type if instance else "fixed")
    if pricing not in dict(ServiceOption.PRICING_CHOICES): raise ValueError("Invalid pricing_type")
    raw_price = data.get("price", instance.price if instance else None)
    if pricing == ServiceOption.QUOTE:
        price = None
    else:
        if raw_price in (None, ""): raise ValueError("A price is required for fixed or from pricing")
        try: price = Decimal(str(raw_price))
        except InvalidOperation: raise ValueError("Price must be a valid number")
        if not price.is_finite() or price < 0: raise ValueError("Price must be zero or greater")
        if price.as_tuple().exponent < -2 or price >= Decimal("100000000"): raise ValueError("Price must fit within 8 digits and 2 decimal places")
    raw_duration = data.get("duration_minutes", instance.duration_minutes if instance else None)
    duration = int(raw_duration) if raw_duration not in (None, "") else None
    if duration is not None and duration < 1: raise ValueError("Duration must be a positive number of minutes")
    sort_order = int(data.get("sort_order", instance.sort_order if instance else 0))
    if sort_order < 0: raise ValueError("Sort order cannot be negative")
    slug = slugify(data.get("slug") or name)[:140] or "option"
    options = ServiceOption.objects.filter(service=service, slug=slug)
    if instance: options = options.exclude(pk=instance.pk)
    base, suffix = slug, 2
    while options.exists():
        slug = f"{base[:130]}-{suffix}"; suffix += 1
        options = ServiceOption.objects.filter(service=service, slug=slug)
        if instance: options = options.exclude(pk=instance.pk)
    return {"name": name, "slug": slug, "description": str(data.get("description", instance.description if instance else "") or "").strip(),
            "pricing_type": pricing, "price": price, "duration_minutes": duration,
            "is_default": _bool(data.get("is_default", instance.is_default if instance else False)),
            "is_active": _bool(data.get("is_active", instance.is_active if instance else True)),
            "sort_order": sort_order}


def category_payload(data, instance=None):
    values = {}
    if "name" in data or instance is None:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Name is required")
        if len(name) > 100: raise ValueError("Name must be 100 characters or fewer")
        values["name"] = name
    if "slug" in data or "name" in data or instance is None:
        name = values.get("name", instance.name if instance else "")
        values["slug"] = _slug(ServiceCategory, data.get("slug") or name, name, instance.id if instance else None)
    for field in ("description", "meta_title", "meta_description"):
        if field in data or instance is None:
            values[field] = str(data.get(field, "") or "").strip()
    for field, default in (("is_active", True), ("is_hidden", False)):
        if field in data or instance is None:
            values[field] = _bool(data.get(field), default)
    if "sort_order" in data or instance is None:
        values["sort_order"] = int(data.get("sort_order", 0))
        if values["sort_order"] < 0:
            raise ValueError("Sort order cannot be negative")
    if len(values.get("meta_title", "")) > 200:
        raise ValueError("Meta title must be 200 characters or fewer")
    if "parent_id" in data or instance is None:
        parent_id = data.get("parent_id")
        if parent_id:
            parent = ServiceCategory.objects.filter(pk=parent_id).first()
            if not parent:
                raise ValueError("Parent category was not found")
            if instance and parent.pk == instance.pk:
                raise ValueError("A category cannot be its own parent")
            seen = set()
            while parent:
                if parent.pk in seen or (instance and parent.pk == instance.pk):
                    raise ValueError("Category hierarchy cannot contain a cycle")
                seen.add(parent.pk)
                parent = parent.parent
            values["parent"] = ServiceCategory.objects.get(pk=parent_id)
        else:
            values["parent"] = None
    return values

