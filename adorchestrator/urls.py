"""AdOrchestrator URL Configuration."""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/campaigns/", include("apps.campaigns.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/creative-ai/", include("apps.creative_ai.urls")),
    path("api/budgets/", include("apps.budgets.urls")),
]
