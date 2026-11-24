from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from apps.analytics.models import AdEvent, Alert
from apps.analytics.services import refresh_performance_snapshots
from apps.campaigns.models import Campaign, Creative
from workers.tasks.analytics import detect_anomalies


class AnomalyTaskTests(TransactionTestCase):
    reset_sequences = True

    def tearDown(self):
        AdEvent.objects.filter(campaign_id=self.campaign.pk).delete()

    def test_detection_deduplicates_alerts_and_queues_race_safe_adjustments(self):
        self.campaign = Campaign.objects.create(
            name="Anomaly campaign",
            daily_budget=Decimal("150.0000"),
            total_budget=Decimal("1000.0000"),
        )
        creative = Creative.objects.create(
            campaign=self.campaign,
            name="Anomaly creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/anomaly.jpg",
        )
        today = date.today()
        for offset in range(1, 8):
            event_date = today - timedelta(days=offset)
            AdEvent.objects.create(
                campaign=self.campaign, creative=creative, platform="META", event_type="CONVERSION",
                spend=Decimal("100.0000"), revenue=Decimal("500.0000"),
                event_time=timezone.now().replace(year=event_date.year, month=event_date.month, day=event_date.day),
            )
        AdEvent.objects.create(
            campaign=self.campaign, creative=creative, platform="META", event_type="CONVERSION",
            spend=Decimal("200.0000"), revenue=Decimal("200.0000"), event_time=timezone.now(),
        )
        refresh_performance_snapshots()

        with patch("workers.tasks.analytics.trigger_budget_reduction.delay") as adjust:
            detect_anomalies.run()
            detect_anomalies.run()

        self.assertEqual(Alert.objects.filter(campaign=self.campaign).count(), 3)
        self.assertEqual(Alert.objects.filter(campaign=self.campaign, alert_type=Alert.AlertType.BUDGET_EXHAUSTED).count(), 1)
        self.assertEqual(adjust.call_count, 2)
