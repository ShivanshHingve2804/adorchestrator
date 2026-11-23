import unittest

from workflows.tests.helpers import run_test_workflow, sample_input


class BulkLaunchRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_prior_deployment_is_rolled_back_after_later_failure(self):
        statuses = {}
        result = await run_test_workflow(
            sample_input(["META", "TIKTOK"]),
            statuses,
            fail_create_for="TIKTOK",
        )

        self.assertIsNone(result)
        self.assertEqual(statuses["test-key:META:creative-1"], "ROLLED_BACK")
        self.assertEqual(statuses["test-key:TIKTOK:creative-1"], "FAILED")
        self.assertEqual(statuses["campaign:campaign-1"], "FAILED")
