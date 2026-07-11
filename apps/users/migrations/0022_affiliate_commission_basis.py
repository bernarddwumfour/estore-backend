from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0021_alter_customerprofile_date_of_birth"),
    ]

    operations = [
        migrations.AddField(
            model_name="affiliate",
            name="commission_basis",
            field=models.CharField(
                choices=[("sale_amount", "Sale amount"), ("profit", "Profit")],
                default="sale_amount",
                help_text=(
                    "Whether the rate applies to the order's sale amount or to the "
                    "profit (selling price minus cost price, after discount)"
                ),
                max_length=20,
                verbose_name="commission basis",
            ),
        ),
    ]
