import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Campaign",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("VALIDATING", "Validating"),
                            ("LAUNCHING", "Launching"),
                            ("ACTIVE", "Active"),
                            ("PAUSED", "Paused"),
                            ("FAILED", "Failed"),
                            ("COMPLETED", "Completed"),
                        ],
                        default="DRAFT",
                        max_length=16,
                    ),
                ),
                ("daily_budget", models.DecimalField(decimal_places=4, max_digits=12)),
                ("total_budget", models.DecimalField(decimal_places=4, max_digits=12)),
                ("spent", models.DecimalField(decimal_places=4, default=0, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("idempotency_key", models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ("targeting", models.JSONField(blank=True, default=dict)),
                ("version", models.IntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="Creative",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("media_type", models.CharField(choices=[("IMAGE", "Image"), ("VIDEO", "Video")], max_length=8)),
                ("media_url", models.URLField(max_length=2048)),
                ("thumbnail_url", models.URLField(blank=True, max_length=2048, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")],
                        default="PENDING",
                        max_length=8,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="creatives", to="campaigns.campaign"),
                ),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.CreateModel(
            name="PlatformDeployment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(choices=[("META", "Meta"), ("GOOGLE", "Google"), ("TIKTOK", "TikTok")], max_length=8)),
                ("platform_campaign_id", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("UPLOADING", "Uploading"),
                            ("CREATING", "Creating"),
                            ("BUDGETING", "Budgeting"),
                            ("ACTIVE", "Active"),
                            ("FAILED", "Failed"),
                            ("ROLLED_BACK", "Rolled back"),
                        ],
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("retry_count", models.IntegerField(default=0)),
                ("last_error", models.TextField(blank=True, null=True)),
                ("temporal_workflow_id", models.CharField(blank=True, max_length=255, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deployments", to="campaigns.campaign"),
                ),
                (
                    "creative",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deployments", to="campaigns.creative"),
                ),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddConstraint(
            model_name="campaign",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=("DRAFT", "VALIDATING", "LAUNCHING", "ACTIVE", "PAUSED", "FAILED", "COMPLETED")),
                name="campaign_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="creative",
            constraint=models.CheckConstraint(condition=models.Q(media_type__in=("IMAGE", "VIDEO")), name="creative_media_type_valid"),
        ),
        migrations.AddConstraint(
            model_name="creative",
            constraint=models.CheckConstraint(condition=models.Q(status__in=("PENDING", "APPROVED", "REJECTED")), name="creative_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="platformdeployment",
            constraint=models.CheckConstraint(condition=models.Q(platform__in=("META", "GOOGLE", "TIKTOK")), name="deployment_platform_valid"),
        ),
        migrations.AddConstraint(
            model_name="platformdeployment",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=("PENDING", "UPLOADING", "CREATING", "BUDGETING", "ACTIVE", "FAILED", "ROLLED_BACK")),
                name="deployment_status_valid",
            ),
        ),
    ]
