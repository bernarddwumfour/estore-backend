from django.db import transaction

from apps.services.models import ServiceRequest


@transaction.atomic
def create_service_request(values, service):
    return ServiceRequest.objects.create(
        service=service,
        custom_service_type=values["custom_service_type"] if service is None else "",
        device_model=values["device_model"],
        customer_name=values["customer_name"],
        customer_email=values["customer_email"],
        customer_phone=values["customer_phone"],
        issue_description=values["issue_description"],
    )
