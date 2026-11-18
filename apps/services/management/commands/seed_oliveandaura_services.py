"""Add starter Olive & Aura beauty services as drafts."""

import os
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.services.models import Service, ServiceCategory, ServiceOption


SERVICES = [
    ("Signature Glow Facial", "facials", "A gentle cleanse, exfoliation, mask and hydration ritual for a fresh glow.", 60, "280"),
    ("Calm Body Massage", "massage", "A relaxing full body massage with warm oil and gentle pressure.", 60, "320"),
    ("Sunday Reset Body Ritual", "body-treatments", "A body exfoliation followed by a nourishing shea moisturising treatment.", 45, "220"),
    ("Aura Unwind Package", "packages", "A calming facial and body massage in one longer appointment.", 90, "450"),
]

CATEGORIES = {
    "facials": "Facials",
    "massage": "Massage",
    "body-treatments": "Body Treatments",
    "packages": "Packages",
}


class Command(BaseCommand):
    help = "Create draft Olive & Aura services and default booking options."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.oliveandaura":
            raise RuntimeError("Run this command with manage_store.py oliveandaura.")
        with transaction.atomic():
            categories = {
                slug: ServiceCategory.objects.get_or_create(slug=slug, defaults={"name": name})[0]
                for slug, name in CATEGORIES.items()
            }
            created = 0
            for position, (title, category_slug, description, duration, price) in enumerate(SERVICES):
                slug = title.lower().replace(" ", "-")
                service, is_new = Service.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "title": title,
                        "short_description": description,
                        "description": description,
                        "category": categories[category_slug],
                        "status": Service.DRAFT,
                        "sort_order": position,
                    },
                )
                created += is_new
                ServiceOption.objects.get_or_create(
                    service=service,
                    slug="standard",
                    defaults={
                        "name": "Standard",
                        "pricing_type": ServiceOption.FIXED,
                        "price": Decimal(price),
                        "duration_minutes": duration,
                        "is_default": True,
                    },
                )
            self.stdout.write(self.style.SUCCESS(f"Created {created} draft services."))
