# Chaos Test Results

## Test available

`tests/chaos/chaos_test.py` creates a campaign with three platform deployments, starts its Temporal workflow, sends SIGKILL to the Temporal worker, waits briefly, restarts it, and polls the launch status. It checks that the workflow reaches a terminal state and that persisted deployment idempotency keys are unique.

Run against a running full Compose stack:

```powershell
Copy-Item .env.prod.example .env.prod
# Replace all secrets/host values, then start the production-style stack.
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api python manage.py migrate --noinput
python tests/chaos/chaos_test.py
```

## Results

| Exercise | Result | Evidence |
|---|---|---|
| 20 simultaneous budget updates | Passed: 1 update succeeded, 19 conflicted, one audit row | Phase 3 test output in `reports/phase_3_report.md` |
| Ten simultaneous auto/manual budget races | Passed in the Phase 3 suite | Phase 3 test output in `reports/phase_3_report.md` |
| Kill and restart the Temporal worker during an actual platform launch | Not run in this environment | The integration script is ready; no full Temporal/mock-platform stack was started for this run |

The actual worker-kill result must be recorded after running the integration exercise on a configured full stack. No live recovery result is claimed here.
