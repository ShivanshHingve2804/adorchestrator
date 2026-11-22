"""ASGI config for AdOrchestrator."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adorchestrator.settings.dev")
application = get_asgi_application()
