from decimal import Decimal
from statistics import quantiles
from time import perf_counter

from django.test import TestCase

from apps.analytics.services import ReportingService
from apps.campaigns.models import Campaign


class ReportingLatencyTests(TestCase):
    def test_warm_report_cache_p95_is_below_200ms(self):
        campaign = Campaign.objects.create(
            name="Latency campaign",
            daily_budget=Decimal("100.0000"),
            total_budget=Decimal("1000.0000"),
        )
        # Avoid cache state from a prior test run.
        campaign_id = campaign.pk
        from django.core.cache import cache

        cache.delete(f"report:v1:{campaign_id}:7")
        ReportingService.get_campaign_report(campaign_id, 7)
        durations = []
        for _ in range(30):
            started = perf_counter()
            result = ReportingService.get_campaign_report(campaign_id, 7)
            durations.append((perf_counter() - started) * 1000)
            self.assertEqual(result["campaign_id"], str(campaign_id))
        p95 = quantiles(durations, n=20)[18]
        print(f"Warm reporting cache p95: {p95:.2f} ms")
        self.assertLess(p95, 200)
