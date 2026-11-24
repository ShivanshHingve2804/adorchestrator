from datetime import date, timedelta

from django.db import migrations


def create_event_partitions_and_view(apps, schema_editor):
    today = date.today()
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE analytics_ad_event (
                id uuid NOT NULL,
                campaign_id uuid NOT NULL,
                creative_id uuid NOT NULL,
                platform varchar(8) NOT NULL CHECK (platform IN ('META', 'GOOGLE', 'TIKTOK')),
                event_type varchar(12) NOT NULL CHECK (event_type IN ('IMPRESSION', 'CLICK', 'CONVERSION')),
                spend numeric(12,4) NOT NULL DEFAULT 0,
                revenue numeric(12,4) NOT NULL DEFAULT 0,
                event_time timestamptz NOT NULL,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                PRIMARY KEY (id, event_time)
            ) PARTITION BY RANGE (event_time)
            """
        )
        for offset in range(-90, 31):
            start = today + timedelta(days=offset)
            end = start + timedelta(days=1)
            cursor.execute(
                f"CREATE TABLE analytics_ad_event_{start:%Y%m%d} PARTITION OF analytics_ad_event "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        cursor.execute(
            "CREATE TABLE analytics_ad_event_default PARTITION OF analytics_ad_event DEFAULT"
        )
        cursor.execute(
            "CREATE INDEX analytics_event_campaign_time_idx ON analytics_ad_event (campaign_id, event_time)"
        )
        cursor.execute(
            "CREATE INDEX analytics_event_creative_time_idx ON analytics_ad_event (creative_id, event_time)"
        )
        cursor.execute(
            """
            CREATE MATERIALIZED VIEW analytics_mv_campaign_daily_perf AS
            SELECT campaign_id, creative_id, platform,
                   (event_time AT TIME ZONE 'UTC')::date AS snapshot_date,
                   COUNT(*) FILTER (WHERE event_type = 'IMPRESSION')::bigint AS impressions,
                   COUNT(*) FILTER (WHERE event_type = 'CLICK')::bigint AS clicks,
                   COUNT(*) FILTER (WHERE event_type = 'CONVERSION')::bigint AS conversions,
                   COALESCE(SUM(spend), 0)::numeric(14,4) AS spend,
                   COALESCE(SUM(revenue), 0)::numeric(14,4) AS revenue,
                   COUNT(*) FILTER (WHERE event_type = 'CLICK')::numeric /
                     NULLIF(COUNT(*) FILTER (WHERE event_type = 'IMPRESSION'), 0) AS ctr,
                   SUM(spend) / NULLIF(COUNT(*) FILTER (WHERE event_type = 'CONVERSION'), 0) AS cpa,
                   SUM(revenue) / NULLIF(SUM(spend), 0) AS roas
            FROM analytics_ad_event
            GROUP BY campaign_id, creative_id, platform, (event_time AT TIME ZONE 'UTC')::date
            """
        )
        cursor.execute(
            "CREATE UNIQUE INDEX analytics_mv_perf_lookup ON analytics_mv_campaign_daily_perf "
            "(campaign_id, creative_id, platform, snapshot_date)"
        )


def drop_event_partitions_and_view(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS analytics_mv_campaign_daily_perf")
        cursor.execute("DROP TABLE IF EXISTS analytics_ad_event CASCADE")


class Migration(migrations.Migration):
    dependencies = [("analytics", "0001_initial")]

    operations = [
        migrations.RunPython(create_event_partitions_and_view, drop_event_partitions_and_view),
    ]
