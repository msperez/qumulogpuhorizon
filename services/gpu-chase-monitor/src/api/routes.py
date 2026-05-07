from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.cache.store import GPUCatalogStore
from src.models.gpu_region import (
    AvailabilityTier,
    CloudProvider,
    GPUCatalogResponse,
    GPUFamily,
    GPUSkuListResponse,
    PriceBand,
    SpokeConfigProposal,
    SpokeConfigRequest,
    WorkloadProfile,
)

router = APIRouter()


def get_store() -> GPUCatalogStore:
    # Overridden in main via dependency_overrides
    raise NotImplementedError


# ---------------------------------------------------------------------------
# GPU Catalog endpoints
# ---------------------------------------------------------------------------

@router.get("/regions", response_model=GPUCatalogResponse)
async def list_regions(
    provider: Optional[list[CloudProvider]] = Query(None),
    gpu_family: Optional[list[GPUFamily]] = Query(None),
    price_band: Optional[list[PriceBand]] = Query(None),
    sovereignty_zone: Optional[list[str]] = Query(None),
    store: GPUCatalogStore = Depends(get_store),
) -> GPUCatalogResponse:
    """Return a world-map-ready summary of GPU availability per region."""
    summaries = await store.get_region_summaries(
        providers=provider,
        gpu_families=gpu_family,
        price_bands=price_band,
        sovereignty_zones=sovereignty_zone,
    )
    return GPUCatalogResponse(
        generated_at=datetime.now(timezone.utc),
        total_regions=len(summaries),
        total_skus=sum(s.sku_count for s in summaries),
        regions=summaries,
    )


@router.get("/regions/{provider}/{region}/skus", response_model=GPUSkuListResponse)
async def list_region_skus(
    provider: CloudProvider,
    region: str,
    store: GPUCatalogStore = Depends(get_store),
) -> GPUSkuListResponse:
    """Return all GPU SKUs for a specific provider + region."""
    skus = await store.get_skus_for_region(provider, region)
    if not skus:
        raise HTTPException(status_code=404, detail=f"No SKUs found for {provider}/{region}")
    return GPUSkuListResponse(
        generated_at=datetime.now(timezone.utc),
        region=region,
        provider=provider,
        skus=skus,
    )


@router.get("/skus", response_model=GPUSkuListResponse)
async def list_skus(
    provider: Optional[list[CloudProvider]] = Query(None),
    gpu_family: Optional[list[GPUFamily]] = Query(None),
    availability: Optional[list[AvailabilityTier]] = Query(None),
    price_band: Optional[list[PriceBand]] = Query(None),
    sovereignty_zone: Optional[list[str]] = Query(None),
    store: GPUCatalogStore = Depends(get_store),
) -> GPUSkuListResponse:
    """Return filtered SKU list."""
    skus = await store.get_all_skus(
        providers=provider,
        gpu_families=gpu_family,
        price_bands=price_band,
        availability=availability,
        sovereignty_zones=sovereignty_zone,
    )
    return GPUSkuListResponse(
        generated_at=datetime.now(timezone.utc),
        region="all",
        provider=provider[0] if provider and len(provider) == 1 else CloudProvider.AWS,
        skus=skus,
    )


# ---------------------------------------------------------------------------
# Spoke configurator endpoint
# ---------------------------------------------------------------------------

# Workload-profile sizing templates: (spoke_nodes, capacity_tb, throughput_gbps)
_PROFILE_SIZING: dict[WorkloadProfile, tuple[int, float, float]] = {
    WorkloadProfile.AI_TRAINING:     (4, 200.0, 100.0),
    WorkloadProfile.AI_INFERENCE:    (2, 50.0,  40.0),
    WorkloadProfile.HPC_SIMULATION:  (6, 400.0, 200.0),
    WorkloadProfile.NGS_GENOMICS:    (3, 100.0, 50.0),
    WorkloadProfile.RENDERING:       (4, 300.0, 80.0),
    WorkloadProfile.GENERIC:         (2, 50.0,  20.0),
}

_HPC_ORCHESTRATOR: dict[CloudProvider, str] = {
    CloudProvider.AWS:   "AWS ParallelCluster",
    CloudProvider.AZURE: "Azure CycleCloud",
    CloudProvider.GCP:   "Slurm on GKE",
}


@router.post("/configure/spoke", response_model=SpokeConfigProposal)
async def configure_spoke(
    req: SpokeConfigRequest,
    store: GPUCatalogStore = Depends(get_store),
) -> SpokeConfigProposal:
    """Return a proposed spoke + compute configuration for the selected SKU and workload."""
    skus = await store.get_skus_for_region(req.provider, req.region)
    sku = next((s for s in skus if s.sku_id == req.sku_id), None)
    if sku is None:
        raise HTTPException(status_code=404, detail=f"SKU {req.sku_id!r} not found")

    nodes, capacity_tb, throughput_gbps = _PROFILE_SIZING[req.workload_profile]

    # Scale capacity if the dataset is larger than the default
    if req.dataset_size_tb > capacity_tb:
        scale = req.dataset_size_tb / capacity_tb
        nodes = max(nodes, int(nodes * scale))
        capacity_tb = req.dataset_size_tb * 1.3  # 30% headroom

    compute_cost = sku.price_per_gpu_hour * req.gpu_count
    spoke_cost_per_hour = nodes * 0.5  # rough node cost
    total_per_hour = compute_cost + spoke_cost_per_hour

    total_cost: Optional[float] = None
    egress_cost: Optional[float] = None
    warnings: list[str] = []

    if req.ephemeral_lifetime_hours is not None:
        total_cost = round(total_per_hour * req.ephemeral_lifetime_hours, 2)
        # Egress: ~$0.08/GB, assume 20% of dataset needs egress
        egress_gb = req.dataset_size_tb * 1024 * 0.2
        egress_cost = round(egress_gb * 0.08, 2)
        if sku.is_advisory_price:
            warnings.append(
                "Spot/capacity-block pricing shown is advisory and may change. "
                "Total cost estimate is not a binding quote."
            )
        if req.ephemeral_lifetime_hours < 4 and req.dataset_size_tb > 10:
            warnings.append(
                f"Ephemeral lifetime ({req.ephemeral_lifetime_hours}h) may be insufficient "
                f"to drain {req.dataset_size_tb} TB namespace at teardown. "
                f"Estimated egress cost: ${egress_cost:,.2f}."
            )

    if req.price_ceiling_usd is not None and total_cost is not None:
        if total_cost > req.price_ceiling_usd:
            warnings.append(
                f"Estimated total cost (${total_cost:,.2f}) exceeds price ceiling "
                f"(${req.price_ceiling_usd:,.2f}). Deployment may be terminated early."
            )

    return SpokeConfigProposal(
        provider=req.provider,
        region=req.region,
        sku_id=req.sku_id,
        workload_profile=req.workload_profile,
        gpu_count=req.gpu_count,
        spoke_node_count=nodes,
        spoke_capacity_tb=round(capacity_tb, 1),
        spoke_throughput_gbps=throughput_gbps,
        estimated_cost_per_hour=round(total_per_hour, 4),
        estimated_total_cost_usd=total_cost,
        estimated_egress_cost_usd=egress_cost,
        hpc_orchestrator=_HPC_ORCHESTRATOR[req.provider],
        warnings=warnings,
    )
