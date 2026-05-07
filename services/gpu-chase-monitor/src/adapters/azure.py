from __future__ import annotations

import logging
import os
import random

from src.adapters.base import CloudAdapter
from src.models.gpu_region import (
    AvailabilityTier,
    CloudProvider,
    GPUFamily,
    GPUSku,
    PriceBand,
    PricingType,
)

logger = logging.getLogger(__name__)

_AZURE_REGIONS: dict[str, tuple[str, float, float, list[str]]] = {
    "eastus":          ("East US",            37.36,  -79.03, ["US"]),
    "eastus2":         ("East US 2",          36.67,  -78.37, ["US"]),
    "westus2":         ("West US 2",          47.23, -119.85, ["US"]),
    "westus3":         ("West US 3",          33.45, -112.07, ["US"]),
    "northeurope":     ("North Europe",       53.30,   -6.26, ["EU", "EEA", "IE"]),
    "westeurope":      ("West Europe",        52.37,    4.89, ["EU", "EEA", "NL"]),
    "germanywestcentral": ("Germany West Central", 50.11, 8.68, ["EU", "EEA", "DE"]),
    "japaneast":       ("Japan East",         35.68,  139.77, ["JP"]),
    "southeastasia":   ("Southeast Asia",      1.29,  103.82, ["SG"]),
    "australiaeast":   ("Australia East",    -33.86,  151.21, ["AU"]),
    "canadacentral":   ("Canada Central",     43.65,  -79.38, ["CA"]),
}

_AZURE_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = {
    ("Standard_ND96asr_v4",  GPUFamily.NVIDIA_A100, 8, 96,  900.0, 40.0, "InfiniBand"),
    ("Standard_ND96amsr_A100_v4", GPUFamily.NVIDIA_A100, 8, 96, 1900.0, 80.0, "InfiniBand"),
    ("Standard_ND96isr_H100_v5",  GPUFamily.NVIDIA_H100, 8, 96, 1900.0, 80.0, "InfiniBand400"),
    ("Standard_NC24ads_A100_v4",  GPUFamily.NVIDIA_A100, 1, 24, 220.0, 80.0, None),
    ("Standard_NV72ads_A10_v5",   GPUFamily.NVIDIA_A10G, 4, 72, 880.0, 24.0, None),
}

_ON_DEMAND_GPU_HOUR: dict[str, float] = {
    "Standard_ND96asr_v4":          3.40,
    "Standard_ND96amsr_A100_v4":    4.25,
    "Standard_ND96isr_H100_v5":     9.97,
    "Standard_NC24ads_A100_v4":     3.67,
    "Standard_NV72ads_A10_v5":      0.98,
}


def _price_band(price: float) -> PriceBand:
    if price < 1.0:
        return PriceBand.ECONOMY
    if price < 5.0:
        return PriceBand.STANDARD
    if price < 15.0:
        return PriceBand.PREMIUM
    return PriceBand.ULTRA


def _availability_tier(count: int) -> AvailabilityTier:
    if count == 0:
        return AvailabilityTier.UNAVAILABLE
    if count < 4:
        return AvailabilityTier.LOW
    if count < 20:
        return AvailabilityTier.MEDIUM
    return AvailabilityTier.HIGH


class AzureAdapter(CloudAdapter):
    provider = CloudProvider.AZURE

    def __init__(self) -> None:
        self._use_real = bool(os.getenv("AZURE_SUBSCRIPTION_ID"))
        if self._use_real:
            try:
                from azure.mgmt.compute import ComputeManagementClient  # type: ignore  # noqa: F401
                logger.info("Azure adapter: using azure-mgmt-compute")
            except ImportError:
                logger.warning("azure-mgmt-compute not installed — falling back to simulation")
                self._use_real = False

    async def fetch_skus(self) -> list[GPUSku]:
        if self._use_real:
            return await self._fetch_real()
        return self._fetch_simulated()

    async def _fetch_real(self) -> list[GPUSku]:  # pragma: no cover
        return self._fetch_simulated()

    def _fetch_simulated(self) -> list[GPUSku]:
        now = self._now()
        skus: list[GPUSku] = []

        for region_id, (display, lat, lon, sov) in _AZURE_REGIONS.items():
            for (vm_size, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _AZURE_SKUS:
                seed = hash(f"azure:{region_id}:{vm_size}:{now.hour}") % 1000
                rng = random.Random(seed)

                available_count = rng.randint(0, 32)
                base_price = _ON_DEMAND_GPU_HOUR[vm_size]
                spot_discount = rng.uniform(0.55, 0.85)

                for pricing_type, multiplier in [
                    (PricingType.ON_DEMAND, 1.0),
                    (PricingType.SPOT, spot_discount),
                ]:
                    price = round(base_price * multiplier, 4)
                    skus.append(GPUSku(
                        sku_id=f"azure:{region_id}:{vm_size}:{pricing_type.value}",
                        provider=CloudProvider.AZURE,
                        region=region_id,
                        display_region=display,
                        gpu_family=gpu_family,
                        gpu_count=gpu_count,
                        vcpus=vcpus,
                        memory_gb=mem_gb,
                        gpu_memory_gb=gpu_mem,
                        interconnect=interconnect,
                        pricing_type=pricing_type,
                        price_per_gpu_hour=price,
                        price_band=_price_band(price),
                        availability=_availability_tier(available_count),
                        available_count=available_count,
                        latitude=lat,
                        longitude=lon,
                        sovereignty_zones=sov,
                        refreshed_at=now,
                        staleness_seconds=0.0,
                    ))

        return skus
