"""WSGI config for AdOrchestrator."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adorchestrator.settings.dev")
application = get_wsgi_application()
