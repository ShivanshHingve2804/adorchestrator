# Chaos & Concurrency Verification Results

AdOrchestrator pairs automated multi-threaded database/Redis stress tests with a live Docker Compose Temporal worker crash-recovery harness (`tests/chaos/chaos_test.py`).

---

## 1. Automated Concurrency Suite (PostgreSQL + Redis)

Verified in Docker Compose against live PostgreSQL 16 and Redis 7 as part of the full 39-test suite (`docker compose exec api python manage.py test --verbosity=2`).

| Exercise | Scope | Verified Result | Source |
|---|---|---|---|
| **20-thread concurrent budget race** | 20 threads simultaneously invoke `BudgetService.adjust_budget` on the same campaign | **Passed:** Exactly `1` update succeeded, `19` returned `ConflictError` (`HTTP 409`), `1` immutable `BudgetAdjustment` audit row persisted, final budget matched winner | [`apps/budgets/tests/test_locking.py`](../apps/budgets/tests/test_locking.py) |
| **10x auto vs. manual adjuster races** | 10 independent iterations racing `AUTO_CPA_SPIKE` (`700.0000`) against `MANUAL` (`1200.0000`) | **Passed:** `10/10` iterations produced `1` winner, `1` conflict, exact audit trail match (`original_budget=1000.0000`) | [`apps/budgets/tests/test_race_conditions.py`](../apps/budgets/tests/test_race_conditions.py) |
| **Budget idempotency & retry replay** | Duplicate `idempotency_key` submissions | **Passed:** Replays return existing `BudgetAdjustment` cleanly with zero duplicate ledger mutations | [`apps/budgets/tests/test_idempotency.py`](../apps/budgets/tests/test_idempotency.py) |
| **Temporal workflow retries & saga rollback** | Transient errors + non-retryable `InvalidMediaError` | **Passed:** Exponential retries succeed; terminal validation failure triggers reverse `rollback_campaign` across created deployments | [`workflows/tests/`](../workflows/tests/) |

---

## 2. Live Temporal Worker Crash & Recovery Exercise

`tests/chaos/chaos_test.py` runs end-to-end against the full 10-container stack (Django API, PostgreSQL, Redis, RabbitMQ, Temporal Server, Temporal Worker, Celery Worker, Celery Beat, Mock Platforms):

1. Creates a campaign + creative and fires `POST /api/campaigns/{id}/bulk_launch/` across `["META", "GOOGLE", "TIKTOK"]`.
2. Waits `0.2s` into execution, sends **`SIGKILL` (`docker compose kill -s SIGKILL temporal-worker`)** mid-flight, pauses `3s`, then restarts `temporal-worker`.
3. Polls `GET /api/campaigns/{id}/launch-status/` until terminal workflow completion and checks all persisted deployment idempotency keys for uniqueness.

### Recorded Live Run (2026-11-25)

| Metric | Observed Result |
|---|---|
| Final workflow status | `COMPLETED` |
| Platform deployments (`META`, `GOOGLE`, `TIKTOK`) | `['ACTIVE', 'ACTIVE', 'ACTIVE']` |
| Deployment rows persisted | `3` |
| Duplicate idempotency keys | `0` |
| Output summary | `Worker recovery result: ('COMPLETED', ['ACTIVE', 'ACTIVE', 'ACTIVE']); deployment rows=3; duplicate keys=0` |

### Live Celery Anomaly Auto-Adjustment Race (2026-11-25)

Running `detect_anomalies` across 25,000 seeded ad events simultaneously fired both `ROAS_DROP` and `CPA_SPIKE` remediation tasks on the same campaign:
- Worker 1 acquired `budget_lock:{campaign_id}` and cut daily budget `250.0000 -> 200.0000` (`EXECUTED`).
- Worker 2 caught `ConflictError` while Worker 1 held the lock, backed off and retried, then sequentially applied `200.0000 -> 140.0000` (`EXECUTED`).

---

## How to Reproduce

### Development Stack
```bash
docker compose up -d
python tests/chaos/chaos_test.py
```

### Production-Style Stack
`docker-compose.prod.yml` enables API authentication (`SessionAuthentication` / `BasicAuthentication`). After copying `.env.prod.example` to `.env.prod` and replacing placeholders:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api python manage.py migrate --noinput
```
Run `tests/chaos/chaos_test.py` with authenticated credentials or adjust `BASE_URL` for your configured reverse proxy.
