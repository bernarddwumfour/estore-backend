try:
    from .celery import app as celery_app  # noqa: F401
except ImportError:  # celery not installed in this environment
    celery_app = None
