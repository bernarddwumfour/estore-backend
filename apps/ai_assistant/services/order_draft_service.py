"""Authoritative assisted-checkout draft and confirmation service."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.ai_assistant.models import AssistantOrderDraft
from apps.orders.order_service import OrderService
from apps.orders.shipping_quote_service import ShippingQuoteService
from apps.products.models import ProductVariant
from apps.users.models import Address


class AssistantOrderDraftService:
    DRAFT_LIFETIME = timedelta(minutes=15)

    @staticmethod
    def _address_for(user):
        return Address.objects.filter(
            user=user, address_type=Address.ADDRESS_TYPE_SHIPPING, is_active=True
        ).order_by("-is_default", "-created_at").first()

    @classmethod
    def prepare(cls, user, variant_id, quantity=1):
        address = cls._address_for(user)
        if not address:
            return None, {"requires_address": True, "error": "Add a saved shipping address in checkout before ordering with the assistant."}

        variant = ProductVariant.objects.select_related("product").filter(
            id=variant_id, is_active=True, product__status="published"
        ).first()
        if not variant or variant.stock < quantity:
            return None, {"error": "That product configuration is no longer available in the requested quantity."}

        items = [{"variant_id": str(variant.id), "quantity": quantity}]
        draft = AssistantOrderDraft.objects.create(
            user=user,
            items=items,
            shipping_address=address,
            expires_at=timezone.now() + cls.DRAFT_LIFETIME,
        )
        return cls.serialize(draft), None

    @classmethod
    def serialize(cls, draft):
        prepared, subtotal, weight_items, error = OrderService._prepare_order_items(draft.items)
        if error:
            return {"id": str(draft.id), "confirmation_token": str(draft.confirmation_token), "expired": False, "error": error.get("items", "Items need refreshing.")}

        destination = {
            "country": draft.shipping_address.country,
            "state": draft.shipping_address.state,
            "city": draft.shipping_address.city,
            "postal_code": draft.shipping_address.postal_code,
            "address": draft.shipping_address.address_line1,
        }
        quotes, quote_error = ShippingQuoteService.get_quote_options(destination, draft.items)
        options = quotes.get("options", []) if quotes else []
        selected = next((o for o in options if o["id"] == draft.shipping_method), options[0] if options else None)
        total = subtotal + Decimal(str(selected["cost"])) if selected else subtotal
        return {
            "id": str(draft.id),
            "confirmation_token": str(draft.confirmation_token),
            "expires_at": draft.expires_at.isoformat(),
            "items": [{"product_id": str(item["variant"].product_id), "variant_id": str(item["variant"].id), "title": item["product_title"], "quantity": item["quantity"], "attributes": item["variant_attributes"], "unit_price": float(item["unit_price"])} for item in prepared],
            "subtotal": float(subtotal),
            "total": float(total),
            "currency": "GHS",
            "shipping_options": options,
            "selected_shipping_method": selected["id"] if selected else "",
            "shipping_address": {"label": draft.shipping_address.full_address},
            "quote_error": quote_error,
        }

    @classmethod
    def confirm(cls, user, draft_id, confirmation_token, payment_method, shipping_method=""):
        draft = AssistantOrderDraft.objects.select_related("shipping_address").filter(
            id=draft_id, user=user, status=AssistantOrderDraft.STATUS_DRAFT,
            confirmation_token=confirmation_token, expires_at__gt=timezone.now(),
        ).first()
        if not draft:
            return None, {"general": "This checkout confirmation has expired or was already used."}

        if shipping_method:
            draft.shipping_method = shipping_method
            draft.save(update_fields=["shipping_method", "updated_at"])

        prepared, subtotal, weight_items, error = OrderService._prepare_order_items(draft.items)
        if error:
            return None, error

        destination = {"country": draft.shipping_address.country, "state": draft.shipping_address.state, "city": draft.shipping_address.city, "postal_code": draft.shipping_address.postal_code, "address": draft.shipping_address.address_line1}
        selected, shipping_error = ShippingQuoteService.resolve_selected_option(
            draft.shipping_method, "", destination, draft.items, subtotal,
            sum((Decimal(str(item["variant"].weight or 0.5)) * item["quantity"] for item in weight_items), Decimal("0")),
        )
        if shipping_error:
            return None, shipping_error

        address_data = draft.shipping_address.to_dict()
        order, error = OrderService.create_order(
            user=user, items=draft.items, shipping_address_data=address_data,
            payment_method=payment_method, billing_address_data=address_data,
            shipping_method_id=draft.shipping_method,
        )
        if error:
            return None, error
        draft.status = AssistantOrderDraft.STATUS_CONFIRMED
        draft.save(update_fields=["status", "updated_at"])
        return order, None
