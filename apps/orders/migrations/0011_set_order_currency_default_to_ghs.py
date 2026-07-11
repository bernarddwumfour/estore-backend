from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0010_add_partially_refunded_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="currency",
            field=models.CharField(default="GHS", max_length=3, verbose_name="currency"),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="currency",
            field=models.CharField(default="GHS", max_length=3, verbose_name="currency"),
        ),
    ]
