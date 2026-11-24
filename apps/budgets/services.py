import uuid
from decimal import Decimal

import redis
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F

from apps.campaigns.models import Campaign

from .models import BudgetAdjustment


class ConflictError(Exception):
    """Raised when another budget adjustment currently owns the campaign lock."""


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

    @classmethod
    def adjust_budget(cls, campaign_id, new_budget, trigger_type, reason, idempotency_key=None):
        if idempotency_key:
            previous = BudgetAdjustment.objects.filter(idempotency_key=idempotency_key).first()
            if previous is not None:
                return previous

        lock_token = uuid.uuid4().hex
        lock_key = f"budget_lock:{campaign_id}"
        redis_client = cls._redis_client()
        try:
            acquired = redis_client.set(
                lock_key,
                lock_token,
                nx=True,
                ex=cls.LOCK_TTL_SECONDS,
            )
        except redis.RedisError as exc:
            raise ConflictError("Budget lock service is unavailable.") from exc
        if not acquired:
            raise ConflictError("Another budget adjustment is in progress for this campaign.")

        try:
            try:
                with transaction.atomic():
                    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
                    if idempotency_key:
                        previous = BudgetAdjustment.objects.filter(idempotency_key=idempotency_key).first()
                        if previous is not None:
                            return previous

                    old_budget = campaign.daily_budget
                    new_budget = Decimal(str(new_budget)).quantize(Decimal("0.0001"))
                    campaign.daily_budget = new_budget
                    campaign.version = F("version") + 1
                    campaign.save(update_fields=["daily_budget", "version", "updated_at"])
                    campaign.refresh_from_db(fields=["daily_budget", "version"])

                    adjustment = BudgetAdjustment.objects.create(
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
                    return adjustment
            except IntegrityError:
                if idempotency_key:
                    previous = BudgetAdjustment.objects.filter(idempotency_key=idempotency_key).first()
                    if previous is not None:
                        return previous
                raise
        finally:
            try:
                redis_client.eval(cls._RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)
            except redis.RedisError:
                # The lock has a short TTL; Redis owns expiry if release is unavailable.
                pass
