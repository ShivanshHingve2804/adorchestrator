# AdOrchestrator REST API Reference

Base URL (local Compose): `http://localhost:8000`

> **Authentication note:** Development settings allow unauthenticated local testing with DRF's browsable API enabled. Production settings (`adorchestrator.settings.prod`) enforce `IsAuthenticated` (`SessionAuthentication` and `BasicAuthentication`).

---

## Campaigns & Bulk Orchestration

### `GET /api/campaigns/`
List paginated campaigns (page size: `20`).

### `POST /api/campaigns/`
Create a campaign. Optional `idempotency_key` prevents duplicate creation.

**Request:**
```json
{
  "name": "Q4 Launch — US",
  "daily_budget": "250.0000",
  "total_budget": "5000.0000",
  "currency": "USD",
  "idempotency_key": "camp-q4-us-001",
  "targeting": { "country": "US", "age_min": 21 }
}
```

### `GET /api/campaigns/{id}/` | `PUT /api/campaigns/{id}/` | `PATCH /api/campaigns/{id}/`
Retrieve or update a campaign.

### `GET /api/campaigns/{campaign_id}/creatives/` | `POST /api/campaigns/{campaign_id}/creatives/`
List or attach image/video creatives to a campaign.

**Request (`POST`):**
```json
{
  "name": "Hero Video V1",
  "media_type": "VIDEO",
  "media_url": "https://cdn.example.test/hero-v1.mp4",
  "thumbnail_url": "https://cdn.example.test/hero-v1-thumb.jpg",
  "metadata": { "duration_seconds": 15 }
}
```
Supported `media_type` values: `IMAGE`, `VIDEO`.

### `POST /api/campaigns/{id}/bulk_launch/`
Launch all campaign creatives asynchronously across selected ad platforms via a Temporal `BulkCampaignLaunchWorkflow`. Creates deterministic per-deployment idempotency keys (`{idempotency_key}:{platform}:{creative_id}`).

**Request:**
```json
{
  "platforms": ["META", "GOOGLE", "TIKTOK"],
  "idempotency_key": "launch-2026-11-25-001"
}
```
- **202 Accepted:** Returns `campaign_id`, `workflow_id`, and `deployments`. Repeating the same `idempotency_key` returns the existing deployments without starting a second workflow.
- **400 Bad Request:** Returned when the campaign has no creatives or duplicate platforms are supplied.
- **503 Service Unavailable:** Returned if the Temporal cluster cannot start the workflow (records `LAUNCH_FAILURE` alerts).

### `GET /api/campaigns/{id}/launch-status/`
Inspect combined campaign status, live Temporal workflow status, and per-platform `PlatformDeployment` states (`PENDING`, `UPLOADING`, `CREATING`, `BUDGETING`, `ACTIVE`, `FAILED`, `ROLLED_BACK`).

---

## Distributed Budget Control

### `POST /api/budgets/campaigns/{campaign_id}/adjust-budget/`
Atomically adjust a campaign's `daily_budget` using two-layer locking (Redis `SET NX EX` distributed lease + PostgreSQL `SELECT ... FOR UPDATE`), optimistic `version` increment, and immutable `BudgetAdjustment` audit logging.

**Request:**
```json
{
  "new_budget": "400.0000",
  "trigger_type": "MANUAL",
  "reason": "Reallocating spend to top ROAS segment",
  "idempotency_key": "budget-adj-001"
}
```
Supported `trigger_type` values: `MANUAL`, `AUTO_CPA_SPIKE`, `AUTO_ROAS_DROP`.

- **200 OK:** Budget updated (or replayed via `idempotency_key`), returning the `BudgetAdjustment` record with `original_budget` / `old_budget`, `new_budget`, `budget_change`, `percent_delta`, and `lock_token`.
- **400 Bad Request:** Returned when `new_budget` is negative or exceeds `total_budget`.
- **409 Conflict:** Returned when another concurrent writer holds `budget_lock:{campaign_id}` or an `idempotency_key` is reused with conflicting parameters.
- **503 Service Unavailable:** Returned when the Redis distributed lock backend is unreachable.

### `GET /api/budgets/campaigns/{campaign_id}/budget-history/`
Return the reverse-chronological `BudgetAdjustment` audit log for the campaign.

---

## Analytics & Anomaly Alerts

### `GET /api/analytics/campaigns/{campaign_id}/report/?days=7`
Fetch daily per-platform performance (`impressions`, `clicks`, `conversions`, `spend`, `revenue`, `ctr`, `cpa`, `roas`) from the PostgreSQL materialized view `analytics_mv_campaign_daily_perf`, cached in Redis for 5 minutes.
- Query param `days`: integer from `1` to `90` (default `7`).

### `GET /api/analytics/alerts/`
List up to 100 alerts ordered by creation time. Supports optional filters:
- `campaign_id=<uuid>`
- `acknowledged=true|false`

Alert types include `CPA_SPIKE`, `ROAS_DROP`, `BUDGET_EXHAUSTED`, and `LAUNCH_FAILURE`.

### `POST /api/analytics/alerts/{alert_id}/acknowledge/`
Idempotently mark an alert as acknowledged (`acknowledged: true`).

---

## Creative AI Analysis

### `POST /api/creative-ai/creatives/{creative_id}/analyze/`
Enqueue asynchronous visual feature extraction via Celery (`workers.tasks.creative_ai.analyze_creative`).

- **202 Accepted:** Returns `creative_id`, `task_id`, and `status: "QUEUED"`.

### `GET /api/creative-ai/creatives/{creative_id}/features/`
List extracted `CreativeFeature` records (stored with provider, model, confidence, and feature key/value metadata).

### `GET /api/creative-ai/summaries/latest/`
Return the most recent `WeeklySummary` correlating creative traits with `CTR`, `CPA`, and `ROAS`. Returns `404` if no summary has been generated yet.
