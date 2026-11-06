import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ai_assistant", "0002_productembedding"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantOrderDraft",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("items", models.JSONField(default=list)),
                ("shipping_method", models.CharField(blank=True, max_length=100)),
                ("confirmation_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("confirmed", "Confirmed")], default="draft", max_length=20)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("shipping_address", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="users.address")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_assistant_order_drafts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "ai_assistant_order_drafts"},
        ),
        migrations.AddIndex(model_name="assistantorderdraft", index=models.Index(fields=["user", "status", "expires_at"], name="ai_assistan_user_id_f6e30f_idx")),
    ]
