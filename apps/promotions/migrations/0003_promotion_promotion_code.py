import secrets

from django.db import migrations, models


def populate_promotion_codes(apps, schema_editor):
    Promotion = apps.get_model("promotions", "Promotion")
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    for promotion in Promotion.objects.filter(promotion_code__isnull=True).iterator():
        while True:
            code = "PRM-" + "".join(secrets.choice(alphabet) for _ in range(12))
            if not Promotion.objects.filter(promotion_code=code).exists():
                Promotion.objects.filter(pk=promotion.pk).update(promotion_code=code)
                break


class Migration(migrations.Migration):
    dependencies = [("promotions", "0002_discountcode_affiliatecommission_and_more")]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="promotion_code",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.RunPython(populate_promotion_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="promotion",
            name="promotion_code",
            field=models.CharField(blank=True, editable=False, max_length=16, unique=True),
        ),
    ]
