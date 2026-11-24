from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("analytics", "0002_partitioned_events_and_materialized_view")]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE analytics_ad_event DROP CONSTRAINT IF EXISTS analytics_ad_event_campaign_id_fkey; "
                "ALTER TABLE analytics_ad_event DROP CONSTRAINT IF EXISTS analytics_ad_event_creative_id_fkey"
            ),
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
