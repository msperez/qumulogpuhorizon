from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.models.telemetry import CostReport, DeploymentCostSummary, LifecycleEvent, TelemetryRecord
from src.rules.lifecycle import COST_SAMPLE_INTERVAL_SECONDS, DeploymentTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GPU Horizon Cost & Telemetry",
    description="Lifecycle management, cost tracking, and ephemeral teardown for GPU Horizon deployments.",
    version="0.1.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_trackers: dict[str, DeploymentTracker] = {}
_provisioning_engine_url = "http://provisioning-engine:8002"


class RegisterDeploymentRequest(BaseModel):
    deployment_id: str
    provider: str
    region: str
    workload_profile: str
    cost_per_hour_usd: float
    spoke_cost_per_hour_usd: float
    started_at: datetime
    phase: str
    price_ceiling_usd: Optional[float] = None
    lifetime_hours: Optional[float] = None


async def _trigger_teardown(deployment_id: str, reason: str) -> None:
    """Calls back to provisioning engine to initiate teardown."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.delete(
                f"{_provisioning_engine_url}/api/v1/deployments/{deployment_id}",
                json={"reason": reason},
            )
        logger.info("Teardown triggered for %s: %s", deployment_id, reason)
    except Exception:
        logger.exception("Failed to trigger teardown for %s", deployment_id)


async def _tick_loop() -> None:
    while True:
        await asyncio.sleep(COST_SAMPLE_INTERVAL_SECONDS)
        for tracker in list(_trackers.values()):
            try:
                await tracker.tick()
            except Exception:
                logger.exception("Error ticking tracker %s", tracker.deployment_id)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_tick_loop())


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/v1/cost/register", response_model=DeploymentCostSummary)
async def register_deployment(req: RegisterDeploymentRequest) -> DeploymentCostSummary:
    tracker = DeploymentTracker(
        deployment_id=req.deployment_id,
        provider=req.provider,
        region=req.region,
        workload_profile=req.workload_profile,
        cost_per_hour_usd=req.cost_per_hour_usd,
        spoke_cost_per_hour_usd=req.spoke_cost_per_hour_usd,
        started_at=req.started_at,
        phase=req.phase,
        price_ceiling_usd=req.price_ceiling_usd,
        lifetime_hours=req.lifetime_hours,
        on_teardown=_trigger_teardown,
    )
    _trackers[req.deployment_id] = tracker
    return tracker.summary()


@app.get("/api/v1/cost", response_model=list[DeploymentCostSummary])
async def list_costs() -> list[DeploymentCostSummary]:
    return [t.summary() for t in _trackers.values()]


@app.get("/api/v1/cost/{deployment_id}", response_model=DeploymentCostSummary)
async def get_cost(deployment_id: str) -> DeploymentCostSummary:
    if deployment_id not in _trackers:
        raise HTTPException(status_code=404, detail="Deployment not tracked")
    return _trackers[deployment_id].summary()


@app.get("/api/v1/cost/{deployment_id}/report", response_model=CostReport)
async def get_report(deployment_id: str) -> CostReport:
    if deployment_id not in _trackers:
        raise HTTPException(status_code=404, detail="Deployment not tracked")
    tracker = _trackers[deployment_id]
    summary = tracker.summary()
    runtime_hours = summary.runtime_hours
    total_per_hour = summary.cost_per_hour_usd
    compute_cost = tracker.cost_per_hour_usd * runtime_hours
    spoke_cost = tracker.spoke_cost_per_hour_usd * runtime_hours
    egress_cost = 0.0  # Real: calculated at teardown based on bytes transferred

    return CostReport(
        deployment_id=deployment_id,
        provider=tracker.provider,
        region=tracker.region,
        workload_profile=tracker.workload_profile,
        started_at=tracker.started_at,
        completed_at=None,
        total_runtime_hours=runtime_hours,
        total_compute_cost_usd=round(compute_cost, 4),
        total_spoke_cost_usd=round(spoke_cost, 4),
        total_egress_cost_usd=egress_cost,
        grand_total_usd=round(summary.current_cost_usd + egress_cost, 4),
        teardown_reason=summary.teardown_reason,
        events=tracker.records(),
    )


@app.patch("/api/v1/cost/{deployment_id}/phase")
async def update_phase(deployment_id: str, phase: str) -> dict:
    if deployment_id not in _trackers:
        raise HTTPException(status_code=404, detail="Deployment not tracked")
    _trackers[deployment_id].update_phase(phase)
    return {"ok": True}


@app.get("/healthz")
async def health() -> dict:
    return {"status": "ok", "tracked_deployments": len(_trackers)}
