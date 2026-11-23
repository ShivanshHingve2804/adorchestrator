from temporalio import activity

from .common import _post_platform, _update_deployment


@activity.defn(name="activate_campaign")
async def activate_campaign(deployment_key: str, platform: str, platform_campaign_id: str):
    await _post_platform(
        platform,
        "activate",
        {"platform_campaign_id": platform_campaign_id},
    )
    await _update_deployment(deployment_key, status="ACTIVE", last_error=None)
