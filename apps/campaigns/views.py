from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campaign, Creative, PlatformDeployment
from .serializers import (
    BulkLaunchSerializer,
    CampaignSerializer,
    CreativeSerializer,
    PlatformDeploymentSerializer,
)


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    @action(detail=True, methods=["post"], url_path="bulk_launch")
    def bulk_launch(self, request, pk=None):
        campaign = self.get_object()
        input_serializer = BulkLaunchSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        platforms = input_serializer.validated_data["platforms"]
        idempotency_key = input_serializer.validated_data["idempotency_key"]
        key_prefix = f"{idempotency_key}:"

        existing = PlatformDeployment.objects.filter(campaign=campaign).filter(
            Q(idempotency_key=idempotency_key) | Q(idempotency_key__startswith=key_prefix)
        )
        if existing.exists():
            return Response(
                {
                    "campaign_id": str(campaign.pk),
                    "deployments": PlatformDeploymentSerializer(existing, many=True).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        creatives = list(campaign.creatives.all())
        if not creatives:
            return Response(
                {"detail": "Add at least one creative before launching this campaign."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            deployments = []
            for platform in platforms:
                for creative in creatives:
                    deployment_key = f"{key_prefix}{platform}:{creative.pk}"
                    deployment, _ = PlatformDeployment.objects.get_or_create(
                        idempotency_key=deployment_key,
                        defaults={
                            "campaign": campaign,
                            "creative": creative,
                            "platform": platform,
                            "status": PlatformDeployment.Status.PENDING,
                        },
                    )
                    deployments.append(deployment)

        return Response(
            {
                "campaign_id": str(campaign.pk),
                "deployments": PlatformDeploymentSerializer(deployments, many=True).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CreativeViewSet(viewsets.ModelViewSet):
    serializer_class = CreativeSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Creative.objects.filter(campaign_id=self.kwargs["campaign_pk"]).select_related("campaign")

    def perform_create(self, serializer):
        campaign = get_object_or_404(Campaign, pk=self.kwargs["campaign_pk"])
        serializer.save(campaign=campaign)
