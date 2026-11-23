from temporalio import activity

from .common import _get_creative_details, _post_platform, _update_deployment


@activity.defn(name="upload_media")
async def upload_media(deployment_key: str, creative_id: str, platform: str):
    await _update_deployment(deployment_key, status="UPLOADING")
    details = await _get_creative_details(creative_id)
    result = await _post_platform(
        platform,
        "upload-media",
        {"creative_id": creative_id, "media_url": details["media_url"]},
    )
    return result["media_id"]
