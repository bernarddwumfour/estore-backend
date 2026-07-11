from django.db import migrations


def relax_orphan_not_nulls(apps, schema_editor):
    """The live Postgres shipments table carries columns that were added
    outside Django's migrations (e.g. carrier_reference NOT NULL), which break
    inserts of Django-managed rows. Drop NOT NULL on any non-model column so
    the ORM can insert without knowing about them."""
    if schema_editor.connection.vendor != "postgresql":
        return

    shipment = apps.get_model("orders", "Shipment")
    model_columns = {field.column for field in shipment._meta.local_fields}

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'shipments'
              AND is_nullable = 'NO'
              AND column_default IS NULL
            """
        )
        orphan_columns = [
            column for (column,) in cursor.fetchall() if column not in model_columns
        ]
        for column in orphan_columns:
            cursor.execute(
                f'ALTER TABLE shipments ALTER COLUMN "{column}" DROP NOT NULL'
            )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0018_shipment_pending_status"),
    ]

    operations = [
        migrations.RunPython(relax_orphan_not_nulls, migrations.RunPython.noop),
    ]
