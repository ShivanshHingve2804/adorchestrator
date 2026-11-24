"""
Django base settings for AdOrchestrator.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_celery_beat",
    # Local apps
    "apps.campaigns",
    "apps.analytics",
    "apps.creative_ai",
    "apps.budgets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "adorchestrator.urls"

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

WSGI_APPLICATION = "adorchestrator.wsgi.application"

# Database - PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "adorchestrator"),
        "USER": os.environ.get("POSTGRES_USER", "ado"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "ado_secret"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Cache - Redis
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# DRF
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_BEAT_SCHEDULE = {
    "refresh-performance-snapshots": {
        "task": "workers.tasks.analytics.refresh_materialized_views",
        "schedule": 900.0,
    },
    "detect-campaign-anomalies": {
        "task": "workers.tasks.analytics.detect_anomalies",
        "schedule": 900.0,
    },
    "maintain-ad-event-partitions": {
        "task": "workers.tasks.analytics.maintain_event_partitions",
        "schedule": 86400.0,
    },
    "generate-weekly-creative-summary": {
        "task": "workers.tasks.creative_ai.generate_weekly_summary",
        "schedule": 604800.0,
    },
}

# Temporal
TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "temporal:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")

# Mock Platforms
MOCK_PLATFORM_BASE_URL = os.environ.get("MOCK_PLATFORM_BASE_URL", "http://mock-platforms:8090")

# AI provider and model identifiers are deployment configuration, not code defaults.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "ollama").lower()
AI_BASE_URL = os.environ.get("AI_BASE_URL", "http://ollama:11434")
AI_VISION_MODEL = os.environ.get("AI_VISION_MODEL", "")
AI_TEXT_MODEL = os.environ.get("AI_TEXT_MODEL", "")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_REQUEST_TIMEOUT = float(os.environ.get("AI_REQUEST_TIMEOUT", "60"))

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
