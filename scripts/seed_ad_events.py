"""Stream synthetic event rows in bounded batches; default workload is five million."""
import argparse
import os
import random
import sys
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adorchestrator.settings.base")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django

django.setup()

from django.utils import timezone  # noqa: E402

from apps.analytics.models import AdEvent  # noqa: E402
from apps.campaigns.models import Campaign, Creative  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5_000_000)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.count < 0 or args.batch_size < 1:
        parser.error("count must be non-negative and batch-size must be positive")

    random.seed(args.seed)
    campaign = Campaign.objects.first()
    if campaign is None:
        campaign = Campaign.objects.create(
            name="Synthetic analytics seed",
            daily_budget=Decimal("1000"),
            total_budget=Decimal("10000"),
            idempotency_key=f"seed-campaign-{uuid.uuid4()}",
        )
    creatives = list(Creative.objects.filter(campaign=campaign)[:10])
    if not creatives:
        creatives = [Creative.objects.create(
            campaign=campaign,
            name=f"Seed creative {i + 1}",
            media_type=Creative.MediaType.IMAGE,
            media_url=f"https://example.invalid/seed-{i + 1}.jpg",
        ) for i in range(3)]

    platforms = list(AdEvent.Platform.values)
    now = timezone.now()
    batch = []
    for index in range(args.count):
        roll = random.random()
        event_type = (
            AdEvent.EventType.IMPRESSION if roll < 0.60 else
            AdEvent.EventType.CLICK if roll < 0.90 else
            AdEvent.EventType.CONVERSION
        )
        batch.append(AdEvent(
            campaign_id=campaign.pk,
            creative_id=random.choice(creatives).pk,
            platform=random.choice(platforms),
            event_type=event_type,
            spend=Decimal(str(round(random.uniform(0.01, 2.50), 4))) if event_type != AdEvent.EventType.IMPRESSION else Decimal("0"),
            revenue=Decimal(str(round(random.uniform(20, 250), 4))) if event_type == AdEvent.EventType.CONVERSION else Decimal("0"),
            event_time=now - timedelta(days=random.randrange(90), seconds=random.randrange(86400)),
            metadata={"seed": args.seed},
        ))
        if len(batch) >= args.batch_size:
            AdEvent.objects.bulk_create(batch, batch_size=args.batch_size)
            batch.clear()
        if (index + 1) % 100_000 == 0:
            print(f"Inserted {index + 1:,}/{args.count:,} event rows", flush=True)
    if batch:
        AdEvent.objects.bulk_create(batch, batch_size=args.batch_size)
    print(f"Inserted {args.count:,} events for campaign {campaign.pk}")


if __name__ == "__main__":
    main()
