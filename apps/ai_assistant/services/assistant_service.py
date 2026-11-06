
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
)

from apps.ai_assistant.models import (
    Conversation,
    ConversationMessage,
)

from apps.ai_assistant.agents.shopper.builder import (
    get_shopper_graph,
)



MAX_HISTORY_MESSAGES = 20


class AssistantService:
    """
    Manage shopper conversations and invoke the
    existing LangGraph assistant.
    """

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
    def _extract_products(messages, selected_product_id=None, selected_variant_id=None):
        """
        Extract lightweight product cards and selectable
        variants from successful search_products results.
        """

        products_by_id = {}

        for message in messages:
            if not isinstance(message, ToolMessage):
                continue

            if message.name != "search_products":
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

                products = result.get("products", [])

                if not isinstance(products, list):
                    continue

                for product in products:
                    if not isinstance(product, dict):
                        continue

                    product_id = product.get("id")

                    if not product_id:
                        continue

                    if selected_product_id and str(product_id) != str(selected_product_id):
                        continue

                    variants = []

                    for variant in product.get("variants") or []:
                        if not isinstance(variant, dict):
                            continue

                        variant_id = variant.get("id")
                        sku = variant.get("sku")

                        if not variant_id or not sku:
                            continue

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
                            "image": variant.get("image"),
                        })

                    products_by_id[str(product_id)] = {
                        "id": str(product_id),
                        "title": product.get("title", ""),
                        "slug": product.get("slug", ""),
                        "min_price": product.get("min_price"),
                        "max_price": product.get("max_price"),
                        "has_stock": bool(
                            product.get("has_stock", False)
                        ),
                        "image": product.get("image"),
                        "selected_variant_id": (
                            str(selected_variant_id)
                            if selected_variant_id else None
                        ),
                        "variants": variants,
                    }

            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        return list(products_by_id.values())[:10]

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
        selected_item = (order_draft or {}).get("items", [None])[0]
        products = cls._extract_products(
            result["messages"],
            selected_product_id=(selected_item or {}).get("product_id"),
            selected_variant_id=(selected_item or {}).get("variant_id"),
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
            "created_at": assistant_message.created_at,
        }
