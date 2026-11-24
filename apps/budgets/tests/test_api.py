from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.budgets.models import BudgetAdjustment
from apps.budgets.services import ConflictError
from apps.campaigns.models import Campaign


class BudgetAdjustmentAPITests(APITestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="API budget",
            daily_budget=Decimal("1000.0000"),
            total_budget=Decimal("10000.0000"),
        )
        self.adjust_url = f"/api/budgets/campaigns/{self.campaign.pk}/adjust-budget/"
        self.history_url = f"/api/budgets/campaigns/{self.campaign.pk}/budget-history/"

    def test_post_adjust_budget_returns_adjustment(self):
        response = self.client.post(
            self.adjust_url,
            {"new_budget": "800.0000", "trigger_type": "MANUAL", "reason": "test", "idempotency_key": "api-1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["old_budget"], "1000.0000")
        self.assertEqual(response.data["new_budget"], "800.0000")
        self.assertEqual(BudgetAdjustment.objects.count(), 1)

    @patch("apps.budgets.views.BudgetService.adjust_budget", side_effect=ConflictError("lock busy"))
    def test_post_adjust_budget_returns_conflict(self, adjust_budget):
        response = self.client.post(
            self.adjust_url,
            {"new_budget": "800.0000", "trigger_type": "MANUAL", "reason": "test"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["detail"], "lock busy")

    def test_get_budget_history_returns_campaign_adjustments(self):
        self.client.post(
            self.adjust_url,
            {"new_budget": "800.0000", "trigger_type": "MANUAL", "reason": "test"},
            format="json",
        )
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["new_budget"], "800.0000")
