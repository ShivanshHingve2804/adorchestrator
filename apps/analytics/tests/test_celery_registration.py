from django.test import SimpleTestCase

from workers.celery_app import app


class CeleryTaskRegistrationTests(SimpleTestCase):
    def test_analytics_and_creative_tasks_are_registered(self):
        app.loader.import_default_modules()

        for task_name in (
            "workers.tasks.analytics.refresh_materialized_views",
            "workers.tasks.analytics.maintain_event_partitions",
            "workers.tasks.analytics.detect_anomalies",
            "workers.tasks.analytics.trigger_budget_reduction",
            "workers.tasks.creative_ai.analyze_creative",
            "workers.tasks.creative_ai.generate_weekly_summary",
        ):
            with self.subTest(task_name=task_name):
                self.assertIn(task_name, app.tasks)
