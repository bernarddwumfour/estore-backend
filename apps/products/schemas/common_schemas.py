"""
Common Schemas - Shared serialization utilities
"""

from typing import Dict


def serialize_pagination_metadata(pagination_meta: Dict) -> Dict:
    """Serialize pagination metadata"""
    return {
        "current_page": pagination_meta["current_page"],
        "per_page": pagination_meta["per_page"],
        "total": pagination_meta["total"],
        "total_pages": pagination_meta["total_pages"],
        "has_next": pagination_meta["has_next"],
        "has_previous": pagination_meta["has_previous"],
        "next_page": pagination_meta["next_page"],
        "previous_page": pagination_meta["previous_page"],
        "start_index": pagination_meta["start_index"],
        "end_index": pagination_meta["end_index"],
    }


def serialize_bulk_action_result(results: Dict) -> Dict:
    """Serialize bulk action result for API response"""
    return {
        "success": [
            {"id": item["id"], "name": item["name"]} for item in results["success"]
        ],
        "failed": [
            {"id": item["id"], "name": item["name"], "reason": item["reason"]}
            for item in results["failed"]
        ],
        "total": results["total"],
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
    }


def serialize_product_bulk_action_result(results: Dict) -> Dict:
    """Serialize product bulk action result for API response"""
    return {
        "success": [
            {"id": item["id"], "name": item["name"]} for item in results["success"]
        ],
        "failed": [
            {"id": item["id"], "name": item["name"], "reason": item["reason"]}
            for item in results["failed"]
        ],
        "total": results["total"],
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
    }