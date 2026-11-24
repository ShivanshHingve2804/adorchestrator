import uuid

from django.db import models

class CreativeFeature(models.Model):
    creative = models.ForeignKey("campaigns.Creative", related_name="features", on_delete=models.CASCADE)
    feature_name = models.CharField(max_length=64)
    feature_value = models.CharField(max_length=255)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=0.900)
    provider = models.CharField(max_length=32)
    model_version = models.CharField(max_length=255)
    extracted_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("feature_name",)
        constraints = [models.UniqueConstraint(fields=["creative", "feature_name"], name="creative_feature_name_uniq")]
        indexes = [models.Index(fields=["feature_name", "feature_value"])]


class WeeklySummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    week_start = models.DateField(unique=True)
    week_end = models.DateField()
    summary_text = models.TextField()
    top_creatives = models.JSONField(default=list, blank=True)
    top_features = models.JSONField(default=list, blank=True)
    anomalies = models.JSONField(default=list, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-week_start",)
