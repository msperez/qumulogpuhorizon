from __future__ import annotations

import asyncio
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

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
    ("p4d.24xlarge",  GPUFamily.NVIDIA_A100, 8,  96,  1152.0, 40.0, "NVLink"),
    ("p4de.24xlarge", GPUFamily.NVIDIA_A100, 8,  96,  1152.0, 80.0, "NVLink"),
    ("p5.48xlarge",   GPUFamily.NVIDIA_H100, 8,  192, 2048.0, 80.0, "NVLink+EFAv2"),
    ("g5.48xlarge",   GPUFamily.NVIDIA_A10G, 8,  192, 768.0,  24.0, None),
    ("g4dn.12xlarge", GPUFamily.NVIDIA_T4,   4,  48,  192.0,  16.0, None),
]

_INSTANCE_META: dict[str, tuple[GPUFamily, int, int, float, float, str | None]] = {
    s[0]: s[1:] for s in _AWS_SKUS
}

# Pricing API location names differ from region IDs
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

# Fallback on-demand prices (per GPU-hour) used when Pricing API fails
_FALLBACK_GPU_HR: dict[str, float] = {
    "p4d.24xlarge":  3.22,
    "p4de.24xlarge": 4.07,
    "p5.48xlarge":   9.80,
    "g5.48xlarge":   1.006 / 8 * 8,  # already per-instance, /gpu done below
    "g4dn.12xlarge": 0.585,
}

# Cache on-demand prices for 6 hours (rarely change)
_PRICE_CACHE_TTL = timedelta(hours=6)


def _price_band(price: float) -> PriceBand:
    if price < 1.0:  return PriceBand.ECONOMY
    if price < 5.0:  return PriceBand.STANDARD
    if price < 15.0: return PriceBand.PREMIUM
    return PriceBand.ULTRA


def _avail_tier(count: Optional[int]) -> AvailabilityTier:
    if count is None:  return AvailabilityTier.MEDIUM
    if count == 0:     return AvailabilityTier.UNAVAILABLE
    if count < 4:      return AvailabilityTier.LOW
    if count < 20:     return AvailabilityTier.MEDIUM
    return AvailabilityTier.HIGH


