import uuid

from django.db import migrations, models


def populate_user_codes(apps, schema_editor):
    User = apps.get_model("users", "User")
    used_codes = set()
    for user in User.objects.only("id").iterator():
        hex_id = uuid.UUID(str(user.pk)).hex.upper()
        length = 12
        code = f"USR-{hex_id[:length]}"
        while code in used_codes:
            length += 1
            code = f"USR-{hex_id[:length]}"
        used_codes.add(code)
        User.objects.filter(pk=user.pk).update(user_code=code)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0022_affiliate_commission_basis"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="user_code",
            field=models.CharField(blank=True, max_length=36, null=True),
        ),
        migrations.RunPython(populate_user_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="user_code",
            field=models.CharField(blank=True, editable=False, max_length=36, unique=True),
        ),
    ]
