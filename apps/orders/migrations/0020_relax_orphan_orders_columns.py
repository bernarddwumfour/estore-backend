from django.db import migrations


def relax_orphan_not_nulls(apps, schema_editor):
    """Same repair as 0019 but for every orders-app table: the live Postgres
    DB carries columns added outside Django's migrations (carrier_reference on
    shipments, carrier_status on shipment_tracking, ...) with NOT NULL and no
    default, which break ORM inserts. Drop NOT NULL on any column Django
    doesn't know about."""
    if schema_editor.connection.vendor != "postgresql":
        return

    app_config = apps.get_app_config("orders")
    with schema_editor.connection.cursor() as cursor:
        for model in app_config.get_models():
            table = model._meta.db_table
            model_columns = {field.column for field in model._meta.local_fields}
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                  AND is_nullable = 'NO'
                  AND column_default IS NULL
                """,
                [table],
            )
            orphan_columns = [
                column
                for (column,) in cursor.fetchall()
                if column not in model_columns
            ]
            for column in orphan_columns:
                cursor.execute(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL'
                )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0019_relax_orphan_shipment_columns"),
    ]

    operations = [
        migrations.RunPython(relax_orphan_not_nulls, migrations.RunPython.noop),
    ]
