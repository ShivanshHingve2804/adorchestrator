from decimal import Decimal

from django.test import TransactionTestCase

from apps.budgets.models import BudgetAdjustment
from apps.campaigns.models import Campaign

from .helpers import concurrent_adjustments


class BudgetRaceConditionTests(TransactionTestCase):
    reset_sequences = True

    def test_auto_and_manual_adjusters_race_ten_times(self):
        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                campaign = Campaign.objects.create(
                    name=f"Race campaign {attempt}",
                    daily_budget=Decimal("1000.0000"),
                    total_budget=Decimal("10000.0000"),
                )
                results = concurrent_adjustments(
                    campaign.pk,
                    [
                        (Decimal("700.0000"), "AUTO_CPA_SPIKE", f"auto-{attempt}"),
                        (Decimal("1200.0000"), "MANUAL", f"manual-{attempt}"),
                    ],
                )
                self.assertEqual(sum(result[0] == "success" for result in results), 1)
                self.assertEqual(sum(result[0] == "conflict" for result in results), 1)
                campaign.refresh_from_db()
                self.assertIn(campaign.daily_budget, (Decimal("700.0000"), Decimal("1200.0000")))
                self.assertEqual(BudgetAdjustment.objects.filter(campaign=campaign).count(), 1)
                adjustment = BudgetAdjustment.objects.get(campaign=campaign)
                self.assertEqual(adjustment.original_budget, Decimal("1000.0000"))
                self.assertEqual(adjustment.new_budget, campaign.daily_budget)
