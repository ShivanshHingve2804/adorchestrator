from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.bulk_launch_workflow import BulkCampaignLaunchWorkflow, BulkLaunchInput


TASK_QUEUE = "ad-orchestrator-test-queue"


def make_activities(statuses, attempts=None, fail_create_for=None):
    attempts = attempts if attempts is not None else {}

    @activity.defn(name="set_campaign_status")
    async def set_campaign_status(campaign_id, campaign_status):
        statuses[f"campaign:{campaign_id}"] = campaign_status

    @activity.defn(name="mark_deployment_failed")
    async def mark_deployment_failed(deployment_key, error):
        statuses[deployment_key] = "FAILED"

    @activity.defn(name="validate_creative")
    async def validate_creative(deployment_key, creative_id, platform):
        return None

    @activity.defn(name="upload_media")
    async def upload_media(deployment_key, creative_id, platform):
        attempts[deployment_key] = attempts.get(deployment_key, 0) + 1
        statuses[deployment_key] = "UPLOADING"
        if attempts[deployment_key] <= attempts.get("upload_failures", 0):
            raise RuntimeError("temporary rate limit")
        return f"media-{platform}-{creative_id}"

    @activity.defn(name="create_campaign")
    async def create_campaign(deployment_key, campaign_id, media_id, platform):
        if platform == fail_create_for:
            from temporalio.exceptions import ApplicationError

            raise ApplicationError("forced create failure", type="FatalTestError", non_retryable=True)
        statuses[deployment_key] = "CREATING"
        return f"platform-campaign-{platform}"

    @activity.defn(name="set_budget")
    async def set_budget(deployment_key, platform, platform_campaign_id, daily_budget):
        statuses[deployment_key] = "BUDGETING"

    @activity.defn(name="activate_campaign")
    async def activate_campaign(deployment_key, platform, platform_campaign_id):
        statuses[deployment_key] = "ACTIVE"

    @activity.defn(name="rollback_campaign")
    async def rollback_campaign(deployment_key, platform, platform_campaign_id):
        statuses[deployment_key] = "ROLLED_BACK"

    return [
        set_campaign_status,
        mark_deployment_failed,
        validate_creative,
        upload_media,
        create_campaign,
        set_budget,
        activate_campaign,
        rollback_campaign,
    ]


async def run_test_workflow(input_data, statuses, attempts=None, fail_create_for=None):
    environment = await WorkflowEnvironment.start_time_skipping()
    async with environment:
        activities = make_activities(statuses, attempts, fail_create_for)
        async with Worker(
            environment.client,
            task_queue=TASK_QUEUE,
            workflows=[BulkCampaignLaunchWorkflow],
            activities=activities,
        ):
            handle = await environment.client.start_workflow(
                BulkCampaignLaunchWorkflow.run,
                input_data,
                id=f"test-{input_data.idempotency_key}",
                task_queue=TASK_QUEUE,
            )
            try:
                return await handle.result()
            except Exception:
                return None


def sample_input(platforms):
    return BulkLaunchInput(
        campaign_id="campaign-1",
        creative_ids=["creative-1"],
        platforms=platforms,
        idempotency_key="test-key",
        daily_budget=25.0,
    )
