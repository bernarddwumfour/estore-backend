import uuid
from django.conf import settings
from django.db import models


class TemplateCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']


class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=[('text', 'Text'), ('image', 'Image')])
    status = models.CharField(max_length=10, default='draft', choices=[('draft', 'Draft'), ('active', 'Active'), ('archived', 'Archived')])
    content = models.JSONField(default=dict)
    slots = models.JSONField(default=list)
    schema_version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
    categories = models.ManyToManyField(TemplateCategory, blank=True, related_name='templates')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class TemplateGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, default='draft', choices=[('draft', 'Draft'), ('active', 'Active'), ('archived', 'Archived')])
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']


class TemplateGroupItem(models.Model):
    group = models.ForeignKey(TemplateGroup, on_delete=models.CASCADE, related_name='items')
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='group_items')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['group', 'template'], name='unique_template_group_member')]


class TemplateInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    template = models.ForeignKey(Template, null=True, on_delete=models.SET_NULL)
    # Immutable design/slot snapshot; later edits always resolve against this snapshot.
    snapshot = models.JSONField()
    values = models.JSONField(default=dict)
    resolved = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    group_name = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class TemplateAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to='templates/%Y/%m/')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
