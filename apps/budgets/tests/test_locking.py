from decimal import Decimal

from django.test import TransactionTestCase

from apps.budgets.models import BudgetAdjustment
from apps.campaigns.models import Campaign

from .helpers import concurrent_adjustments


class BudgetLockingTests(TransactionTestCase):
    reset_sequences = True

    def test_twenty_concurrent_adjustments_have_one_winner(self):
        campaign = Campaign.objects.create(
            name="Concurrent budget",
            daily_budget=Decimal("1000.0000"),
            total_budget=Decimal("10000.0000"),
        )
        requests = [(Decimal(500 + i * 25), "MANUAL", f"thread-{i}") for i in range(20)]

        results = concurrent_adjustments(campaign.pk, requests)
        successes = [item for item in results if item[0] == "success"]
        conflicts = [item for item in results if item[0] == "conflict"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 19)
        campaign.refresh_from_db()
        self.assertEqual(campaign.daily_budget, Decimal(successes[0][1]).quantize(Decimal("0.0001")))
        self.assertEqual(BudgetAdjustment.objects.filter(campaign=campaign).count(), 1)
        print(f"20-thread budget lock: {len(successes)} succeeded, {len(conflicts)} conflicted; final={campaign.daily_budget}")
