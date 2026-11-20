import json
import logging
from functools import wraps
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from apps.common.logging import log_action, LogSeverity
from apps.users.decorators.auth import jwt_required, role_required
from apps.templates.services import RevisionConflict
from estore.utils.responses import APIResponse
logger = logging.getLogger(__name__)

def endpoint(methods):
    def decorate(fn):
        @csrf_exempt
        @require_http_methods(methods)
        @jwt_required
        @role_required('admin', 'staff')
        @ratelimit(key='user', rate='100/h', method='GET', block=True)
        @ratelimit(key='user', rate='50/h', method=['POST', 'PATCH', 'DELETE'], block=True)
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            try:
                request.template_data = {} if request.method == 'GET' or request.content_type == 'multipart/form-data' else json.loads(request.body or '{}')
                if not isinstance(request.template_data, dict):
                    raise ValueError('Request body must be an object.')
                response = fn(request, *args, **kwargs)
                log_action(logger=logger, severity=LogSeverity.INFO, action=fn.__name__, description='Template admin request completed', status_code=response.status_code, user=request.user, request=request, app_name='templates')
                return response
            except RevisionConflict as exc:
                return APIResponse.conflict(str(exc))
            except ObjectDoesNotExist:
                return APIResponse.not_found()
            except IntegrityError:
                return APIResponse.conflict('A record with these values already exists.')
            except (ValueError, TypeError, ValidationError) as exc:
                return APIResponse.validation_error({'detail': str(exc)})
            except Exception:
                logger.exception('Template admin operation failed')
                return APIResponse.server_error()
        return wrapped
    return decorate

