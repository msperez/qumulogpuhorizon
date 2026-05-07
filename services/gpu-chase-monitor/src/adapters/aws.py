from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

import httpx

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

# (instance_type, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem_gb, interconnect)
_AWS_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = [
    ("p4d.24xlarge",  GPUFamily.NVIDIA_A100, 8,  96,  1152.0, 40.0,  "NVLink"),
    ("p4de.24xlarge", GPUFamily.NVIDIA_A100, 8,  96,  1152.0, 80.0,  "NVLink"),
    ("p5.48xlarge",   GPUFamily.NVIDIA_H100, 8,  192, 2048.0, 80.0,  "NVLink+EFAv2"),
    ("g5.48xlarge",   GPUFamily.NVIDIA_A10G, 8,  192, 768.0,  24.0,  None),
    ("g4dn.12xlarge", GPUFamily.NVIDIA_T4,   4,  48,  192.0,  16.0,  None),
]

_ON_DEMAND_GPU_HOUR: dict[str, float] = {
    "p4d.24xlarge":  3.22,
    "p4de.24xlarge": 4.07,
    "p5.48xlarge":   9.80,
    "g5.48xlarge":   1.006,
    "g4dn.12xlarge": 0.585,
}

# AWS region name → display name used in the Pricing API
_PRICING_LOCATION: dict[str, str] = {
    "us-east-1":      "US East (N. Virginia)",
    "us-west-2":      "US West (Oregon)",
    "eu-west-1":      "Europe (Ireland)",
    "eu-central-1":   "EU (Frankfurt)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ca-central-1":   "Canada (Central)",
}


def _price_band(price: float) -> PriceBand:
    if price < 1.0:   return PriceBand.ECONOMY
    if price < 5.0:   return PriceBand.STANDARD
    if price < 15.0:  return PriceBand.PREMIUM
    return PriceBand.ULTRA


def _availability_tier(count: int) -> AvailabilityTier:
    if count == 0:   return AvailabilityTier.UNAVAILABLE
    if count < 4:    return AvailabilityTier.LOW
    if count < 20:   return AvailabilityTier.MEDIUM
    return AvailabilityTier.HIGH


