"""Public availability and customer-owned appointment discovery."""
import json
from datetime import date
from uuid import UUID

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.services.models import Appointment
from apps.services.services.booking_service import available_slots
from apps.services.views.booking_views import serialize_appointment
from apps.ai_assistant.services.appointment_action_service import prepare


class AvailabilityInput(BaseModel):
    option_id: UUID = Field(description="Exact service option ID from a service catalog tool")
    day: date = Field(description="Appointment date in YYYY-MM-DD format")


class AppointmentsInput(BaseModel):
    appointment_id: UUID | None = Field(default=None, description="Optional exact appointment ID")


class PrepareBookingInput(BaseModel):
    option_id: UUID
    starts_at: str = Field(description="Exact available ISO time returned by check_service_availability")
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str = Field(min_length=1, max_length=40)


class CancelInput(BaseModel):
    appointment_id: UUID


def _user(config):
    user_id = (config or {}).get("configurable", {}).get("authenticated_user_id")
    return get_user_model().objects.filter(pk=user_id, is_active=True).first() if user_id else None


@tool(args_schema=PrepareBookingInput)
def prepare_appointment(option_id: UUID, starts_at: str, customer_name: str, customer_phone: str, config: RunnableConfig) -> str:
    """Prepare a review link for an appointment. This does not create a booking."""
    user = _user(config)
    if not user: return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to book."})
    try:
        review = prepare(user, "book", {"option_id": str(option_id), "starts_at": starts_at, "customer_name": customer_name, "customer_phone": customer_phone})
        return json.dumps({"success": True, "review": review})
    except (ValueError, TypeError):
        return json.dumps({"success": False, "error": "The appointment details or selected time are invalid or unavailable."})


@tool(args_schema=CancelInput)
def prepare_appointment_cancellation(appointment_id: UUID, config: RunnableConfig) -> str:
    """Prepare a cancellation review link for the signed-in customer's own appointment."""
    user = _user(config)
    if not user: return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to manage appointments."})
    try:
        return json.dumps({"success": True, "review": prepare(user, "cancel", {"appointment_id": str(appointment_id)})})
    except (ValueError, TypeError):
        return json.dumps({"success": False, "error": "Appointment not found or cannot be cancelled."})


@tool(args_schema=AvailabilityInput)
def check_service_availability(option_id: UUID, day: date) -> str:
    """Get currently available appointment start times for a verified service option and date."""
    return json.dumps({"success": True, "date": day.isoformat(), "option_id": str(option_id),
                       "slots": available_slots(option_id, day)})


@tool(args_schema=AppointmentsInput)
def list_my_appointments(appointment_id: UUID | None = None, config: RunnableConfig = None) -> str:
    """List the signed-in customer's appointments, or retrieve one by its exact ID."""
    user_id = (config or {}).get("configurable", {}).get("authenticated_user_id")
    if not user_id or not get_user_model().objects.filter(pk=user_id, is_active=True).exists():
        return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to view appointments."})
    items = Appointment.objects.filter(user_id=user_id)
    if appointment_id:
        items = items.filter(pk=appointment_id)
    results = [serialize_appointment(item) for item in items[:20]]
    if appointment_id and not results:
        return json.dumps({"success": False, "error": "Appointment not found."})
    return json.dumps({"success": True, "appointments": results})
