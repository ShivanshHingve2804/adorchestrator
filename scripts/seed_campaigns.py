"""Create a small, repeatable demo campaign set without requiring platform calls."""
import os
import sys
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adorchestrator.settings.base")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django

django.setup()

from apps.campaigns.models import Campaign, Creative  # noqa: E402


def main():
    for campaign_index in range(3):
        key = f"demo-campaign-{campaign_index + 1}"
        campaign, _ = Campaign.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "name": f"Demo campaign {campaign_index + 1}",
                "daily_budget": Decimal("250.0000"),
                "total_budget": Decimal("5000.0000"),
                "targeting": {"country": "US", "seed": True},
            },
        )
        for creative_index in range(2):
            Creative.objects.get_or_create(
                campaign=campaign,
                name=f"Demo creative {creative_index + 1}",
                defaults={
                    "media_type": Creative.MediaType.IMAGE,
                    "media_url": f"https://example.invalid/demo-{campaign_index + 1}-{creative_index + 1}.jpg",
                    "metadata": {"seed": True},
                },
            )
        print(f"{campaign.pk}: {campaign.name}")


if __name__ == "__main__":
    main()
