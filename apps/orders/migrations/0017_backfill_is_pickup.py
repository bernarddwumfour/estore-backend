from django.db import migrations


def backfill_is_pickup(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(shipping_method="In-Store Pickup").update(is_pickup=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0016_order_completed_at_order_is_pickup_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_is_pickup, noop),
    ]
