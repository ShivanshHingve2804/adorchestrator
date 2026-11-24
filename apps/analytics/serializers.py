from rest_framework import serializers

from .models import Alert, PerformanceSnapshot


class PerformanceSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceSnapshot
        fields = "__all__"


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = ("id", "fired_at")
