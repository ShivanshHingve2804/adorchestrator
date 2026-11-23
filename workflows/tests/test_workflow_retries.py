import unittest

from workflows.tests.helpers import run_test_workflow, sample_input


class BulkLaunchRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_activity_retries_then_deployment_activates(self):
        statuses = {}
        attempts = {"upload_failures": 2}
        result = await run_test_workflow(sample_input(["META"]), statuses, attempts=attempts)

        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(attempts["test-key:META:creative-1"], 3)
        self.assertEqual(statuses["test-key:META:creative-1"], "ACTIVE")