class AWSAdapter(CloudAdapter):
    """
    Queries real AWS APIs when boto3 is importable and credentials are reachable
    (env vars, ~/.aws/credentials, or EC2 instance profile — whichever boto3
    finds first).  Falls back to simulation transparently.
    """
    provider = CloudProvider.AWS

    def __init__(self) -> None:
        self._boto3 = None
        self._credentials_ok = False
        # On-demand price cache: {(region, instance): price_per_gpu_hour}
        self._od_cache: dict[tuple[str, str], float] = {}
        self._od_cache_ts: Optional[datetime] = None
        self._executor = ThreadPoolExecutor(max_workers=8)

        try:
            import boto3  # type: ignore
            import botocore  # type: ignore
            session = boto3.Session()
            creds = session.get_credentials()
            if creds is not None:
                # Resolve to confirm they aren't stubs
                resolved = creds.get_frozen_credentials()
                if resolved.access_key:
                    self._boto3 = boto3
                    self._credentials_ok = True
                    logger.info("AWS adapter: real mode — credentials found (%s)",
                                "instance-profile" if not resolved.token else "sts/env")
        except Exception as exc:
            logger.warning("AWS adapter: credential check failed (%s) — using simulation", exc)

    async def fetch_skus(self) -> list[GPUSku]:
        if self._credentials_ok:
            try:
                return await self._fetch_real()
            except Exception as exc:
                logger.error("AWS real fetch failed: %s — falling back to simulation", exc)
        return self._fetch_simulated()

    # ------------------------------------------------------------------
    # Real AWS implementation
    # ------------------------------------------------------------------

    async def _fetch_real(self) -> list[GPUSku]:
        loop = asyncio.get_event_loop()

        # Refresh on-demand prices if cache is stale
        if (self._od_cache_ts is None
                or datetime.now(timezone.utc) - self._od_cache_ts > _PRICE_CACHE_TTL):
            self._od_cache = await loop.run_in_executor(
                self._executor, self._fetch_ondemand_prices
            )
            self._od_cache_ts = datetime.now(timezone.utc)
            logger.info("AWS on-demand price cache refreshed: %d entries", len(self._od_cache))

        # Fetch all regions in parallel
        futures = {
            loop.run_in_executor(self._executor, self._fetch_region, region_id): region_id
            for region_id in _AWS_REGIONS
        }
        all_skus: list[GPUSku] = []
        for coro in asyncio.as_completed(list(futures)):
            try:
                skus = await coro
                all_skus.extend(skus)
            except Exception as exc:
                logger.warning("AWS region fetch failed: %s", exc)

        logger.info("AWS real adapter: fetched %d SKUs across %d regions",
                    len(all_skus), len(_AWS_REGIONS))
        return all_skus

    def _fetch_region(self, region_id: str) -> list[GPUSku]:
        boto3 = self._boto3
        display, lat, lon, sov = _AWS_REGIONS[region_id]
        now = datetime.now(timezone.utc)
        ec2 = boto3.client("ec2", region_name=region_id)

        # ── Which GPU instance types are offered in this region? ──────────
        try:
            resp = ec2.describe_instance_type_offerings(
                LocationType="region",
                Filters=[
                    {"Name": "instance-type", "Values": list(_INSTANCE_META)},
                    {"Name": "location",      "Values": [region_id]},
                ],
            )
            offered = {o["InstanceType"] for o in resp["InstanceTypeOfferings"]}
        except Exception as exc:
            logger.warning("describe_instance_type_offerings failed %s: %s", region_id, exc)
            offered = set(_INSTANCE_META)  # assume all offered on error

        # ── Current spot prices ───────────────────────────────────────────
        spot_gpu_hr: dict[str, float] = {}
        try:
            spot_resp = ec2.describe_spot_price_history(
                InstanceTypes=list(_INSTANCE_META),
                ProductDescriptions=["Linux/UNIX"],
                MaxResults=len(_INSTANCE_META) * 6,
            )
            # Keep cheapest AZ price per instance type
            for sp in spot_resp.get("SpotPriceHistory", []):
                itype = sp["InstanceType"]
                total_hr = float(sp["SpotPrice"])
                gpu_count = _INSTANCE_META[itype][1]  # index 1 = gpu_count
                per_gpu = total_hr / gpu_count
                if itype not in spot_gpu_hr or per_gpu < spot_gpu_hr[itype]:
                    spot_gpu_hr[itype] = per_gpu
        except Exception as exc:
            logger.warning("describe_spot_price_history failed %s: %s", region_id, exc)

        # ── Build SKU list ────────────────────────────────────────────────
        results: list[GPUSku] = []
        for instance, (gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _INSTANCE_META.items():
            if instance not in offered:
                continue

            od_per_gpu = self._od_cache.get(
                (region_id, instance),
                _FALLBACK_GPU_HR.get(instance, 0.0) / gpu_count,
            )

            # On-demand SKU — availability unknown via public API; show MEDIUM
            results.append(self._sku(
                region_id, display, lat, lon, sov, now, instance,
                gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                PricingType.ON_DEMAND, od_per_gpu, AvailabilityTier.MEDIUM, None,
            ))

            # Spot SKU — only if we got a real price
            if instance in spot_gpu_hr:
                results.append(self._sku(
                    region_id, display, lat, lon, sov, now, instance,
                    gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.SPOT, spot_gpu_hr[instance], AvailabilityTier.LOW, None,
                ))

        return results

    def _fetch_ondemand_prices(self) -> dict[tuple[str, str], float]:
        """
        Calls the AWS Pricing API (us-east-1 global endpoint) for on-demand
        Linux/shared prices for all GPU instance types in all target regions.
        Returns {(region_id, instance_type): price_per_gpu_hour}.
        """
        boto3 = self._boto3
        pricing = boto3.client("pricing", region_name="us-east-1")
        prices: dict[tuple[str, str], float] = {}

        for region_id, location in _PRICING_LOCATION.items():
            for instance, (_, gpu_count, *_rest) in _INSTANCE_META.items():
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
                        item = json.loads(item_str)
                        for term in item.get("terms", {}).get("OnDemand", {}).values():
                            for dim in term.get("priceDimensions", {}).values():
                                usd = float(dim["pricePerUnit"].get("USD", 0))
                                if usd > 0:
                                    prices[(region_id, instance)] = usd / gpu_count
                except Exception as exc:
                    logger.debug("Pricing API failed %s/%s: %s", region_id, instance, exc)

        return prices

    @staticmethod
    def _sku(
        region_id: str, display: str, lat: float, lon: float, sov: list[str],
        now: datetime, instance: str,
        gpu_family: GPUFamily, gpu_count: int, vcpus: int,
        mem_gb: float, gpu_mem: float, interconnect: str | None,
        pricing_type: PricingType, price_per_gpu_hour: float,
        availability: AvailabilityTier, available_count: Optional[int],
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
        now = datetime.now(timezone.utc)
        skus: list[GPUSku] = []
        for region_id, (display, lat, lon, sov) in _AWS_REGIONS.items():
            for instance, (gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _INSTANCE_META.items():
                seed = hash(f"{region_id}:{instance}:{now.hour}") % 1000
                rng = random.Random(seed)
                available_count = rng.randint(0, 40)
                base = _FALLBACK_GPU_HR.get(instance, 3.0) / gpu_count
                for pricing_type, mult in [
                    (PricingType.ON_DEMAND, 1.0),
                    (PricingType.SPOT, rng.uniform(0.6, 0.9)),
                ]:
                    price = round(base * mult, 4)
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
                        availability=_avail_tier(available_count),
                        available_count=available_count,
                        latitude=lat,
                        longitude=lon,
                        sovereignty_zones=sov,
                        refreshed_at=now,
                        staleness_seconds=0.0,
                        simulated=True,
                    ))
        return skus
