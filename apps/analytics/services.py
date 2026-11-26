from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from .models import Alert


REPORT_CACHE_TTL = 300
REPORT_VERSION_KEY = "report:cache_version"


def record_launch_failure(campaign_id, deployment_key, message):
    return Alert.objects.get_or_create(
        dedupe_key=f"launch-failure:{deployment_key}",
        defaults={
            "campaign_id": campaign_id,
            "alert_type": Alert.AlertType.LAUNCH_FAILURE,
            "severity": Alert.Severity.CRITICAL,
            "message": message[:2000],
            "context": {"deployment_key": deployment_key},
        },
    )[0]


class ReportingService:
    @staticmethod
    def _cache_version():
        version = cache.get(REPORT_VERSION_KEY)
        if version is None:
            return 1
        return int(version)

    @classmethod
    def invalidate_report_cache(cls):
        try:
            cache.incr(REPORT_VERSION_KEY)
        except ValueError:
            cache.set(REPORT_VERSION_KEY, 2, None)

    @classmethod
    def get_campaign_report(cls, campaign_id, days=7):
        days = max(1, min(int(days), 90))
        version = cls._cache_version()
        cache_key = f"report:v{version}:{campaign_id}:{days}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        start_date = timezone.now().date() - timedelta(days=days - 1)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshot_date, platform,
                       SUM(impressions)::bigint, SUM(clicks)::bigint,
                       SUM(conversions)::bigint, SUM(spend), SUM(revenue),
                       SUM(clicks)::numeric / NULLIF(SUM(impressions), 0),
                       SUM(spend) / NULLIF(SUM(conversions), 0),
                       SUM(revenue) / NULLIF(SUM(spend), 0)
                FROM analytics_mv_campaign_daily_perf
                WHERE campaign_id = %s AND snapshot_date >= %s
                GROUP BY snapshot_date, platform
                ORDER BY snapshot_date DESC, platform
                """,
                [str(campaign_id), start_date],
            )
            rows = [
                {
                    "date": row[0].isoformat(),
                    "platform": row[1],
                    "impressions": row[2],
                    "clicks": row[3],
                    "conversions": row[4],
                    "spend": float(row[5] or 0),
                    "revenue": float(row[6] or 0),
                    "ctr": float(row[7]) if row[7] is not None else None,
                    "cpa": float(row[8]) if row[8] is not None else None,
                    "roas": float(row[9]) if row[9] is not None else None,
                }
                for row in cursor.fetchall()
            ]

        report = {"campaign_id": str(campaign_id), "days": days, "data": rows}
        cache.set(cache_key, report, REPORT_CACHE_TTL)
        return report


def refresh_performance_snapshots():
    """Refresh the aggregate view, then upsert its latest daily rows into the snapshot table."""
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY analytics_mv_campaign_daily_perf")
        cursor.execute(
            """
            INSERT INTO analytics_performancesnapshot
              (campaign_id, creative_id, platform, snapshot_date, impressions, clicks,
               conversions, spend, revenue, ctr, cpa, roas, updated_at)
            SELECT m.campaign_id, m.creative_id, m.platform, m.snapshot_date,
                   m.impressions, m.clicks, m.conversions, m.spend, m.revenue,
                   m.ctr, m.cpa, m.roas, NOW()
            FROM analytics_mv_campaign_daily_perf m
            JOIN campaigns_campaign c ON c.id = m.campaign_id
            JOIN campaigns_creative cr ON cr.id = m.creative_id
            ON CONFLICT (campaign_id, creative_id, platform, snapshot_date) DO UPDATE SET
              impressions = EXCLUDED.impressions,
              clicks = EXCLUDED.clicks,
              conversions = EXCLUDED.conversions,
              spend = EXCLUDED.spend,
              revenue = EXCLUDED.revenue,
              ctr = EXCLUDED.ctr,
              cpa = EXCLUDED.cpa,
              roas = EXCLUDED.roas,
              updated_at = NOW()
            """
        )
    ReportingService.invalidate_report_cache()
