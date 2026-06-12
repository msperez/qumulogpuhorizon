from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
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

_GCP_REGIONS: dict[str, tuple[str, float, float, list[str]]] = {
    "us-central1":          ("US Central (Iowa)",          41.85,  -93.62, ["US"]),
    "us-east1":             ("US East (S. Carolina)",      33.84,  -81.16, ["US"]),
    "us-east4":             ("US East (N. Virginia)",      38.95,  -77.33, ["US"]),
    "us-east5":             ("US East (Columbus)",         39.96,  -82.99, ["US"]),
    "us-south1":            ("US South (Dallas)",          32.78,  -96.81, ["US"]),
    "us-west1":             ("US West (Oregon)",           45.60, -121.18, ["US"]),
    "us-west4":             ("US West (Las Vegas)",        36.17, -115.14, ["US"]),
    "northamerica-northeast1": ("Canada (Montréal)",       45.50,  -73.57, ["CA"]),
    "southamerica-east1":   ("South America (São Paulo)", -23.55,  -46.63, ["BR"]),
    "europe-west1":         ("Europe West (Belgium)",      50.45,    3.81, ["EU", "EEA", "BE"]),
    "europe-west2":         ("Europe West (London)",       51.51,   -0.13, ["EU", "EEA", "UK", "GB"]),
    "europe-west4":         ("Europe West (Netherlands)",  52.37,    4.89, ["EU", "EEA", "NL"]),
    "europe-west6":         ("Europe West (Zürich)",       47.37,    8.54, ["EU", "EEA", "CH"]),
    "europe-west9":         ("Europe West (Paris)",        48.86,    2.35, ["EU", "EEA", "FR"]),
    "asia-east1":           ("Asia East (Taiwan)",         24.05,  120.55, ["TW"]),
    "asia-northeast1":      ("Asia Northeast (Tokyo)",     35.68,  139.69, ["JP"]),
    "asia-northeast3":      ("Asia Northeast (Seoul)",     37.57,  126.98, ["KR"]),
    "asia-south1":          ("Asia South (Mumbai)",        19.08,   72.88, ["IN"]),
    "asia-southeast1":      ("Asia Southeast (Singapore)",  1.35,  103.82, ["SG"]),
    "australia-southeast1": ("Australia Southeast",       -33.86,  151.21, ["AU"]),
    "me-central1":          ("Middle East (Doha)",         25.29,   51.53, ["QA"]),
}

# (machine_type, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem_gb, interconnect)
_GCP_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = [
    # H200 — a3-ultragpu (newest)
    ("a3-ultragpu-8g",  GPUFamily.NVIDIA_H200,  8,  208, 1872.0, 1128.0, "NVLink+ICI"),
    # H100 — a3-highgpu / a3-megagpu
    ("a3-highgpu-8g",   GPUFamily.NVIDIA_H100,  8,  208, 1872.0,  640.0, "NVLink"),
    ("a3-megagpu-8g",   GPUFamily.NVIDIA_H100,  8,  208, 1872.0,  640.0, "NVLink+SXM5"),
    # A100 — a2 family
    ("a2-highgpu-8g",   GPUFamily.NVIDIA_A100,  8,  96,   680.0,  320.0, "NVLink"),
    ("a2-ultragpu-8g",  GPUFamily.NVIDIA_A100,  8,  96,   680.0,  640.0, "NVLink"),
    ("a2-megagpu-16g",  GPUFamily.NVIDIA_A100, 16,  96,  1360.0,  320.0, "NVLink"),
    # L4 — g2-standard
    ("g2-standard-96",  GPUFamily.NVIDIA_L4,    8,  96,   384.0,  192.0, None),
    # T4 — n1 with attached GPU
    ("n1-standard-8",   GPUFamily.NVIDIA_T4,    1,  8,    30.0,   16.0,  None),
]

_FALLBACK_PRICES: dict[str, float] = {
    "a3-ultragpu-8g":  4.50,   # H200 (est.)
    "a3-highgpu-8g":   10.46,  # H100
    "a3-megagpu-8g":   12.00,  # H100 SXM5 (est.)
    "a2-highgpu-8g":   2.934,  # A100 40 GB
    "a2-ultragpu-8g":  3.80,   # A100 80 GB (est.)
    "a2-megagpu-16g":  2.934,  # A100 40 GB x16
    "g2-standard-96":  2.04,   # L4
    "n1-standard-8":   0.35,   # T4
}

