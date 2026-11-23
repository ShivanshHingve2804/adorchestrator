from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.core.exceptions import ValidationError

from apps.campaigns.models import Campaign, Creative, PlatformDeployment


class CampaignModelTests(TestCase):
    def make_campaign(self, **overrides):
        values = {
            "name": "Spring launch",
            "status": Campaign.Status.DRAFT,
            "daily_budget": Decimal("125.5000"),
            "total_budget": Decimal("2500.0000"),
            "spent": Decimal("10.2500"),
            "currency": "USD",
            "idempotency_key": "campaign-create-1",
            "targeting": {"country": "US"},
            "version": 3,
        }
        values.update(overrides)
        return Campaign.objects.create(**values)

    def test_campaign_creation_with_all_fields(self):
        campaign = self.make_campaign()

        self.assertIsNotNone(campaign.pk)
        self.assertEqual(campaign.name, "Spring launch")
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertEqual(campaign.daily_budget, Decimal("125.5000"))
        self.assertEqual(campaign.total_budget, Decimal("2500.0000"))
        self.assertEqual(campaign.spent, Decimal("10.2500"))
        self.assertEqual(campaign.currency, "USD")
        self.assertEqual(campaign.idempotency_key, "campaign-create-1")
        self.assertEqual(campaign.targeting, {"country": "US"})
        self.assertEqual(campaign.version, 3)
        self.assertIsNotNone(campaign.created_at)
        self.assertIsNotNone(campaign.updated_at)

    def test_status_choices_are_enforced(self):
        campaign = Campaign(
            name="Invalid status",
            status="UNKNOWN",
            daily_budget=Decimal("1.0000"),
            total_budget=Decimal("1.0000"),
        )
        with self.assertRaises(ValidationError):
            campaign.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_campaign(name="Invalid status", status="UNKNOWN", idempotency_key="invalid-status")

    def test_idempotency_key_is_unique(self):
        self.make_campaign()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_campaign(name="Duplicate key")

    def test_creative_foreign_key_relationship(self):
        campaign = self.make_campaign()
        creative = Creative.objects.create(
            campaign=campaign,
            name="Product image",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/product.jpg",
        )

        self.assertEqual(creative.campaign, campaign)
        self.assertEqual(campaign.creatives.get(), creative)
        self.assertEqual(creative.status, Creative.Status.PENDING)

    def test_platform_deployment_creation(self):
        campaign = self.make_campaign()
        creative = Creative.objects.create(
            campaign=campaign,
            name="Video ad",
            media_type=Creative.MediaType.VIDEO,
            media_url="https://cdn.example.test/ad.mp4",
        )
        deployment = PlatformDeployment.objects.create(
            campaign=campaign,
            creative=creative,
            platform=PlatformDeployment.Platform.META,
            idempotency_key="launch-1:META:creative-1",
        )

        self.assertEqual(deployment.status, PlatformDeployment.Status.PENDING)
        self.assertEqual(deployment.retry_count, 0)
        self.assertEqual(deployment.campaign, campaign)
        self.assertEqual(deployment.creative, creative)
