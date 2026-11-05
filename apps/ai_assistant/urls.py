
from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("chat/", views.assistant_chat, name="assistant-chat"),
]
