from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from src.models.deployment import (
    CloudProvider,
    Deployment,
    DeploymentEvent,
    DeploymentPhase,
    HpcOrchestrator,
)

logger = logging.getLogger(__name__)


class CloudBridgeEngine:
    """
    Executes infrastructure provisioning through IaC (Terraform/Pulumi) and
    HPC orchestrator modules. Production calls out to the cloud; the MVP
    simulates each step with realistic timing and structured events.
    """

    # Maps provider → default HPC orchestrator
    _DEFAULT_HPC: dict[CloudProvider, HpcOrchestrator] = {
        CloudProvider.AWS:   HpcOrchestrator.PARALLEL_CLUSTER,
        CloudProvider.AZURE: HpcOrchestrator.CYCLE_CLOUD,
        CloudProvider.GCP:   HpcOrchestrator.SLURM,
    }

    async def provision(self, deployment: Deployment) -> None:
        await self._step(
            deployment,
            DeploymentPhase.PROVISIONING_COMPUTE,
            f"Applying Terraform plan for {deployment.request.provider}/{deployment.request.region}",
            simulate_seconds=4.0,
            detail={
                "sku_id": deployment.request.sku_id,
                "gpu_count": deployment.request.gpu_count,
                "hpc_orchestrator": deployment.request.hpc_orchestrator,
            },
        )
        deployment.compute_stack_id = f"stack-{uuid.uuid4().hex[:8]}"
        self._emit(deployment, DeploymentPhase.PROVISIONING_COMPUTE,
                   f"Compute stack ready: {deployment.compute_stack_id}")

    async def teardown(self, deployment: Deployment) -> None:
        await self._step(
            deployment,
            DeploymentPhase.DESTROYING,
            f"Destroying compute stack {deployment.compute_stack_id}",
            simulate_seconds=3.0,
        )

    async def _step(
        self,
        deployment: Deployment,
        phase: DeploymentPhase,
        message: str,
        simulate_seconds: float = 1.0,
        detail: dict | None = None,
    ) -> None:
        self._emit(deployment, phase, message, detail)
        await asyncio.sleep(simulate_seconds)

    @staticmethod
    def _emit(
        deployment: Deployment,
        phase: DeploymentPhase,
        message: str,
        detail: dict | None = None,
    ) -> None:
        event = DeploymentEvent(
            timestamp=datetime.now(timezone.utc),
            phase=phase,
            message=message,
            detail=detail,
        )
        deployment.events.append(event)
        deployment.phase = phase
        deployment.updated_at = event.timestamp
        logger.info("[%s] %s: %s", deployment.deployment_id[:8], phase, message)
