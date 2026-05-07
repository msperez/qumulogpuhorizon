from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone

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

# Static region metadata: (display_name, lat, lon, sovereignty_zones)
_AWS_REGIONS: dict[str, tuple[str, float, float, list[str]]] = {
    "us-east-1":      ("US East (N. Virginia)",    38.13,  -78.45, ["US"]),
    "us-west-2":      ("US West (Oregon)",          45.52, -122.68, ["US"]),
    "eu-west-1":      ("Europe (Ireland)",          53.33,  -6.25,  ["EU", "EEA"]),
    "eu-central-1":   ("Europe (Frankfurt)",        50.11,   8.68,  ["EU", "EEA", "DE"]),
    "ap-southeast-1": ("Asia Pacific (Singapore)",   1.35,  103.82, ["SG"]),
    "ap-northeast-1": ("Asia Pacific (Tokyo)",      35.68,  139.69, ["JP"]),
    "ap-southeast-2": ("Asia Pacific (Sydney)",    -33.87,  151.21, ["AU"]),
    "ca-central-1":   ("Canada (Central)",          45.42,  -75.70, ["CA"]),
}

# SKU catalogue: (gpu_family, gpu_count, vcpus, mem_gb, gpu_mem_gb, interconnect)
_AWS_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = [
    ("p4d.24xlarge",  GPUFamily.NVIDIA_A100, 8,  96,  1152.0, 40.0,  "NVLink"),
    ("p4de.24xlarge", GPUFamily.NVIDIA_A100, 8,  96,  1152.0, 80.0,  "NVLink"),
    ("p5.48xlarge",   GPUFamily.NVIDIA_H100, 8,  192, 2048.0, 80.0,  "NVLink+EFAv2"),
    ("g5.48xlarge",   GPUFamily.NVIDIA_A10G, 8,  192, 768.0,  24.0,  None),
    ("g4dn.12xlarge", GPUFamily.NVIDIA_T4,   4,  48,  192.0,  16.0,  None),
]

# Base on-demand prices per GPU-hour (approximate list prices)
_ON_DEMAND_GPU_HOUR: dict[str, float] = {
    "p4d.24xlarge":  3.22,
    "p4de.24xlarge": 4.07,
    "p5.48xlarge":   9.80,
    "g5.48xlarge":   1.006,
    "g4dn.12xlarge": 0.585,
}


def _price_band(price: float) -> PriceBand:
    if price < 1.0:
        return PriceBand.ECONOMY
    if price < 5.0:
        return PriceBand.STANDARD
    if price < 15.0:
        return PriceBand.PREMIUM
    return PriceBand.ULTRA


def _availability_tier(available_count: int) -> AvailabilityTier:
    if available_count == 0:
        return AvailabilityTier.UNAVAILABLE
    if available_count < 4:
        return AvailabilityTier.LOW
    if available_count < 20:
        return AvailabilityTier.MEDIUM
    return AvailabilityTier.HIGH


class AWSAdapter(CloudAdapter):
    provider = CloudProvider.AWS

    def __init__(self) -> None:
        # Real implementation would use boto3; we simulate here.
        self._use_real = os.getenv("AWS_REGION") is not None
        if self._use_real:
            try:
                import boto3  # type: ignore  # noqa: F401
                logger.info("AWS adapter: using boto3")
            except ImportError:
                logger.warning("boto3 not installed — falling back to simulation")
                self._use_real = False

    async def fetch_skus(self) -> list[GPUSku]:
        if self._use_real:
            return await self._fetch_real()
        return self._fetch_simulated()

    async def _fetch_real(self) -> list[GPUSku]:  # pragma: no cover
        # Placeholder: query EC2 describe_instance_type_offerings and
        # pricing API. Left for real AWS credential wiring.
        return self._fetch_simulated()

    def _fetch_simulated(self) -> list[GPUSku]:
        now = self._now()
        skus: list[GPUSku] = []

        for region_id, (display, lat, lon, sov) in _AWS_REGIONS.items():
            for (instance, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _AWS_SKUS:
                seed = hash(f"{region_id}:{instance}:{now.hour}") % 1000
                rng = random.Random(seed)

                available_count = rng.randint(0, 40)
                base_price = _ON_DEMAND_GPU_HOUR[instance]
                spot_discount = rng.uniform(0.6, 0.9)

                for pricing_type, multiplier in [
                    (PricingType.ON_DEMAND, 1.0),
                    (PricingType.SPOT, spot_discount),
                ]:
                    price = round(base_price * multiplier, 4)
                    skus.append(GPUSku(
                        sku_id=f"aws:{region_id}:{instance}:{pricing_type.value}",
                        provider=CloudProvider.AWS,
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