# GCP accelerator type attached to each machine type
_MACHINE_ACCELERATOR: dict[str, str] = {
    "a3-ultragpu-8g":  "nvidia-h200-141gb",
    "a3-highgpu-8g":   "nvidia-h100-80gb",
    "a3-megagpu-8g":   "nvidia-h100-mega-80gb",
    "a2-highgpu-8g":   "nvidia-tesla-a100",
    "a2-ultragpu-8g":  "nvidia-a100-80gb",
    "a2-megagpu-16g":  "nvidia-tesla-a100",
    "g2-standard-96":  "nvidia-l4",
    "n1-standard-8":   "nvidia-tesla-t4",
}

# Zones sampled per region for availability checks
_REGION_ZONES: dict[str, list[str]] = {
    "us-central1":             ["us-central1-a", "us-central1-b", "us-central1-c"],
    "us-east1":                ["us-east1-b", "us-east1-c"],
    "us-east4":                ["us-east4-a", "us-east4-b"],
    "us-east5":                ["us-east5-a", "us-east5-b"],
    "us-south1":               ["us-south1-a", "us-south1-b"],
    "us-west1":                ["us-west1-a", "us-west1-b"],
    "us-west4":                ["us-west4-a", "us-west4-b"],
    "northamerica-northeast1": ["northamerica-northeast1-a", "northamerica-northeast1-b"],
    "southamerica-east1":      ["southamerica-east1-a", "southamerica-east1-b"],
    "europe-west1":            ["europe-west1-b", "europe-west1-c"],
    "europe-west2":            ["europe-west2-a", "europe-west2-b"],
    "europe-west4":            ["europe-west4-a", "europe-west4-b"],
    "europe-west6":            ["europe-west6-a", "europe-west6-b"],
    "europe-west9":            ["europe-west9-a", "europe-west9-b"],
    "asia-east1":              ["asia-east1-a", "asia-east1-b"],
    "asia-northeast1":         ["asia-northeast1-a", "asia-northeast1-b"],
    "asia-northeast3":         ["asia-northeast3-a", "asia-northeast3-b"],
    "asia-south1":             ["asia-south1-a", "asia-south1-b"],
    "asia-southeast1":         ["asia-southeast1-a", "asia-southeast1-b"],
    "australia-southeast1":    ["australia-southeast1-a"],
    "me-central1":             ["me-central1-a"],
}


def _price_band(price: float) -> PriceBand:
    if price < 1.0:  return PriceBand.ECONOMY
    if price < 5.0:  return PriceBand.STANDARD
    if price < 15.0: return PriceBand.PREMIUM
    return PriceBand.ULTRA


def _availability_tier(count: int) -> AvailabilityTier:
    if count == 0:  return AvailabilityTier.UNAVAILABLE
    if count < 4:   return AvailabilityTier.LOW
    if count < 20:  return AvailabilityTier.MEDIUM
    return AvailabilityTier.HIGH


