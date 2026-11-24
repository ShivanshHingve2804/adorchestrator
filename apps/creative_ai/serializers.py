from rest_framework import serializers

from .models import CreativeFeature, WeeklySummary


class CreativeFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreativeFeature
        fields = "__all__"


class WeeklySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklySummary
        fields = "__all__"
