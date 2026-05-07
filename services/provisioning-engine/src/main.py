from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.cloud_bridge.engine import CloudBridgeEngine
from src.models.deployment import (
    Deployment,
    DeploymentListResponse,
    DeploymentPhase,
    DeploymentRequest,
    TeardownReason,
    TeardownRequest,
)
from src.spoke_orchestrator.orchestrator import SpokeOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GPU Horizon Provisioning Engine",
    description="Cloud Bridge + Spoke Orchestrator for one-click Qumulo spoke deployment.",
    version="0.1.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_deployments: dict[str, Deployment] = {}
_cloud_bridge = CloudBridgeEngine()
_spoke_orchestrator = SpokeOrchestrator()


async def _run_deployment(deployment: Deployment) -> None:
    now = datetime.now(timezone.utc)
    deployment.started_at = now
    deployment.updated_at = now

    try:
        await _cloud_bridge.provision(deployment)
        await _spoke_orchestrator.bootstrap(deployment)

        deployment.phase = DeploymentPhase.RUNNING
        deployment.updated_at = datetime.now(timezone.utc)
        logger.info("Deployment %s is RUNNING", deployment.deployment_id)

    except Exception as exc:
        deployment.phase = DeploymentPhase.FAILED
        deployment.error = str(exc)
        deployment.updated_at = datetime.now(timezone.utc)
        logger.exception("Deployment %s FAILED", deployment.deployment_id)


async def _run_teardown(deployment: Deployment, reason: TeardownReason) -> None:
    deployment.teardown_reason = reason
    deployment.updated_at = datetime.now(timezone.utc)

    try:
        await _spoke_orchestrator.drain_and_deregister(deployment)
        await _cloud_bridge.teardown(deployment)

        deployment.phase = DeploymentPhase.COMPLETED
        deployment.completed_at = datetime.now(timezone.utc)
        deployment.updated_at = deployment.completed_at
        logger.info("Deployment %s COMPLETED teardown (%s)", deployment.deployment_id, reason)

    except Exception as exc:
        deployment.phase = DeploymentPhase.FAILED
        deployment.error = str(exc)
        deployment.updated_at = datetime.now(timezone.utc)
        logger.exception("Teardown of %s FAILED", deployment.deployment_id)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/v1/deployments", response_model=Deployment, status_code=202)
async def create_deployment(req: DeploymentRequest) -> Deployment:
    now = datetime.now(timezone.utc)
    deployment = Deployment(request=req, created_at=now, updated_at=now)
    _deployments[deployment.deployment_id] = deployment
    asyncio.create_task(_run_deployment(deployment))
    return deployment


@app.get("/api/v1/deployments", response_model=DeploymentListResponse)
async def list_deployments(
    phase: Optional[DeploymentPhase] = None,
    operator_id: Optional[str] = None,
) -> DeploymentListResponse:
    result = list(_deployments.values())
    if phase:
        result = [d for d in result if d.phase == phase]
    if operator_id:
        result = [d for d in result if d.request.operator_id == operator_id]
    return DeploymentListResponse(deployments=result, total=len(result))


@app.get("/api/v1/deployments/{deployment_id}", response_model=Deployment)
async def get_deployment(deployment_id: str) -> Deployment:
    if deployment_id not in _deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return _deployments[deployment_id]


@app.delete("/api/v1/deployments/{deployment_id}", response_model=Deployment)
async def teardown_deployment(deployment_id: str, req: TeardownRequest) -> Deployment:
    if deployment_id not in _deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    deployment = _deployments[deployment_id]
    if deployment.phase not in (DeploymentPhase.RUNNING, DeploymentPhase.PENDING):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot tear down deployment in phase {deployment.phase}",
        )
    asyncio.create_task(_run_teardown(deployment, req.reason))
    return deployment


@app.get("/healthz")
async def health() -> dict:
    return {
        "status": "ok",
        "total_deployments": len(_deployments),
        "running": sum(1 for d in _deployments.values() if d.phase == DeploymentPhase.RUNNING),
    }
