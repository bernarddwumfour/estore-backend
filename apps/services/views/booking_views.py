from datetime import date

from django.db import transaction
from django.utils.dateparse import parse_datetime, parse_time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.services.models import Appointment, BookingException, BookingHours, BookingSettings
from apps.services.schemas.service_schemas import _payload
from apps.services.services.booking_service import available_slots, create_appointment
from apps.users.decorators.auth import jwt_required, role_required
from estore.utils.responses import APIResponse


def serialize_appointment(item):
    return {"id": str(item.pk), "service": item.service_title, "option": item.option_name,
            "pricing_type": item.pricing_type, "price": str(item.price) if item.price is not None else None,
            "starts_at": item.starts_at.isoformat(), "ends_at": item.ends_at.isoformat(),
            "status": item.status, "customer_name": item.customer_name, "customer_phone": item.customer_phone}


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def slots(request):
    try:
        day = date.fromisoformat(request.GET.get("date", ""))
        from uuid import UUID
        option_id = UUID(request.GET.get("option_id", ""))
        return APIResponse.success({"slots": available_slots(option_id, day)}, "Availability retrieved")
    except (ValueError, TypeError):
        return APIResponse.bad_request("A valid date and option_id are required")


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def appointments(request):
    if request.method == "GET":
        return APIResponse.success({"appointments": [serialize_appointment(a) for a in Appointment.objects.filter(user=request.user)[:100]]}, "Appointments retrieved")
    try:
        from uuid import UUID
        data = _payload(request)
        start = parse_datetime(data.get("starts_at", ""))
        if start is None:
            raise ValueError("A valid start time is required")
        item = create_appointment(request.user, UUID(data.get("option_id", "")), start,
                                  data.get("customer_name", ""), data.get("customer_phone", ""))
        return APIResponse.created({"appointment": serialize_appointment(item)}, "Appointment requested")
    except (ValueError, TypeError, AttributeError) as exc:
        return APIResponse.validation_error({"appointment": str(exc)})


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
@jwt_required
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="20/h", method="DELETE", block=True)
def appointment_detail(request, appointment_id):
    with transaction.atomic():
        BookingSettings.objects.select_for_update().filter(pk=1).first()
        item = Appointment.objects.select_for_update().filter(pk=appointment_id, user=request.user).first()
        if not item:
            return APIResponse.not_found("Appointment not found")
        if request.method == "DELETE":
            if item.status not in (Appointment.PENDING, Appointment.CONFIRMED):
                return APIResponse.validation_error({"appointment": "This appointment cannot be cancelled"})
            item.status = Appointment.CANCELLED
            item.save(update_fields=["status", "updated_at"])
    return APIResponse.success({"appointment": serialize_appointment(item)}, "Appointment retrieved")


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="50/h", method="PUT", block=True)
def booking_settings(request):
    config, _ = BookingSettings.objects.get_or_create(pk=1)
    if request.method == "PUT":
        try:
            from zoneinfo import ZoneInfo
            data = _payload(request)
            zone = str(data.get("timezone", config.timezone))
            ZoneInfo(zone)
            interval = int(data.get("slot_interval_minutes", config.slot_interval_minutes))
            if not 5 <= interval <= 240 or not isinstance(data.get("enabled", config.enabled), bool):
                raise ValueError("Invalid booking settings")
            with transaction.atomic():
                config = BookingSettings.objects.select_for_update().get(pk=1)
                config.timezone, config.slot_interval_minutes = zone, interval
                config.enabled = data.get("enabled", config.enabled)
                config.save()
                if "hours" in data:
                    entries = data["hours"]
                    if not isinstance(entries, list): raise ValueError("Hours must be a list")
                    BookingHours.objects.all().delete()
                    for entry in entries:
                        weekday = int(entry["weekday"])
                        opens, closes = parse_time(entry["opens_at"]), parse_time(entry["closes_at"])
                        if weekday not in range(7) or not opens or not closes or opens >= closes: raise ValueError("Invalid working hours")
                        BookingHours.objects.create(weekday=weekday, opens_at=opens, closes_at=closes, is_open=True)
        except Exception as exc:
            return APIResponse.validation_error({"settings": str(exc)})
    return APIResponse.success({"enabled": config.enabled, "timezone": config.timezone,
        "slot_interval_minutes": config.slot_interval_minutes,
        "hours": [{"weekday": h.weekday, "opens_at": h.opens_at.isoformat(), "closes_at": h.closes_at.isoformat()} for h in BookingHours.objects.filter(is_open=True)]}, "Booking settings retrieved")


@require_http_methods(["GET"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def admin_appointments(request):
    return APIResponse.success({"appointments": [serialize_appointment(a) for a in Appointment.objects.all()[:100]]}, "Appointments retrieved")


@csrf_exempt
@require_http_methods(["PATCH"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="50/h", method="PATCH", block=True)
def admin_appointment_detail(request, appointment_id):
    try:
        status = _payload(request).get("status")
        with transaction.atomic():
            BookingSettings.objects.select_for_update().filter(pk=1).first()
            item = Appointment.objects.select_for_update().filter(pk=appointment_id).first()
            if not item: return APIResponse.not_found("Appointment not found")
            transitions = {Appointment.PENDING: {Appointment.CONFIRMED, Appointment.CANCELLED},
                           Appointment.CONFIRMED: {Appointment.COMPLETED, Appointment.CANCELLED}}
            if status not in transitions.get(item.status, set()): raise ValueError("Invalid status transition")
            item.status = status
            item.save(update_fields=["status", "updated_at"])
        return APIResponse.success({"appointment": serialize_appointment(item)}, "Appointment updated")
    except ValueError as exc:
        return APIResponse.validation_error({"appointment": str(exc)})


@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
@ratelimit(key="user", rate="50/h", method=("POST", "DELETE"), block=True)
def booking_exceptions(request):
    if request.method == "GET":
        entries = BookingException.objects.order_by("date")
        return APIResponse.success({"exceptions": [{"date": e.date.isoformat(), "is_closed": e.is_closed,
            "opens_at": e.opens_at.isoformat() if e.opens_at else None,
            "closes_at": e.closes_at.isoformat() if e.closes_at else None} for e in entries]}, "Exceptions retrieved")
    try:
        data = _payload(request)
        day = date.fromisoformat(data.get("date", ""))
        with transaction.atomic():
            BookingSettings.objects.get_or_create(pk=1)
            BookingSettings.objects.select_for_update().get(pk=1)
            if request.method == "DELETE":
                BookingException.objects.filter(date=day).delete()
            else:
                closed = data.get("is_closed", True)
                if not isinstance(closed, bool): raise ValueError("is_closed must be a boolean")
                opens = parse_time(data.get("opens_at") or "") if not closed else None
                closes = parse_time(data.get("closes_at") or "") if not closed else None
                if not closed and (not opens or not closes or opens >= closes): raise ValueError("Invalid opening hours")
                BookingException.objects.update_or_create(date=day, defaults={"is_closed": closed, "opens_at": opens, "closes_at": closes})
        return APIResponse.success({}, "Exception updated")
    except (TypeError, ValueError) as exc:
        return APIResponse.validation_error({"exception": str(exc)})
