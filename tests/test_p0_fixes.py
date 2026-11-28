from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import httpx
import redis
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from apps.analytics.models import AdEvent, Alert
from apps.analytics.services import ReportingService, refresh_performance_snapshots
from apps.budgets.models import BudgetAdjustment
from apps.budgets.services import (
    BudgetService,
    BudgetValidationError,
    ConflictError,
    LockUnavailableError,
)
from apps.campaigns.models import Campaign, Creative, PlatformDeployment
from workers.tasks.analytics import (
    _ensure_daily_partition,
    detect_anomalies,
    trigger_budget_reduction,
)
from workflows.activities.common import _delete_platform_campaign, _post_platform
from workflows.activities.rollback_campaign import rollback_campaign
from workflows.bulk_launch_workflow import BulkCampaignLaunchWorkflow
from workflows.tests.helpers import TASK_QUEUE, make_activities, sample_input


class BudgetServiceP0Tests(APITestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="P0 budget campaign",
            daily_budget=Decimal("500.0000"),
            total_budget=Decimal("1000.0000"),
        )
        self.adjust_url = f"/api/budgets/campaigns/{self.campaign.pk}/adjust-budget/"

    @patch.object(BudgetService, "_redis_client")
    def test_redis_outage_maps_to_lock_unavailable_503(self, mock_redis_factory):
        mock_redis_factory.return_value.set.side_effect = redis.ConnectionError("redis down")

        with self.assertRaises(LockUnavailableError):
            BudgetService.adjust_budget(
                campaign_id=self.campaign.pk,
                new_budget=Decimal("400.0000"),
                trigger_type="MANUAL",
                reason="redis outage check",
            )

        response = self.client.post(
            self.adjust_url,
            {"new_budget": "400.0000", "trigger_type": "MANUAL", "reason": "redis outage check"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_new_budget_above_total_budget_returns_400(self):
        with self.assertRaises(BudgetValidationError):
            BudgetService.adjust_budget(
                campaign_id=self.campaign.pk,
                new_budget=Decimal("1500.0000"),
                trigger_type="MANUAL",
                reason="exceeds total",
            )

        response = self.client.post(
            self.adjust_url,
            {"new_budget": "1500.0000", "trigger_type": "MANUAL", "reason": "exceeds total"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_idempotency_key_payload_mismatch_returns_409(self):
        first = self.client.post(
            self.adjust_url,
            {
                "new_budget": "400.0000",
                "trigger_type": "MANUAL",
                "reason": "initial",
                "idempotency_key": "budget-idem-p0",
            },
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        mismatch = self.client.post(
            self.adjust_url,
            {
                "new_budget": "300.0000",
                "trigger_type": "MANUAL",
                "reason": "different amount",
                "idempotency_key": "budget-idem-p0",
            },
            format="json",
        )
        self.assertEqual(mismatch.status_code, status.HTTP_409_CONFLICT)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.daily_budget, Decimal("400.0000"))

    def test_scale_budget_reads_latest_budget_inside_lock(self):
        BudgetService.adjust_budget(
            campaign_id=self.campaign.pk,
            new_budget=Decimal("800.0000"),
            trigger_type="MANUAL",
            reason="manual bump before auto cut",
        )
        trigger_budget_reduction.run(str(self.campaign.pk), "0.50", "2026-11-26", "CPA_SPIKE")
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.daily_budget, Decimal("400.0000"))
        self.assertEqual(BudgetAdjustment.objects.filter(campaign=self.campaign).count(), 2)


class BulkLaunchConcurrencyP0Tests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_bulk_launch_same_key_starts_workflow_once(self):
        campaign = Campaign.objects.create(
            name="Concurrent launch",
            daily_budget=Decimal("200.0000"),
            total_budget=Decimal("2000.0000"),
        )
        Creative.objects.create(
            campaign=campaign,
            name="Launch creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/launch.jpg",
        )
        barrier = Barrier(2)
        payload = {"platforms": ["META", "GOOGLE"], "idempotency_key": "concurrent-launch-1"}

        def invoke_launch():
            try:
                client = APIClient()
                barrier.wait(timeout=10)
                return client.post(f"/api/campaigns/{campaign.pk}/bulk_launch/", payload, format="json")
            finally:
                connections.close_all()

        with patch("apps.campaigns.views.start_bulk_launch_workflow", return_value="wf-concurrent-1"):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: invoke_launch(), range(2)))

        self.assertTrue(all(resp.status_code == 202 for resp in responses))
        self.assertEqual(PlatformDeployment.objects.filter(campaign=campaign).count(), 2)
        self.assertEqual(
            {d.temporal_workflow_id for d in PlatformDeployment.objects.filter(campaign=campaign)},
            {"wf-concurrent-1"},
        )

    def test_bulk_launch_does_not_reset_active_campaign_on_replay(self):
        campaign = Campaign.objects.create(
            name="Active campaign replay",
            status=Campaign.Status.ACTIVE,
            daily_budget=Decimal("200.0000"),
            total_budget=Decimal("2000.0000"),
        )
        creative = Creative.objects.create(
            campaign=campaign,
            name="Active creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/active.jpg",
        )
        PlatformDeployment.objects.create(
            campaign=campaign,
            creative=creative,
            platform=PlatformDeployment.Platform.META,
            status=PlatformDeployment.Status.ACTIVE,
            idempotency_key="active-key:META:" + str(creative.pk),
            temporal_workflow_id=None,
        )

        client = APIClient()
        with patch("apps.campaigns.views.start_bulk_launch_workflow", return_value="wf-active-replay"):
            response = client.post(
                f"/api/campaigns/{campaign.pk}/bulk_launch/",
                {"platforms": ["META"], "idempotency_key": "active-key"},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.ACTIVE)


class TemporalSagaP0Tests(IsolatedAsyncioTestCase):
    async def test_compensation_failure_raises_non_retryable_application_error(self):
        statuses = {}
        base_activities = [
            fn for fn in make_activities(statuses, fail_create_for="TIKTOK") if fn.__name__ != "rollback_campaign"
        ]

        @activity.defn(name="rollback_campaign")
        async def failing_rollback(deployment_key, platform, platform_campaign_id):
            raise ApplicationError("rollback hard failure", type="RollbackError", non_retryable=True)

        activities = [*base_activities, failing_rollback]
        environment = await WorkflowEnvironment.start_time_skipping()
        async with environment:
            async with Worker(
                environment.client,
                task_queue=TASK_QUEUE,
                workflows=[BulkCampaignLaunchWorkflow],
                activities=activities,
            ):
                handle = await environment.client.start_workflow(
                    BulkCampaignLaunchWorkflow.run,
                    sample_input(["META", "TIKTOK"]),
                    id="test-saga-comp-fail",
                    task_queue=TASK_QUEUE,
                )
                with self.assertRaises(WorkflowFailureError) as raised:
                    await handle.result()
                self.assertIsInstance(raised.exception.cause, ApplicationError)
                self.assertEqual(raised.exception.cause.type, "SagaCompensationError")
                self.assertTrue(raised.exception.cause.non_retryable)
        self.assertEqual(statuses["campaign:campaign-1"], "FAILED")

    async def test_delete_platform_campaign_treats_404_as_idempotent(self):
        mock_response = MagicMock(status_code=404)
        mock_client = AsyncMock()
        mock_client.delete.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _delete_platform_campaign("META", "meta_camp_123")
        self.assertTrue(result["already_deleted"])

    async def test_post_platform_treats_408_as_retryable(self):
        request = httpx.Request("POST", "http://mock-platforms:8090/meta/upload-media")
        response = httpx.Response(408, request=request, text="Request Timeout")
        mock_client = AsyncMock()
        mock_client.post.return_value = response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            with self.assertRaises(RuntimeError):
                await _post_platform("META", "upload-media", {"creative_id": "1", "media_url": "https://x"})

    async def test_rollback_preserves_last_error(self):
        with (
            patch("workflows.activities.rollback_campaign._delete_platform_campaign", new_callable=AsyncMock) as delete_fn,
            patch("workflows.activities.rollback_campaign._update_deployment", new_callable=AsyncMock) as update_fn,
        ):
            delete_fn.return_value = {"rolled_back": True}
            await rollback_campaign("dep-key", "META", "meta_123")
        update_fn.assert_awaited_once_with("dep-key", status="ROLLED_BACK")


class AnalyticsP0Tests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="Analytics P0",
            daily_budget=Decimal("500.0000"),
            total_budget=Decimal("5000.0000"),
        )
        self.creative = Creative.objects.create(
            campaign=self.campaign,
            name="Analytics P0 creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/p0.jpg",
        )

    def tearDown(self):
        AdEvent.objects.filter(campaign_id=self.campaign.pk).delete()

    def test_partition_creation_migrates_rows_from_default_partition(self):
        target_day = timezone.now().date() + timedelta(days=60)
        suffix = target_day.strftime("%Y%m%d")
        part_name = f"analytics_ad_event_{suffix}"
        event_id = uuid.uuid4()
        event_ts = datetime.combine(target_day, timezone.now().time(), tzinfo=timezone.now().tzinfo)

        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{part_name}"')
        AdEvent.objects.create(
            id=event_id,
            campaign=self.campaign,
            creative=self.creative,
            platform="META",
            event_type="IMPRESSION",
            event_time=event_ts,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM analytics_ad_event_default WHERE id = %s", [str(event_id)])
            self.assertEqual(cursor.fetchone()[0], 1)

            _ensure_daily_partition(cursor, target_day)

            cursor.execute("SELECT COUNT(*) FROM analytics_ad_event_default WHERE id = %s", [str(event_id)])
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute(f'SELECT COUNT(*) FROM "{part_name}" WHERE id = %s', [str(event_id)])
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute(f'DROP TABLE IF EXISTS "{part_name}"')

    def test_detect_anomalies_uses_weighted_seven_day_baseline(self):
        today = timezone.now().date()
        base_now = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        for offset in range(1, 7):
            day = today - timedelta(days=offset)
            AdEvent.objects.create(
                campaign=self.campaign, creative=self.creative, platform="META", event_type="CONVERSION",
                spend=Decimal("1.0000"), revenue=Decimal("5.0000"),
                event_time=base_now.replace(year=day.year, month=day.month, day=day.day),
            )
        heavy_day = today - timedelta(days=7)
        for _ in range(10):
            AdEvent.objects.create(
                campaign=self.campaign, creative=self.creative, platform="META", event_type="CONVERSION",
                spend=Decimal("100.0000"), revenue=Decimal("500.0000"),
                event_time=base_now.replace(year=heavy_day.year, month=heavy_day.month, day=heavy_day.day),
            )
        # Weighted avg_cpa = 1006 / 16 = 62.875; unweighted mean was (6*1 + 100)/7 = 15.14.
        # Today CPA = 80.00: <= 62.875 * 1.5 (94.31), so no CPA_SPIKE alert should fire.
        AdEvent.objects.create(
            campaign=self.campaign, creative=self.creative, platform="META", event_type="CONVERSION",
            spend=Decimal("80.0000"), revenue=Decimal("400.0000"), event_time=base_now,
        )
        refresh_performance_snapshots()

        with patch("workers.tasks.analytics.trigger_budget_reduction.delay") as adjust:
            detect_anomalies.run()

        self.assertEqual(Alert.objects.filter(campaign=self.campaign, alert_type=Alert.AlertType.CPA_SPIKE).count(), 0)
        adjust.assert_not_called()

    def test_refresh_performance_snapshots_invalidates_report_cache(self):
        first = ReportingService.get_campaign_report(self.campaign.pk, days=7)
        self.assertEqual(first["data"], [])

        AdEvent.objects.create(
            campaign=self.campaign, creative=self.creative, platform="META",
            event_type="IMPRESSION", event_time=timezone.now() - timedelta(minutes=1),
        )
        refresh_performance_snapshots()

        second = ReportingService.get_campaign_report(self.campaign.pk, days=7)
        self.assertEqual(len(second["data"]), 1)
        self.assertEqual(second["data"][0]["impressions"], 1)


class P0ErrorTypeUnitTests(TestCase):
    def test_conflict_and_lock_unavailable_are_distinct(self):
        self.assertFalse(issubclass(LockUnavailableError, ConflictError))
        self.assertFalse(issubclass(BudgetValidationError, ConflictError))


class BudgetAdjustmentModelTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="Model fixes campaign",
            daily_budget=Decimal("600.0000"),
            total_budget=Decimal("3000.0000"),
        )

    def test_save_auto_computes_deltas_on_create_with_round_half_up(self):
        adjustment = BudgetAdjustment.objects.create(
            campaign=self.campaign,
            concurrency_token=uuid.uuid4(),
            source="SOURCE_SPEND_HOUSE_CORR_ACCOUNTS",
            adjustment_type="TYPE_ABSOLUTE",
            new_budget=Decimal("400.0000"),
            original_budget=Decimal("600.0000"),
            campaign_idempotency_key="camp-model-1",
            status=BudgetAdjustment.Status.EXECUTED,
        )
        self.assertEqual(adjustment.budget_change, Decimal("-200.0000"))
        self.assertEqual(adjustment.percent_delta, Decimal("-33.3333"))

    def test_roll_back_supports_executed_and_to_dict_serializes_strings(self):
        adjustment = BudgetAdjustment.objects.create(
            campaign=self.campaign,
            concurrency_token=uuid.uuid4(),
            source="SOURCE_SPEND_HOUSE_CORR_ACCOUNTS",
            adjustment_type="TYPE_ABSOLUTE",
            new_budget=Decimal("450.0000"),
            original_budget=Decimal("600.0000"),
            campaign_idempotency_key="camp-model-2",
            status=BudgetAdjustment.Status.EXECUTED,
        )
        adjustment.roll_back("reverting executed adjustment")
        adjustment.refresh_from_db()

        self.assertEqual(adjustment.status, BudgetAdjustment.Status.ROLLED_BACK)
        self.assertEqual(len(adjustment.audit_log), 1)
        self.assertEqual(adjustment.audit_log[0]["action"], "ROLLBACK")
        self.assertTrue(adjustment.audit_log[0]["timestamp"])

        payload = adjustment.to_dict()
        self.assertEqual(payload["new_budget"], "450.0000")
        self.assertEqual(payload["original_budget"], "600.0000")
        self.assertEqual(payload["budget_change"], "-150.0000")
        self.assertEqual(payload["percent_delta"], "-25.0000")
