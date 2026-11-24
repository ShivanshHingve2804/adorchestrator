from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.campaigns.models import Campaign

from .models import BudgetAdjustment
from .serializers import AdjustBudgetRequestSerializer, BudgetAdjustmentSerializer
from .services import BudgetService, ConflictError


class AdjustBudgetView(APIView):
    def post(self, request, campaign_id):
        campaign = get_object_or_404(Campaign, pk=campaign_id)
        request_serializer = AdjustBudgetRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        values = request_serializer.validated_data
        try:
            adjustment = BudgetService.adjust_budget(
                campaign_id=campaign.pk,
                new_budget=values["new_budget"],
                trigger_type=values["trigger_type"],
                reason=values["reason"],
                idempotency_key=values.get("idempotency_key"),
            )
        except ConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(BudgetAdjustmentSerializer(adjustment).data, status=status.HTTP_200_OK)


class BudgetHistoryView(APIView):
    def get(self, request, campaign_id):
        campaign = get_object_or_404(Campaign, pk=campaign_id)
        adjustments = BudgetAdjustment.objects.filter(campaign=campaign).order_by("-created_at")
        return Response(BudgetAdjustmentSerializer(adjustments, many=True).data)
