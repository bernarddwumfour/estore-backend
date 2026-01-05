"""
Django settings for estore project.
Industry-ready base configuration (no DRF).
"""

import dj_database_url
from pathlib import Path
from decouple import config, Csv
import os

# ------------------------------------------------------------------------------
# BASE
# ------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="unsafe-dev-secret-key")  # dev only

DEBUG = config("DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ------------------------------------------------------------------------------
# APPLICATIONS
# ------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "corsheaders",
    # Local apps
    "users",
    "products",
    "orders",
    "api",
]

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
        "DIRS": [],
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

DATABASES = {
    'default': dj_database_url.parse(os.environ.get('DATABASE_URL'), conn_max_age=600),
}



# ------------------------------------------------------------------------------
# AUTH
# ------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
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
STATIC_URL = "/static/"

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


CORS_ALLOWED_ORIGINS = [
    "https://9000-firebase-estore-1765889581026.cluster-ikslh4rdsnbqsvu5nw3v4dqjj2.cloudworkstations.dev",
]
CORS_ALLOW_CREDENTIALS = True

FRONTEND_BASE_URL = config(
    "FRONTEND_BASE_URL",
    default="https://9000-firebase-estore-1765889581026.cluster-ikslh4rdsnbqsvu5nw3v4dqjj2.cloudworkstations.dev/",
)


# ------------------------------------------------------------------------------
# SECURITY HEADERS
# ------------------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ------------------------------------------------------------------------------
# JWT (manual implementation – no DRF)
# ------------------------------------------------------------------------------
JWT_SETTINGS = {
    "SECRET_KEY": config("JWT_SECRET_KEY", default=SECRET_KEY),
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_LIFETIME": 60 * 15,  # 15 minutes
    "REFRESH_TOKEN_LIFETIME": 60 * 60 * 24 * 7,  # 7 days
}

# ------------------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs/django.log",
        },
    },
    "root": {
        "handlers": ["file"],
        "level": "INFO",
    },
}

# Only log to file if NOT on Render
if not os.environ.get('RENDER'):
    LOGGING['handlers']['file'] = {
        'level': 'DEBUG',
        'class': 'logging.FileHandler',
        'filename': 'debug.log',
    }

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "bernardkusi25@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "aemezmgmtvfavptl")
DEFAULT_FROM_EMAIL = os.getenv("SENDER_EMAIL", SMTP_USERNAME)

# App Configuration
SITE_NAME = os.getenv("SITE_NAME", "API Service")

# Email Verification
EMAIL_VERIFICATION_EXPIRY_HOURS = 24
DISABLE_EMAIL_VERIFICATION = (
    os.getenv("DISABLE_EMAIL_VERIFICATION", "False").lower() == "true"
)

# API Domain
DOMAIN_NAME = os.getenv("DOMAIN_NAME", "localhost:8000")
USE_HTTPS = os.getenv("USE_HTTPS", "False").lower() == "true"


# Base URL to serve media files from
MEDIA_URL = "/media/"

# Absolute filesystem path to the directory that will hold user-uploaded files
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