class AWSAdapter(CloudAdapter):
    provider = CloudProvider.AWS

    def __init__(self) -> None:
        self._use_real = os.getenv("AWS_REGION") is not None
        if self._use_real:
            try:
                import boto3  # type: ignore  # noqa: F401
                logger.info("AWS adapter: real mode (boto3)")
            except ImportError:
                logger.warning("boto3 not installed — falling back to simulation")
                self._use_real = False

    async def fetch_skus(self) -> list[GPUSku]:
        if self._use_real:
            return await self._fetch_real()
        return self._fetch_simulated()

    # ------------------------------------------------------------------
    # Real AWS implementation
    # ------------------------------------------------------------------

    async def _fetch_real(self) -> list[GPUSku]:
        import boto3  # type: ignore
        import json

        results: list[GPUSku] = []
        now = self._now()

        # Fetch on-demand prices once from the global Pricing API (us-east-1 endpoint)
        od_prices = await self._fetch_ondemand_prices(boto3)

        for region_id, (display, lat, lon, sov) in _AWS_REGIONS.items():
            ec2 = boto3.client("ec2", region_name=region_id)

            # Which GPU instance types are offered in this region?
            try:
                resp = ec2.describe_instance_type_offerings(
                    LocationType="region",
                    Filters=[
                        {"Name": "instance-type",
                         "Values": [s[0] for s in _AWS_SKUS]},
                        {"Name": "location", "Values": [region_id]},
                    ],
                )
                offered = {o["InstanceType"] for o in resp["InstanceTypeOfferings"]}
            except Exception as exc:
                logger.warning("AWS offerings fetch failed for %s: %s", region_id, exc)
                offered = {s[0] for s in _AWS_SKUS}

            # Spot prices for this region
            spot_prices: dict[str, float] = {}
            try:
                spot_resp = ec2.describe_spot_price_history(
                    InstanceTypes=[s[0] for s in _AWS_SKUS],
                    ProductDescriptions=["Linux/UNIX"],
                    MaxResults=len(_AWS_SKUS) * 5,
                )
                for sp in spot_resp.get("SpotPriceHistory", []):
                    itype = sp["InstanceType"]
                    price = float(sp["SpotPrice"])
                    # Keep cheapest AZ price per instance type
                    if itype not in spot_prices or price < spot_prices[itype]:
                        spot_prices[itype] = price
            except Exception as exc:
                logger.warning("AWS spot prices failed for %s: %s", region_id, exc)

            for (instance, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _AWS_SKUS:
                if instance not in offered:
                    continue

                base_price = od_prices.get(
                    (region_id, instance),
                    _ON_DEMAND_GPU_HOUR.get(instance, 0.0)
                )
                per_gpu_od = base_price / gpu_count

                results.append(self._make_sku(
                    region_id, display, lat, lon, sov, now,
                    instance, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.ON_DEMAND, per_gpu_od,
                    availability=AvailabilityTier.MEDIUM,  # capacity not directly queryable
                    available_count=None,
                ))

                if instance in spot_prices:
                    spot_per_gpu = spot_prices[instance] / gpu_count
                    results.append(self._make_sku(
                        region_id, display, lat, lon, sov, now,
                        instance, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                        PricingType.SPOT, spot_per_gpu,
                        availability=AvailabilityTier.LOW,  # spot = scarce by nature
                        available_count=None,
                    ))

        return results

    async def _fetch_ondemand_prices(self, boto3: Any) -> dict[tuple[str, str], float]:
        """Returns {(region_id, instance_type): total_instance_price_per_hour}."""
        pricing = boto3.client("pricing", region_name="us-east-1")
        prices: dict[tuple[str, str], float] = {}

        for region_id, (_, _, _, _) in _AWS_REGIONS.items():
            location = _PRICING_LOCATION.get(region_id)
            if not location:
                continue
            for (instance, *_) in _AWS_SKUS:
                try:
                    resp = pricing.get_products(
                        ServiceCode="AmazonEC2",
                        Filters=[
                            {"Type": "TERM_MATCH", "Field": "instanceType",    "Value": instance},
                            {"Type": "TERM_MATCH", "Field": "location",        "Value": location},
                            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                            {"Type": "TERM_MATCH", "Field": "tenancy",         "Value": "Shared"},
                            {"Type": "TERM_MATCH", "Field": "preInstalledSw",  "Value": "NA"},
                            {"Type": "TERM_MATCH", "Field": "capacitystatus",  "Value": "Used"},
                        ],
                        MaxResults=1,
                    )
                    for item_str in resp.get("PriceList", []):
                        import json
                        item = json.loads(item_str)
                        od_terms = item.get("terms", {}).get("OnDemand", {})
                        for term in od_terms.values():
                            for dim in term.get("priceDimensions", {}).values():
                                usd = float(dim["pricePerUnit"].get("USD", 0))
                                if usd > 0:
                                    prices[(region_id, instance)] = usd
                except Exception as exc:
                    logger.debug("Pricing API failed %s/%s: %s", region_id, instance, exc)

        return prices

    @staticmethod
    def _make_sku(
        region_id: str, display: str, lat: float, lon: float, sov: list[str],
        now: datetime,
        instance: str, gpu_family: GPUFamily, gpu_count: int, vcpus: int,
        mem_gb: float, gpu_mem: float, interconnect: str | None,
        pricing_type: PricingType, price_per_gpu_hour: float,
        availability: AvailabilityTier, available_count: int | None,
    ) -> GPUSku:
        return GPUSku(
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
            price_per_gpu_hour=round(price_per_gpu_hour, 4),
            price_band=_price_band(price_per_gpu_hour),
            availability=availability,
            available_count=available_count,
            latitude=lat,
            longitude=lon,
            sovereignty_zones=sov,
            refreshed_at=now,
            staleness_seconds=0.0,
            simulated=False,
        )

    # ------------------------------------------------------------------
    # Simulation fallback
    # ------------------------------------------------------------------

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
