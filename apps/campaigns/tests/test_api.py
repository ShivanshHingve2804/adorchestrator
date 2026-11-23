from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.campaigns.models import Campaign, Creative, PlatformDeployment


class CampaignAPITests(APITestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="Spring launch",
            daily_budget=Decimal("125.5000"),
            total_budget=Decimal("2500.0000"),
            idempotency_key="campaign-api-1",
        )

    def test_get_campaign_list(self):
        response = self.client.get("/api/campaigns/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.campaign.pk))

    def test_post_campaign_creates_campaign(self):
        response = self.client.post(
            "/api/campaigns/",
            {
                "name": "New campaign",
                "daily_budget": "50.0000",
                "total_budget": "500.0000",
                "currency": "CAD",
                "targeting": {"country": "CA"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New campaign")
        self.assertTrue(Campaign.objects.filter(pk=response.data["id"]).exists())

    def test_get_campaign_detail(self):
        response = self.client.get(f"/api/campaigns/{self.campaign.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Spring launch")

    def test_patch_campaign_updates_fields(self):
        response = self.client.patch(
            f"/api/campaigns/{self.campaign.pk}/",
            {"name": "Updated launch", "status": Campaign.Status.PAUSED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.name, "Updated launch")
        self.assertEqual(self.campaign.status, Campaign.Status.PAUSED)

    def test_post_creative_creates_it_under_campaign(self):
        response = self.client.post(
            f"/api/campaigns/{self.campaign.pk}/creatives/",
            {
                "name": "Product image",
                "media_type": "IMAGE",
                "media_url": "https://cdn.example.test/product.jpg",
                "metadata": {"variant": "blue"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        creative = Creative.objects.get(pk=response.data["id"])
        self.assertEqual(creative.campaign, self.campaign)
        self.assertEqual(creative.metadata, {"variant": "blue"})

    def test_bulk_launch_returns_202_and_creates_deployments(self):
        self.make_creative()

        response = self.client.post(
            f"/api/campaigns/{self.campaign.pk}/bulk_launch/",
            {"platforms": ["META", "TIKTOK"], "idempotency_key": "launch-request-1"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(response.data["deployments"]), 2)
        self.assertEqual(PlatformDeployment.objects.filter(campaign=self.campaign).count(), 2)
        self.assertTrue(
            all(row["status"] == PlatformDeployment.Status.PENDING for row in response.data["deployments"])
        )

    def test_bulk_launch_is_idempotent_for_same_key(self):
        self.make_creative()
        payload = {"platforms": ["META", "TIKTOK"], "idempotency_key": "launch-request-2"}
        path = f"/api/campaigns/{self.campaign.pk}/bulk_launch/"

        first = self.client.post(path, payload, format="json")
        second = self.client.post(path, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            [row["id"] for row in first.data["deployments"]],
            [row["id"] for row in second.data["deployments"]],
        )
        self.assertEqual(PlatformDeployment.objects.filter(campaign=self.campaign).count(), 2)

    def test_bulk_launch_returns_deployment_already_stored_with_request_key(self):
        creative = self.make_creative()
        existing = PlatformDeployment.objects.create(
            campaign=self.campaign,
            creative=creative,
            platform=PlatformDeployment.Platform.META,
            idempotency_key="preexisting-launch-key",
        )

        response = self.client.post(
            f"/api/campaigns/{self.campaign.pk}/bulk_launch/",
            {"platforms": ["META"], "idempotency_key": "preexisting-launch-key"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(response.data["deployments"]), 1)
        self.assertEqual(response.data["deployments"][0]["id"], str(existing.pk))
        self.assertEqual(PlatformDeployment.objects.filter(campaign=self.campaign).count(), 1)

    def make_creative(self):
        return Creative.objects.create(
            campaign=self.campaign,
            name="Main creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://cdn.example.test/main.png",
        )
