import json
import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.products.models import Category


logger = logging.getLogger(__name__)


class CategoryListInput(BaseModel):
    parent_slug: str | None = Field(
        default=None,
        description=(
            "Optional parent category slug. "
            "When omitted, return all active and visible "
            "categories, including nested subcategories."
        ),
    )


@tool(args_schema=CategoryListInput)
def list_product_categories(
    parent_slug: str | None = None,
) -> str:
    """
    Retrieve all publicly visible store categories.

    A category's own visibility determines whether
    it is returned. Hidden parent categories do not
    automatically hide their visible children.

    When parent_slug is provided, return its direct
    publicly visible children.
    """

    try:
        # Only filter categories by their OWN visibility.
        categories = list(
            Category.objects.filter(
                is_active=True,
                is_hidden=False,
            ).select_related("parent")
        )

        # Find parent independently, allowing visible
        # children of a hidden organizational parent
        # to be browsed by its slug.
        if parent_slug:
            parent = Category.objects.filter(
                slug=parent_slug,
                is_active=True,
            ).first()

            if parent is None:
                return json.dumps({
                    "success": False,
                    "error": "Category not found.",
                })

            categories = [
                category
                for category in categories
                if category.parent_id == parent.id
            ]

        # Sort by full category path.
        categories.sort(
            key=lambda category: (
                category.full_path or category.name
            ).lower()
        )

        results = []

        for category in categories:
            parent = category.parent

            # Do not advertise hidden/inactive parents
            # as publicly browsable categories.
            parent_is_public = (
                parent is not None
                and parent.is_active
                and not parent.is_hidden
            )

            results.append({
                "id": str(category.id),
                "name": category.name,
                "slug": category.slug,
                "full_path": (
                    category.full_path
                    if parent_is_public or parent is None
                    else category.name
                ),
                "parent_id": (
                    str(parent.id)
                    if parent_is_public
                    else None
                ),
                "parent_name": (
                    parent.name
                    if parent_is_public
                    else None
                ),
            })

        return json.dumps({
            "success": True,
            "total": len(results),
            "categories": results,
        })

    except Exception:
        logger.exception(
            "AI category retrieval failed"
        )

        return json.dumps({
            "success": False,
            "error": "Categories are temporarily unavailable.",
        })