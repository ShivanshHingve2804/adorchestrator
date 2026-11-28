import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Q
from django.utils import timezone


class BudgetAdjustment(models.Model):
    """
    Tracks budget adjustments with proper locking and visibility isolation.

    Each budget adjustment is linked to a Campaign and has a correlated Concurrency Token
    that provides is-atomicity across the Campaign + all BudgetAdjustment records.
    All Campaigns with the same concurrency token operate in "isolation mode" - they cannot
    see each other's adjustments, ignore their own, and never compromise each other's persistence.
    No two campaigns on the same budget owner can have the same concurrency token at the same time.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        EXECUTED = "EXECUTED", "Executed"
        ROLLED_BACK = "ROLLED_BACK", "Rolled back"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        related_name="budget_adjustments",
        on_delete=models.CASCADE,
    )

    # Unique concurrency token per Campaign + all adjustments for that Campaign
    concurrency_token = models.UUIDField(
        unique=True,
        help_text="Correlated token with Campaign that marks the isolation boundary",
    )

    class TriggerType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        AUTO_CPA_SPIKE = "AUTO_CPA_SPIKE", "Automatic CPA spike"
        AUTO_ROAS_DROP = "AUTO_ROAS_DROP", "Automatic ROAS drop"
        AUTO_SCHEDULE = "AUTO_SCHEDULE", "Automatic schedule"

    trigger_type = models.CharField(
        max_length=20,
        choices=TriggerType.choices,
        default=TriggerType.MANUAL,
    )
    reason = models.TextField(blank=True, default="")
    lock_token = models.CharField(max_length=255, null=True, blank=True)

    # Source of the adjustment - determines identity of the default account
    source = models.CharField(
        max_length=50,
        help_text=(
            "Determines the default account for calculation. "
            "Map: SOURCE_SPEND_HOUSE_CORR_ACCOUNTS → correlating House Account Log entries, "
            "SOURCE_COMP_PERFORMANCE_KPI → compersion based on performance executed under kpi-based thresholds."
        ),
    )

    # Adjustment type - how we interpret `new_budget`
    adjustment_type = models.CharField(
        max_length=50,
        help_text=(
            "Interpretation of `new_budget` field. "
            "Map: TYPE_ABSOLUTE → absolute dollar amount applied to daily budget; "
            "TYPE_PERCENT → percentage delta applied to existing daily_budget."
        ),
    )

    # The computed new budget amount
    new_budget = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )

    # Original budget value before adjustment (for audit and rollback)
    original_budget = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )

    # Idempotency key used when creating the Deployment
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Idempotency key used while creating the Deployment that triggered this adjustment. "
            "Required: used in query filters. Setting allows idempotency: "
            "platform_idempotency_key, campaign_idempotency_key, or a client supplied request key."
        ),
    )

    # The computed change and percentage deltas
    budget_change = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )

    # Percentage delta relative to original campaign daily budget
    percent_delta = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )

    platform_idempotency_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "Idempotency key of the PlatformDeployment that triggered this adjustment. "
            "Required when source is SOURCE_PLATFORM_DEPLOYMENT or SOURCE_COMP_PERFORMANCE_KPI. "
            "If null, we assume the adjustment came from a direct Campaign action (SOURCE_SPEND_HOUSE_CORR_ACCOUNTS)."
        ),
    )

    campaign_idempotency_key = models.CharField(
        max_length=255,
        help_text=(
            "Idempotency key of the Campaign; used to query deployments belonging to the campaign. "
            "Required for SOURCE_COMP_PERFORMANCE_KPI."
        ),
    )

    # Computed default account and its rationale
    default_account = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "Default account identifier: 'house_correlation.RealAcc' or 'performance_task.Mission.get_account_id()'."
        ),
    )

    # Abstract defaults applied to the Campaign's daily budget
    # 변경된 가격의 총합이 positive한지 negative한지 점검하는 로직이 설정되기도 함.
    change_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Summary of abstract defaults applied: "
            "{default_accounts: {account_id: {'ratio', 'neg', 'idx_inc', 'apply', 'abs_chg', 'abs_chg'}}}"
        ),
    )

    # Approval and audit info
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    approved_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_adjustments",
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    requested_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_adjustments",
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    rejection_reason = models.TextField(null=True, blank=True)

    audit_log = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Changes to the Adjustment fields (e.g., status/debitor/creditor)".lower()
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-requested_at",)

        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["source"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["concurrency_token", "status"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(source__in=["SOURCE_SPEND_HOUSE_CORR_ACCOUNTS", "SOURCE_PLATFORM_DEPLOYMENT", "SOURCE_COMP_PERFORMANCE_KPI"]),
                name="budget_adjustment_source_valid",
            ),
            models.CheckConstraint(
                condition=Q(adjustment_type__in=["TYPE_ABSOLUTE", "TYPE_PERCENT"]),
                name="budget_adjustment_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=("PENDING", "APPROVED", "REJECTED", "EXECUTED", "ROLLED_BACK")
                ),
                name="budget_adjustment_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    trigger_type__in=("MANUAL", "AUTO_CPA_SPIKE", "AUTO_ROAS_DROP", "AUTO_SCHEDULE")
                ),
                name="budget_adjustment_trigger_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        # Auto-compute budget_change and percent_delta on first save
        if (
            self._state.adding
            and self.new_budget is not None
            and self.original_budget is not None
        ):
            change = self.new_budget - self.original_budget
            self.budget_change = change.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            percent = (
                (change / self.original_budget * Decimal("100"))
                if self.original_budget
                else Decimal("0")
            )
            self.percent_delta = percent.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        return super().save(*args, **kwargs)

    def roll_back(self, reason: str = "Budget adjustment rolled back"):
        """Mark adjustment as rolled back via audit flow."""
        if self.status not in (self.Status.APPROVED, self.Status.EXECUTED):
            raise ValueError(f"Can only roll back APPROVED or EXECUTED adjustments, got {self.status}")

        self.status = self.Status.ROLLED_BACK
        self.audit_log.append({
            "action": "ROLLBACK",
            "reason": reason,
            "timestamp": timezone.now().isoformat(),
        })
        self.save()

    @property
    def old_budget(self):
        """Alias the Phase 3 audit field to the existing original-budget column."""
        return self.original_budget

    @old_budget.setter
    def old_budget(self, value):
        self.original_budget = value

    def to_dict(self) -> dict:
        """Serialize for external consumers."""
        return {
            "id": str(self.id),
            "campaign_id": str(self.campaign.pk),
            "campaign_name": self.campaign.name,
            "concurrency_token": str(self.concurrency_token),
            "source": self.source,
            "adjustment_type": self.adjustment_type,
            "new_budget": str(self.new_budget),
            "original_budget": str(self.original_budget),
            "budget_change": str(self.budget_change),
            "percent_delta": str(self.percent_delta),
            "platform_idempotency_key": self.platform_idempotency_key,
            "campaign_idempotency_key": self.campaign_idempotency_key,
            "default_account": self.default_account,
            "change_summary": self.change_summary,
            "status": self.status,
            "requested_by": str(self.requested_by.username) if self.requested_by else None,
            "requested_at": self.requested_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "audit_log": self.audit_log,
        }
