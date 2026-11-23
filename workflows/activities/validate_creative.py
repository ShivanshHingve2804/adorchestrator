from temporalio import activity
from temporalio.exceptions import ApplicationError

from .common import _get_creative_details, _post_platform


@activity.defn(name="validate_creative")
async def validate_creative(deployment_key: str, creative_id: str, platform: str):
    details = await _get_creative_details(creative_id)
    result = await _post_platform(
        platform,
        "validate-creative",
        {"creative_id": creative_id, "media_type": details["media_type"]},
    )
    if not result.get("valid", False):
        raise ApplicationError(
            f"Creative {creative_id} is invalid for {platform}",
            type="InvalidMediaError",
            non_retryable=True,
        )
