"""Production settings."""
from .base import *  # noqa: F401, F403

DEBUG = False

# Add production-specific overrides here
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
