import random
import uuid

from locust import HttpUser, between, task


class CampaignUser(HttpUser):
    wait_time = between(0.1, 0.8)

    def on_start(self):
        campaign = self.client.post(
            "/api/campaigns/",
            json={
                "name": f"Load campaign {uuid.uuid4()}",
                "daily_budget": "250.0000",
                "total_budget": "5000.0000",
            },
        )
        if campaign.status_code != 201:
            self.environment.runner.quit()
            return
        self.campaign_id = campaign.json()["id"]
        creative = self.client.post(
            f"/api/campaigns/{self.campaign_id}/creatives/",
            json={
                "name": "Load creative",
                "media_type": "IMAGE",
                "media_url": "https://cdn.example.test/load.jpg",
            },
        )
        if creative.status_code != 201:
            self.environment.runner.quit()

    @task(3)
    def update_budget(self):
        self.client.post(
            f"/api/budgets/campaigns/{self.campaign_id}/adjust-budget/",
            json={
                "new_budget": f"{random.randint(100, 1000)}.0000",
                "trigger_type": "MANUAL",
                "reason": "Locust load exercise",
                "idempotency_key": f"locust-{uuid.uuid4()}"[:255],
            },
            name="POST /api/budgets/.../adjust-budget/",
        )

    @task(1)
    def idempotent_bulk_launch(self):
        self.client.post(
            f"/api/campaigns/{self.campaign_id}/bulk_launch/",
            json={"platforms": ["META"], "idempotency_key": f"locust-launch-{self.campaign_id}"},
            name="POST /api/campaigns/.../bulk_launch/",
        )
