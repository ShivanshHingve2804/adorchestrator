from decimal import Decimal, InvalidOperation
import uuid

import redis
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F

from apps.campaigns.models import Campaign

from .models import BudgetAdjustment


class ConflictError(Exception):
    """Raised when another budget adjustment owns the campaign lock or an idempotency key collides."""


class LockUnavailableError(Exception):
    """Raised when the Redis distributed lock backend cannot be reached."""


class BudgetValidationError(Exception):
    """Raised when a requested budget value or multiplier violates domain constraints."""


class CampaignNotFoundError(Exception):
    """Raised when the target campaign does not exist."""


class BudgetService:
    LOCK_TTL_SECONDS = 10
    _RELEASE_LOCK_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """

    @staticmethod
    def _redis_client():
        return redis.Redis.from_url(settings.CACHES["default"]["LOCATION"])

    @staticmethod
    def _source_for_trigger(trigger_type):
        if trigger_type in ("AUTO_CPA_SPIKE", "AUTO_ROAS_DROP"):
            return "SOURCE_COMP_PERFORMANCE_KPI"
        return "SOURCE_SPEND_HOUSE_CORR_ACCOUNTS"

    @staticmethod
    def _parse_decimal(raw_value, label):
        try:
            return Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise BudgetValidationError(f"Invalid decimal value for {label}.") from exc

    @staticmethod
    def _validate_idempotent_replay(previous, campaign_id, trigger_type, expected_budget=None):
        if str(previous.campaign_id) != str(campaign_id) or previous.trigger_type != trigger_type:
            raise ConflictError("Idempotency key already used for a different campaign or trigger.")
        if expected_budget is not None and previous.new_budget != expected_budget:
            raise ConflictError("Idempotency key already used with a different budget amount.")
        return previous

    @classmethod
    def _execute_locked_adjustment(
        cls,
        campaign_id,
        compute_budget,
        trigger_type,
        reason,
        idempotency_key=None,
        expected_budget=None,
    ):
        """Serialize budget updates per campaign using Redis NX lease plus SELECT FOR UPDATE."""
        if idempotency_key:
            previous = BudgetAdjustment.objects.filter(idempotency_key=idempotency_key).first()
            if previous is not None:
                return cls._validate_idempotent_replay(previous, campaign_id, trigger_type, expected_budget)

        lock_token = uuid.uuid4().hex
        lock_key = f"budget_lock:{campaign_id}"
        redis_client = cls._redis_client()
        try:
            acquired = redis_client.set(lock_key, lock_token, nx=True, ex=cls.LOCK_TTL_SECONDS)
        except redis.RedisError as exc:
            raise LockUnavailableError("Budget lock service is unavailable.") from exc
        if not acquired:
            raise ConflictError("Another budget adjustment is in progress for this campaign.")

        try:
            try:
                with transaction.atomic():
                    try:
                        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
                    except Campaign.DoesNotExist as exc:
                        raise CampaignNotFoundError("Campaign not found.") from exc

                    if idempotency_key:
                        previous = BudgetAdjustment.objects.filter(idempotency_key=idempotency_key).first()
                        if previous is not None:
                            return cls._validate_idempotent_replay(
                                previous, campaign_id, trigger_type, expected_budget
                            )

                    old_budget = campaign.daily_budget
                    new_budget = compute_budget(campaign).quantize(Decimal("0.0001"))
                    if new_budget < Decimal("0"):
                        raise BudgetValidationError("Daily budget cannot be negative.")
                    if campaign.total_budget is not None and new_budget > campaign.total_budget:
                        raise BudgetValidationError("Daily budget cannot exceed total campaign budget.")

                    campaign.daily_budget = new_budget
                    campaign.version = F("version") + 1
                    campaign.save(update_fields=["daily_budget", "version", "updated_at"])
                    campaign.refresh_from_db(fields=["daily_budget", "version"])

                    return BudgetAdjustment.objects.create(
                        campaign=campaign,
                        concurrency_token=uuid.uuid4(),
                        source=cls._source_for_trigger(trigger_type),
                        adjustment_type="TYPE_ABSOLUTE",
                        trigger_type=trigger_type,
                        new_budget=new_budget,
                        original_budget=old_budget,
                        reason=reason,
                        lock_token=lock_token,
                        idempotency_key=idempotency_key,
                        budget_change=new_budget - old_budget,
                        percent_delta=(
                            (new_budget - old_budget) / old_budget * Decimal("100")
                            if old_budget
                            else Decimal("0")
                        ),
                        campaign_idempotency_key=campaign.idempotency_key or str(campaign.pk),
                        status=BudgetAdjustment.Status.EXECUTED,
                    )
            except IntegrityError:
                if idempotency_key:
                    previous = BudgetAdjustment.objects.filter(idempotency_key=idempotency_key).first()
                    if previous is not None:
                        return cls._validate_idempotent_replay(
                            previous, campaign_id, trigger_type, expected_budget
                        )
                raise
        finally:
            try:
                redis_client.eval(cls._RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)
            except redis.RedisError:
                # Lease carries a short TTL; avoid masking domain results if Redis fails on release.
                pass

    @classmethod
    def adjust_budget(cls, campaign_id, new_budget, trigger_type, reason, idempotency_key=None):
        target = cls._parse_decimal(new_budget, "new_budget").quantize(Decimal("0.0001"))
        if target < Decimal("0"):
            raise BudgetValidationError("Daily budget cannot be negative.")
        return cls._execute_locked_adjustment(
            campaign_id=campaign_id,
            compute_budget=lambda _campaign: target,
            trigger_type=trigger_type,
            reason=reason,
            idempotency_key=idempotency_key,
            expected_budget=target,
        )

    @classmethod
    def scale_budget(cls, campaign_id, multiplier, trigger_type, reason, idempotency_key=None):
        """Scale current daily_budget inside the row lock to avoid stale percentage reads."""
        factor = cls._parse_decimal(multiplier, "multiplier")
        if factor <= Decimal("0"):
            raise BudgetValidationError("Budget multiplier must be positive.")
        return cls._execute_locked_adjustment(
            campaign_id=campaign_id,
            compute_budget=lambda campaign: campaign.daily_budget * factor,
            trigger_type=trigger_type,
            reason=reason,
            idempotency_key=idempotency_key,
        )
