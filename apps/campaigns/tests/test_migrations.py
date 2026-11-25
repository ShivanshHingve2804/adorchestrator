from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase


class CampaignMigrationTests(SimpleTestCase):
    def test_campaign_migration_history_restores_id_field(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)

        self.assertIn(("campaigns", "0002_campaign_schema_baseline"), loader.graph.nodes)
        dependencies = loader.disk_migrations["campaigns", "0003_add_concurrency_token"].dependencies
        self.assertIn(("campaigns", "0001_initial"), dependencies)
        self.assertIn(("budgets", "0001_initial"), dependencies)
        plan = loader.graph.forwards_plan(("campaigns", "0006_restore_campaign_id"))
        self.assertIn(("campaigns", "0003_add_concurrency_token"), plan)
        self.assertIn(("campaigns", "0002_campaign_schema_baseline"), plan)
        state = loader.project_state([("campaigns", "0006_restore_campaign_id")])
        campaign_fields = state.models["campaigns", "campaign"].fields
        self.assertIn("id", campaign_fields)
        self.assertTrue(campaign_fields["id"].primary_key)
        self.assertNotIn("idim", campaign_fields)
