from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import redis
from django.conf import settings
from django.db import connections

from apps.budgets.services import BudgetService, ConflictError


class SynchronizedRedisClient:
    """Make every worker attempt SET before any caller proceeds past lock acquisition."""

    def __init__(self, parties):
        self.client = redis.Redis.from_url(settings.CACHES["default"]["LOCATION"])
        self.barrier = Barrier(parties)

    def set(self, *args, **kwargs):
        self.barrier.wait(timeout=10)
        result = self.client.set(*args, **kwargs)
        self.barrier.wait(timeout=10)
        return result

    def eval(self, *args, **kwargs):
        return self.client.eval(*args, **kwargs)


def concurrent_adjustments(campaign_id, requests):
    redis_client = SynchronizedRedisClient(len(requests))

    def adjust(request):
        budget, trigger, key = request
        try:
            result = BudgetService.adjust_budget(
                campaign_id=campaign_id,
                new_budget=budget,
                trigger_type=trigger,
                reason="concurrent test adjustment",
                idempotency_key=key,
            )
            return ("success", budget, result)
        except ConflictError as exc:
            return ("conflict", budget, str(exc))
        finally:
            # Django keeps one connection per worker thread unless explicitly closed.
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        with patch.object(BudgetService, "_redis_client", return_value=redis_client):
            return list(executor.map(adjust, requests))
