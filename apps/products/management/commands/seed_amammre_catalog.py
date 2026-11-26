"""Create the approved top-level categories for Amammre Wears."""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.products.models import Category

CATEGORIES = [
    ("Men", "men"),
    ("Ladies", "ladies"),
    ("Unisex", "unisex"),
    ("Children", "children"),
    ("Accessories", "accessories"),
]


class Command(BaseCommand):
    help = "Create the approved Amammre categories without duplicating existing records."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.amammre":
            raise CommandError("Run this command with manage_store.py amammre.")
        with transaction.atomic():
            created = 0
            for name, slug in CATEGORIES:
                _, is_new = Category.objects.get_or_create(slug=slug, defaults={"name": name})
                created += is_new
        self.stdout.write(self.style.SUCCESS(f"Created {created} categories; {len(CATEGORIES)} approved categories available."))
