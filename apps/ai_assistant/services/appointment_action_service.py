"""Short-lived customer-owned appointment reviews."""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import transaction

from apps.services.models import Appointment, BookingSettings
from apps.services.selectors.service_selectors import public_services
from apps.services.services.booking_service import available_slots, create_appointment
from apps.services.views.booking_views import serialize_appointment

TTL = 600


def prepare(user, action, data):
    if action == "book":
        start = datetime.fromisoformat(data["starts_at"])
        if start.tzinfo is None: raise ValueError("Time must include a timezone")
        settings = BookingSettings.objects.filter(pk=1, enabled=True).first()
        if not settings: raise ValueError("Bookings are unavailable")
        local = start.astimezone(ZoneInfo(settings.timezone))
        if local.isoformat() not in available_slots(data["option_id"], local.date()): raise ValueError("This time is unavailable")
        service = public_services().filter(options__pk=data["option_id"]).distinct().first()
        option = next(o for o in service.public_options if str(o.pk) == data["option_id"])
        if not data["customer_name"].strip() or not data["customer_phone"].strip(): raise ValueError("Name and phone are required")
        preview = {"service": service.title, "option": option.name, "starts_at": local.isoformat(), "duration_minutes": option.duration_minutes,
                   "pricing_type": option.pricing_type, "price": str(option.price) if option.price is not None else None,
                   "customer_name": data["customer_name"], "customer_phone": data["customer_phone"]}
    elif action == "cancel":
        item = Appointment.objects.filter(pk=data["appointment_id"], user=user, status__in=[Appointment.PENDING, Appointment.CONFIRMED]).first()
        if not item: raise ValueError("Appointment not found or cannot be cancelled")
        preview = serialize_appointment(item)
    else:
        raise ValueError("Invalid action")
    token = str(uuid.uuid4())
    cache.set(f"assistant_appointment:{token}", {"user_id": str(user.pk), "action": action, "data": data, "preview": preview}, TTL)
    return {"action": action, "review_path": f"/appointments/review/{token}", "expires_in_seconds": TTL, "details": preview}


def get_review(user, token):
    record = cache.get(f"assistant_appointment:{token}")
    return record if record and record["user_id"] == str(user.pk) else None


def confirm(user, token):
    key = f"assistant_appointment:{token}"
    record = get_review(user, token)
    if not record: raise ValueError("Review not found or expired")
    if not cache.add(f"{key}:used", True, TTL): raise ValueError("This review was already confirmed")
    try:
        data = record["data"]
        if record["action"] == "book":
            item = create_appointment(user, data["option_id"], datetime.fromisoformat(data["starts_at"]), data["customer_name"], data["customer_phone"])
        else:
            with transaction.atomic():
                BookingSettings.objects.select_for_update().filter(pk=1).first()
                item = Appointment.objects.select_for_update().filter(pk=data["appointment_id"], user=user).first()
                if not item or item.status not in (Appointment.PENDING, Appointment.CONFIRMED): raise ValueError("Appointment cannot be cancelled")
                item.status = Appointment.CANCELLED
                item.save(update_fields=["status", "updated_at"])
        cache.delete(key)
        return serialize_appointment(item)
    except Exception:
        cache.delete(f"{key}:used")
        raise
