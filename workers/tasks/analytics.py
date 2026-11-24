from datetime import date, datetime, timedelta
from decimal import Decimal

from celery import shared_task
from django.db import connection

from apps.analytics.models import Alert


CPA_SPIKE_THRESHOLD = Decimal("1.5")
ROAS_DROP_THRESHOLD = Decimal("0.6")


@shared_task
def refresh_materialized_views():
    from apps.analytics.services import refresh_performance_snapshots

    refresh_performance_snapshots()


@shared_task
def maintain_event_partitions():
    """Keep daily partitions ahead of writes and detach data older than 90 days."""
    today = date.today()
    with connection.cursor() as cursor:
        for offset in range(0, 32):
            partition_day = today + timedelta(days=offset)
            suffix = partition_day.strftime("%Y%m%d")
            name = f"analytics_ad_event_{suffix}"
            start = partition_day.isoformat()
            end = (partition_day + timedelta(days=1)).isoformat()
            cursor.execute(
                f'CREATE TABLE IF NOT EXISTS "{name}" PARTITION OF analytics_ad_event '
                f"FOR VALUES FROM ('{start}') TO ('{end}')"
            )
        cutoff = today - timedelta(days=90)
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
            "AND tablename LIKE 'analytics_ad_event_%'"
        )
        for (table_name,) in cursor.fetchall():
            suffix = table_name.removeprefix("analytics_ad_event_")
            try:
                partition_day = datetime.strptime(suffix, "%Y%m%d").date()
            except ValueError:
                continue
            if partition_day < cutoff:
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')


@shared_task
def detect_anomalies():
    """Compare the latest daily campaign metrics with the preceding seven days."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH daily AS (
                SELECT campaign_id, snapshot_date, SUM(spend) AS spend,
                       SUM(conversions) AS conversions, SUM(revenue) AS revenue
                FROM analytics_mv_campaign_daily_perf
                GROUP BY campaign_id, snapshot_date
            ), latest AS (
                SELECT campaign_id, MAX(snapshot_date) AS report_day
                FROM daily GROUP BY campaign_id
            ), metrics AS (
                SELECT l.campaign_id, l.report_day,
                       r.spend AS recent_spend, r.conversions AS recent_conversions,
                       r.revenue AS recent_revenue,
                       b.avg_cpa, b.avg_roas
                FROM latest l
                JOIN daily r ON r.campaign_id = l.campaign_id AND r.snapshot_date = l.report_day
                LEFT JOIN LATERAL (
                    SELECT AVG(spend / NULLIF(conversions, 0)) AS avg_cpa,
                           AVG(revenue / NULLIF(spend, 0)) AS avg_roas
                    FROM daily d
                    WHERE d.campaign_id = l.campaign_id
                      AND d.snapshot_date BETWEEN l.report_day - 7 AND l.report_day - 1
                ) b ON TRUE
            )
            SELECT campaign_id, report_day,
                   recent_spend / NULLIF(recent_conversions, 0) AS recent_cpa,
                   avg_cpa,
                   recent_revenue / NULLIF(recent_spend, 0) AS recent_roas,
                   avg_roas
            FROM metrics
            """
        )
        rows = cursor.fetchall()

    for campaign_id, report_day, recent_cpa, avg_cpa, recent_roas, avg_roas in rows:
        if recent_cpa and avg_cpa and recent_cpa > avg_cpa * CPA_SPIKE_THRESHOLD:
            _, created = _record_anomaly(
                campaign_id, report_day, Alert.AlertType.CPA_SPIKE, Alert.Severity.CRITICAL,
                f"CPA rose to {recent_cpa:.2f} from a seven-day average of {avg_cpa:.2f}.",
                {"recent_cpa": float(recent_cpa), "average_cpa": float(avg_cpa)},
            )
            if created:
                trigger_budget_reduction.delay(str(campaign_id), "0.70", str(report_day), "CPA_SPIKE")

        if recent_roas and avg_roas and recent_roas < avg_roas * ROAS_DROP_THRESHOLD:
            _, created = _record_anomaly(
                campaign_id, report_day, Alert.AlertType.ROAS_DROP, Alert.Severity.WARNING,
                f"ROAS fell to {recent_roas:.2f} from a seven-day average of {avg_roas:.2f}.",
                {"recent_roas": float(recent_roas), "average_roas": float(avg_roas)},
            )
            if created:
                trigger_budget_reduction.delay(str(campaign_id), "0.80", str(report_day), "ROAS_DROP")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH latest AS (
                SELECT campaign_id, MAX(snapshot_date) AS report_day
                FROM analytics_mv_campaign_daily_perf GROUP BY campaign_id
            ), spend AS (
                SELECT m.campaign_id, l.report_day, SUM(m.spend) AS daily_spend
                FROM analytics_mv_campaign_daily_perf m
                JOIN latest l ON l.campaign_id = m.campaign_id AND l.report_day = m.snapshot_date
                GROUP BY m.campaign_id, l.report_day
            )
            SELECT s.campaign_id, s.report_day, s.daily_spend, c.daily_budget
            FROM spend s JOIN campaigns_campaign c ON c.idim = s.campaign_id
            WHERE s.daily_spend >= c.daily_budget
            """
        )
        exhausted = cursor.fetchall()
    for campaign_id, report_day, daily_spend, daily_budget in exhausted:
        _record_anomaly(
            campaign_id, report_day, Alert.AlertType.BUDGET_EXHAUSTED, Alert.Severity.WARNING,
            f"Daily spend reached {daily_spend:.2f} against a budget of {daily_budget:.2f}.",
            {"daily_spend": float(daily_spend), "daily_budget": float(daily_budget)},
        )


def _record_anomaly(campaign_id, report_day, alert_type, severity, message, context):
    return Alert.objects.get_or_create(
        dedupe_key=f"{alert_type}:{campaign_id}:{report_day.isoformat()}",
        defaults={
            "campaign_id": campaign_id,
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            "context": context,
        },
    )


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def trigger_budget_reduction(campaign_id, multiplier, report_day, alert_type):
    from apps.budgets.services import BudgetService
    from apps.campaigns.models import Campaign

    campaign = Campaign.objects.get(pk=campaign_id)
    new_budget = (campaign.daily_budget * Decimal(multiplier)).quantize(Decimal("0.0001"))
    BudgetService.adjust_budget(
        campaign_id=campaign.pk,
        new_budget=new_budget,
        trigger_type=f"AUTO_{alert_type}",
        reason=f"Automatic {alert_type} adjustment for {report_day}.",
        idempotency_key=f"anomaly:{alert_type}:{campaign_id}:{report_day}",
    )
