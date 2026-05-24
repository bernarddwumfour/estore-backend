# apps/users/utils/auth_utils.py

def is_authenticated_user(request) -> bool:
    """Check if request has an authenticated user"""
    return (hasattr(request, 'user') and 
            request.user is not None and 
            hasattr(request.user, 'is_authenticated') and 
            request.user.is_authenticated)


def get_user_or_none(request):
    """Get user from request or return None"""
    if is_authenticated_user(request):
        return request.user
    return None