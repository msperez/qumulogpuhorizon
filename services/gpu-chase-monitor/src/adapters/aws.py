from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from concurrent.futures import ThreadPoolExecutor
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

_PROBE_TTL = timedelta(minutes=10)
_PRICE_CACHE_TTL = timedelta(hours=6)
# get_spot_placement_scores accepts at most 25 instance types per call
_PLACEMENT_SCORE_BATCH = 25

_AWS_REGIONS: dict[str, tuple[str, float, float, list[str]]] = {
    # North America
    "us-east-1":      ("US East (N. Virginia)",    38.13,  -78.45,  ["US"]),
    "us-east-2":      ("US East (Ohio)",            40.00,  -82.99,  ["US"]),
    "us-west-1":      ("US West (N. California)",  37.77, -122.41,  ["US"]),
    "us-west-2":      ("US West (Oregon)",          45.52, -122.68,  ["US"]),
    "ca-central-1":   ("Canada (Central)",          45.42,  -75.70,  ["CA"]),
    # South America
    "sa-east-1":      ("South America (São Paulo)", -23.55, -46.63, ["BR"]),
    # Europe
    "eu-west-1":      ("Europe (Ireland)",          53.33,   -6.25,  ["EU", "EEA"]),
    "eu-west-2":      ("Europe (London)",           51.51,   -0.13,  ["EU", "EEA", "UK", "GB"]),
    "eu-west-3":      ("Europe (Paris)",            48.86,    2.35,  ["EU", "EEA", "FR"]),
    "eu-central-1":   ("Europe (Frankfurt)",        50.11,    8.68,  ["EU", "EEA", "DE"]),
    "eu-north-1":     ("Europe (Stockholm)",        59.33,   18.06,  ["EU", "EEA", "SE"]),
    # Asia Pacific
    "ap-south-1":     ("Asia Pacific (Mumbai)",     19.08,   72.88,  ["IN"]),
    "ap-southeast-1": ("Asia Pacific (Singapore)",   1.35,  103.82,  ["SG"]),
    "ap-southeast-2": ("Asia Pacific (Sydney)",    -33.87,  151.21,  ["AU"]),
    "ap-northeast-1": ("Asia Pacific (Tokyo)",      35.68,  139.69,  ["JP"]),
    "ap-northeast-2": ("Asia Pacific (Seoul)",      37.57,  126.98,  ["KR"]),
    "ap-northeast-3": ("Asia Pacific (Osaka)",      34.69,  135.50,  ["JP"]),
}

# (instance_type, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem_gb, interconnect)
_AWS_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = [
    # H200 — latest generation (p5e/p5en)
    ("p5e.48xlarge",   GPUFamily.NVIDIA_H200,    8, 192,  2048.0, 1128.0, "NVLink+EFAv3"),
    ("p5en.48xlarge",  GPUFamily.NVIDIA_H200,    8, 192,  2048.0, 1128.0, "EFAv3"),
    # H100 — flagship training
    ("p5.48xlarge",    GPUFamily.NVIDIA_H100,    8, 192,  2048.0,  640.0, "NVLink+EFAv2"),
    # A100 — proven HPC workhorse
    ("p4d.24xlarge",   GPUFamily.NVIDIA_A100,    8,  96,  1152.0,  320.0, "NVLink"),
    ("p4de.24xlarge",  GPUFamily.NVIDIA_A100,    8,  96,  1152.0,  640.0, "NVLink"),
    # Blackwell RTX PRO 6000 — g7e family (newest gen workloads)
    ("g7e.48xlarge",   GPUFamily.NVIDIA_RTX6000, 8, 192,   768.0,  768.0, "EFAv3"),
    # L40S — inference + rendering
    ("g6e.48xlarge",   GPUFamily.NVIDIA_L40S,    8, 192,  1536.0,  384.0, "EFAv3"),
    # A10G — mixed inference/training
    ("g5.48xlarge",    GPUFamily.NVIDIA_A10G,    8, 192,   768.0,  192.0, None),
    # L4 — cost-efficient inference
    ("g6.48xlarge",    GPUFamily.NVIDIA_L4,      8, 192,   768.0,  192.0, None),
    # T4 — entry-level / legacy
    ("g4dn.12xlarge",  GPUFamily.NVIDIA_T4,      4,  48,   192.0,   64.0, None),
]

