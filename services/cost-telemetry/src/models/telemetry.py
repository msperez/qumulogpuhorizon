from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LifecycleEvent(str, Enum):
    DEPLOYMENT_STARTED = "deployment_started"
    PHASE_CHANGED = "phase_changed"
    COST_SAMPLE = "cost_sample"
    PRICE_CEILING_WARNING = "price_ceiling_warning"
    PRICE_CEILING_BREACHED = "price_ceiling_breached"
    LIFETIME_WARNING = "lifetime_warning"
    LIFETIME_EXPIRED = "lifetime_expired"
    TEARDOWN_TRIGGERED = "teardown_triggered"
    DEPLOYMENT_COMPLETED = "deployment_completed"


class TelemetryRecord(BaseModel):
    record_id: str
    deployment_id: str
    event: LifecycleEvent
    timestamp: datetime
    value: Optional[float] = None   # cost USD, remaining hours, etc.
    message: str
    metadata: dict = Field(default_factory=dict)


class DeploymentCostSummary(BaseModel):
    deployment_id: str
    provider: str
    region: str
    started_at: Optional[datetime]
    updated_at: datetime
    phase: str
    runtime_hours: float
    cost_per_hour_usd: float
    current_cost_usd: float
    price_ceiling_usd: Optional[float]
    ceiling_pct_consumed: Optional[float]     # 0–100
    lifetime_hours: Optional[float]
    lifetime_remaining_hours: Optional[float]
    teardown_triggered: bool
    teardown_reason: Optional[str]


class CostReport(BaseModel):
    deployment_id: str
    provider: str
    region: str
    workload_profile: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    total_runtime_hours: float
    total_compute_cost_usd: float
    total_spoke_cost_usd: float
    total_egress_cost_usd: float
    grand_total_usd: float
    teardown_reason: Optional[str]
    events: list[TelemetryRecord]
