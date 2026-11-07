"""Confirm admin prepared user changes."""

from django.core.cache import cache

from apps.users.models import User


class AdminUserActionService:
    @staticmethod
    def client_preview(admin, action_id):
        """Build sensitive confirmation details after the LLM has finished."""
        if not admin.is_active or admin.role != User.ROLE_ADMIN:
            return None
        record = cache.get(f"admin_user_action:{action_id}")
        if not record or record["user_id"] != str(admin.pk):
            return None
        target = User.objects.filter(pk=record["target_id"]).first()
        if not target:
            return None
        return {
            "action_id": action_id,
            "action": "update_user",
            "details": {
                "target_id": str(target.pk),
                "target_summary": f"{target.full_name} <{target.email}> (currently {target.role})",
                "data": record["changes"],
                "ids": [],
                "bulk_action": None,
            },
            "expires_in_seconds": 600,
            "confirmation_path": f"/api/assistant/admin/users/actions/{action_id}/confirm/",
        }

    @staticmethod
    def confirm(admin, action_id):
        if not admin.is_active or admin.role != User.ROLE_ADMIN:
            return None, {"permission": "Admin access required"}
        key = f"admin_user_action:{action_id}"
        record = cache.get(key)
        if not record or record["user_id"] != str(admin.pk):
            return None, {"action": "Pending action not found or expired"}
        if not cache.add(f"{key}:used", True, 600):
            return None, {"action": "Action has already been confirmed"}
        target = User.objects.filter(pk=record["target_id"]).first()
        if not target:
            cache.delete(key)
            return None, {"user": "User not found"}
        if target.pk == admin.pk and record["changes"].get("is_active") is False:
            cache.delete(key)
            return None, {"user": "You cannot deactivate your own account"}
        if target.is_superuser:
            cache.delete(key)
            return None, {"user": "Superuser accounts cannot be changed through the agent"}
        if target.pk == admin.pk and record["changes"].get("role", User.ROLE_ADMIN) != User.ROLE_ADMIN:
            cache.delete(key)
            return None, {"user": "You cannot change your own administrator role"}
        for field, value in record["changes"].items():
            setattr(target, field, value)
        if record["changes"].get("role") == User.ROLE_CUSTOMER:
            target.is_staff = False
            target.is_superuser = False
        target.save()
        result = {"id": str(target.pk), "email": target.email,
                  "role": target.role, "is_active": target.is_active}
        cache.delete(key)
        return result, None
