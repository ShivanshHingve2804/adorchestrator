import http from 'k6/http';
import { check, sleep } from 'k6';

const base = __ENV.BASE_URL || 'http://localhost:8000';

export const options = {
  scenarios: { api_load: { executor: 'constant-vus', vus: Number(__ENV.VUS || 25), duration: __ENV.DURATION || '1m' } },
  thresholds: { http_req_duration: ['p(95)<500'], checks: ['rate>0.95'] },
};

export function setup() {
  const campaignResponse = http.post(`${base}/api/campaigns/`, JSON.stringify({
    name: `k6 campaign ${Date.now()}`,
    daily_budget: '250.0000',
    total_budget: '5000.0000',
  }), { headers: { 'Content-Type': 'application/json' } });
  check(campaignResponse, { 'campaign created': (r) => r.status === 201 });
  const campaignId = campaignResponse.json('id');
  const creativeResponse = http.post(`${base}/api/campaigns/${campaignId}/creatives/`, JSON.stringify({
    name: 'k6 creative', media_type: 'IMAGE', media_url: 'https://cdn.example.test/k6.jpg',
  }), { headers: { 'Content-Type': 'application/json' } });
  check(creativeResponse, { 'creative created': (r) => r.status === 201 });
  return { campaignId };
}

export default function (data) {
  const key = `k6-${__VU}-${__ITER}`;
  const response = http.post(
    `${base}/api/budgets/campaigns/${data.campaignId}/adjust-budget/`,
    JSON.stringify({ new_budget: '300.0000', trigger_type: 'MANUAL', reason: 'k6 load test', idempotency_key: key }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  check(response, { 'budget result is success or expected lock conflict': (r) => r.status === 200 || r.status === 409 });
  sleep(0.1);
}
