from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0017_backfill_is_pickup"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shipment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("shipped", "Shipped"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
                verbose_name="status",
            ),
        ),
        migrations.AlterField(
            model_name="shipment",
            name="shipped_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="shipped at"),
        ),
        migrations.AlterField(
            model_name="shipmenttracking",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("shipped", "Shipped"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                max_length=20,
                verbose_name="status",
            ),
        ),
    ]
