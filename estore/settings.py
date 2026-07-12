"""
Django settings for estore project.
Industry-ready base configuration (no DRF).
"""

import dj_database_url
from pathlib import Path
from decouple import config, Csv
from importlib.util import find_spec
import os
try:
    import environ
except ModuleNotFoundError:  # pragma: no cover - local fallback for lean envs
    environ = None

BASE_DIR = Path(__file__).resolve().parent.parent

if environ is not None:
    env = environ.Env()
    environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = config("SECRET_KEY")  # required; no insecure fallback

DEBUG = config("DEBUG", default=False, cast=bool)  # secure-by-default

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

RATELIMIT_ENABLE = True


PAYSTACK_SECRET_KEY = config("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = config("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_BASE_URL = 'https://api.paystack.co'  # Production URL (same for test keys)

PAYSTACK_WEBHOOK_SECRET = config("PAYSTACK_WEBHOOK_SECRET", default="")

PAYSTACK_CALLBACK_URL = config("PAYSTACK_CALLBACK_URL", default="http://localhost:3000/orders/callback")
PAYMENT_SUCCESS_URL = config("PAYMENT_SUCCESS_URL", default="http://localhost:3000/orders/success")
PAYMENT_CANCEL_URL = config("PAYMENT_CANCEL_URL", default="http://localhost:3000/orders/cancel")

AFFILIATE_CODE_DISCOUNT_TYPE = config("AFFILIATE_CODE_DISCOUNT_TYPE", default="percentage")
AFFILIATE_CODE_DISCOUNT_VALUE = config("AFFILIATE_CODE_DISCOUNT_VALUE", default="5.00")
AFFILIATE_COMMISSION_BASE = config("AFFILIATE_COMMISSION_BASE", default="discounted_subtotal")
# APPLICATIONS

TERMINAL_AFRICA_API_KEY = config("TERMINAL_AFRICA_API_KEY", default="")
TERMINAL_AFRICA_BASE_URL = config("TERMINAL_AFRICA_BASE_URL", default="https://api.terminal.africa/v1")
TERMINAL_AFRICA_WEBHOOK_SECRET = config("TERMINAL_AFRICA_WEBHOOK_SECRET", default="")


ZERNIO_API_KEY = config("ZERNIO_API_KEY", default="")
ZERNIO_BASE_URL = config("ZERNIO_BASE_URL", default="https://zernio.com/api/v1")
# Optional comma-separated platform filter, e.g. "instagram,twitter". Empty = all connected accounts.
ZERNIO_PLATFORMS = [p.strip() for p in config("ZERNIO_PLATFORMS", default="").split(",") if p.strip()]

# Public storefront base URL used in social post captions
STOREFRONT_BASE_URL = config("STOREFRONT_BASE_URL", default="http://localhost:3000")

# Default shipping origin (warehouse address)
DEFAULT_SHIPPING_ORIGIN = {
    "country": "GH",
    "state": "Greater Accra",
    "city": "Accra",
    "postal_code": "00233",
    "address": "Your Warehouse Address, Accra, Ghana",
}

# Store Address Configuration (for POS in-store pickup)
STORE_ADDRESS = {
    'first_name': config("STORE_ADDRESS_FIRST_NAME", default="Store"),
    'last_name': config("STORE_ADDRESS_LAST_NAME", default="Pickup"),
    'email': config("STORE_ADDRESS_EMAIL", default="store@example.com"),
    'phone': config("STORE_ADDRESS_PHONE", default="+233000000000"),
    'address_line1': config("STORE_ADDRESS_LINE1", default="123 Main Street"),
    'address_line2': config("STORE_ADDRESS_LINE2", default=""),
    'city': config("STORE_ADDRESS_CITY", default="Accra"),
    'state': config("STORE_ADDRESS_STATE", default="Greater Accra"),
    'postal_code': config("STORE_ADDRESS_POSTAL_CODE", default="GA-123"),
    'country': config("STORE_ADDRESS_COUNTRY", default="GH"),
    'instructions': config("STORE_ADDRESS_INSTRUCTIONS", default="In-Store Pickup"),
}

# Cache backend.
# Use Redis in any environment where REDIS_URL is set (required in production for
# cross-process rate limiting and shared Paystack reference storage). Falls back to
# per-process LocMemCache only for local development.
REDIS_URL = config("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# Celery. Uses Redis as broker when available; otherwise runs tasks eagerly
# (inline) so local development and tests need no broker.
if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]


RATELIMIT_USE_CACHE = 'default'
RATELIMIT_VIEW = 'apps.common.views.rate_limit_exceeded'
RATELIMIT_HEADERS_ENABLED = True

# ==================== RATE LIMIT EXEMPTIONS (Optional) ====================

# RATELIMIT_EXEMPT_IPS = [
#     '127.0.0.1',
#     '::1',
# ]

# # URLs that bypass rate limiting (health checks, webhooks)
# RATELIMIT_EXEMPT_PATHS = [
#     '/health',
#     '/metrics',
# ]


# ------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    'cloudinary_storage', 
    'django.contrib.staticfiles',
    'cloudinary',
    # Third-party
    "corsheaders",
    # Local apps
    "apps.users",
    "apps.products",
    "apps.orders",
    "apps.common",
    "apps.promotions",
    "apps.marketing",
    "apps.social",
    "apps.blog",
]

for optional_app in ["cloudinary_storage", "django.contrib.staticfiles", "cloudinary"]:
    if optional_app in INSTALLED_APPS and not find_spec(optional_app):
        INSTALLED_APPS.remove(optional_app)

