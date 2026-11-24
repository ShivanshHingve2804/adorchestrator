from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.campaigns.models import Creative
from workers.tasks.creative_ai import analyze_creative

from .models import CreativeFeature, WeeklySummary
from .serializers import CreativeFeatureSerializer, WeeklySummarySerializer


class CreativeFeatureListView(APIView):
    def get(self, request, creative_id):
        creative = get_object_or_404(Creative, pk=creative_id)
        features = CreativeFeature.objects.filter(creative=creative)
        return Response(CreativeFeatureSerializer(features, many=True).data)


class AnalyzeCreativeView(APIView):
    def post(self, request, creative_id):
        creative = get_object_or_404(Creative, pk=creative_id)
        task = analyze_creative.delay(str(creative.pk))
        return Response(
            {"creative_id": str(creative.pk), "task_id": task.id, "status": "QUEUED"},
            status=status.HTTP_202_ACCEPTED,
        )


class LatestWeeklySummaryView(APIView):
    def get(self, request):
        summary = WeeklySummary.objects.first()
        if summary is None:
            return Response({"detail": "No weekly summary has been generated."}, status=404)
        return Response(WeeklySummarySerializer(summary).data)
