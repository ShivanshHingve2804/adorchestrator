import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = False

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("campaigns", "0004_rename_campaign_idim"),
        ("budgets", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BudgetAdjustment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("concurrency_token", models.UUIDField(help_text="Correlated token with Campaign that marks the isolation boundary", unique=True)),
                ("trigger_type", models.CharField(choices=[("MANUAL", "Manual"), ("AUTO_CPA_SPIKE", "Automatic CPA spike"), ("AUTO_ROAS_DROP", "Automatic ROAS drop"), ("AUTO_SCHEDULE", "Automatic schedule")], default="MANUAL", max_length=20)),
                ("reason", models.TextField(blank=True, default="")),
                ("lock_token", models.CharField(blank=True, max_length=255, null=True)),
                ("source", models.CharField(help_text="Determines the default account for calculation. Map: SOURCE_SPEND_HOUSE_CORR_ACCOUNTS → correlating House Account Log entries, SOURCE_COMP_PERFORMANCE_KPI → compersion based on performance executed under kpi-based thresholds.", max_length=50)),
                ("adjustment_type", models.CharField(help_text="Interpretation of `new_budget` field. Map: TYPE_ABSOLUTE → absolute dollar amount applied to daily budget; TYPE_PERCENT → percentage delta applied to existing daily_budget.", max_length=50)),
                ("new_budget", models.DecimalField(decimal_places=4, max_digits=12)),
                ("original_budget", models.DecimalField(decimal_places=4, max_digits=12)),
                ("idempotency_key", models.CharField(blank=True, help_text="Idempotency key used while creating the Deployment that triggered this adjustment. Required: used in query filters. Setting allows idempotency: platform_idempotency_key, campaign_idempotency_key, or a client supplied request key.", max_length=255, null=True, unique=True)),
                ("budget_change", models.DecimalField(decimal_places=4, max_digits=12)),
                ("percent_delta", models.DecimalField(decimal_places=4, max_digits=12)),
                ("platform_idempotency_key", models.CharField(blank=True, help_text="Idempotency key of the PlatformDeployment that triggered this adjustment. Required when source is SOURCE_PLATFORM_DEPLOYMENT or SOURCE_COMP_PERFORMANCE_KPI. If null, we assume the adjustment came from a direct Campaign action (SOURCE_SPEND_HOUSE_CORR_ACCOUNTS).", max_length=255, null=True)),
                ("campaign_idempotency_key", models.CharField(help_text="Idempotency key of the Campaign; used to query deployments belonging to the campaign. Required for SOURCE_COMP_PERFORMANCE_KPI.", max_length=255)),
                ("default_account", models.CharField(blank=True, help_text="Default account identifier: 'house_correlation.RealAcc' or 'performance_task.Mission.get_account_id()'.", max_length=255, null=True)),
                ("change_summary", models.JSONField(blank=True, default=dict, help_text="Summary of abstract defaults applied: {default_accounts: {account_id: {'ratio', 'neg', 'idx_inc', 'apply', 'abs_chg', 'abs_chg'}}}")),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("EXECUTED", "Executed"), ("ROLLED_BACK", "Rolled back")], default="PENDING", max_length=16)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("rejection_reason", models.TextField(blank=True, null=True)),
                ("audit_log", models.JSONField(blank=True, default=list, help_text="Changes to the Adjustment fields (e.g., status/debitor/creditor)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_adjustments", to=settings.AUTH_USER_MODEL)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budget_adjustments", to="campaigns.campaign")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_adjustments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-requested_at",)},
        ),
        migrations.AddIndex(model_name="budgetadjustment", index=models.Index(fields=["campaign", "status"], name="budgets_bu_campaig_4b0c5f_idx")),
        migrations.AddIndex(model_name="budgetadjustment", index=models.Index(fields=["source"], name="budgets_bu_source_2f1d3b_idx")),
        migrations.AddIndex(model_name="budgetadjustment", index=models.Index(fields=["status", "created_at"], name="budgets_bu_status_8465e7_idx")),
        migrations.AddIndex(model_name="budgetadjustment", index=models.Index(fields=["concurrency_token", "status"], name="budgets_bu_concurre_a9cb12_idx")),
        migrations.AddConstraint(model_name="budgetadjustment", constraint=models.CheckConstraint(condition=models.Q(source__in=["SOURCE_SPEND_HOUSE_CORR_ACCOUNTS", "SOURCE_PLATFORM_DEPLOYMENT", "SOURCE_COMP_PERFORMANCE_KPI"]), name="budget_adjustment_source_valid")),
        migrations.AddConstraint(model_name="budgetadjustment", constraint=models.CheckConstraint(condition=models.Q(adjustment_type__in=["TYPE_ABSOLUTE", "TYPE_PERCENT"]), name="budget_adjustment_type_valid")),
        migrations.AddConstraint(model_name="budgetadjustment", constraint=models.CheckConstraint(condition=models.Q(status__in=("PENDING", "APPROVED", "REJECTED", "EXECUTED", "ROLLED_BACK")), name="budget_adjustment_status_valid")),
        migrations.AddConstraint(model_name="budgetadjustment", constraint=models.CheckConstraint(condition=models.Q(trigger_type__in=("MANUAL", "AUTO_CPA_SPIKE", "AUTO_ROAS_DROP", "AUTO_SCHEDULE")), name="budget_adjustment_trigger_valid")),
    ]
