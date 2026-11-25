from datetime import date, timedelta

from django.db import connection


def compute_feature_correlations(days=7):
    days = max(1, min(int(days), 90))
    start_date = date.today() - timedelta(days=days - 1)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT f.feature_name, f.feature_value,
                   COUNT(DISTINCT f.creative_id)::integer AS creative_count,
                   AVG(m.ctr) AS average_ctr,
                   AVG(m.roas) AS average_roas,
                   AVG(m.cpa) AS average_cpa
            FROM creative_ai_creativefeature f
            JOIN analytics_mv_campaign_daily_perf m ON m.creative_id = f.creative_id
            WHERE m.snapshot_date >= %s
            GROUP BY f.feature_name, f.feature_value
            ORDER BY AVG(m.roas) DESC NULLS LAST
            """,
            [start_date],
        )
        features = [
            {
                "feature_name": row[0],
                "feature_value": row[1],
                "creative_count": row[2],
                "average_ctr": float(row[3]) if row[3] is not None else None,
                "average_roas": float(row[4]) if row[4] is not None else None,
                "average_cpa": float(row[5]) if row[5] is not None else None,
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT m.creative_id, cr.name, ca.name, SUM(m.spend) AS spend,
                   SUM(m.revenue) AS revenue
            FROM analytics_mv_campaign_daily_perf m
            JOIN campaigns_creative cr ON cr.id = m.creative_id
            JOIN campaigns_campaign ca ON ca.id = m.campaign_id
            WHERE m.snapshot_date >= %s
            GROUP BY m.creative_id, cr.name, ca.name
            ORDER BY SUM(m.revenue) / NULLIF(SUM(m.spend), 0) DESC NULLS LAST
            LIMIT 10
            """,
            [start_date],
        )
        top_creatives = [
            {
                "creative_id": str(row[0]),
                "creative_name": row[1],
                "campaign_name": row[2],
                "spend": float(row[3] or 0),
                "revenue": float(row[4] or 0),
                "roas": float(row[4] / row[3]) if row[3] else None,
            }
            for row in cursor.fetchall()
        ]

    return {
        "days": days,
        "top_features": features[:10],
        "anomalies": [item for item in features if item["creative_count"] == 1],
        "top_creatives": top_creatives,
    }
