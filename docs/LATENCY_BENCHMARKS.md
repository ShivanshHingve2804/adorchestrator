# Latency Benchmarks

## Reporting service cache

| Run | Request | Samples | p95 | Target |
|---|---|---:|---:|---:|
| 2026-11-24 local Docker test database | Warm `ReportingService.get_campaign_report()` cache reads | 30 | 0.19 ms | < 200 ms |

The measurement is for the warmed service call with Redis cache, not the full HTTP stack or a production-sized database. The test warms the cache once, times 30 reads, and asserts p95 below 200 ms. Cold materialized-view refresh and database query timings are not included.

Run it with:

```powershell
docker compose run --no-deps --rm api python manage.py test apps.analytics.tests.test_latency --verbosity=2 --noinput
```

Use the Locust and k6 scripts under `tests/load/` to benchmark HTTP behavior against the full stack. Record machine size, event count, cache state, worker count, and p50/p95/p99 when adding a production result.
