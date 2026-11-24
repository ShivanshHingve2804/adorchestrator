import asyncio
import logging
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adorchestrator.settings.dev")

import django

django.setup()

from django.conf import settings  # noqa: E402
from temporalio.client import Client  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from workflows.activities.activate_campaign import activate_campaign  # noqa: E402
from workflows.activities.common import mark_deployment_failed, set_campaign_status  # noqa: E402
from workflows.activities.create_campaign import create_campaign  # noqa: E402
from workflows.activities.rollback_campaign import rollback_campaign  # noqa: E402
from workflows.activities.set_budget import set_budget  # noqa: E402
from workflows.activities.upload_media import upload_media  # noqa: E402
from workflows.activities.validate_creative import validate_creative  # noqa: E402
from workflows.bulk_launch_workflow import BulkCampaignLaunchWorkflow  # noqa: E402


TASK_QUEUE = "ad-orchestrator-queue"
logger = logging.getLogger(__name__)


async def run_worker():
    while True:
        try:
            client = await Client.connect(
                settings.TEMPORAL_HOST,
                namespace=settings.TEMPORAL_NAMESPACE,
            )
            break
        except Exception:
            logger.exception("Temporal is not ready at %s; retrying in 5 seconds", settings.TEMPORAL_HOST)
            await asyncio.sleep(5)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[BulkCampaignLaunchWorkflow],
        activities=[
            set_campaign_status,
            mark_deployment_failed,
            validate_creative,
            upload_media,
            create_campaign,
            set_budget,
            activate_campaign,
            rollback_campaign,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
