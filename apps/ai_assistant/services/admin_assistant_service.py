"""Invoke the admin graph for an authorized staff member."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from django.core.exceptions import ValidationError

from apps.ai_assistant.agents.admin.builder import get_admin_graph
from apps.ai_assistant.services.assistant_service import AssistantService
from apps.ai_assistant.services.admin_user_action_service import AdminUserActionService
from apps.social.models import SocialMedia


LIST_TOOL_TABLES = {
    "search_admin_products": ("Products", "products", [
        ("title", "Product"), ("status", "Status"), ("category.name", "Category"),
        ("min_price", "Min price"), ("max_price", "Max price"), ("total_stock", "Stock"),
    ]),
    "list_admin_variants": ("Variants", "variants", [
        ("product.title", "Product"), ("sku", "SKU"), ("attributes", "Options"),
        ("price", "Price"), ("stock", "Stock"), ("is_active", "Active"),
    ]),
    "list_admin_categories": ("Categories", "categories", [
        ("name", "Category"), ("full_path", "Path"), ("parent_name", "Parent"),
        ("is_active", "Active"), ("is_hidden", "Hidden"),
    ]),
    "get_inventory_health": ("Inventory health", "items", [
        ("product", "Product"), ("sku", "SKU"), ("stock", "Stock"),
        ("threshold", "Low stock threshold"), ("status", "Status"),
    ]),
    "search_admin_users": ("Users", "users", [
        ("first_name", "First name"), ("user_id", "User ID"), ("role", "Role"),
        ("is_active", "Active"), ("email_verified", "Email verified"),
    ]),
    "search_admin_affiliates": ("Affiliates", "affiliates", [
        ("first_name", "First name"), ("user_id", "User ID"),
        ("is_active", "Active"), ("is_approved", "Approved"), ("level", "Level"),
    ]),
    "search_admin_promotions": ("Promotions", "promotions", [
        ("name", "Promotion"), ("status", "Status"), ("bundle_price", "Bundle price"),
        ("savings_amount", "Savings"), ("has_stock", "Has stock"),
    ]),
    "search_admin_discount_codes": ("Discount codes", "discount_codes", [
        ("code", "Code"), ("name", "Name"), ("discount_type", "Type"),
        ("value", "Value"), ("is_active", "Active"), ("is_affiliate_code", "Affiliate code"),
    ]),
    "search_admin_blog_posts": ("Blog posts", "posts", [
        ("title", "Title"), ("status", "Status"), ("category.name", "Category"),
        ("is_featured", "Featured"), ("published_at", "Published"),
    ]),
    "search_admin_reviews": ("Reviews", "reviews", [
        ("type", "Type"), ("product_title", "Product"), ("order_number", "Order"),
        ("rating", "Rating"), ("overall_rating", "Order rating"),
        ("comment_preview", "Review"), ("is_approved", "Approved"),
    ]),
}


def _list_table(tool_name, payload):
    config = LIST_TOOL_TABLES.get(tool_name)
    data = payload.get("data")
    if not config or not isinstance(data, dict):
        return None
    title, rows_key, columns = config
    rows = data.get(rows_key)
    if not isinstance(rows, list):
        return None
    return {
        "title": title,
        "columns": [{"key": key, "label": label} for key, label in columns],
        "rows": rows,
        "total": data.get("total", data.get("total_at_risk", len(rows))),
        "pagination": data.get("pagination"),
    }


class AdminAssistantService:
    @staticmethod
    def send_message(user, message, history=None, media_ids=None):
        if not user.is_active or user.role not in {user.ROLE_ADMIN, user.ROLE_STAFF}:
            raise PermissionError("Admin access required.")
        messages = []
        for item in (history or [])[-12:]:
            if item["role"] == "user":
                messages.append(HumanMessage(content=item["text"]))
            else:
                messages.append(AIMessage(content=item["text"]))
        media_ids = media_ids or []
        attached = []
        if media_ids:
            try:
                attached = list(SocialMedia.objects.filter(
                    pk__in=media_ids, media_type=SocialMedia.TYPE_IMAGE,
                ))
            except (TypeError, ValueError, ValidationError):
                attached = []
            if len(attached) != len(media_ids) or any(not item.url for item in attached):
                raise ValueError("One or more attached images are unavailable.")
        content = [{"type": "text", "text": message.strip()}]
        for media in attached:
            content[0]["text"] += f"\nAttached image ID: {media.pk}; name: {media.name}"
            content.append({"type": "image_url", "image_url": {"url": media.url}})
        messages.append(HumanMessage(content=content if attached else message.strip()))
        result = get_admin_graph().invoke(
            {"messages": messages},
            config={"configurable": {"authenticated_user_id": str(user.pk)},
                    "recursion_limit": 12},
        )
        answer = AssistantService._extract_text(result["messages"][-1])
        if not answer.strip():
            raise RuntimeError("Empty admin agent response")
        pending_actions = []
        tables = []
        for message in result["messages"]:
            if not isinstance(message, ToolMessage):
                continue
            try:
                payload = json.loads(message.content)
            except (TypeError, ValueError):
                continue
            table = _list_table(getattr(message, "name", ""), payload)
            if table:
                tables.append(table)
            if payload.get("success") and payload.get("pending_action"):
                pending = payload["pending_action"]
                if pending.get("action") == "update_user":
                    client_preview = AdminUserActionService.client_preview(
                        user, pending.get("action_id", "")
                    )
                    if client_preview:
                        pending_actions.append(client_preview)
                    continue
                pending_actions.append(pending)
        return {"response": answer, "pending_actions": pending_actions, "tables": tables}
