import uuid

from django.db import models
from django.db.models import Q


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        VALIDATING = "VALIDATING", "Validating"
        LAUNCHING = "LAUNCHING", "Launching"
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        FAILED = "FAILED", "Failed"
        COMPLETED = "COMPLETED", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    daily_budget = models.DecimalField(max_digits=12, decimal_places=4)
    total_budget = models.DecimalField(max_digits=12, decimal_places=4)
    spent = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    concurrency_token = models.UUIDField(editable=False, unique=True, null=True, blank=True)
    targeting = models.JSONField(default=dict, blank=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=("DRAFT", "VALIDATING", "LAUNCHING", "ACTIVE", "PAUSED", "FAILED", "COMPLETED")
                ),
                name="campaign_status_valid",
            ),
        ]

    def __str__(self):
        return self.name


class Creative(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Video"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="creatives", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    media_type = models.CharField(max_length=8, choices=MediaType.choices)
    media_url = models.URLField(max_length=2048)
    thumbnail_url = models.URLField(max_length=2048, null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(media_type__in=("IMAGE", "VIDEO")),
                name="creative_media_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("PENDING", "APPROVED", "REJECTED")),
                name="creative_status_valid",
            ),
        ]

    def __str__(self):
        return self.name


class PlatformDeployment(models.Model):
    class Platform(models.TextChoices):
        META = "META", "Meta"
        GOOGLE = "GOOGLE", "Google"
        TIKTOK = "TIKTOK", "TikTok"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        UPLOADING = "UPLOADING", "Uploading"
        CREATING = "CREATING", "Creating"
        BUDGETING = "BUDGETING", "Budgeting"
        ACTIVE = "ACTIVE", "Active"
        FAILED = "FAILED", "Failed"
        ROLLED_BACK = "ROLLED_BACK", "Rolled back"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="deployments", on_delete=models.CASCADE)
    creative = models.ForeignKey(Creative, related_name="deployments", on_delete=models.CASCADE)
    platform = models.CharField(max_length=8, choices=Platform.choices)
    platform_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    idempotency_key = models.CharField(max_length=255, unique=True)
    retry_count = models.IntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)
    temporal_workflow_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(platform__in=("META", "GOOGLE", "TIKTOK")),
                name="deployment_platform_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=("PENDING", "UPLOADING", "CREATING", "BUDGETING", "ACTIVE", "FAILED", "ROLLED_BACK")
                ),
                name="deployment_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.campaign} / {self.platform} / {self.creative}"
