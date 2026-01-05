"""
Decorators for authentication and permission handling.
"""
from django.http import JsonResponse
from api.utils import get_user_from_token

def jwt_required(view_func):
    """Decorator to require JWT authentication."""
    def wrapper(request, *args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'success': False,
                'message': 'Authentication required',
                'error': 'No token provided'
            }, status=401)
        
        token = auth_header.split(' ')[1]
        
        # Validate token
        user, error = get_user_from_token(token)
        if error:
            return JsonResponse({
                'success': False,
                'message': 'Authentication failed',
                'error': error
            }, status=401)
        
        # Add user to request
        request.user = user
        return view_func(request, *args, **kwargs)
    
    return wrapper

def require_methods(allowed_methods):
    """Decorator to restrict HTTP methods."""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if request.method not in allowed_methods:
                return JsonResponse({
                    'success': False,
                    'message': f'Method {request.method} not allowed',
                    'error': f'Allowed methods: {", ".join(allowed_methods)}'
                }, status=405)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator