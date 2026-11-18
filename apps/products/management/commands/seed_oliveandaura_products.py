"""Add the approved Olive & Aura starter catalog as draft products."""

from decimal import Decimal
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.products.models import Category, Product, ProductVariant


PRODUCTS = [
    ("Golden Shea Body Butter", "body-care", "A rich shea body butter with a soft vanilla scent.", "200 ml", "150", "OA-BODY-BUTTER-200"),
    ("Olive Glow Body Oil", "body-care", "A silky body oil with olive and jojoba oils.", "100 ml", "180", "OA-BODY-OIL-100"),
    ("Aura Rose Body Mist", "fragrance", "A lightweight rose and white musk fragrance mist.", "150 ml", "120", "OA-ROSE-MIST-150"),
    ("Soft Ritual Body Wash", "body-care", "A creamy body wash with a gentle oat and honey scent.", "250 ml", "110", "OA-BODY-WASH-250"),
    ("Sunday Reset Body Scrub", "body-care", "A sugar body scrub with coconut oil and a warm citrus scent.", "200 g", "140", "OA-BODY-SCRUB-200"),
    ("Everyday Lip Balm", "skin-care", "A shea and cocoa butter balm with a subtle vanilla scent.", "15 g", "45", "OA-LIP-BALM-15"),
    ("Quiet Evening Candle", "home-fragrance", "A lavender and sandalwood scented candle.", "180 g", "160", "OA-CANDLE-180"),
    ("The Glow Ritual Gift Set", "gift-sets", "Golden Shea Body Butter, Olive Glow Body Oil, and Everyday Lip Balm.", "3 items", "340", "OA-GLOW-GIFT-SET"),
]

CATEGORIES = {
    "body-care": "Body Care",
    "fragrance": "Fragrance",
    "skin-care": "Skin Care",
    "home-fragrance": "Home Fragrance",
    "gift-sets": "Gift Sets",
}


class Command(BaseCommand):
    help = "Create the initial Olive & Aura draft products without duplicating existing entries."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.oliveandaura":
            raise RuntimeError("Run this command with manage_store.py oliveandaura.")
        with transaction.atomic():
            categories = {}
            for slug, name in CATEGORIES.items():
                categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})

            created = 0
            for title, category_slug, description, size, price, sku in PRODUCTS:
                slug = title.lower().replace(" & ", "-").replace(" ", "-")
                product, is_new = Product.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "title": title,
                        "description": description,
                        "category": categories[category_slug],
                        "status": Product.STATUS_DRAFT,
                    },
                )
                created += is_new
                ProductVariant.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "product": product,
                        "slug": "standard",
                        "attributes": {"size": size},
                        "price": Decimal(price),
                        "stock": 0,
                        "is_default": True,
                    },
                )
            self.stdout.write(self.style.SUCCESS(f"Created {created} Olive & Aura draft products."))
