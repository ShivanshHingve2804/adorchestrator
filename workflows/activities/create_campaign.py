from temporalio import activity

from .common import _post_platform, _update_deployment


@activity.defn(name="create_campaign")
async def create_campaign(deployment_key: str, campaign_id: str, media_id: str, platform: str):
    await _update_deployment(deployment_key, status="CREATING")
    result = await _post_platform(
        platform,
        "create-campaign",
        {"campaign_id": campaign_id, "media_id": media_id, "idempotency_key": deployment_key},
    )
    platform_campaign_id = result["platform_campaign_id"]
    await _update_deployment(deployment_key, platform_campaign_id=platform_campaign_id)
    return platform_campaign_id
