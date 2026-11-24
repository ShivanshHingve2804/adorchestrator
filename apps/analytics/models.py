import uuid

from django.db import models


class AdEvent(models.Model):
    """Append-only event table, physically partitioned by event_time in PostgreSQL."""

    class EventType(models.TextChoices):
        IMPRESSION = "IMPRESSION", "Impression"
        CLICK = "CLICK", "Click"
        CONVERSION = "CONVERSION", "Conversion"

    class Platform(models.TextChoices):
        META = "META", "Meta"
        GOOGLE = "GOOGLE", "Google"
        TIKTOK = "TIKTOK", "TikTok"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey("campaigns.Campaign", db_constraint=False, on_delete=models.DO_NOTHING)
    creative = models.ForeignKey("campaigns.Creative", db_constraint=False, on_delete=models.DO_NOTHING)
    platform = models.CharField(max_length=8, choices=Platform.choices)
    event_type = models.CharField(max_length=12, choices=EventType.choices)
    spend = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    event_time = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        managed = False
        db_table = "analytics_ad_event"
        indexes = [models.Index(fields=["campaign", "event_time"])]


class PerformanceSnapshot(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", related_name="performance_snapshots", on_delete=models.CASCADE)
    creative = models.ForeignKey("campaigns.Creative", related_name="performance_snapshots", on_delete=models.CASCADE)
    platform = models.CharField(max_length=8, choices=AdEvent.Platform.choices)
    snapshot_date = models.DateField()
    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    conversions = models.BigIntegerField(default=0)
    spend = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    ctr = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    cpa = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    roas = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-snapshot_date",)
        constraints = [models.UniqueConstraint(
            fields=["campaign", "creative", "platform", "snapshot_date"],
            name="snapshot_campaign_creative_platform_day_uniq",
        )]
        indexes = [models.Index(fields=["campaign", "snapshot_date"])]


class Alert(models.Model):
    class AlertType(models.TextChoices):
        CPA_SPIKE = "CPA_SPIKE", "CPA spike"
        ROAS_DROP = "ROAS_DROP", "ROAS drop"
        BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED", "Budget exhausted"
        LAUNCH_FAILURE = "LAUNCH_FAILURE", "Launch failure"

    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey("campaigns.Campaign", related_name="alerts", on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=24, choices=AlertType.choices)
    severity = models.CharField(max_length=12, choices=Severity.choices)
    message = models.TextField()
    acknowledged = models.BooleanField(default=False)
    context = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=255, unique=True)
    fired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fired_at",)
        indexes = [models.Index(fields=["acknowledged", "fired_at"])]
