
from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("chat/", views.assistant_chat, name="assistant-chat"),
    path("orders/<uuid:draft_id>/confirm/", views.confirm_assistant_order, name="assistant-order-confirm"),
]
