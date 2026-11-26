"""Create the approved Amammre product proposals as drafts without images."""
import os
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.products.models import Category, Product, ProductVariant

# Proposed designs for catalog review; construction and material require confirmation.
PRODUCTS = [
    {"title": "Northern Heritage Smock", "category": "men", "code": "SMOCK", "description": "A relaxed, short-sleeve smock inspired by northern Ghanaian fugu and batakari styles. Its striped design and decorated neckline make it a striking choice for celebrations and special occasions.", "features": ["Relaxed tunic silhouette with a gently flared lower section", "Short sleeves and round neckline with a short front slit", "Narrow stripe design with decorative neckline detail", "Material and production method to be confirmed"], "colours": ["Navy / White", "Black / White"], "sizes": ["M", "L", "XL"]},
    {"title": "African Print Short-Sleeve Shirt", "category": "men", "code": "M-SHIRT", "description": "A regular-fit short-sleeve shirt with a geometric African print. Designed for easy pairing with plain trousers or jeans for casual outings and celebrations.", "features": ["Short sleeves and a collared neckline", "Button-front design with a straight hem", "Regular fit with an all-over geometric print", "Fabric composition to be confirmed"], "colours": ["Brown / Cream", "Blue / Gold"], "sizes": ["M", "L", "XL"]},
    {"title": "African Print Kaba & Slit", "category": "ladies", "code": "KABA", "description": "A coordinated blouse and skirt set inspired by the Ghanaian kaba and slit silhouette. The matching print creates a considered look for church, family gatherings and celebrations.", "features": ["Two-piece set with a fitted short-sleeve blouse", "Ankle-length straight skirt with a walking slit", "Matching geometric print across both pieces", "Fabric, lining and fastenings to be confirmed"], "colours": ["Burgundy / Gold", "Blue / Cream"], "sizes": ["S", "M", "L", "XL"]},
    {"title": "African Print Wrap Dress", "category": "ladies", "code": "DRESS", "description": "A midi-length wrap-style dress with a geometric African print. The waist tie and gently flared silhouette create an easy look for daytime outings or special occasions.", "features": ["Wrap-style V-neck front with waist tie", "Short sleeves and midi-length skirt", "Gently flared silhouette in an all-over print", "Fabric, lining and wrap construction to be confirmed"], "colours": ["Rust / Cream", "Green / Gold"], "sizes": ["S", "M", "L", "XL"]},
    {"title": "Batik Relaxed Shirt", "category": "unisex", "code": "BATIK", "description": "A relaxed unisex shirt with an organic batik-style motif. Wear it buttoned or open over a plain top for a comfortable, easy-to-style outfit.", "features": ["Relaxed unisex silhouette", "Short sleeves, open collar and button front", "Straight hem with an organic batik-style pattern", "Fibre and dyeing method to be confirmed"], "colours": ["Indigo / Cream", "Earth Brown / Cream"], "sizes": ["S", "M", "L", "XL"]},
    {"title": "African Print Bucket Hat", "category": "unisex", "code": "HAT", "description": "A soft bucket hat with a geometric African print, rounded crown and sloping brim. An easy finishing piece for casual looks.", "features": ["Rounded crown and all-around sloping brim", "Stitched brim and all-over geometric print", "Available in two proposed size ranges", "Fabric composition and head measurements to be confirmed"], "colours": ["Gold / Black", "Green / Cream"], "sizes": ["S/M", "L/XL"]},
    {"title": "Children's Print T-Shirt", "category": "children", "code": "K-TEE", "description": "A short-sleeve children's T-shirt with a crew neckline and a patterned chest pocket. A simple everyday piece with a colourful print detail.", "features": ["Short sleeves and crew neckline", "Regular fit with one printed chest pocket", "Plain main body with a contrasting print detail", "Fabric composition and size measurements to be confirmed"], "colours": ["Cream / Gold-Black", "Black / Blue-Cream"], "sizes": ["2-3 years", "4-5 years", "6-7 years"]},
    {"title": "Children's Print Outfit Set", "category": "children", "code": "K-SET", "description": "A coordinated children's outfit made up of a short-sleeve shirt and matching shorts. The geometric print gives the set a playful look for family gatherings and celebrations.", "features": ["Two-piece matching shirt and shorts set", "Short-sleeve collared button-front shirt", "Knee-length shorts with an elastic-style waist", "Fabric, fastenings and measurements to be confirmed"], "colours": ["Blue / Gold", "Red / Cream"], "sizes": ["2-3 years", "4-5 years", "6-7 years"]},
    {"title": "Beaded Bracelet", "category": "accessories", "code": "BRACELET", "description": "A single-strand beaded bracelet with a simple clasp. Its colour combinations offer a subtle finishing touch for everyday and occasion wear.", "features": ["Single strand of rounded beads", "Two proposed colour combinations", "Simple clasp fastening", "Bead material, clasp and circumference to be confirmed"], "colours": ["Amber / Black", "Blue / White"], "sizes": ["Small", "Medium"]},
    {"title": "African Print Headwrap", "category": "accessories", "code": "WRAP", "description": "A rectangular headwrap in a geometric African print. It can be styled in different ways to complement traditional or contemporary outfits.", "features": ["Rectangular fabric headwrap", "All-over geometric print", "One proposed size with three colourways", "Fabric, dimensions and edge finish to be confirmed"], "colours": ["Gold / Black", "Burgundy / Cream", "Blue / White"], "sizes": ["One size"]},
]


class Command(BaseCommand):
    help = "Create proposed Amammre products and variants as drafts; no images, prices or stock."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.amammre":
            raise CommandError("Run this command with manage_store.py amammre.")
        with transaction.atomic():
            categories = {item.slug: item for item in Category.objects.filter(slug__in={p["category"] for p in PRODUCTS})}
            missing = {p["category"] for p in PRODUCTS} - set(categories)
            if missing:
                raise CommandError(f"Missing categories: {', '.join(sorted(missing))}")
            created_products = created_variants = 0
            for data in PRODUCTS:
                product, created = Product.objects.get_or_create(
                    slug=slugify(data["title"]),
                    defaults={"title": data["title"], "description": data["description"], "features": data["features"],
                              "options": {"Color": data["colours"], "Size": data["sizes"]},
                              "category": categories[data["category"]], "status": Product.STATUS_DRAFT},
                )
                if not created:
                    self.stdout.write(f"Skipped existing product: {product.title}")
                    continue
                created_products += 1
                for colour_index, colour in enumerate(data["colours"], start=1):
                    for size_index, size in enumerate(data["sizes"], start=1):
                        ProductVariant.objects.create(
                            product=product, sku=f"AW-{data['code']}-{colour_index:02d}-{size_index:02d}",
                            slug=slugify(f"{colour}-{size}"), attributes={"Color": colour, "Size": size},
                            price=Decimal("0.00"), stock=0, is_default=(colour_index == 1 and size_index == 1),
                        )
                        created_variants += 1
            self.stdout.write(self.style.SUCCESS(f"Created {created_products} draft products and {created_variants} variants (no images, unconfirmed prices and stock)."))
