"""
Mock Ad Platform APIs — FastAPI server simulating Meta, TikTok, Google Ads APIs.
Includes chaos injection for realistic failure testing.
"""
import random
import asyncio
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from functools import wraps
import os

app = FastAPI(title="Mock Ad Platforms", version="1.0.0")

# --- Chaos Configuration ---
CHAOS_CONFIG = {
    "rate_limit_pct": float(os.environ.get("CHAOS_RATE_LIMIT_PCT", 0.15)),
    "server_error_pct": float(os.environ.get("CHAOS_SERVER_ERROR_PCT", 0.08)),
    "timeout_pct": float(os.environ.get("CHAOS_TIMEOUT_PCT", 0.05)),
    "partial_failure_pct": float(os.environ.get("CHAOS_PARTIAL_FAILURE_PCT", 0.05)),
}


def chaos_middleware(func):
    """Decorator that injects realistic ad platform failures."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        roll = random.random()
        cumulative = 0.0

        cumulative += CHAOS_CONFIG["rate_limit_pct"]
        if roll < cumulative:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Retry after 5 seconds.",
                headers={"Retry-After": "5"},
            )

        cumulative += CHAOS_CONFIG["server_error_pct"]
        if roll < cumulative:
            raise HTTPException(status_code=500, detail="Internal server error.")

        cumulative += CHAOS_CONFIG["timeout_pct"]
        if roll < cumulative:
            await asyncio.sleep(35)
            raise HTTPException(status_code=504, detail="Gateway timeout")

        result = await func(*args, **kwargs)

        if random.random() < CHAOS_CONFIG["partial_failure_pct"]:
            return {
                "status": "error",
                "error_code": "PARTIAL_FAILURE",
                "message": "Campaign created but activation failed",
                "data": result,
            }

        return {"status": "success", "data": result}

    return wrapper


# --- Request/Response Models ---
class ValidateRequest(BaseModel):
    creative_id: str
    media_type: str = "IMAGE"

class UploadRequest(BaseModel):
    creative_id: str
    media_url: str

class CreateCampaignRequest(BaseModel):
    campaign_id: str
    media_id: str
    idempotency_key: str

class SetBudgetRequest(BaseModel):
    platform_campaign_id: str
    daily_budget: float

class ActivateRequest(BaseModel):
    platform_campaign_id: str


# --- Meta Ads API ---
@app.post("/meta/validate-creative")
@chaos_middleware
async def meta_validate(req: ValidateRequest):
    return {"creative_id": req.creative_id, "valid": True, "platform": "META"}

@app.post("/meta/upload-media")
@chaos_middleware
async def meta_upload(req: UploadRequest):
    return {"media_id": f"meta_media_{uuid.uuid4().hex[:8]}", "platform": "META"}

@app.post("/meta/create-campaign")
@chaos_middleware
async def meta_create(req: CreateCampaignRequest):
    return {"platform_campaign_id": f"meta_camp_{uuid.uuid4().hex[:8]}", "platform": "META"}

@app.post("/meta/set-budget")
@chaos_middleware
async def meta_budget(req: SetBudgetRequest):
    return {"platform_campaign_id": req.platform_campaign_id, "budget_set": req.daily_budget}

@app.post("/meta/activate")
@chaos_middleware
async def meta_activate(req: ActivateRequest):
    return {"platform_campaign_id": req.platform_campaign_id, "status": "ACTIVE"}

@app.delete("/meta/campaign/{campaign_id}")
async def meta_rollback(campaign_id: str):
    return {"status": "success", "data": {"campaign_id": campaign_id, "rolled_back": True}}


# --- TikTok Ads API ---
@app.post("/tiktok/validate-creative")
@chaos_middleware
async def tiktok_validate(req: ValidateRequest):
    return {"creative_id": req.creative_id, "valid": True, "platform": "TIKTOK"}

@app.post("/tiktok/upload-media")
@chaos_middleware
async def tiktok_upload(req: UploadRequest):
    return {"media_id": f"tt_media_{uuid.uuid4().hex[:8]}", "platform": "TIKTOK"}

@app.post("/tiktok/create-campaign")
@chaos_middleware
async def tiktok_create(req: CreateCampaignRequest):
    return {"platform_campaign_id": f"tt_camp_{uuid.uuid4().hex[:8]}", "platform": "TIKTOK"}

@app.post("/tiktok/set-budget")
@chaos_middleware
async def tiktok_budget(req: SetBudgetRequest):
    return {"platform_campaign_id": req.platform_campaign_id, "budget_set": req.daily_budget}

@app.post("/tiktok/activate")
@chaos_middleware
async def tiktok_activate(req: ActivateRequest):
    return {"platform_campaign_id": req.platform_campaign_id, "status": "ACTIVE"}

@app.delete("/tiktok/campaign/{campaign_id}")
async def tiktok_rollback(campaign_id: str):
    return {"status": "success", "data": {"campaign_id": campaign_id, "rolled_back": True}}


# --- Google Ads API ---
@app.post("/google/validate-creative")
@chaos_middleware
async def google_validate(req: ValidateRequest):
    return {"creative_id": req.creative_id, "valid": True, "platform": "GOOGLE"}

@app.post("/google/upload-media")
@chaos_middleware
async def google_upload(req: UploadRequest):
    return {"media_id": f"goog_media_{uuid.uuid4().hex[:8]}", "platform": "GOOGLE"}

@app.post("/google/create-campaign")
@chaos_middleware
async def google_create(req: CreateCampaignRequest):
    return {"platform_campaign_id": f"goog_camp_{uuid.uuid4().hex[:8]}", "platform": "GOOGLE"}

@app.post("/google/set-budget")
@chaos_middleware
async def google_budget(req: SetBudgetRequest):
    return {"platform_campaign_id": req.platform_campaign_id, "budget_set": req.daily_budget}

@app.post("/google/activate")
@chaos_middleware
async def google_activate(req: ActivateRequest):
    return {"platform_campaign_id": req.platform_campaign_id, "status": "ACTIVE"}

@app.delete("/google/campaign/{campaign_id}")
async def google_rollback(campaign_id: str):
    return {"status": "success", "data": {"campaign_id": campaign_id, "rolled_back": True}}


# --- Health Check ---
@app.get("/health")
async def health():
    return {"status": "healthy", "chaos_config": CHAOS_CONFIG}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
