from django.urls import path

from .views import AlertAcknowledgeView, AlertListView, CampaignReportView

urlpatterns = [
    path("campaigns/<uuid:campaign_id>/report/", CampaignReportView.as_view(), name="campaign-report"),
    path("alerts/", AlertListView.as_view(), name="alert-list"),
    path("alerts/<uuid:alert_id>/acknowledge/", AlertAcknowledgeView.as_view(), name="alert-acknowledge"),
]