class GCPAdapter(CloudAdapter):
    """
    Real mode: activated by GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CLOUD_PROJECT.
    Queries the Compute Engine API for machine type availability per zone and
    accelerator type offerings, then fetches SKU-level pricing from the Cloud
    Billing Catalog API.
    Falls back to simulation when credentials are absent.
    """
    provider = CloudProvider.GCP

    def __init__(self) -> None:
        self._project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self._use_real = bool(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or self._project
        )
        if self._use_real:
            try:
                from google.cloud import compute_v1  # type: ignore  # noqa: F401
                logger.info("GCP adapter: real mode (google-cloud-compute)")
            except ImportError:
                logger.warning("google-cloud-compute not installed — falling back to simulation")
                self._use_real = False

    async def fetch_skus(self) -> list[GPUSku]:
        if not self._use_real:
            logger.warning("GCP adapter: no credentials — skipping GCP data")
            return []
        return await self._fetch_real()

    # ------------------------------------------------------------------
    # Real GCP implementation
    # ------------------------------------------------------------------

    async def _fetch_real(self) -> list[GPUSku]:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, self._fetch_real_sync)

    def _fetch_real_sync(self) -> list[GPUSku]:
        from google.cloud import compute_v1  # type: ignore

        machine_client = compute_v1.MachineTypesClient()
        accel_client = compute_v1.AcceleratorTypesClient()
        now = self._now()
        results: list[GPUSku] = []

        # Fetch on-demand prices from Cloud Billing Catalog
        od_prices = self._fetch_billing_prices()

        for region_id, (display, lat, lon, sov) in _GCP_REGIONS.items():
            zones = _REGION_ZONES.get(region_id, [f"{region_id}-a"])

            # Check which machine types are available across zones in this region
            available_machines: set[str] = set()
            for zone in zones:
                try:
                    for mt in machine_client.list(project=self._project, zone=zone):
                        available_machines.add(mt.name)
                except Exception as exc:
                    logger.debug("GCP machine types failed %s/%s: %s", region_id, zone, exc)

            # Check accelerator availability (indicates GPU capacity exists)
            available_accels: set[str] = set()
            for zone in zones:
                try:
                    for at in accel_client.list(project=self._project, zone=zone):
                        available_accels.add(at.name)
                except Exception as exc:
                    logger.debug("GCP accelerator types failed %s/%s: %s", region_id, zone, exc)

            for (machine, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _GCP_SKUS:
                base_name = machine.split("-")[0] + "-" + machine.split("-")[1]
                if available_machines and not any(m.startswith(base_name) for m in available_machines):
                    continue

                accel = _MACHINE_ACCELERATOR.get(machine, "")
                avail_tier = (
                    AvailabilityTier.MEDIUM
                    if (not available_accels or accel in available_accels)
                    else AvailabilityTier.UNAVAILABLE
                )

                base_price = od_prices.get(machine, _FALLBACK_PRICES.get(machine, 0.0))
                per_gpu_od = base_price / gpu_count

                # On-demand
                results.append(self._make_sku(
                    region_id, display, lat, lon, sov, now,
                    machine, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.ON_DEMAND, per_gpu_od, avail_tier, None,
                ))

                # Spot (GCP preemptible) — ~60–70% discount
                spot_per_gpu = per_gpu_od * 0.35
                results.append(self._make_sku(
                    region_id, display, lat, lon, sov, now,
                    machine, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.SPOT, spot_per_gpu, AvailabilityTier.LOW, None,
                ))

                # Committed use (1-year) — ~30% discount
                committed_per_gpu = per_gpu_od * 0.70
                results.append(self._make_sku(
                    region_id, display, lat, lon, sov, now,
                    machine, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.COMMITTED_USE, committed_per_gpu, avail_tier, None,
                ))

        logger.info("GCP real adapter: fetched %d SKUs", len(results))
        return results

    def _fetch_billing_prices(self) -> dict[str, float]:
        """
        Queries the Cloud Billing Catalog for Compute Engine GPU machine pricing.
        Returns {machine_type: total_instance_price_per_hour}.
        Requires billing API access; returns empty dict on any failure so the
        caller gracefully falls back to hardcoded prices.
        """
        try:
            from google.cloud import billing_v1  # type: ignore

            catalog = billing_v1.CloudCatalogClient()
            # Compute Engine service ID
            ce_service = "services/6F81-5844-456A"
            prices: dict[str, float] = {}

            for sku in catalog.list_skus(parent=ce_service):
                desc = sku.description.lower()
                for machine, *_ in _GCP_SKUS:
                    # Match by machine family name in the SKU description
                    family = machine.split("-")[0].upper()  # e.g. "A2", "A3", "N1"
                    if family.lower() in desc and "gpu" in desc:
                        for tier in sku.pricing_info:
                            expr = tier.pricing_expression
                            if expr.tiered_rates:
                                unit_price = expr.tiered_rates[0].unit_price
                                price = unit_price.units + unit_price.nanos / 1e9
                                if price > 0 and machine not in prices:
                                    prices[machine] = price
            return prices
        except Exception as exc:
            logger.debug("GCP billing prices fetch failed: %s", exc)
            return {}

    @staticmethod
    def _make_sku(
        region_id: str, display: str, lat: float, lon: float, sov: list[str],
        now: datetime,
        machine: str, gpu_family: GPUFamily, gpu_count: int, vcpus: int,
        mem_gb: float, gpu_mem: float, interconnect: str | None,
        pricing_type: PricingType, price_per_gpu_hour: float,
        availability: AvailabilityTier, available_count: int | None,
    ) -> GPUSku:
        return GPUSku(
            sku_id=f"gcp:{region_id}:{machine}:{pricing_type.value}",
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