if "django.contrib.staticfiles" not in INSTALLED_APPS:
    for dependent_app in ["cloudinary_storage", "cloudinary"]:
        if dependent_app in INSTALLED_APPS:
            INSTALLED_APPS.remove(dependent_app)

# Cloudinary Config (credentials sourced from environment — never hardcode)
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': config("CLOUDINARY_CLOUD_NAME", default=""),
    'API_KEY': config("CLOUDINARY_API_KEY", default=""),
    'API_SECRET': config("CLOUDINARY_API_SECRET", default=""),
}

# Set as default media storage
if "cloudinary_storage" in INSTALLED_APPS:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# ------------------------------------------------------------------------------
# MIDDLEWARE
# ------------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ------------------------------------------------------------------------------
# URLS / WSGI
# ------------------------------------------------------------------------------
ROOT_URLCONF = "estore.urls"
WSGI_APPLICATION = "estore.wsgi.application"

# ------------------------------------------------------------------------------
# TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ------------------------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------------------------
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

# Database
# core/settings.py

# SSL is required for Neon in production; disable for local/sqlite test runs via
# DB_SSL_REQUIRE=False (sqlite rejects the sslmode option).
DATABASE_URL = config("DATABASE_URL", default="")
DB_SSL_REQUIRE = config(
    "DB_SSL_REQUIRE",
    default=bool(DATABASE_URL and not DATABASE_URL.startswith("sqlite")),
    cast=bool,
)

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=DB_SSL_REQUIRE,  # Critical for Neon in production
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ------------------------------------------------------------------------------
# AUTH
# ------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "users.User"

# ------------------------------------------------------------------------------
# INTERNATIONALIZATION
# ------------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------------------
# STATIC FILES
# ------------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# ------------------------------------------------------------------------------
# CORS / CSRF
# ------------------------------------------------------------------------------
# CORS_ALLOWED_ORIGINS = config(
#     "CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv()
# )

# CSRF_TRUSTED_ORIGINS = config(
#     "CSRF_TRUSTED_ORIGINS", default="http://localhost:3000", cast=Csv()
# )

# CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_SSL_REDIRECT = True

CSRF_TRUSTED_ORIGINS = [
    "https://estore-backend-mtec.onrender.com",
]

CORS_ALLOWED_ORIGINS = [
    "https://9000-firebase-estore-1765889581026.cluster-ikslh4rdsnbqsvu5nw3v4dqjj2.cloudworkstations.dev",
    "https://estore-frontend-boqb.vercel.app",
    "http://localhost:3000",
    
]
CORS_ALLOW_CREDENTIALS = True

FRONTEND_BASE_URL = config(
    "FRONTEND_BASE_URL",
    default="https://estore-frontend-boqb.vercel.app",
)


# ------------------------------------------------------------------------------
# SECURITY HEADERS
# ------------------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# HTTPS / transport hardening — enforced only outside local development.
# Render (and most PaaS) terminate TLS at the proxy, so trust the forwarded proto.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ------------------------------------------------------------------------------
# JWT (manual implementation – no DRF)
# ------------------------------------------------------------------------------
JWT_SECRET_KEY = config("JWT_SECRET_KEY", default=SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_ISSUER = config("JWT_ISSUER", default="estore-backend")
JWT_AUDIENCE = config("JWT_AUDIENCE", default="estore-clients")
ACCESS_TOKEN_TTL = 60 * 15  # 15 minutes
REFRESH_TOKEN_TTL = 60 * 60 * 24 * 7  # 7 days
VERIFICATION_TOKEN_TTL = 60 * 60 * 24  # 24 hours

JWT_SETTINGS = {
    "SECRET_KEY": JWT_SECRET_KEY,
    "ALGORITHM": JWT_ALGORITHM,
    "ACCESS_TOKEN_LIFETIME": ACCESS_TOKEN_TTL,
    "REFRESH_TOKEN_LIFETIME": REFRESH_TOKEN_TTL,
}

# ------------------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------------------

# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'handlers': {
#         'console': {
#             'class': 'logging.StreamHandler',
#         },
#     },
#     'root': {
#         'handlers': ['console'],
#         'level': 'INFO',
#     },
# }
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",  # Only show warnings and errors
    },
    "loggers": {
        "django_ratelimit": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

# 2. Only add File Logging if NOT on Render (Local Development)
# if not os.environ.get('RENDER'):
#     LOGGING['handlers']['file'] = {
#         "level": "INFO",
#         "class": "logging.FileHandler",
#         "filename": BASE_DIR / "logs/django.log",
#     }
#     LOGGING['root']['handlers'].append('file')


# Email Configuration (Resend)
RESEND_API_KEY = config("RESEND_API_KEY", default="").strip()
DEFAULT_FROM_EMAIL = config("SENDER_EMAIL", default="").strip()

# App Configuration
SITE_NAME = config("SITE_NAME", default="API Service")
DEFAULT_FROM_NAME = config("DEFAULT_FROM_NAME", default=SITE_NAME)

# Email Verification
EMAIL_VERIFICATION_EXPIRY_HOURS = 24
DISABLE_EMAIL_VERIFICATION = config("DISABLE_EMAIL_VERIFICATION", default=False, cast=bool)

# API Domain
DOMAIN_NAME = config("DOMAIN_NAME", default="localhost:8000")
USE_HTTPS = config("USE_HTTPS", default=False, cast=bool)


# Base URL to serve media files from
MEDIA_URL = "/media/"

# Absolute filesystem path to the directory that will hold user-uploaded files
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
APPEND_SLASH = False
