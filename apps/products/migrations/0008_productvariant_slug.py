# Generated manually for stable, readable public variant URLs.

from django.db import migrations, models
from django.utils.text import slugify


def populate_variant_slugs(apps, schema_editor):
    ProductVariant = apps.get_model("products", "ProductVariant")

    for variant in ProductVariant.objects.all().iterator():
        parts = [str(value) for value in (variant.attributes or {}).values() if value]
        base = slugify("-".join(parts)) or slugify(variant.sku) or "variant"
        candidate = base
        suffix = 2
        while ProductVariant.objects.filter(
            product_id=variant.product_id, slug=candidate
        ).exclude(pk=variant.pk).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        variant.slug = candidate
        variant.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [("products", "0007_alter_productreview_is_approved")]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="slug",
            field=models.SlugField(blank=True, help_text="Stable, human-readable URL identifier within this product", max_length=180, verbose_name="public URL slug"),
        ),
        migrations.RunPython(populate_variant_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="productvariant",
            name="slug",
            field=models.SlugField(help_text="Stable, human-readable URL identifier within this product", max_length=180, verbose_name="public URL slug"),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(
                fields=("product", "slug"), name="unique_variant_slug_per_product"
            ),
        ),
    ]
