import httpx
from celery import shared_task
from django.conf import settings

from apps.campaigns.models import Creative
from apps.creative_ai.models import CreativeFeature, WeeklySummary


@shared_task(bind=True, autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=2, rate_limit="10/m")
def analyze_creative(self, creative_id):
    from apps.creative_ai.extractor import extract_features

    creative = Creative.objects.get(pk=creative_id)
    values = extract_features(creative.media_url, creative.media_type)
    provider = settings.AI_PROVIDER.lower()
    model = settings.AI_VISION_MODEL
    for name, value in values.items():
        CreativeFeature.objects.update_or_create(
            creative=creative,
            feature_name=name,
            defaults={
                "feature_value": value,
                "confidence": 0.9,
                "provider": provider,
                "model_version": model,
            },
        )
    return {"creative_id": str(creative.pk), "feature_count": len(values)}


@shared_task(bind=True, autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=2)
def generate_weekly_summary(self):
    from apps.creative_ai.correlator import compute_feature_correlations
    from apps.creative_ai.summary_generator import generate_summary

    from datetime import date, timedelta

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    correlations = compute_feature_correlations(days=7)
    summary = generate_summary(correlations)
    record, _ = WeeklySummary.objects.update_or_create(
        week_start=week_start,
        defaults={
            "week_end": week_end,
            "summary_text": summary,
            "top_creatives": correlations["top_creatives"],
            "top_features": correlations["top_features"],
            "anomalies": correlations["anomalies"],
        },
    )
    return str(record.pk)
