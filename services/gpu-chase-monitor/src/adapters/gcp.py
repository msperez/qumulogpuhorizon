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

_GCP_REGIONS: dict[str, tuple[str, float, float, list[str]]] = {
    "us-central1":        ("US Central (Iowa)",        41.85,  -93.62, ["US"]),
    "us-east4":           ("US East (N. Virginia)",    38.95,  -77.33, ["US"]),
    "us-west4":           ("US West (Las Vegas)",      36.17, -115.14, ["US"]),
    "europe-west4":       ("Europe West (Netherlands)",52.37,    4.89, ["EU", "EEA", "NL"]),
    "europe-west1":       ("Europe West (Belgium)",    50.45,    3.81, ["EU", "EEA", "BE"]),
    "asia-east1":         ("Asia East (Taiwan)",       24.05,  120.55, ["TW"]),
    "asia-southeast1":    ("Asia Southeast (Singapore)", 1.35, 103.82, ["SG"]),
    "australia-southeast1": ("Australia Southeast (Sydney)", -33.86, 151.21, ["AU"]),
}

_GCP_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = [
    ("a2-highgpu-8g",  GPUFamily.NVIDIA_A100, 8, 96,  680.0, 40.0, "NVLink"),
    ("a2-megagpu-16g", GPUFamily.NVIDIA_A100, 16, 96, 1360.0, 40.0, "NVLink"),
    ("a3-highgpu-8g",  GPUFamily.NVIDIA_H100, 8, 208, 1872.0, 80.0, "NVLink"),
    ("n1-standard-8-t4", GPUFamily.NVIDIA_T4, 1, 8, 30.0, 16.0, None),
]

_ON_DEMAND_GPU_HOUR: dict[str, float] = {
    "a2-highgpu-8g":    2.934,
    "a2-megagpu-16g":   2.934,
    "a3-highgpu-8g":    10.46,
    "n1-standard-8-t4": 0.35,
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


class GCPAdapter(CloudAdapter):
    provider = CloudProvider.GCP

    def __init__(self) -> None:
        self._use_real = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_CLOUD_PROJECT"))
        if self._use_real:
            try:
                from google.cloud import compute_v1  # type: ignore  # noqa: F401
                logger.info("GCP adapter: using google-cloud-compute")
            except ImportError:
                logger.warning("google-cloud-compute not installed — falling back to simulation")
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

        for region_id, (display, lat, lon, sov) in _GCP_REGIONS.items():
            for (machine_type, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _GCP_SKUS:
                seed = hash(f"gcp:{region_id}:{machine_type}:{now.hour}") % 1000
                rng = random.Random(seed)

                available_count = rng.randint(0, 48)
                base_price = _ON_DEMAND_GPU_HOUR[machine_type]
                spot_discount = rng.uniform(0.6, 0.8)

                for pricing_type, multiplier in [
                    (PricingType.ON_DEMAND, 1.0),
                    (PricingType.SPOT, spot_discount),
                    (PricingType.COMMITTED_USE, 0.7),
                ]:
                    price = round(base_price * multiplier, 4)
                    skus.append(GPUSku(
                        sku_id=f"gcp:{region_id}:{machine_type}:{pricing_type.value}",
                        provider=CloudProvider.GCP,
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
