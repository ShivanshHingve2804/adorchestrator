import json
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.campaigns.models import Campaign, Creative
from apps.creative_ai.extractor import FEATURE_NAMES, extract_features
from apps.creative_ai.models import CreativeFeature, WeeklySummary
from workers.tasks.creative_ai import analyze_creative, generate_weekly_summary


class ExtractorTests(SimpleTestCase):
    @override_settings(AI_PROVIDER="ollama", AI_VISION_MODEL="configured-vision-id")
    @patch("apps.creative_ai.extractor._provider_content")
    @patch("apps.creative_ai.extractor._download_media", return_value=[("image/jpeg", b"jpeg")])
    def test_extracts_the_required_structured_features(self, download, provider):
        provider.return_value = json.dumps({name: f"sample-{name}" for name in FEATURE_NAMES})
        result = extract_features("https://assets.example.test/ad.jpg", "IMAGE")
        self.assertEqual(set(result), set(FEATURE_NAMES))
        self.assertEqual(result["hook_style"], "sample-hook_style")
        download.assert_called_once()
        provider.assert_called_once()

    @override_settings(AI_PROVIDER="ollama", AI_VISION_MODEL="configured-vision-id")
    @patch("apps.creative_ai.extractor._provider_content")
    @patch("apps.creative_ai.extractor._download_media", return_value=[("image/jpeg", b"frame")])
    def test_video_media_uses_sampled_frames(self, download, provider):
        provider.return_value = json.dumps({name: f"video-{name}" for name in FEATURE_NAMES})
        result = extract_features("https://assets.example.test/ad.mp4", "VIDEO")
        self.assertEqual(result["pacing"], "video-pacing")
        download.assert_called_once_with("https://assets.example.test/ad.mp4", "VIDEO")


class CreativeAITests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            name="Creative AI campaign",
            daily_budget=Decimal("100.0000"),
            total_budget=Decimal("1000.0000"),
        )
        self.creative = Creative.objects.create(
            campaign=self.campaign,
            name="Creative",
            media_type=Creative.MediaType.IMAGE,
            media_url="https://assets.example.test/ad.jpg",
        )
        self.client = APIClient()

    @patch("apps.creative_ai.views.analyze_creative.delay")
    def test_analyze_endpoint_queues_celery_task(self, delay):
        delay.return_value.id = "celery-task-1"
        response = self.client.post(f"/api/creative-ai/creatives/{self.creative.pk}/analyze/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["task_id"], "celery-task-1")
        delay.assert_called_once_with(str(self.creative.pk))

    @override_settings(AI_PROVIDER="ollama", AI_VISION_MODEL="vision-config")
    @patch("apps.creative_ai.extractor.extract_features")
    def test_analysis_task_upserts_features(self, extract):
        extract.return_value = {name: name.replace("_", " ") for name in FEATURE_NAMES}
        result = analyze_creative.run(str(self.creative.pk))
        self.assertEqual(result["feature_count"], len(FEATURE_NAMES))
        self.assertEqual(CreativeFeature.objects.filter(creative=self.creative).count(), len(FEATURE_NAMES))
        self.assertEqual(CreativeFeature.objects.get(creative=self.creative, feature_name="cta_type").model_version, "vision-config")

    @patch("apps.creative_ai.correlator.compute_feature_correlations", return_value={
        "top_features": [{"feature_name": "hook_style", "feature_value": "question"}],
        "top_creatives": [],
        "anomalies": [],
    })
    @patch("apps.creative_ai.summary_generator.generate_summary", return_value="A measured weekly summary.")
    def test_weekly_summary_is_created_and_replaced_for_the_same_week(self, generate, correlate):
        first = generate_weekly_summary.run()
        second = generate_weekly_summary.run()
        self.assertEqual(first, second)
        self.assertEqual(WeeklySummary.objects.count(), 1)
        self.assertEqual(WeeklySummary.objects.get().summary_text, "A measured weekly summary.")

    def test_latest_summary_endpoint_returns_404_when_empty(self):
        response = self.client.get("/api/creative-ai/summaries/latest/")
        self.assertEqual(response.status_code, 404)
