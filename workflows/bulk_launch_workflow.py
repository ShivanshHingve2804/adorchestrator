from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError


@dataclass
class BulkLaunchInput:
    campaign_id: str
    creative_ids: list[str]
    platforms: list[str]
    idempotency_key: str
    daily_budget: float


@workflow.defn
class BulkCampaignLaunchWorkflow:
    @workflow.run
    async def run(self, input: BulkLaunchInput) -> dict:
        activity_retry = RetryPolicy(
            maximum_attempts=5,
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        )
        rollback_retry = RetryPolicy(
            maximum_attempts=10,
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
        )
        completed = []
        await workflow.execute_activity(
            "set_campaign_status",
            args=[input.campaign_id, "LAUNCHING"],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=activity_retry,
        )

        for platform in input.platforms:
            for creative_id in input.creative_ids:
                deployment_key = f"{input.idempotency_key}:{platform}:{creative_id}"
                try:
                    await workflow.execute_activity(
                        "validate_creative",
                        args=[deployment_key, creative_id, platform],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(
                            maximum_attempts=5,
                            initial_interval=timedelta(seconds=2),
                            backoff_coefficient=2.0,
                            maximum_interval=timedelta(seconds=60),
                            non_retryable_error_types=["InvalidMediaError"],
                        ),
                    )
                    media_id = await workflow.execute_activity(
                        "upload_media",
                        args=[deployment_key, creative_id, platform],
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=activity_retry,
                    )
                    platform_campaign_id = await workflow.execute_activity(
                        "create_campaign",
                        args=[deployment_key, input.campaign_id, media_id, platform],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=activity_retry,
                    )
                    completed.append((deployment_key, platform, platform_campaign_id))
                    await workflow.execute_activity(
                        "set_budget",
                        args=[deployment_key, platform, platform_campaign_id, input.daily_budget],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=activity_retry,
                    )
                    await workflow.execute_activity(
                        "activate_campaign",
                        args=[deployment_key, platform, platform_campaign_id],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=activity_retry,
                    )
                except Exception as exc:
                    await workflow.execute_activity(
                        "mark_deployment_failed",
                        args=[deployment_key, str(exc)],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=activity_retry,
                    )
                    rollback_errors = []
                    for completed_key, completed_platform, platform_campaign_id in reversed(completed):
                        try:
                            await workflow.execute_activity(
                                "rollback_campaign",
                                args=[completed_key, completed_platform, platform_campaign_id],
                                start_to_close_timeout=timedelta(minutes=2),
                                retry_policy=rollback_retry,
                            )
                        except Exception as rollback_exc:
                            rollback_errors.append(str(rollback_exc))
                            await workflow.execute_activity(
                                "mark_deployment_failed",
                                args=[completed_key, f"Rollback failed: {rollback_exc}"],
                                start_to_close_timeout=timedelta(seconds=30),
                                retry_policy=activity_retry,
                            )
                    await workflow.execute_activity(
                        "set_campaign_status",
                        args=[input.campaign_id, "FAILED"],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=activity_retry,
                    )
                    if rollback_errors:
                        raise ApplicationError(
                            f"Launch failed ({exc}); compensation also failed: {'; '.join(rollback_errors)}",
                            type="SagaCompensationError",
                            non_retryable=True,
                        ) from exc
                    raise

        await workflow.execute_activity(
            "set_campaign_status",
            args=[input.campaign_id, "ACTIVE"],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=activity_retry,
        )
        return {"campaign_id": input.campaign_id, "status": "ACTIVE", "deployment_count": len(completed)}
