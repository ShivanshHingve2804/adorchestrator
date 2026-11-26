from temporalio import activity

from .common import _delete_platform_campaign, _update_deployment


@activity.defn(name="rollback_campaign")
async def rollback_campaign(deployment_key: str, platform: str, platform_campaign_id: str):
    result = await _delete_platform_campaign(platform, platform_campaign_id)
    await _update_deployment(deployment_key, status="ROLLED_BACK")
    return result
