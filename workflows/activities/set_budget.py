from temporalio import activity

from .common import _post_platform, _update_deployment


@activity.defn(name="set_budget")
async def set_budget(deployment_key: str, platform: str, platform_campaign_id: str, daily_budget: float):
    await _update_deployment(deployment_key, status="BUDGETING")
    await _post_platform(
        platform,
        "set-budget",
        {"platform_campaign_id": platform_campaign_id, "daily_budget": daily_budget},
    )
