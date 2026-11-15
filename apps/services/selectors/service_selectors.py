from django.db.models import Q, Prefetch

from apps.services.models import Service, ServiceCategory, ServiceOption, ServiceImage


def public_services():
    return Service.objects.filter(status=Service.PUBLISHED).filter(
        Q(category__isnull=True) | Q(category__is_active=True, category__is_hidden=False)
    ).select_related("category").prefetch_related(
        Prefetch("options", queryset=ServiceOption.objects.filter(is_active=True), to_attr="public_options"),
        Prefetch("images", queryset=ServiceImage.objects.filter(is_active=True), to_attr="public_images"),
    )


def get_public_service(slug):
    return public_services().filter(slug=slug).first()


def admin_services_queryset(status=None, search=None):
    queryset = Service.objects.select_related("category").prefetch_related("options", "images")
    if status in dict(Service.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(Q(title__icontains=search) | Q(slug__icontains=search))
    return queryset


def public_categories(search=None):
    queryset = ServiceCategory.objects.filter(is_active=True, is_hidden=False).select_related("parent")
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
    return queryset

