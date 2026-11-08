
import json
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)

from apps.ai_assistant.models import (
    Conversation,
    ConversationMessage,
)

from apps.ai_assistant.agents.shopper.builder import (
    get_shopper_graph,
)
from apps.ai_assistant.agents.guest.builder import get_guest_graph



MAX_HISTORY_MESSAGES = 20


class AssistantService:
    """
    Manage shopper conversations and invoke the
    existing LangGraph assistant.
    """

    @classmethod
    def send_guest_message(cls, message, history=None):
        """Run the public-only guest graph without creating an account conversation."""
        message = message.strip()
        if not message:
            raise ValueError("Message cannot be empty.")
        messages = []
        for item in (history or [])[-12:]:
            if item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
            else:
                messages.append(AIMessage(content=item["content"]))
        messages.append(HumanMessage(content=message))

        result = get_guest_graph().invoke(
            {"messages": messages}, config={"recursion_limit": 12},
        )
        response_text = cls._extract_text(result["messages"][-1])
        if not response_text.strip():
            raise RuntimeError("The assistant returned an empty response.")
        return {
            "conversation_id": None,
            "message_id": str(uuid4()),
            "response": response_text,
            "products": cls._extract_products(result["messages"], response_text=response_text),
            "promotions": cls._extract_guest_promotions(result["messages"]),
            "order_draft": None,
            "order_tracking": None,
            "requires_shipping_address": False,
            "created_at": timezone.now().isoformat(),
        }

    @staticmethod
    def _extract_guest_promotions(messages):
        promotions_by_slug = {}
        allowed_tools = {"search_active_promotions", "get_public_promotion_details"}
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name not in allowed_tools:
                continue
            try:
                result = json.loads(message.content)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if result.get("success") is not True:
                continue
            promotions = result.get("promotions") or []
            if isinstance(result.get("promotion"), dict):
                promotions = [*promotions, result["promotion"]]
            for promotion in promotions:
                if isinstance(promotion, dict) and promotion.get("slug"):
                    promotions_by_slug[promotion["slug"]] = promotion
        return list(promotions_by_slug.values())[:10]

    @staticmethod
    def _get_conversation(user, conversation_id=None):
        if conversation_id:
            try:
                return Conversation.objects.get(
                    id=conversation_id,
                    user=user,
                    is_active=True,
                )
            except (
                Conversation.DoesNotExist,
                ValidationError,
                ValueError,
            ):
                raise ValueError("Conversation not found.")

        return None

    @staticmethod
    def _load_history(conversation):
        """
        Load recent customer-facing messages.
        """

        recent_messages = list(
            conversation.messages.order_by(
                "-created_at"
            )[:MAX_HISTORY_MESSAGES]
        )

        recent_messages.reverse()

        history = []

        for message in recent_messages:
            if message.role == ConversationMessage.ROLE_USER:
                history.append(
                    HumanMessage(content=message.content)
                )

            elif message.role == ConversationMessage.ROLE_ASSISTANT:
                history.append(
                    AIMessage(content=message.content)
                )
                products = message.metadata.get("products", [])
                if products:
                    history.append(SystemMessage(content=(
                        "Previously verified customer-visible product cards. "
                        "Their variant IDs may be used only with prepare_order, "
                        "which revalidates live stock and price: "
                        + json.dumps(products)
                    )))

        return history

    @staticmethod
    def _extract_text(message):
        """
        Extract readable text from the final AI message.
        """

        content = message.content

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []

            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                ):
                    text_parts.append(
                        block.get("text", "")
                    )

            return "\n".join(text_parts)

        return str(content)

    
    @staticmethod
    def _infer_selected_variant(product, response_text):
        """Resolve a variant only when the assistant names an unambiguous set of its attributes."""
        if not response_text:
            return None

        normalize = lambda value: "".join(
            character for character in str(value).lower() if character.isalnum()
        )
        normalized_response = normalize(response_text)
        title_signature = normalize(product.get("title", "")).replace("apple", "")
        if not title_signature or title_signature not in normalized_response:
            return None

        variants = product.get("variants") or []
        mentioned_attributes = {}
        for variant in variants:
            for key, value in (variant.get("attributes") or {}).items():
                normalized_value = normalize(value)
                if normalized_value and normalized_value in normalized_response:
                    mentioned_attributes.setdefault(key, set()).add(normalized_value)

        if not mentioned_attributes:
            return variants[0].get("id") if len(variants) == 1 else None

        matching_variants = []
        for variant in variants:
            attributes = variant.get("attributes") or {}
            if all(
                normalize(attributes.get(key, "")) in mentioned_values
                for key, mentioned_values in mentioned_attributes.items()
            ):
                matching_variants.append(variant)

        return matching_variants[0].get("id") if len(matching_variants) == 1 else None

    @staticmethod
    def _extract_products(
        messages,
        selected_variants_by_product=None,
        response_text="",
    ):
        """
        Extract lightweight product cards and selectable
        variants from successful search_products results.
        """

        products_by_id = {}

        for message in messages:
            if not isinstance(message, ToolMessage):
                continue

            if message.name not in {"search_products", "get_product_details"}:
                continue

            try:
                content = message.content

                if not isinstance(content, str):
                    continue

                result = json.loads(content)

                if not isinstance(result, dict):
                    continue

                if result.get("success") is not True:
                    continue

                products = (
                    result.get("products", [])
                    if message.name == "search_products"
                    else [result.get("product")]
                )

                if not isinstance(products, list):
                    continue

                for product in products:
                    if not isinstance(product, dict):
                        continue

                    product_id = product.get("id")

                    if not product_id:
                        continue

                    variants = []

                    for variant in product.get("variants") or []:
                        if not isinstance(variant, dict):
                            continue

                        variant_id = variant.get("id")
                        sku = variant.get("sku")

                        if not variant_id or not sku:
                            continue

                        images = variant.get("images") or []
                        image = variant.get("image") or next(
                            (entry.get("url") for entry in images if isinstance(entry, dict) and entry.get("url")),
                            None,
                        )
                        variants.append({
                            "id": str(variant_id),
                            "sku": str(sku),
                            "attributes": (
                                variant.get("attributes") or {}
                            ),
                            "price": variant.get("price"),
                            "discounted_price": variant.get(
                                "discounted_price"
                            ),
                            "is_in_stock": bool(
                                variant.get("is_in_stock", False)
                            ),
                            "image": image,
                        })

                    product_key = str(product_id)
                    previous_product = products_by_id.get(product_key, {})
                    selected_variant_id = (
                        (selected_variants_by_product or {}).get(product_key)
                        or product.get("selected_variant_id")
                        or previous_product.get("selected_variant_id")
                    )
                    products_by_id[product_key] = {
                        "id": str(product_id),
                        "title": product.get("title", ""),
                        "slug": product.get("slug", ""),
                        "min_price": product.get("min_price"),
                        "max_price": product.get("max_price"),
                        "has_stock": bool(
                            product.get("has_stock", False)
                        ),
                        "image": product.get("image") or (variants[0]["image"] if variants else None),
                        # The search tool may have resolved an exact colour /
                        # storage request. Preserve that UI selection instead
                        # of falling back to the parent product's default.
                        "selected_variant_id": str(selected_variant_id)
                        if selected_variant_id
                        else None,
                        "variants": variants,
                    }

            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        cards = list(products_by_id.values())[:10]
        for product in cards:
            product_key = product["id"]
            draft_variant_id = (selected_variants_by_product or {}).get(product_key)
            inferred_variant_id = AssistantService._infer_selected_variant(
                product, response_text
            )
            product["selected_variant_id"] = (
                draft_variant_id
                or inferred_variant_id
                or product.get("selected_variant_id")
            )
        return cards

    @staticmethod
    def _recent_product_cards(conversation, limit=20):
        if conversation is None:
            return []
        for previous in conversation.messages.filter(
            role=ConversationMessage.ROLE_ASSISTANT
        ).order_by("-created_at")[:limit]:
            cards = (previous.metadata or {}).get("products") or []
            if isinstance(cards, list) and cards:
                return [card for card in cards if isinstance(card, dict)]
        return []

    @staticmethod
    def _merge_followup_product_cards(products, previous_cards, message, response_text):
        """Reuse recent verified cards for an image/show follow-up with no new catalog call."""
        import re

        text = f"{message} {response_text}".lower()
        tokens = set(re.findall(r"[a-z0-9]+", text))
        display_intent = bool(tokens & {"show", "see", "view", "display", "image", "images", "picture", "pictures", "photo", "photos"})
        reference_to_prior = bool(tokens & {"them", "those", "these", "both", "it", "that", "this", "ones", "one"})
        if not display_intent:
            return products

        normalized_text = "".join(character for character in text if character.isalnum())
        mentioned = []
        for card in previous_cards:
            signature = "".join(
                character
                for character in str(card.get("title", "")).lower()
                if character.isalnum()
            ).replace("apple", "")
            if signature and signature in normalized_text:
                mentioned.append(card)

        # Pronouns such as "show them" refer to the latest product cards.
        candidates = mentioned or (previous_cards if reference_to_prior else [])
        if not candidates:
            return products

        resolved_candidates = []
        for card in candidates:
            inferred_variant_id = AssistantService._infer_selected_variant(
                card, response_text
            )
            resolved_candidates.append(
                {
                    **card,
                    **(
                        {"selected_variant_id": inferred_variant_id}
                        if inferred_variant_id
                        else {}
                    ),
                }
            )

        merged = {str(card.get("id")): card for card in products if card.get("id")}
        for previous in resolved_candidates:
            product_id = previous.get("id")
            if not product_id:
                continue
            product_key = str(product_id)
            existing = merged.get(product_key)
            if existing is None:
                merged[product_key] = previous
            elif not existing.get("selected_variant_id") and previous.get("selected_variant_id"):
                merged[product_key] = {
                    **existing,
                    "selected_variant_id": previous["selected_variant_id"],
                }
        return list(merged.values())[:10]

    @staticmethod
    def _extract_order_draft(messages):
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "prepare_order":
                continue
            try:
                result = json.loads(message.content)
                if result.get("success") and isinstance(result.get("draft"), dict):
                    return result["draft"]
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_order_tracking(messages):
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "track_customer_orders":
                continue
            try:
                result = json.loads(message.content)
                if result.get("success") and isinstance(result.get("orders"), list):
                    return {
                        "orders": result["orders"],
                        "message": result.get("message"),
                        "view": result.get("view", "detail"),
                    }
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_shipping_address_requirement(messages):
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "prepare_order":
                continue
            try:
                result = json.loads(message.content)
                if result.get("requires_address") is True:
                    return True
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return False


    @classmethod
    def send_message(
        cls,
        user,
        message,
        conversation_id=None,
    ):
        """
        Process a customer message through the shopper agent.
        """

        message = message.strip()

        if not message:
            raise ValueError("Message cannot be empty.")

        # Do not persist the customer's message until the assistant has
        # generated a usable response. Otherwise a failed request is left in
        # the conversation and a retry sends the same message twice.
        conversation = cls._get_conversation(
            user=user,
            conversation_id=conversation_id,
        )

        history = (
            cls._load_history(conversation)
            if conversation is not None
            else []
        )
        history.append(HumanMessage(content=message))

        graph = get_shopper_graph()

        result = graph.invoke(
    {"messages": history},
    config={
        "configurable": {
            "authenticated_user_id": (
                str(user.pk)
                if user is not None and user.is_authenticated
                else None
            ),
        },
    },
)
        
        import logging

        logger = logging.getLogger(__name__)

        for graph_message in result["messages"]:
            if isinstance(graph_message, ToolMessage):
                logger.warning(
                    "SHOPPER TOOL RESULT | name=%s | content=%s",
                    graph_message.name,
                    str(graph_message.content)[:2000],
                )

        final_message = result["messages"][-1]

        response_text = cls._extract_text(final_message)

        if not response_text.strip():
            raise RuntimeError(
                "The assistant returned an empty response."
            )

        order_draft = cls._extract_order_draft(result["messages"])
        order_tracking = cls._extract_order_tracking(result["messages"])
        requires_shipping_address = cls._extract_shipping_address_requirement(
            result["messages"]
        )
        selected_variants_by_product = {
            str(item["product_id"]): str(item["variant_id"])
            for item in (order_draft or {}).get("items", [])
            if item.get("product_id") and item.get("variant_id")
        }
        products = cls._extract_products(
            result["messages"],
            selected_variants_by_product=selected_variants_by_product,
            response_text=response_text,
        )
        products = cls._merge_followup_product_cards(
            products,
            cls._recent_product_cards(conversation),
            message,
            response_text,
        )
        lowered_response = response_text.lower()
        is_image_request = any(
            word in message.lower()
            for word in ("show", "see", "image", "picture", "photo")
        )
        claims_images_unavailable = any(
            phrase in lowered_response
            for phrase in (
                "can't display images",
                "cannot display images",
                "can't show images",
                "cannot show images",
                "product cards in the store interface",
            )
        )
        if products and is_image_request and claims_images_unavailable:
            response_text = (
                "Here are the product cards for the variants you selected. "
                "Their images are shown below."
            )
        
        logger.warning(
    "SHOPPER EXTRACTED PRODUCTS | count=%s | titles=%s",
    len(products),
    [product["title"] for product in products],
)

        with transaction.atomic():
            if conversation is None:
                conversation = Conversation.objects.create(
                    user=user,
                    title=message[:200],
                )

            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.ROLE_USER,
                content=message,
            )

            assistant_message = ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.ROLE_ASSISTANT,
                content=response_text,
                metadata={
                    "products": products,
                    "order_draft": order_draft,
                    "order_tracking": order_tracking,
                    "requires_shipping_address": requires_shipping_address,
                },
            )

            conversation.updated_at = timezone.now()

            conversation.save(
                update_fields=["updated_at"]
            )

        return {
            "conversation_id": str(conversation.id),
            "message_id": str(assistant_message.id),
            "response": response_text,
            "products": products,
            "order_draft": order_draft,
            "order_tracking": order_tracking,
            "requires_shipping_address": requires_shipping_address,
            "created_at": assistant_message.created_at,
        }
