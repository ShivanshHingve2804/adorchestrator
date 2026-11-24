"""Production settings."""
import os

from .base import *  # noqa: F401, F403

DEBUG = False

if not SECRET_KEY or SECRET_KEY == "insecure-dev-key-change-me":
    raise RuntimeError("SECRET_KEY must be set to a unique secret in production.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must contain explicit production hostnames.")

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", "3600"))

REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = ["rest_framework.permissions.IsAuthenticated"]
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "rest_framework.authentication.SessionAuthentication",
    "rest_framework.authentication.BasicAuthentication",
]
DATABASES["default"]["OPTIONS"] = {"sslmode": os.environ.get("POSTGRES_SSLMODE", "require")}

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
