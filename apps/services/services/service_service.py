from django.db import transaction
from django.utils import timezone

from apps.services.models import Service, ServiceCategory, ServiceImage, ServiceOption
from apps.services.schemas.service_schemas import _option_payload


class ServiceCatalogService:
    """Transactional writes for the independent service catalog."""

    @staticmethod
    @transaction.atomic
    def create_service(values, options_data=None):
        options_data = options_data or []
        if not isinstance(options_data, list):
            raise ValueError("Options must be a list")
        service = Service.objects.create(**values)
        for item in options_data:
            if not isinstance(item, dict):
                raise ValueError("Each option must be an object")
            create_option(service, _option_payload(item, service))
        if service.status == Service.PUBLISHED and not service.options.filter(is_active=True).exists():
            raise ValueError("Add at least one active option before publishing")
        return service

    @staticmethod
    @transaction.atomic
    def update_service(service, values):
        if values.get("status") == Service.PUBLISHED and not service.options.filter(is_active=True).exists():
            raise ValueError("Add at least one active option before publishing")
        if values.get("status") == Service.PUBLISHED and not service.published_at:
            values["published_at"] = timezone.now()
        for key, value in values.items():
            setattr(service, key, value)
        service.save()
        return service

    @staticmethod
    def archive_service(service):
        service.status = Service.ARCHIVED
        service.save(update_fields=["status", "updated_at"])
        return service


def create_service(values, options_data=None):
    return ServiceCatalogService.create_service(values, options_data)


def update_service(service, values):
    return ServiceCatalogService.update_service(service, values)


def archive_service(service):
    return ServiceCatalogService.archive_service(service)


@transaction.atomic
def create_option(service, values):
    if values["is_default"]:
        service.options.filter(is_default=True).update(is_default=False)
    return ServiceOption.objects.create(service=service, **values)


@transaction.atomic
def update_option(option, values):
    remains_active = values.get("is_active", option.is_active)
    if option.service.status == Service.PUBLISHED and option.is_active and not remains_active:
        if not option.service.options.filter(is_active=True).exclude(pk=option.pk).exists():
            raise ValueError("A published service must keep at least one active option")
    if values["is_default"]:
        option.service.options.exclude(pk=option.pk).filter(is_default=True).update(is_default=False)
    for key, value in values.items():
        setattr(option, key, value)
    option.save()
    return option


def delete_option(option):
    if option.service.status == Service.PUBLISHED and option.is_active:
        if not option.service.options.filter(is_active=True).exclude(pk=option.pk).exists():
            raise ValueError("A published service must keep at least one active option")
    option.delete()


@transaction.atomic
def create_category(values, image_file=None):
    category = ServiceCategory.objects.create(**values)
    if image_file:
        category.image.save(image_file.name, image_file, save=True)
    return category


def update_category(category, values, image_file=None):
    for key, value in values.items():
        setattr(category, key, value)
    old_image = category.image if image_file and category.image else None
    if image_file:
        category.image = image_file
    category.save()
    if old_image and old_image.name != category.image.name:
        transaction.on_commit(lambda: old_image.storage.delete(old_image.name), robust=True)
    return category


def delete_category(category):
    if category.services.exists() or category.children.exists():
        raise ValueError("Move or remove its services and child categories first")
    category.delete()


@transaction.atomic
def create_image(service, image_file, image_type, alt_text="", order=0):
    if image_type == ServiceImage.MAIN:
        service.images.filter(image_type=ServiceImage.MAIN).update(image_type=ServiceImage.GALLERY)
    return ServiceImage.objects.create(service=service, image=image_file, image_type=image_type,
                                       alt_text=alt_text, order=order)


def delete_image(image):
    image.delete()


def validate_category_image(image):
    if not image:
        return
    if image.size > 5 * 1024 * 1024:
        raise ValueError("Image file too large. Maximum size is 5MB")
    from PIL import Image
    try:
        with Image.open(image) as uploaded:
            if uploaded.format not in ("JPEG", "PNG", "GIF", "WEBP"):
                raise ValueError("Unsupported image type")
            uploaded.verify()
        image.seek(0)
    except Exception as exc:
        raise ValueError("Invalid image file") from exc
