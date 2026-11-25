# Latency Benchmarks

All measurements below reflect observed execution in the local Docker Compose environment (PostgreSQL 16 + Redis 7).

---

## 1. Seeded Dataset Analytics Query Latency (25,000 Events)

Seeded `3` campaigns and `25,000` `AdEvent` rows (`scripts/seed_ad_events.py --count 25000`), refreshed `analytics_mv_campaign_daily_perf` (`546` materialized rows across campaigns/creatives/days), and measured `ReportingService.get_campaign_report(campaign_id, days=7)` returning `21` grouped daily/platform rows:

| Path | Cache State | Measured Latency | Target |
|---|---|---:|---:|
| Materialized View SQL aggregation | **Cold** (cache miss) | **1.26 ms** | < 200 ms |
| Redis cached report lookup | **Warm** (cache hit) | **0.21 ms** | < 200 ms |

---

## 2. Automated Suite Latency Test (30-Sample p95)

`apps/analytics/tests/test_latency.py` warms `ReportingService.get_campaign_report()` once, executes 30 consecutive cached reads, and asserts `p95 < 200 ms`:

| Run | Operation | Samples | p95 Latency | Target | Status |
|---|---|---:|---:|---:|---|
| 2026-11-24 Docker test DB | Warm `ReportingService.get_campaign_report()` | 30 | **0.19 ms** | < 200 ms | Passed |
| 2026-11-25 Full 39-test Docker run | Warm `ReportingService.get_campaign_report()` | 30 | **0.38 ms** | < 200 ms | Passed |

> **Scope note:** These timings measure service-layer execution (SQL materialized view read + Redis lookup) rather than end-to-end HTTP load over network.

Run the automated latency test locally:
```bash
docker compose exec api python manage.py test apps.analytics.tests.test_latency --verbosity=2 --noinput
```

---

## 3. High-Volume Seeding & Load Testing

Scale synthetic event generation up to 5,000,000+ rows using chunked batch inserts (`batch_size=5000`) and run HTTP load profiles with Locust or k6:

```bash
# Seed 5M synthetic AdEvents (default) or customize --count
docker compose exec api python scripts/seed_ad_events.py --count 5000000

# Locust HTTP load profile (budget races + idempotent bulk launches)
cd tests/load && locust -f locustfile.py --host=http://localhost:8000

# k6 constant-VU load test (p95 < 500ms HTTP threshold)
k6 run tests/load/k6_script.js
```

When benchmarking production infrastructure, record host CPU/RAM, event count, Redis hit rate, Gunicorn/worker count, and HTTP `p50`/`p95`/`p99`.
