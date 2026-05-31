from typing import Any


def coerce_bool(value: Any, default: bool = True) -> bool:
    """
    Coerce various input types to boolean.
    
    Args:
        value: The value to coerce
        default: Default value if coercion fails
    
    Returns:
        Boolean value
    """
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    
    if isinstance(value, (int, float)):
        return bool(value)
    
    return default


def sanitize_search_query(query: str, max_length: int = 200) -> str:
    """Sanitize and truncate search query"""
    if not query:
        return ""
    
    query = query.strip()
    if len(query) > max_length:
        query = query[:max_length]
    
    return query