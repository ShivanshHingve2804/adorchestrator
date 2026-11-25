from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from temporalio.exceptions import ApplicationError

from workflows.activities.validate_creative import validate_creative


class CreativeValidationActivityTests(IsolatedAsyncioTestCase):
    @patch("workflows.activities.validate_creative._post_platform", new_callable=AsyncMock)
    @patch("workflows.activities.validate_creative._get_creative_details", new_callable=AsyncMock)
    async def test_valid_creative_is_checked_with_its_media_type(self, get_details, post_platform):
        get_details.return_value = {"media_type": "IMAGE", "media_url": "https://ads.example/ad.jpg"}
        post_platform.return_value = {"valid": True}

        await validate_creative("deployment-1", "creative-1", "META")

        get_details.assert_awaited_once_with("creative-1")
        post_platform.assert_awaited_once_with(
            "META",
            "validate-creative",
            {"creative_id": "creative-1", "media_type": "IMAGE"},
        )

    @patch("workflows.activities.validate_creative._post_platform", new_callable=AsyncMock)
    @patch("workflows.activities.validate_creative._get_creative_details", new_callable=AsyncMock)
    async def test_invalid_creative_raises_non_retryable_application_error(self, get_details, post_platform):
        get_details.return_value = {"media_type": "VIDEO", "media_url": "https://ads.example/ad.mp4"}
        post_platform.return_value = {"valid": False}

        with self.assertRaises(ApplicationError) as raised:
            await validate_creative("deployment-1", "creative-1", "TIKTOK")

        self.assertEqual(raised.exception.type, "InvalidMediaError")
        self.assertTrue(raised.exception.non_retryable)