_INSTANCE_META: dict[str, tuple[GPUFamily, int, int, float, float, str | None]] = {
    s[0]: s[1:] for s in _AWS_SKUS
}

# Pricing API location names differ from region IDs
_PRICING_LOCATION: dict[str, str] = {
    "us-east-1":      "US East (N. Virginia)",
    "us-east-2":      "US East (Ohio)",
    "us-west-1":      "US West (N. California)",
    "us-west-2":      "US West (Oregon)",
    "ca-central-1":   "Canada (Central)",
    "sa-east-1":      "South America (Sao Paulo)",
    "eu-west-1":      "Europe (Ireland)",
    "eu-west-2":      "Europe (London)",
    "eu-west-3":      "Europe (Paris)",
    "eu-central-1":   "EU (Frankfurt)",
    "eu-north-1":     "Europe (Stockholm)",
    "ap-south-1":     "Asia Pacific (Mumbai)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
}

# Fallback on-demand prices (USD per GPU-hour) used when Pricing API fails
_FALLBACK_GPU_HR: dict[str, float] = {
    "p5e.48xlarge":   3.90,   # H200 ~$31.2/hr ÷ 8
    "p5en.48xlarge":  4.10,   # H200 network-optimized
    "p5.48xlarge":    9.80,   # H100
    "p4d.24xlarge":   3.22,   # A100 40 GB
    "p4de.24xlarge":  4.07,   # A100 80 GB
    "g7e.48xlarge":   3.50,   # RTX PRO 6000 Blackwell (est.)
    "g6e.48xlarge":   2.44,   # L40S
    "g5.48xlarge":    1.006,  # A10G
    "g6.48xlarge":    2.04,   # L4
    "g4dn.12xlarge":  0.585,  # T4
}


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


def _spot_avail_from_az_count(az_count: int) -> AvailabilityTier:
    """Derive spot availability from how many AZs in a region have recent spot prices."""
    if az_count >= 3: return AvailabilityTier.HIGH
    if az_count == 2: return AvailabilityTier.MEDIUM
    if az_count == 1: return AvailabilityTier.LOW
    return AvailabilityTier.UNAVAILABLE


