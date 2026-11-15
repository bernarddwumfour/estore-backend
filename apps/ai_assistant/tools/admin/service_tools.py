"""Staff-only service catalog and appointment queries."""
import json
from datetime import date
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Any, Literal

from apps.ai_assistant.tools.admin.product_tools import _authorized
from apps.ai_assistant.tools.admin.product_write_tools import _prepare
from apps.services.models import Appointment, BookingException, BookingHours, BookingSettings, Service, ServiceCategory
from apps.services.schemas.service_schemas import serialize_category, serialize_service
from apps.services.selectors.service_selectors import admin_services_queryset
from apps.services.views.booking_views import serialize_appointment


def result(config, data=None, error=None):
    if not _authorized(config or {}):
        return json.dumps({"success": False, "error": "Admin access required."})
    return json.dumps({"success": error is None, "data": data, "error": error}, default=str)


class SearchInput(BaseModel):
    search: str = Field(default="", max_length=200)
    status: str = Field(default="all", description="all, draft, published, or archived")
    limit: int = Field(default=10, ge=1, le=20)


class ServiceInput(BaseModel):
    service_id: UUID


class AppointmentSearchInput(BaseModel):
    day: date | None = None
    status: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class AppointmentInput(BaseModel):
    appointment_id: UUID


class PrepareServiceActionInput(BaseModel):
    action: Literal["create_service", "update_service", "create_service_option", "update_service_option", "create_service_category", "update_service_category", "update_appointment", "update_booking_settings", "set_booking_exception", "delete_booking_exception"]
    target_id: UUID | None = Field(default=None, description="Existing service, option, category or appointment ID, as appropriate")
    changes: dict[str, Any] = Field(description="Requested field values; appointment changes support status only")


@tool(args_schema=PrepareServiceActionInput)
def prepare_admin_service_action(action: str, changes: dict[str, Any], target_id: UUID | None = None, config: RunnableConfig = None) -> str:
    """Prepare a service, option, category, appointment status, booking settings, or date exception change for staff confirmation."""
    return _prepare(config or {}, action, {"target_id": str(target_id) if target_id else "", "data": changes})


@tool(args_schema=SearchInput)
def search_admin_services(search: str = "", status: str = "all", limit: int = 10, config: RunnableConfig = None) -> str:
    """Search all service catalog entries including drafts and archived services."""
    if not _authorized(config or {}): return result(config)
    if status not in {"all", "draft", "published", "archived"}: return result(config, error="Invalid status.")
    return result(config, {"services": [serialize_service(s, True) for s in admin_services_queryset(status, search)[:limit]]})


@tool(args_schema=ServiceInput)
def get_admin_service(service_id: UUID, config: RunnableConfig) -> str:
    """Get a service with its options and administrative fields by exact ID."""
    if not _authorized(config): return result(config)
    item = Service.objects.select_related("category").prefetch_related("options", "images").filter(pk=service_id).first()
    return result(config, serialize_service(item, True) if item else None, None if item else "Service not found.")


@tool
def list_admin_service_categories(config: RunnableConfig) -> str:
    """List service categories including hidden and inactive categories."""
    if not _authorized(config): return result(config)
    return result(config, {"categories": [serialize_category(c, True) for c in ServiceCategory.objects.all()[:100]]})


@tool(args_schema=AppointmentSearchInput)
def search_admin_appointments(day: date | None = None, status: str | None = None, limit: int = 10, config: RunnableConfig = None) -> str:
    """Find appointments by date in the configured store timezone and/or status."""
    if not _authorized(config or {}): return result(config)
    if status and status not in dict(Appointment.STATUS_CHOICES): return result(config, error="Invalid appointment status.")
    items = Appointment.objects.all()
    if status: items = items.filter(status=status)
    if day:
        from zoneinfo import ZoneInfo
        from datetime import datetime, time, timedelta
        settings = BookingSettings.objects.filter(pk=1).first()
        zone = ZoneInfo(settings.timezone if settings else "Africa/Accra")
        start = datetime.combine(day, time.min, tzinfo=zone)
        items = items.filter(starts_at__gte=start, starts_at__lt=start + timedelta(days=1))
    return result(config, {"appointments": [serialize_appointment(a) for a in items[:limit]]})


@tool(args_schema=AppointmentInput)
def get_admin_appointment(appointment_id: UUID, config: RunnableConfig) -> str:
    """Get an appointment by its verified ID."""
    if not _authorized(config): return result(config)
    item = Appointment.objects.filter(pk=appointment_id).first()
    return result(config, serialize_appointment(item) if item else None, None if item else "Appointment not found.")


@tool
def get_admin_booking_settings(config: RunnableConfig) -> str:
    """Get store booking availability settings, weekly hours, and date exceptions."""
    if not _authorized(config): return result(config)
    settings = BookingSettings.objects.filter(pk=1).first()
    return result(config, {"enabled": settings.enabled if settings else False,
        "timezone": settings.timezone if settings else "Africa/Accra",
        "slot_interval_minutes": settings.slot_interval_minutes if settings else 30,
        "hours": list(BookingHours.objects.values("weekday", "opens_at", "closes_at", "is_open")),
        "exceptions": list(BookingException.objects.order_by("date").values("date", "is_closed", "opens_at", "closes_at")[:100])})
