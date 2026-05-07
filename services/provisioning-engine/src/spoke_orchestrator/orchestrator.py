from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from src.models.deployment import Deployment, DeploymentEvent, DeploymentPhase

logger = logging.getLogger(__name__)


def _emit(deployment: Deployment, phase: DeploymentPhase, message: str, detail: dict | None = None) -> None:
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


class SpokeOrchestrator:
    """
    Bootstraps a Qumulo cluster on provisioned cloud resources, applies the
    workload profile, joins it to Cloud Data Fabric, and registers it with the
    chosen HPC orchestrator.
    """

    async def bootstrap(self, deployment: Deployment) -> None:
        _emit(
            deployment,
            DeploymentPhase.BOOTSTRAPPING_SPOKE,
            f"Bootstrapping Qumulo spoke: {deployment.request.spoke_node_count} nodes, "
            f"{deployment.request.spoke_capacity_tb} TB, profile={deployment.request.workload_profile}",
        )
        await asyncio.sleep(5.0)  # cluster formation

        deployment.spoke_cluster_id = f"qsp-{uuid.uuid4().hex[:8]}"
        _emit(
            deployment,
            DeploymentPhase.BOOTSTRAPPING_SPOKE,
            f"Spoke cluster ready: {deployment.spoke_cluster_id}",
            detail={"cluster_id": deployment.spoke_cluster_id},
        )

        # Attach to Cloud Data Fabric
        _emit(
            deployment,
            DeploymentPhase.ATTACHING_CDF,
            f"Attaching spoke to CDF namespace: {deployment.request.cdf_namespace}",
        )
        await asyncio.sleep(2.0)
        _emit(
            deployment,
            DeploymentPhase.ATTACHING_CDF,
            "CDF namespace attachment complete — global namespace is active",
        )

        # Register with HPC orchestrator
        _emit(
            deployment,
            DeploymentPhase.REGISTERING_HPC,
            f"Registering compute environment with {deployment.request.hpc_orchestrator}",
        )
        await asyncio.sleep(2.0)
        deployment.hpc_environment_id = f"hpc-env-{uuid.uuid4().hex[:8]}"
        _emit(
            deployment,
            DeploymentPhase.REGISTERING_HPC,
            f"HPC environment registered: {deployment.hpc_environment_id}",
            detail={"orchestrator": deployment.request.hpc_orchestrator,
                    "env_id": deployment.hpc_environment_id},
        )

        # Optionally submit job
        if deployment.request.job_script:
            await self._submit_job(deployment)

    async def _submit_job(self, deployment: Deployment) -> None:
        _emit(
            deployment,
            DeploymentPhase.SUBMITTING_JOB,
            f"Submitting workload to {deployment.request.hpc_orchestrator}",
        )
        await asyncio.sleep(1.0)
        deployment.job_id = f"job-{uuid.uuid4().hex[:8]}"
        _emit(
            deployment,
            DeploymentPhase.SUBMITTING_JOB,
            f"Job submitted: {deployment.job_id}",
            detail={"job_id": deployment.job_id},
        )

    async def drain_and_deregister(self, deployment: Deployment) -> None:
        _emit(
            deployment,
            DeploymentPhase.DRAINING,
            "Draining CDF namespace — flushing pending replication",
        )
        await asyncio.sleep(3.0)

        _emit(
            deployment,
            DeploymentPhase.DRAINING,
            f"Deregistering HPC environment {deployment.hpc_environment_id}",
        )
        await asyncio.sleep(1.0)
        _emit(
            deployment,
            DeploymentPhase.DRAINING,
            "Namespace drained and HPC environment deregistered",
        )