class AWSAdapter(CloudAdapter):
    """
    Queries real AWS APIs when boto3 is importable and credentials are reachable.
    Falls back to deterministic simulation transparently.
    """
    provider = CloudProvider.AWS

    def __init__(self) -> None:
        self._boto3 = None
        self._credentials_ok = False
        # On-demand price cache: {(region, instance): price_per_gpu_hour}
        self._od_cache: dict[tuple[str, str], float] = {}
        self._od_cache_ts: Optional[datetime] = None
        # Spot placement score cache: {(region_id, instance_type): AvailabilityTier}
        self._probe_cache: dict[tuple[str, str], AvailabilityTier] = {}
        self._probe_ts: Optional[datetime] = None
        self._executor = ThreadPoolExecutor(max_workers=8)

        try:
            import boto3  # type: ignore
            import botocore  # type: ignore  # noqa: F401
            session = boto3.Session()
            creds = session.get_credentials()
            if creds is not None:
                resolved = creds.get_frozen_credentials()
                if resolved.access_key:
                    self._boto3 = boto3
                    self._credentials_ok = True
                    logger.info("AWS adapter: real mode — credentials found (%s)",
                                "sts/env" if resolved.token else "static/instance-profile")
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

        # Refresh on-demand prices if cache is stale (6-hour TTL)
        if (self._od_cache_ts is None
                or datetime.now(timezone.utc) - self._od_cache_ts > _PRICE_CACHE_TTL):
            self._od_cache = await loop.run_in_executor(
                self._executor, self._fetch_ondemand_prices
            )
            self._od_cache_ts = datetime.now(timezone.utc)
            logger.info("AWS on-demand price cache refreshed: %d entries", len(self._od_cache))

        # Refresh spot placement scores (10-minute TTL, batched per API limit)
        if (self._probe_ts is None
                or datetime.now(timezone.utc) - self._probe_ts > _PROBE_TTL):
            try:
                new_probe = await loop.run_in_executor(
                    self._executor, self._fetch_placement_scores
                )
                self._probe_cache = new_probe
                self._probe_ts = datetime.now(timezone.utc)
                logger.info("AWS spot placement scores refreshed: %d entries", len(new_probe))
            except Exception as exc:
                logger.warning("AWS spot placement scores failed: %s — keeping prior cache", exc)

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

        # Capacity blocks — run alongside region fetches, failures are non-fatal
        try:
            cb_skus = await loop.run_in_executor(self._executor, self._fetch_capacity_blocks)
            all_skus.extend(cb_skus)
            logger.info("AWS capacity blocks: %d offerings found", len(cb_skus))
        except Exception as exc:
            logger.warning("AWS capacity block fetch failed: %s", exc)

        logger.info("AWS real adapter: fetched %d SKUs across %d regions",
                    len(all_skus), len(_AWS_REGIONS))
        return all_skus

    def _fetch_region(self, region_id: str) -> list[GPUSku]:
        boto3 = self._boto3
        display, lat, lon, sov = _AWS_REGIONS[region_id]
        now = datetime.now(timezone.utc)
        ec2 = boto3.client("ec2", region_name=region_id)

        # ── AZ-level offerings (paginated) ────────────────────────────────
        # Querying at AZ level tells us which specific AZs have each instance
        # type — a stronger availability signal than region-level presence.
        offered_azs: dict[str, set[str]] = {}  # instance → set of AZs
        try:
            paginator = ec2.get_paginator("describe_instance_type_offerings")
            pages = paginator.paginate(
                LocationType="availability-zone",
                Filters=[
                    {"Name": "instance-type", "Values": list(_INSTANCE_META)},
                ],
            )
            for page in pages:
                for offering in page["InstanceTypeOfferings"]:
                    itype = offering["InstanceType"]
                    az = offering["Location"]
                    # Only count AZs that belong to this region
                    if az.startswith(region_id):
                        offered_azs.setdefault(itype, set()).add(az)
        except Exception as exc:
            logger.warning("describe_instance_type_offerings failed %s: %s", region_id, exc)
            # Assume all offered with 1 AZ on error
            offered_azs = {itype: {region_id + "a"} for itype in _INSTANCE_META}

        # ── Spot prices — track distinct AZs per instance for availability ──
        # More AZs reporting spot prices → more readily available spot capacity.
        spot_gpu_hr: dict[str, float] = {}      # cheapest price per instance
        spot_az_count: dict[str, int] = {}      # distinct AZs seen per instance
        spot_az_seen: dict[str, set[str]] = {}  # working set
        try:
            spot_resp = ec2.describe_spot_price_history(
                InstanceTypes=list(_INSTANCE_META),
                ProductDescriptions=["Linux/UNIX"],
                MaxResults=len(_INSTANCE_META) * 6,
            )
            for sp in spot_resp.get("SpotPriceHistory", []):
                itype = sp["InstanceType"]
                az = sp.get("AvailabilityZone", "")
                total_hr = float(sp["SpotPrice"])
                gpu_count = _INSTANCE_META[itype][1]
                per_gpu = total_hr / gpu_count
                if itype not in spot_gpu_hr or per_gpu < spot_gpu_hr[itype]:
                    spot_gpu_hr[itype] = per_gpu
                spot_az_seen.setdefault(itype, set()).add(az)
            spot_az_count = {k: len(v) for k, v in spot_az_seen.items()}
        except Exception as exc:
            logger.warning("describe_spot_price_history failed %s: %s", region_id, exc)

        # ── Build SKU list ────────────────────────────────────────────────
        results: list[GPUSku] = []
        for instance, (gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _INSTANCE_META.items():
            az_set = offered_azs.get(instance, set())
            if not az_set:
                continue  # not available in this region at all

            od_per_gpu = self._od_cache.get(
                (region_id, instance),
                _FALLBACK_GPU_HR.get(instance, 3.0),
            )

            # On-demand availability from spot placement scores (10-min cache)
            od_avail = self._probe_cache.get((region_id, instance), AvailabilityTier.MEDIUM)
            results.append(self._sku(
                region_id, display, lat, lon, sov, now, instance,
                gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                PricingType.ON_DEMAND, od_per_gpu, od_avail, None,
            ))

            # Spot SKU — only emit if we got a real spot price
            if instance in spot_gpu_hr:
                spot_avail = _spot_avail_from_az_count(spot_az_count.get(instance, 0))
                results.append(self._sku(
                    region_id, display, lat, lon, sov, now, instance,
                    gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.SPOT, spot_gpu_hr[instance], spot_avail, None,
                ))

        return results

    def _fetch_capacity_blocks(self) -> list[GPUSku]:
        """
        Fetches available AWS Capacity Block offerings (ML-targeted future reservations).
        Shell uses these weekly; this makes them visible alongside spot/on-demand.
        Capacity blocks are guaranteed capacity, so availability is always HIGH.
        IAM requires ec2:DescribeCapacityBlockOfferings.
        """
        boto3 = self._boto3
        result: list[GPUSku] = []
        now = datetime.now(timezone.utc)

        for region_id, (display, lat, lon, sov) in _AWS_REGIONS.items():
            ec2 = boto3.client("ec2", region_name=region_id)
            for instance, (gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _INSTANCE_META.items():
                try:
                    resp = ec2.describe_capacity_block_offerings(
                        InstanceType=instance,
                        InstanceCount=1,
                    )
                    seen: set[int] = set()
                    for offering in resp.get("CapacityBlockOfferings", []):
                        duration_hrs = offering.get("CapacityBlockDurationHours", 0)
                        upfront = float(offering.get("UpfrontFee", 0) or 0)
                        if duration_hrs <= 0 or upfront <= 0 or duration_hrs in seen:
                            continue
                        seen.add(duration_hrs)
                        price_per_gpu_hr = (upfront / duration_hrs) / gpu_count
                        sku = self._sku(
                            region_id, display, lat, lon, sov, now, instance,
                            gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                            PricingType.CAPACITY_BLOCK, price_per_gpu_hr,
                            AvailabilityTier.HIGH, None,
                        )
                        # Attach block duration so the UI can show "168h block" etc.
                        sku = sku.model_copy(update={"capacity_block_duration_hours": float(duration_hrs)})
                        result.append(sku)
                except Exception as exc:
                    logger.debug("describe_capacity_block_offerings %s/%s: %s",
                                 region_id, instance, exc)

        return result

    def _fetch_placement_scores(self) -> dict[tuple[str, str], AvailabilityTier]:
        """
        Calls get_spot_placement_scores in batches of ≤25 instance types (API limit).
        Returns {(region_id, instance_type): AvailabilityTier}.
        Score 8-10 → HIGH, 5-7 → MEDIUM, 1-4 → LOW, 0/absent → UNAVAILABLE.
        """
        boto3 = self._boto3
        ec2 = boto3.client("ec2", region_name="us-east-1")
        region_names = list(_AWS_REGIONS)
        result: dict[tuple[str, str], AvailabilityTier] = {}
        instance_list = list(_INSTANCE_META)

        for batch_start in range(0, len(instance_list), _PLACEMENT_SCORE_BATCH):
            batch = instance_list[batch_start: batch_start + _PLACEMENT_SCORE_BATCH]
            try:
                resp = ec2.get_spot_placement_scores(
                    InstanceTypes=batch,
                    TargetCapacity=1,
                    RegionNames=region_names,
                    SingleAvailabilityZone=False,
                )
                for rec in resp.get("SpotPlacementScores", []):
                    region = rec.get("Region", "")
                    score = rec.get("Score", 0)
                    instance = rec.get("InstanceType", "")
                    if region not in _AWS_REGIONS or instance not in _INSTANCE_META:
                        continue
                    if score >= 8:
                        tier = AvailabilityTier.HIGH
                    elif score >= 5:
                        tier = AvailabilityTier.MEDIUM
                    elif score >= 1:
                        tier = AvailabilityTier.LOW
                    else:
                        tier = AvailabilityTier.UNAVAILABLE
                    result[(region, instance)] = tier
            except Exception as exc:
                logger.debug("get_spot_placement_scores batch failed: %s", exc)

        return result

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
                base = _FALLBACK_GPU_HR.get(instance, 3.0)
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
