import httpx
from asgiref.sync import sync_to_async
from django.utils import timezone
from temporalio import activity
from temporalio.exceptions import ApplicationError


async def _get_creative_details(creative_id):
    from apps.campaigns.models import Creative

    def get_details():
        creative = Creative.objects.get(pk=creative_id)
        return {"media_type": creative.media_type, "media_url": creative.media_url}

    return await sync_to_async(get_details, thread_sensitive=True)()


async def _update_deployment(deployment_key, **fields):
    from apps.campaigns.models import PlatformDeployment

    if "retry_count" not in fields and activity.in_activity():
        fields["retry_count"] = max(0, activity.info().attempt - 1)

    def update():
        PlatformDeployment.objects.filter(idempotency_key=deployment_key).update(
            **fields, updated_at=timezone.now()
        )
        if fields.get("status") == "FAILED":
            deployment = PlatformDeployment.objects.filter(idempotency_key=deployment_key).first()
            if deployment:
                from apps.analytics.services import record_launch_failure

                record_launch_failure(
                    deployment.campaign_id,
                    deployment_key,
                    fields.get("last_error") or "Campaign launch failed",
                )

    await sync_to_async(update, thread_sensitive=True)()


async def _update_campaign(campaign_id, campaign_status):
    from apps.campaigns.models import Campaign

    def update():
        Campaign.objects.filter(pk=campaign_id).update(status=campaign_status)

    await sync_to_async(update, thread_sensitive=True)()


async def _post_platform(platform, endpoint, payload):
    from django.conf import settings

    url = f"{settings.MOCK_PLATFORM_BASE_URL.rstrip('/')}/{platform.lower()}/{endpoint}"
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {408, 429} and 400 <= exc.response.status_code < 500:
                raise ApplicationError(
                    f"Platform rejected {endpoint}: {exc.response.text}",
                    type="InvalidMediaError",
                    non_retryable=True,
                ) from exc
            raise RuntimeError(f"Platform {platform} {endpoint} returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Platform {platform} {endpoint} request failed: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Platform {platform} {endpoint} returned invalid JSON") from exc
    if body.get("status") != "success":
        raise RuntimeError(body.get("message", f"Platform {platform} reported a partial failure"))
    return body.get("data", {})


async def _delete_platform_campaign(platform, platform_campaign_id):
    from django.conf import settings

    url = (
        f"{settings.MOCK_PLATFORM_BASE_URL.rstrip('/')}/"
        f"{platform.lower()}/campaign/{platform_campaign_id}"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        try:
            response = await client.delete(url)
            if response.status_code == 404:
                return {"campaign_id": platform_campaign_id, "already_deleted": True}
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Rollback for {platform_campaign_id} returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Rollback for {platform_campaign_id} failed: {exc}") from exc
    body = response.json()
    if body.get("status") != "success":
        raise RuntimeError(body.get("message", "Platform rollback reported failure"))
    return body.get("data", {})


@activity.defn(name="set_campaign_status")
async def set_campaign_status(campaign_id: str, campaign_status: str):
    await _update_campaign(campaign_id, campaign_status)


@activity.defn(name="mark_deployment_failed")
async def mark_deployment_failed(deployment_key: str, error: str):
    await _update_deployment(deployment_key, status="FAILED", last_error=error[:4000])
