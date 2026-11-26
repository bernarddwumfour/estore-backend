"""Publish the approved Amammre demo products with temporary pricing and stock."""
import os
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.products.models import Product, ProductVariant
from apps.products.revalidation import notify_product_change

PRICES = {
    "northern-heritage-smock": "450.00",
    "african-print-short-sleeve-shirt": "240.00",
    "african-print-kaba-slit": "520.00",
    "african-print-wrap-dress": "380.00",
    "batik-relaxed-shirt": "280.00",
    "african-print-bucket-hat": "120.00",
    "childrens-print-t-shirt": "120.00",
    "childrens-print-outfit-set": "220.00",
    "beaded-bracelet": "90.00",
    "african-print-headwrap": "85.00",
}


class Command(BaseCommand):
    help = "Publish Amammre demo products with sample prices and stock, without modifying other products."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.amammre":
            raise CommandError("Run this command with manage_store.py amammre.")
        with transaction.atomic():
            products = list(Product.objects.filter(slug__in=PRICES).prefetch_related("variants"))
            missing = set(PRICES) - {product.slug for product in products}
            if missing:
                raise CommandError(f"Missing demo products: {', '.join(sorted(missing))}")
            for product in products:
                if not product.variants.filter(sku__startswith="AW-").exists():
                    raise CommandError(f"No demo variants found for {product.title}.")
            variant_count = 0
            for product in products:
                variant_count += ProductVariant.objects.filter(product=product, sku__startswith="AW-").update(
                    price=Decimal(PRICES[product.slug]), stock=10, is_active=True
                )
            product_count = Product.objects.filter(pk__in=[p.pk for p in products]).update(
                status=Product.STATUS_PUBLISHED, published_at=timezone.now(), is_new=True
            )
        self.stdout.write(self.style.SUCCESS(f"Published {product_count} demo products and stocked {variant_count} variants. Prices and stock are sample values."))
        try:
            notify_product_change(categories_changed=True)
        except Exception as exc:
            self.stderr.write(f"Storefront cache notification failed: {exc}. Restart or refresh the storefront.")
