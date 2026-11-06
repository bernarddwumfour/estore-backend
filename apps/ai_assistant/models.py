import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class Conversation(models.Model):
    """
    A shopping assistant conversation belonging to an authenticated customer.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_assistant_conversations",
    )

    title = models.CharField(
        max_length=200,
        blank=True,
        default="New shopping conversation",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_assistant_conversations"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.user_id})"


class ConversationMessage(models.Model):
    """
    Individual customer and assistant messages.

    Tool execution details can be stored separately in metadata
    without exposing internal tool information to the customer.
    """

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"

    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
    )

    content = models.TextField()

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_assistant_messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class AssistantOrderDraft(models.Model):
    """A short-lived, customer-owned checkout prepared by the shopper agent."""

    STATUS_DRAFT = "draft"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_CONFIRMED, "Confirmed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="ai_assistant_order_drafts")
    items = models.JSONField(default=list)
    shipping_address = models.ForeignKey("users.Address", on_delete=models.PROTECT)
    shipping_method = models.CharField(max_length=100, blank=True)
    confirmation_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_assistant_order_drafts"
        indexes = [models.Index(fields=["user", "status", "expires_at"])]
    
    

class ProductEmbedding(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    product = models.OneToOneField(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="search_embedding",
    )

    embedding = VectorField(dimensions=1536)

    content_hash = models.CharField(
        max_length=64,
        db_index=True,
    )

    model_name = models.CharField(
        max_length=100,
        default="text-embedding-3-small",
    )

    indexed_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "ai_product_embeddings"

    def __str__(self):
        return f"Embedding for {self.product_id}"
