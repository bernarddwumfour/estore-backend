from django.apps import AppConfig


class AiAssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai_assistant"
    verbose_name = "AI Shopping Assistant"

    def ready(self):
        from . import signals  # noqa: F401
