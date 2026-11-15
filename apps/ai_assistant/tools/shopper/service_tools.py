"""Read-only discovery of publicly available services."""
import json
import logging

from django.db.models import Q
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.services.schemas.service_schemas import serialize_category, serialize_service
from apps.services.selectors.service_selectors import public_categories, public_services

logger = logging.getLogger(__name__)


class ServiceSearchInput(BaseModel):
    query: str = Field(default="", max_length=200, description="Short service keywords")
    category_slug: str | None = Field(default=None, max_length=120, description="Verified service category slug")
    limit: int = Field(default=10, ge=1, le=20)


class ServiceDetailInput(BaseModel):
    slug: str = Field(min_length=1, max_length=220, description="Exact service slug returned by search_services")


class ServiceComparisonInput(BaseModel):
    slugs: list[str] = Field(min_length=1, max_length=4, description="One to four verified service slugs; one service can have multiple options")


class ServiceCategoriesInput(BaseModel):
    search: str = Field(default="", max_length=100, description="Optional category keywords")


def _error():
    logger.exception("Shopper service catalog tool failed")
    return json.dumps({"success": False, "error": "Services are temporarily unavailable."})


@tool(args_schema=ServiceSearchInput)
def search_services(query: str = "", category_slug: str | None = None, limit: int = 10) -> str:
    """Find published, publicly visible services by keywords and optional category."""
    try:
        services = public_services()
        if query.strip():
            q = query.strip()
            services = services.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))
        if category_slug:
            services = services.filter(category__slug=category_slug)
        results = [serialize_service(service) for service in services[:limit]]
        return json.dumps({"success": True, "services": results, "count": len(results)})
    except Exception:
        return _error()


@tool(args_schema=ServiceDetailInput)
def get_service_details(slug: str) -> str:
    """Get a visible service and its active options, prices, duration and images using its verified slug."""
    try:
        service = public_services().filter(slug=slug).first()
        if service is None:
            return json.dumps({"success": False, "error": "Service not found."})
        return json.dumps({"success": True, "service": serialize_service(service)})
    except Exception:
        return _error()


@tool(args_schema=ServiceCategoriesInput)
def list_service_categories(search: str = "") -> str:
    """List active, visible service categories, optionally filtered by name or description."""
    try:
        categories = [serialize_category(category) for category in public_categories(search.strip())[:100]]
        return json.dumps({"success": True, "categories": categories, "count": len(categories)})
    except Exception:
        return _error()


@tool(args_schema=ServiceComparisonInput)
def compare_services(slugs: list[str]) -> str:
    """Compare one to four verified services and their active options; do not infer missing prices."""
    try:
        unique_slugs = list(dict.fromkeys(slugs))
        services = {service.slug: service for service in public_services().filter(slug__in=unique_slugs)}
        missing = [slug for slug in unique_slugs if slug not in services]
        return json.dumps({"success": True, "services": [serialize_service(services[slug]) for slug in unique_slugs if slug in services], "not_found": missing})
    except Exception:
        return _error()
