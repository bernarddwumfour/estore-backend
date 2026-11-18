"""Attach the generated starter catalog images to Olive & Aura variants."""

import os
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from apps.products.models import ProductVariant, VariantImage


IMAGES = {
    "OA-BODY-BUTTER-200": "golden-shea-body-butter.png",
    "OA-BODY-OIL-100": "olive-glow-body-oil.png",
    "OA-ROSE-MIST-150": "aura-rose-body-mist.png",
    "OA-BODY-WASH-250": "soft-ritual-body-wash.png",
    "OA-BODY-SCRUB-200": "sunday-reset-body-scrub.png",
    "OA-LIP-BALM-15": "everyday-lip-balm.png",
    "OA-CANDLE-180": "quiet-evening-candle.png",
    "OA-GLOW-GIFT-SET": "the-glow-ritual-gift-set.png",
}


class Command(BaseCommand):
    help = "Upload and attach the generated Olive & Aura starter images."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.oliveandaura":
            raise RuntimeError("Run this command with manage_store.py oliveandaura.")

        image_dir = Path(__file__).resolve().parents[4] / "oliveandaura-product-images"
        created = 0
        for sku, filename in IMAGES.items():
            variant = ProductVariant.objects.get(sku=sku)
            if variant.images.filter(image_type=VariantImage.IMAGE_TYPE_MAIN).exists():
                continue
            image = VariantImage(
                variant=variant,
                image_type=VariantImage.IMAGE_TYPE_MAIN,
                alt_text=f"{variant.product.title} product mockup",
                order=0,
            )
            with (image_dir / filename).open("rb") as source:
                image.image.save(filename, File(source), save=True)
            created += 1
            self.stdout.write(f"Attached {sku}: {image.image.url}")
        self.stdout.write(self.style.SUCCESS(f"Attached {created} images."))
