"""Validate and execute service changes for the existing admin confirmation flow."""
from django.db import transaction
from apps.services.models import Appointment, BookingSettings, BookingHours, BookingException, Service, ServiceCategory, ServiceOption
from apps.services.schemas.service_schemas import _service_payload, _option_payload, category_payload
from apps.services.services import service_service

SERVICE_ACTIONS = {"create_service", "update_service", "create_service_option", "update_service_option", "create_service_category", "update_service_category", "update_appointment", "update_booking_settings", "set_booking_exception", "delete_booking_exception"}


def validate_and_execute(action, target_id, data, execute=False):
    if not isinstance(data, dict) or not data:
        raise ValueError("Provide the fields to change")
    allowed = {
        "create_service": {"title", "slug", "short_description", "description", "category_id", "features", "status", "is_featured", "sort_order", "meta_title", "meta_description"},
        "update_service": {"title", "slug", "short_description", "description", "category_id", "features", "status", "is_featured", "sort_order", "meta_title", "meta_description"},
        "create_service_option": {"name", "slug", "description", "pricing_type", "price", "duration_minutes", "is_default", "is_active", "sort_order"},
        "update_service_option": {"name", "slug", "description", "pricing_type", "price", "duration_minutes", "is_default", "is_active", "sort_order"},
        "create_service_category": {"name", "slug", "description", "parent_id", "is_hidden", "is_active", "meta_title", "meta_description", "sort_order"},
        "update_service_category": {"name", "slug", "description", "parent_id", "is_hidden", "is_active", "meta_title", "meta_description", "sort_order"},
        "update_appointment": {"status"},
        "update_booking_settings": {"enabled", "timezone", "slot_interval_minutes", "hours"},
        "set_booking_exception": {"date", "is_closed", "opens_at", "closes_at"},
        "delete_booking_exception": {"date"},
    }
    if action not in allowed or set(data) - allowed[action]:
        raise ValueError("Unsupported action or fields")
    if action == "update_booking_settings":
        from zoneinfo import ZoneInfo
        from django.utils.dateparse import parse_time
        if "enabled" in data and not isinstance(data["enabled"], bool): raise ValueError("Enabled must be boolean")
        if "timezone" in data: ZoneInfo(data["timezone"])
        if "slot_interval_minutes" in data and (not isinstance(data["slot_interval_minutes"], int) or isinstance(data["slot_interval_minutes"], bool) or not 5 <= data["slot_interval_minutes"] <= 240): raise ValueError("Invalid slot interval")
        hours = data.get("hours")
        parsed = []
        if hours is not None:
            if not isinstance(hours, list): raise ValueError("Hours must be a list")
            for h in hours:
                day = h.get("weekday")
                start, end = parse_time(h.get("opens_at", "")), parse_time(h.get("closes_at", ""))
                if not isinstance(day, int) or isinstance(day, bool) or day not in range(7) or not start or not end or start >= end or day in [x[0] for x in parsed]: raise ValueError("Invalid weekly hours")
                parsed.append((day, start, end))
        if execute:
            BookingSettings.objects.get_or_create(pk=1)
            item = BookingSettings.objects.select_for_update().get(pk=1)
            for field in ("enabled", "timezone", "slot_interval_minutes"):
                if field in data: setattr(item, field, data[field])
            item.save()
            if hours is not None:
                BookingHours.objects.all().delete()
                BookingHours.objects.bulk_create([BookingHours(weekday=d, opens_at=start, closes_at=end) for d, start, end in parsed])
            return item
    elif action in {"set_booking_exception", "delete_booking_exception"}:
        from datetime import date
        from django.utils.dateparse import parse_time
        day = date.fromisoformat(data.get("date", ""))
        closed = data.get("is_closed", True)
        if not isinstance(closed, bool): raise ValueError("is_closed must be boolean")
        start = parse_time(data.get("opens_at") or "") if not closed else None
        end = parse_time(data.get("closes_at") or "") if not closed else None
        if not closed and (not start or not end or start >= end): raise ValueError("Invalid opening hours")
        if execute:
            BookingSettings.objects.get_or_create(pk=1)
            BookingSettings.objects.select_for_update().get(pk=1)
            if action == "delete_booking_exception":
                item = BookingException.objects.filter(date=day).first()
                if not item: raise ValueError("Exception not found")
                item.delete()
                item.pk = day
                return item
            return BookingException.objects.update_or_create(date=day, defaults={"is_closed": closed, "opens_at": start, "closes_at": end})[0]
    elif action == "create_service":
        values = _service_payload(data)
        if values.get("status") == Service.PUBLISHED:
            raise ValueError("Create a draft first, then add an option before publishing")
        if execute: return service_service.create_service(values)
    elif action == "update_service":
        item = Service.objects.get(pk=target_id)
        values = _service_payload(data, item)
        if values.get("status") == Service.PUBLISHED and not item.options.filter(is_active=True).exists():
            raise ValueError("Add an active option before publishing")
        if execute: return service_service.update_service(item, values)
    elif action == "create_service_option":
        item = Service.objects.get(pk=target_id)
        values = _option_payload(data, item)
        if execute: return service_service.create_option(item, values)
    elif action == "update_service_option":
        item = ServiceOption.objects.select_related("service").get(pk=target_id)
        values = _option_payload(data, item.service, item)
        if execute: return service_service.update_option(item, values)
    elif action == "create_service_category":
        values = category_payload(data)
        if execute: return service_service.create_category(values)
    elif action == "update_service_category":
        item = ServiceCategory.objects.get(pk=target_id)
        values = category_payload(data, item)
        if execute: return service_service.update_category(item, values)
    elif action == "update_appointment":
        if set(data) != {"status"}: raise ValueError("Specify only the appointment status")
        if execute:
            BookingSettings.objects.select_for_update().filter(pk=1).first()
            item = Appointment.objects.select_for_update().get(pk=target_id)
        else:
            item = Appointment.objects.get(pk=target_id)
        transitions = {Appointment.PENDING: {Appointment.CONFIRMED, Appointment.CANCELLED}, Appointment.CONFIRMED: {Appointment.COMPLETED, Appointment.CANCELLED}}
        if data["status"] not in transitions.get(item.status, set()): raise ValueError("Invalid appointment status transition")
        if execute:
            item.status = data["status"]
            item.save(update_fields=["status", "updated_at"])
            return item
    else:
        raise ValueError("Unsupported action")


def validate(action, target_id, data):
    try:
        validate_and_execute(action, target_id, data)
        return None
    except (ValueError, TypeError, KeyError, AttributeError, Service.DoesNotExist, ServiceOption.DoesNotExist, ServiceCategory.DoesNotExist, Appointment.DoesNotExist) as exc:
        return {"service": str(exc) or "Record not found"}


def execute(action, target_id, data):
    error = validate(action, target_id, data)
    if error: return None, error
    try:
        item = validate_and_execute(action, target_id, data, execute=True)
        return {"id": str(item.pk), "name": str(item)}, None
    except (ValueError, TypeError, KeyError, AttributeError, Service.DoesNotExist, ServiceOption.DoesNotExist, ServiceCategory.DoesNotExist, Appointment.DoesNotExist) as exc:
        return None, {"service": str(exc) or "Record not found"}
