from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from .models import Campaign, Creative, PlatformDeployment
from .serializers import (
    BulkLaunchSerializer,
    CampaignSerializer,
    CreativeSerializer,
    PlatformDeploymentSerializer,
)


TASK_QUEUE = "ad-orchestrator-queue"


async def _start_temporal_workflow(workflow_input, workflow_id):
    from workflows.bulk_launch_workflow import BulkCampaignLaunchWorkflow

    client = await Client.connect(settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE)
    try:
        handle = await client.start_workflow(
            BulkCampaignLaunchWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(workflow_id)
    return handle.id


def start_bulk_launch_workflow(workflow_input, workflow_id):
    return async_to_sync(_start_temporal_workflow)(workflow_input, workflow_id)


async def _get_temporal_workflow_status(workflow_id):
    client = await Client.connect(settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE)
    handle = client.get_workflow_handle(workflow_id)
    description = await handle.describe()
    return description.status.name


def get_temporal_workflow_status(workflow_id):
    return async_to_sync(_get_temporal_workflow_status)(workflow_id)


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    @staticmethod
    def _prepare_bulk_deployments(pk, platforms, idempotency_key):
        key_prefix = f"{idempotency_key}:"
        with transaction.atomic():
            campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=pk)
            existing = list(
                PlatformDeployment.objects.filter(campaign=campaign).filter(
                    Q(idempotency_key=idempotency_key) | Q(idempotency_key__startswith=key_prefix)
                )
            )
            if existing:
                if any(row.idempotency_key == idempotency_key for row in existing):
                    return campaign, existing, platforms, [], None, True
                workflow_ids = {row.temporal_workflow_id for row in existing if row.temporal_workflow_id}
                if len(workflow_ids) == 1 and all(row.temporal_workflow_id for row in existing):
                    return campaign, existing, platforms, [], workflow_ids.pop(), True
                deployments = existing
                platforms = list(dict.fromkeys(row.platform for row in deployments))
                creatives = list(dict.fromkeys(str(row.creative_id) for row in deployments))
            else:
                creatives = list(campaign.creatives.values_list("id", flat=True))
                if not creatives:
                    return campaign, [], platforms, [], None, False
                deployments = [
                    PlatformDeployment.objects.get_or_create(
                        idempotency_key=f"{key_prefix}{platform}:{creative_id}",
                        defaults={
                            "campaign": campaign,
                            "creative_id": creative_id,
                            "platform": platform,
                            "status": PlatformDeployment.Status.PENDING,
                        },
                    )[0]
                    for platform in platforms
                    for creative_id in creatives
                ]

            if all(row.idempotency_key == idempotency_key for row in deployments):
                return campaign, deployments, platforms, creatives, None, True

            if campaign.status not in (Campaign.Status.ACTIVE, Campaign.Status.COMPLETED):
                campaign.status = Campaign.Status.LAUNCHING
                campaign.save(update_fields=["status", "updated_at"])

            return campaign, deployments, platforms, creatives, None, False

    @action(detail=True, methods=["post"], url_path="bulk_launch")
    def bulk_launch(self, request, pk=None):
        input_serializer = BulkLaunchSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        platforms = input_serializer.validated_data["platforms"]
        idempotency_key = input_serializer.validated_data["idempotency_key"]

        campaign, deployments, platforms, creatives, existing_wf_id, already_handled = (
            self._prepare_bulk_deployments(pk, platforms, idempotency_key)
        )
        if already_handled:
            payload = {
                "campaign_id": str(campaign.pk),
                "deployments": PlatformDeploymentSerializer(deployments, many=True).data,
            }
            if existing_wf_id:
                payload["workflow_id"] = existing_wf_id
            return Response(payload, status=status.HTTP_202_ACCEPTED)
        if not deployments:
            return Response(
                {"detail": "Add at least one creative before launching this campaign."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from workflows.bulk_launch_workflow import BulkLaunchInput

        campaign_id_str = str(campaign.pk)
        workflow_id = f"bulk-launch-{campaign_id_str}-{idempotency_key}"
        workflow_input = BulkLaunchInput(
            campaign_id=campaign_id_str,
            creative_ids=[str(creative_id) for creative_id in creatives],
            platforms=platforms,
            idempotency_key=idempotency_key,
            daily_budget=float(campaign.daily_budget),
        )
        try:
            workflow_id = start_bulk_launch_workflow(workflow_input, workflow_id)
        except Exception as exc:
            with transaction.atomic():
                locked_campaign = Campaign.objects.select_for_update().get(pk=campaign_id_str)
                locked_deployments = list(
                    PlatformDeployment.objects.filter(pk__in=[row.pk for row in deployments]).select_for_update()
                )
                if all(row.temporal_workflow_id for row in locked_deployments):
                    return Response(
                        {
                            "campaign_id": campaign_id_str,
                            "workflow_id": locked_deployments[0].temporal_workflow_id,
                            "deployments": PlatformDeploymentSerializer(locked_deployments, many=True).data,
                        },
                        status=status.HTTP_202_ACCEPTED,
                    )
                if locked_campaign.status == Campaign.Status.LAUNCHING:
                    locked_campaign.status = Campaign.Status.FAILED
                    locked_campaign.save(update_fields=["status", "updated_at"])
                PlatformDeployment.objects.filter(
                    pk__in=[row.pk for row in locked_deployments],
                    status=PlatformDeployment.Status.PENDING,
                ).update(
                    status=PlatformDeployment.Status.FAILED,
                    last_error=f"Could not start Temporal workflow: {exc}"[:4000],
                )
            from apps.analytics.services import record_launch_failure

            for row in deployments:
                record_launch_failure(campaign_id_str, row.idempotency_key, f"Could not start Temporal workflow: {exc}")
            return Response(
                {"detail": "Temporal workflow could not be started."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        PlatformDeployment.objects.filter(
            pk__in=[row.pk for row in deployments],
            temporal_workflow_id__isnull=True,
        ).update(temporal_workflow_id=workflow_id)
        for deployment in deployments:
            if not deployment.temporal_workflow_id:
                deployment.temporal_workflow_id = workflow_id

        return Response(
            {
                "campaign_id": campaign_id_str,
                "workflow_id": workflow_id,
                "deployments": PlatformDeploymentSerializer(deployments, many=True).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="launch-status")
    def launch_status(self, request, pk=None):
        campaign = self.get_object()
        deployments = list(campaign.deployments.all())
        workflow_ids = {row.temporal_workflow_id for row in deployments if row.temporal_workflow_id}
        workflow_status = None
        if len(workflow_ids) == 1:
            try:
                workflow_status = get_temporal_workflow_status(next(iter(workflow_ids)))
            except Exception:
                workflow_status = None
        return Response(
            {
                "campaign_id": str(campaign.pk),
                "campaign_status": campaign.status,
                "workflow_status": workflow_status,
                "deployments": PlatformDeploymentSerializer(deployments, many=True).data,
            }
        )
class CreativeViewSet(viewsets.ModelViewSet):
    serializer_class = CreativeSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Creative.objects.filter(campaign_id=self.kwargs["campaign_pk"]).select_related("campaign")

    def perform_create(self, serializer):
        campaign = get_object_or_404(Campaign, pk=self.kwargs["campaign_pk"])
        serializer.save(campaign=campaign)
