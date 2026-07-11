from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0009_add_created_by_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('paid', 'Paid'),
                    ('failed', 'Failed'),
                    ('partially_refunded', 'Partially Refunded'),
                    ('refunded', 'Refunded'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
                verbose_name='payment status',
            ),
        ),
    ]
