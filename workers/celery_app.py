import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adorchestrator.settings.base")

app = Celery("adorchestrator", include=["workers.tasks.analytics", "workers.tasks.creative_ai"])
app.config_from_object("django.conf:settings", namespace="CELERY")
