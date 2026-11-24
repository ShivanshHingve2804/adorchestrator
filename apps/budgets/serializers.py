from decimal import Decimal

from rest_framework import serializers

from .models import BudgetAdjustment


class BudgetAdjustmentSerializer(serializers.ModelSerializer):
    old_budget = serializers.DecimalField(
        max_digits=12,
        decimal_places=4,
        source="original_budget",
        read_only=True,
    )

    class Meta:
        model = BudgetAdjustment
        fields = "__all__"
        read_only_fields = (
            "id",
            "campaign",
            "concurrency_token",
            "source",
            "adjustment_type",
            "new_budget",
            "original_budget",
            "budget_change",
            "percent_delta",
            "platform_idempotency_key",
            "campaign_idempotency_key",
            "default_account",
            "change_summary",
            "status",
            "approved_by",
            "approved_at",
            "requested_by",
            "requested_at",
            "rejection_reason",
            "audit_log",
            "created_at",
            "updated_at",
            "trigger_type",
            "reason",
            "lock_token",
            "idempotency_key",
            "old_budget",
        )


class AdjustBudgetRequestSerializer(serializers.Serializer):
    new_budget = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"))
    trigger_type = serializers.ChoiceField(choices=BudgetAdjustment.TriggerType.choices)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=False)
