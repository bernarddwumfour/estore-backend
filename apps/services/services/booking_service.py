"""Appointment availability and serialized allocation for a single store."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from apps.services.models import Appointment, BookingException, BookingHours, BookingSettings
from apps.services.selectors.service_selectors import public_services


def available_slots(option_id, date):
    config = BookingSettings.objects.filter(pk=1, enabled=True).first()
    if not config:
        return []
    option = next((o for service in public_services().filter(options__pk=option_id).distinct()
                   for o in service.public_options if str(o.pk) == str(option_id)), None)
    if not option or not option.duration_minutes:
        return []
    try:
        zone = ZoneInfo(config.timezone)
    except ZoneInfoNotFoundError:
        return []
    exception = BookingException.objects.filter(date=date).first()
    hours = BookingHours.objects.filter(weekday=date.weekday(), is_open=True).first()
    if exception:
        if exception.is_closed:
            return []
        opens, closes = exception.opens_at, exception.closes_at
    elif hours:
        opens, closes = hours.opens_at, hours.closes_at
    else:
        return []
    if not opens or not closes or opens >= closes or not config.slot_interval_minutes:
        return []
    start = datetime.combine(date, opens, tzinfo=zone)
    end = datetime.combine(date, closes, tzinfo=zone)
    busy = list(Appointment.objects.filter(status__in=[Appointment.PENDING, Appointment.CONFIRMED], starts_at__lt=end, ends_at__gt=start).values_list("starts_at", "ends_at"))
    slots = []
    while start + timedelta(minutes=option.duration_minutes) <= end:
        finish = start + timedelta(minutes=option.duration_minutes)
        if start > timezone.now() and not any(start < b_end and finish > b_start for b_start, b_end in busy):
            slots.append(start.isoformat())
        start += timedelta(minutes=config.slot_interval_minutes)
    return slots


@transaction.atomic
def create_appointment(user, option_id, starts_at, customer_name, customer_phone):
    config = BookingSettings.objects.select_for_update().filter(pk=1, enabled=True).first()
    if not config:
        raise ValueError("Bookings are currently unavailable")
    if timezone.is_naive(starts_at):
        raise ValueError("Start time must include a timezone")
    if not customer_name.strip() or len(customer_name) > 200 or not customer_phone.strip() or len(customer_phone) > 40:
        raise ValueError("A valid name and phone number are required")
    zone = ZoneInfo(config.timezone)
    local_start = starts_at.astimezone(zone)
    if local_start.isoformat() not in available_slots(option_id, local_start.date()):
        raise ValueError("This appointment time is no longer available")
    service = public_services().filter(options__pk=option_id).distinct().first()
    option = next(o for o in service.public_options if str(o.pk) == str(option_id))
    return Appointment.objects.create(user=user, option=option, service_title=service.title,
        option_name=option.name, pricing_type=option.pricing_type, price=option.price,
        customer_name=customer_name.strip(), customer_phone=customer_phone.strip(),
        starts_at=starts_at, ends_at=starts_at + timedelta(minutes=option.duration_minutes))
