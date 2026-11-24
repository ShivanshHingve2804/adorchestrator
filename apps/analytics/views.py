from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.campaigns.models import Campaign

from .models import Alert
from .serializers import AlertSerializer
from .services import ReportingService


class CampaignReportView(APIView):
    def get(self, request, campaign_id):
        campaign = get_object_or_404(Campaign, pk=campaign_id)
        try:
            days = int(request.query_params.get("days", 7))
        except (TypeError, ValueError):
            return Response({"detail": "days must be an integer from 1 to 90"}, status=400)
        if not 1 <= days <= 90:
            return Response({"detail": "days must be between 1 and 90"}, status=400)
        return Response(ReportingService.get_campaign_report(campaign.pk, days))


class AlertListView(APIView):
    def get(self, request):
        alerts = Alert.objects.select_related("campaign").all()
        campaign_id = request.query_params.get("campaign_id")
        if campaign_id:
            alerts = alerts.filter(campaign_id=campaign_id)
        acknowledged = request.query_params.get("acknowledged")
        if acknowledged in ("true", "false"):
            alerts = alerts.filter(acknowledged=(acknowledged == "true"))
        return Response(AlertSerializer(alerts[:100], many=True).data)


class AlertAcknowledgeView(APIView):
    def post(self, request, alert_id):
        alert = get_object_or_404(Alert, pk=alert_id)
        if not alert.acknowledged:
            alert.acknowledged = True
            alert.save(update_fields=["acknowledged"])
        return Response(AlertSerializer(alert).data, status=status.HTTP_200_OK)
