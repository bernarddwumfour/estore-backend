"""Create the initial iPlug service catalog without changing existing entries."""

import os

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.services.models import Service, ServiceCategory, ServiceOption


SERVICES = (
    ("Battery Replacement", "battery-replacement", "Restore your device to peak performance with a new battery.", 60),
    ("Screen Repair", "screen-repair", "Repair cracked glass and unresponsive displays.", 90),
    ("Trade-In Evaluation", "trade-in", "Find out what your old device is worth in store credit.", 30),
    ("Logic Board Repair", "hardware-diagnostics", "Diagnose water damage, boot problems, and board faults.", 120),
)


class Command(BaseCommand):
    help = "Create the published iPlug services and quote-based options for API testing."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.iplug":
            raise RuntimeError("Run this command with manage_store.py iplug.")

        with transaction.atomic():
            category, _ = ServiceCategory.objects.get_or_create(
                slug="device-services", defaults={"name": "Device Services"}
            )
            created = 0
            for position, (title, slug, description, duration) in enumerate(SERVICES):
                service, is_new = Service.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "title": title,
                        "short_description": description,
                        "description": description,
                        "category": category,
                        "status": Service.PUBLISHED,
                        "sort_order": position,
                        "published_at": timezone.now(),
                    },
                )
                created += is_new
                option, _ = ServiceOption.objects.get_or_create(
                    service=service,
                    slug="assessment",
                    defaults={
                        "name": "Assessment",
                        "pricing_type": ServiceOption.QUOTE,
                        "duration_minutes": duration,
                        "is_default": True,
                    },
                )
                if option.duration_minutes is None:
                    option.duration_minutes = duration
                    option.save(update_fields=["duration_minutes", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Created {created} iPlug services."))
