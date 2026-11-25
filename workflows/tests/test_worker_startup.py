import os
import subprocess
import sys
import unittest


class TemporalWorkerStartupTests(unittest.TestCase):
    def test_worker_bootstrap_uses_the_same_default_settings_as_celery(self):
        environment = os.environ.copy()
        environment.pop("DJANGO_SETTINGS_MODULE", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; import workflows.worker; print(os.environ['DJANGO_SETTINGS_MODULE'])",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(result.stdout.strip(), "adorchestrator.settings.base")
