import secrets

from django.db import migrations, models


def populate_post_codes(apps, schema_editor):
    BlogPost = apps.get_model("blog", "BlogPost")
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    for post in BlogPost.objects.filter(post_code__isnull=True).iterator():
        while True:
            code = "BLG-" + "".join(secrets.choice(alphabet) for _ in range(12))
            if not BlogPost.objects.filter(post_code=code).exists():
                BlogPost.objects.filter(pk=post.pk).update(post_code=code)
                break


class Migration(migrations.Migration):
    dependencies = [("blog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="blogpost",
            name="post_code",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.RunPython(populate_post_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="blogpost",
            name="post_code",
            field=models.CharField(blank=True, editable=False, max_length=16, unique=True),
        ),
    ]
