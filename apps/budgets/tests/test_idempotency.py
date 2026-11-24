from decimal import Decimal

from django.test import TestCase

from apps.budgets.models import BudgetAdjustment
from apps.budgets.services import BudgetService
from apps.campaigns.models import Campaign


class BudgetIdempotencyTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="Idempotent budget",
            daily_budget=Decimal("1000.0000"),
            total_budget=Decimal("10000.0000"),
        )

    def test_same_key_returns_existing_adjustment_and_applies_once(self):
        args = dict(
            campaign_id=self.campaign.pk,
            new_budget=Decimal("750.0000"),
            trigger_type="MANUAL",
            reason="manual adjustment",
            idempotency_key="same-request-key",
        )
        first = BudgetService.adjust_budget(**args)
        second = BudgetService.adjust_budget(**args)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BudgetAdjustment.objects.count(), 1)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.daily_budget, Decimal("750.0000"))
        self.assertEqual(self.campaign.version, 2)
