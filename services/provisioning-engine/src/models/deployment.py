from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class DeploymentPhase(str, Enum):
    PENDING = "pending"
    PROVISIONING_COMPUTE = "provisioning_compute"
    BOOTSTRAPPING_SPOKE = "bootstrapping_spoke"
    ATTACHING_CDF = "attaching_cdf"
    REGISTERING_HPC = "registering_hpc"
    SUBMITTING_JOB = "submitting_job"
    RUNNING = "running"
    DRAINING = "draining"
    DESTROYING = "destroying"
    COMPLETED = "completed"
    FAILED = "failed"


class TeardownReason(str, Enum):
    LIFETIME_EXPIRED = "lifetime_expired"
    PRICE_CEILING_BREACHED = "price_ceiling_breached"
    IDLE_TIMEOUT = "idle_timeout"
    MANUAL = "manual"
    ERROR = "error"


class HpcOrchestrator(str, Enum):
    CYCLE_CLOUD = "azure_cyclecloud"
    PARALLEL_CLUSTER = "aws_parallelcluster"
    SLURM = "slurm"


class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class DeploymentRequest(BaseModel):
    provider: CloudProvider
    region: str
    sku_id: str
    gpu_count: int = Field(ge=1)
    workload_profile: str
    spoke_node_count: int = Field(ge=1)
    spoke_capacity_tb: float = Field(gt=0)
    hpc_orchestrator: HpcOrchestrator
    cdf_namespace: str
    ephemeral_lifetime_hours: Optional[float] = None
    price_ceiling_usd: Optional[float] = None
    idle_timeout_minutes: Optional[int] = None
    job_script: Optional[str] = None
    operator_id: str


class DeploymentEvent(BaseModel):
    timestamp: datetime
    phase: DeploymentPhase
    message: str
    detail: Optional[dict] = None


class Deployment(BaseModel):
    deployment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: DeploymentRequest
    phase: DeploymentPhase = DeploymentPhase.PENDING
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    teardown_reason: Optional[TeardownReason] = None
    events: list[DeploymentEvent] = Field(default_factory=list)
    spoke_cluster_id: Optional[str] = None
    compute_stack_id: Optional[str] = None
    hpc_environment_id: Optional[str] = None
    job_id: Optional[str] = None
    current_cost_usd: float = 0.0
    error: Optional[str] = None


class DeploymentListResponse(BaseModel):
    deployments: list[Deployment]
    total: int


class TeardownRequest(BaseModel):
    reason: TeardownReason = TeardownReason.MANUAL
