from rest_framework import serializers

from .models import Campaign, Creative, PlatformDeployment


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = (
            "id",
            "name",
            "status",
            "daily_budget",
            "total_budget",
            "spent",
            "currency",
            "idempotency_key",
            "targeting",
            "version",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "spent", "version", "created_at", "updated_at")


class CreativeSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Creative
        fields = (
            "id",
            "campaign",
            "name",
            "media_type",
            "media_url",
            "thumbnail_url",
            "status",
            "metadata",
            "created_at",
        )
        read_only_fields = ("id", "campaign", "created_at")


class PlatformDeploymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformDeployment
        fields = "__all__"
        read_only_fields = (
            "id",
            "campaign",
            "creative",
            "platform",
            "platform_campaign_id",
            "status",
            "idempotency_key",
            "retry_count",
            "last_error",
            "temporal_workflow_id",
            "created_at",
            "updated_at",
        )


class BulkLaunchSerializer(serializers.Serializer):
    platforms = serializers.ListField(
        child=serializers.ChoiceField(choices=PlatformDeployment.Platform.choices),
        allow_empty=False,
    )
    idempotency_key = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)

    def validate_platforms(self, platforms):
        if len(set(platforms)) != len(platforms):
            raise serializers.ValidationError("Each platform may only be listed once.")
        return platforms
