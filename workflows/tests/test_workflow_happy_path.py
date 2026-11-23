import unittest

from workflows.tests.helpers import run_test_workflow, sample_input


class BulkLaunchHappyPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_platform_deployments_end_active(self):
        statuses = {}
        result = await run_test_workflow(sample_input(["META", "TIKTOK", "GOOGLE"]), statuses)

        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(result["deployment_count"], 3)
        self.assertEqual(statuses["campaign:campaign-1"], "ACTIVE")
        self.assertEqual(
            [statuses[f"test-key:{platform}:creative-1"] for platform in ("META", "TIKTOK", "GOOGLE")],
            ["ACTIVE", "ACTIVE", "ACTIVE"],
        )
