from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class GPUFamily(str, Enum):
    NVIDIA_A100 = "a100"
    NVIDIA_H100 = "h100"
    NVIDIA_A10G = "a10g"
    NVIDIA_L40S = "l40s"
    NVIDIA_L4   = "l4"
    NVIDIA_V100 = "v100"
    NVIDIA_T4 = "t4"
    AMD_MI300X = "mi300x"


class AvailabilityTier(str, Enum):
    HIGH = "high"       # >50% of capacity available
    MEDIUM = "medium"   # 10–50%
    LOW = "low"         # <10%
    UNAVAILABLE = "unavailable"


class PriceBand(str, Enum):
    ECONOMY = "economy"     # < $1/GPU-hr
    STANDARD = "standard"   # $1–$5/GPU-hr
    PREMIUM = "premium"     # $5–$15/GPU-hr
    ULTRA = "ultra"         # > $15/GPU-hr


class PricingType(str, Enum):
    ON_DEMAND = "on_demand"
    SPOT = "spot"
    CAPACITY_BLOCK = "capacity_block"
    COMMITTED_USE = "committed_use"


class GPUSku(BaseModel):
    sku_id: str
    provider: CloudProvider
    region: str
    display_region: str
    gpu_family: GPUFamily
    gpu_count: int
    vcpus: int
    memory_gb: float
    gpu_memory_gb: float
    interconnect: Optional[str] = None       # e.g. "NVLink", "InfiniBand"
    pricing_type: PricingType
    price_per_gpu_hour: float
    price_band: PriceBand
    availability: AvailabilityTier
    available_count: Optional[int] = None    # None = unknown
    latitude: float
    longitude: float
    sovereignty_zones: list[str] = Field(default_factory=list)
    refreshed_at: datetime
    staleness_seconds: float = 0.0

    @property
    def is_advisory_price(self) -> bool:
        return self.pricing_type in (PricingType.SPOT, PricingType.CAPACITY_BLOCK)


class RegionSummary(BaseModel):
    provider: CloudProvider
    region: str
    display_region: str
    latitude: float
    longitude: float
    best_availability: AvailabilityTier
    best_price_per_gpu_hour: float
    price_band: PriceBand
    gpu_families: list[GPUFamily]
    sku_count: int
    refreshed_at: datetime
    staleness_seconds: float


class GPUCatalogResponse(BaseModel):
    generated_at: datetime
    total_regions: int
    total_skus: int
    regions: list[RegionSummary]


class GPUSkuListResponse(BaseModel):
    generated_at: datetime
    region: str
    provider: CloudProvider
    skus: list[GPUSku]


class WorkloadProfile(str, Enum):
    AI_TRAINING = "ai_training"
    AI_INFERENCE = "ai_inference"
    HPC_SIMULATION = "hpc_simulation"
    NGS_GENOMICS = "ngs_genomics"
    RENDERING = "rendering"
    GENERIC = "generic"


class SpokeConfigRequest(BaseModel):
    provider: CloudProvider
    region: str
    sku_id: str
    workload_profile: WorkloadProfile
    gpu_count: int = Field(ge=1)
    dataset_size_tb: float = Field(ge=0.0)
    ephemeral_lifetime_hours: Optional[float] = None
    price_ceiling_usd: Optional[float] = None


class SpokeConfigProposal(BaseModel):
    provider: CloudProvider
    region: str
    sku_id: str
    workload_profile: WorkloadProfile
    gpu_count: int
    spoke_node_count: int
    spoke_capacity_tb: float
    spoke_throughput_gbps: float
    estimated_cost_per_hour: float
    estimated_total_cost_usd: Optional[float] = None
    estimated_egress_cost_usd: Optional[float] = None
    hpc_orchestrator: str
    warnings: list[str] = Field(default_factory=list)
