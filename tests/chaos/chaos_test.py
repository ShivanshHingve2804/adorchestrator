"""Manual integration exercise: kill/restart the Temporal worker during a bulk launch."""
import os
import subprocess
import time
import uuid

import httpx


def compose(*args):
    subprocess.run(["docker", "compose", *args], check=True)


def main():
    base = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    with httpx.Client(base_url=base, timeout=15) as client:
        key = f"chaos-{uuid.uuid4()}"
        response = client.post("/api/campaigns/", json={
            "name": "Temporal worker recovery exercise",
            "daily_budget": "100.0000",
            "total_budget": "1000.0000",
            "idempotency_key": key,
        })
        response.raise_for_status()
        campaign_id = response.json()["id"]
        creative = client.post(f"/api/campaigns/{campaign_id}/creatives/", json={
            "name": "Recovery creative", "media_type": "IMAGE",
            "media_url": "https://cdn.example.test/recovery.jpg",
        })
        creative.raise_for_status()
        launch = client.post(f"/api/campaigns/{campaign_id}/bulk_launch/", json={
            "platforms": ["META", "GOOGLE", "TIKTOK"], "idempotency_key": key,
        })
        launch.raise_for_status()

        time.sleep(float(os.environ.get("CHAOS_KILL_AFTER_SECONDS", "0.2")))
        compose("kill", "-s", "SIGKILL", "temporal-worker")
        time.sleep(float(os.environ.get("CHAOS_PAUSE_SECONDS", "3")))
        compose("up", "-d", "temporal-worker")

        deadline = time.monotonic() + float(os.environ.get("CHAOS_TIMEOUT_SECONDS", "300"))
        last_status = None
        while time.monotonic() < deadline:
            status_response = client.get(f"/api/campaigns/{campaign_id}/launch-status/")
            status_response.raise_for_status()
            data = status_response.json()
            deployments = data["deployments"]
            keys = [item["idempotency_key"] for item in deployments]
            if len(keys) != len(set(keys)):
                raise SystemExit(f"Duplicate deployment keys detected: {keys}")
            last_status = (data.get("workflow_status"), [item["status"] for item in deployments])
            if len(deployments) == 3 and all(item["status"] in {"ACTIVE", "FAILED", "ROLLED_BACK"} for item in deployments):
                print(f"Worker recovery result: {last_status}; deployment rows={len(deployments)}; duplicate keys=0")
                return
            time.sleep(2)
        raise SystemExit(f"Workflow did not finish before timeout; last status={last_status}")


if __name__ == "__main__":
    main()
