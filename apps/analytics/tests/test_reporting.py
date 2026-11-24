from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import AdEvent, Alert, PerformanceSnapshot
from apps.analytics.services import refresh_performance_snapshots
from apps.campaigns.models import Campaign, Creative


class AnalyticsReportingTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="Analytics campaign",
            daily_budget=Decimal("100.0000"),
            total_budget=Decimal("1000.0000"),
        )
        self.creative = Creative.objects.create(
            campaign=self.campaign,
            name="Analytics creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/analytics.jpg",
        )
        self.client = APIClient()

    def tearDown(self):
        AdEvent.objects.filter(campaign_id=self.campaign.pk).delete()

    def test_event_partitions_and_reporting_materialization(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT relkind FROM pg_class WHERE oid = 'analytics_ad_event'::regclass")
            self.assertEqual(cursor.fetchone()[0], "p")
        event_time = timezone.now() - timedelta(minutes=1)
        AdEvent.objects.create(
            campaign=self.campaign, creative=self.creative, platform="META",
            event_type="IMPRESSION", event_time=event_time,
        )
        AdEvent.objects.create(
            campaign=self.campaign, creative=self.creative, platform="META",
            event_type="CONVERSION", spend=Decimal("25.0000"), revenue=Decimal("100.0000"),
            event_time=event_time,
        )

        refresh_performance_snapshots()
        response = self.client.get(f"/api/analytics/campaigns/{self.campaign.pk}/report/?days=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"][0]["impressions"], 1)
        self.assertEqual(response.data["data"][0]["conversions"], 1)
        self.assertEqual(response.data["data"][0]["roas"], 4.0)
        self.assertEqual(PerformanceSnapshot.objects.filter(campaign=self.campaign).count(), 1)

    def test_report_rejects_days_outside_supported_range(self):
        response = self.client.get(f"/api/analytics/campaigns/{self.campaign.pk}/report/?days=120")
        self.assertEqual(response.status_code, 400)

    def test_alerts_can_be_listed_and_acknowledged(self):
        alert = Alert.objects.create(
            campaign=self.campaign,
            alert_type=Alert.AlertType.CPA_SPIKE,
            severity=Alert.Severity.WARNING,
            message="CPA is above baseline",
            dedupe_key=f"test-alert:{self.campaign.pk}",
        )
        listed = self.client.get("/api/analytics/alerts/", {"campaign_id": str(self.campaign.pk)})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        response = self.client.post(f"/api/analytics/alerts/{alert.pk}/acknowledge/")
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertTrue(alert.acknowledged)
