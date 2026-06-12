from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

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

# Azure Retail Prices API — publicly accessible, no credentials required
_AZURE_RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"

_AZURE_REGIONS: dict[str, tuple[str, float, float, list[str]]] = {
    "eastus":             ("East US",              37.36,  -79.03, ["US"]),
    "eastus2":            ("East US 2",            36.67,  -78.37, ["US"]),
    "westus2":            ("West US 2",            47.23, -119.85, ["US"]),
    "westus3":            ("West US 3",            33.45, -112.07, ["US"]),
    "northeurope":        ("North Europe",         53.30,   -6.26, ["EU", "EEA", "IE"]),
    "westeurope":         ("West Europe",          52.37,    4.89, ["EU", "EEA", "NL"]),
    "germanywestcentral": ("Germany West Central", 50.11,    8.68, ["EU", "EEA", "DE"]),
    "japaneast":          ("Japan East",           35.68,  139.77, ["JP"]),
    "southeastasia":      ("Southeast Asia",        1.29,  103.82, ["SG"]),
    "australiaeast":      ("Australia East",      -33.86,  151.21, ["AU"]),
    "canadacentral":      ("Canada Central",       43.65,  -79.38, ["CA"]),
}

# (arm_sku_name, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem_gb, interconnect)
_AZURE_SKUS: list[tuple[str, GPUFamily, int, int, float, float, str | None]] = [
    ("Standard_ND96asr_v4",         GPUFamily.NVIDIA_A100, 8, 96,  900.0,  40.0, "InfiniBand"),
    ("Standard_ND96amsr_A100_v4",   GPUFamily.NVIDIA_A100, 8, 96,  1900.0, 80.0, "InfiniBand"),
    ("Standard_ND96isr_H100_v5",    GPUFamily.NVIDIA_H100, 8, 96,  1900.0, 80.0, "InfiniBand400"),
    ("Standard_NC24ads_A100_v4",    GPUFamily.NVIDIA_A100, 1, 24,  220.0,  80.0, None),
    ("Standard_NV72ads_A10_v5",     GPUFamily.NVIDIA_A10G, 4, 72,  880.0,  24.0, None),
]

_FALLBACK_PRICES: dict[str, float] = {
    "Standard_ND96asr_v4":        3.40,
    "Standard_ND96amsr_A100_v4":  4.25,
    "Standard_ND96isr_H100_v5":   9.97,
    "Standard_NC24ads_A100_v4":   3.67,
    "Standard_NV72ads_A10_v5":    0.98,
}

# Maps arm_sku_name fragment to the skuName keyword used in the Retail Prices API
_SKU_PRICE_KEYWORD: dict[str, str] = {
    "Standard_ND96asr_v4":        "ND96asr A100 v4",
    "Standard_ND96amsr_A100_v4":  "ND96amsr A100 v4",
    "Standard_ND96isr_H100_v5":   "ND96isr H100 v5",
    "Standard_NC24ads_A100_v4":   "NC24ads A100 v4",
    "Standard_NV72ads_A10_v5":    "NV72ads A10 v5",
}


def _price_band(price: float) -> PriceBand:
    if price < 1.0:  return PriceBand.ECONOMY
    if price < 5.0:  return PriceBand.STANDARD
    if price < 15.0: return PriceBand.PREMIUM
    return PriceBand.ULTRA



class AzureAdapter(CloudAdapter):
    """
    Two real-data tiers:
      1. Public Retail Prices API — works with NO credentials (pricing only).
      2. azure-mgmt-compute       — requires AZURE_SUBSCRIPTION_ID (pricing + availability).
    Falls back to simulation when both are unavailable.
    """
    provider = CloudProvider.AZURE

    def __init__(self) -> None:
        self._use_mgmt = bool(os.getenv("AZURE_SUBSCRIPTION_ID"))
        if self._use_mgmt:
            try:
                from azure.mgmt.compute import ComputeManagementClient  # type: ignore  # noqa: F401
                from azure.identity import DefaultAzureCredential       # type: ignore  # noqa: F401
                logger.info("Azure adapter: real mode (azure-mgmt-compute)")
            except ImportError:
                logger.warning("azure-mgmt-compute not installed — falling back to public Retail Prices API")
                self._use_mgmt = False

    async def fetch_skus(self) -> list[GPUSku]:
        if self._use_mgmt:
            return await self._fetch_with_credentials()
        return await self._fetch_public_pricing()

    # ------------------------------------------------------------------
    # Public Azure Retail Prices API — no credentials needed
    # ------------------------------------------------------------------

    async def _fetch_public_pricing(self) -> list[GPUSku]:
        """
        Calls https://prices.azure.com/api/retail/prices — a publicly documented,
        unauthenticated REST endpoint that returns real Azure VM pricing.
        Docs: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
        """
        now = self._now()
        # Fetch prices for all GPU VM families in one pass per SKU keyword
        od_prices: dict[tuple[str, str], float] = {}   # (region, arm_sku) → price/hr
        spot_prices: dict[tuple[str, str], float] = {}

        async with httpx.AsyncClient(timeout=20) as client:
            for arm_sku, keyword in _SKU_PRICE_KEYWORD.items():
                for price_type, store in [("Consumption", od_prices), ("DevTestConsumption", None)]:
                    try:
                        params = {
                            "$filter": (
                                f"serviceName eq 'Virtual Machines' "
                                f"and priceType eq '{price_type}' "
                                f"and contains(skuName, '{keyword}')"
                            )
                        }
                        resp = await client.get(_AZURE_RETAIL_PRICES_URL, params=params)
                        resp.raise_for_status()
                        for item in resp.json().get("Items", []):
                            region = item.get("armRegionName", "")
                            # Spot items have "Spot" in skuName
                            is_spot = "spot" in item.get("skuName", "").lower()
                            price = float(item.get("retailPrice", 0))
                            if not price:
                                continue
                            if is_spot:
                                key = (region, arm_sku)
                                if key not in spot_prices or price < spot_prices[key]:
                                    spot_prices[key] = price
                            else:
                                key = (region, arm_sku)
                                if key not in od_prices or price < od_prices[key]:
                                    od_prices[key] = price
                    except Exception as exc:
                        logger.debug("Retail Prices API call failed for %s: %s", arm_sku, exc)

        # Build SKU list from the fetched prices
        results: list[GPUSku] = []

        for region_id, (display, lat, lon, sov) in _AZURE_REGIONS.items():
            for (arm_sku, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect) in _AZURE_SKUS:
                od_total = od_prices.get((region_id, arm_sku))
                if od_total is None:
                    continue  # SKU not available in this region per the API

                per_gpu_od = od_total / gpu_count
                results.append(self._make_sku(
                    region_id, display, lat, lon, sov, now,
                    arm_sku, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                    PricingType.ON_DEMAND, per_gpu_od,
                    availability=AvailabilityTier.MEDIUM,
                    available_count=None,
                    simulated=False,
                ))

                spot_total = spot_prices.get((region_id, arm_sku))
                if spot_total:
                    per_gpu_spot = spot_total / gpu_count
                    results.append(self._make_sku(
                        region_id, display, lat, lon, sov, now,
                        arm_sku, gpu_family, gpu_count, vcpus, mem_gb, gpu_mem, interconnect,
                        PricingType.SPOT, per_gpu_spot,
                        availability=AvailabilityTier.LOW,
                        available_count=None,
                        simulated=False,
                    ))

        if not results:
            logger.warning("Azure Retail Prices API returned no usable GPU SKUs — check network or API availability")
            return []

        logger.info("Azure Retail Prices API: fetched %d real SKUs", len(results))
        return results

    # ------------------------------------------------------------------
    # Full real mode with azure-mgmt-compute credentials
    # ------------------------------------------------------------------

    async def _fetch_with_credentials(self) -> list[GPUSku]:  # pragma: no cover
        from azure.identity import DefaultAzureCredential     # type: ignore
        from azure.mgmt.compute import ComputeManagementClient  # type: ignore

        subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
        credential = DefaultAzureCredential()
        compute_client = ComputeManagementClient(credential, subscription_id)
        now = self._now()

        # Fetch which SKUs are available per region
        available_skus: dict[tuple[str, str], bool] = {}
        try:
            for sku in compute_client.resource_skus.list():
                if sku.resource_type != "virtualMachines":
                    continue
                if not any(sku.name == s[0] for s in _AZURE_SKUS):
                    continue
                for loc in (sku.locations or []):
                    region = loc.lower().replace(" ", "")
                    restrictions = sku.restrictions or []
                    not_available = any(
                        r.reason_code == "NotAvailableForSubscription"
                        for r in restrictions
                    )
                    available_skus[(region, sku.name)] = not not_available
        except Exception as exc:
            logger.warning("azure-mgmt-compute resource_skus failed: %s", exc)

        base_results = await self._fetch_public_pricing()

        # Annotate availability from credentials
        for sku in base_results:
            region_norm = sku.region.lower().replace(" ", "")
            arm_name = sku.sku_id.split(":")[2]
            is_available = available_skus.get((region_norm, arm_name), True)
            if not is_available:
                sku.availability = AvailabilityTier.UNAVAILABLE

        return base_results

    @staticmethod
    def _make_sku(
        region_id: str, display: str, lat: float, lon: float, sov: list[str],
        now: datetime,
        arm_sku: str, gpu_family: GPUFamily, gpu_count: int, vcpus: int,
        mem_gb: float, gpu_mem: float, interconnect: str | None,
        pricing_type: PricingType, price_per_gpu_hour: float,
        availability: AvailabilityTier, available_count: int | None,
        simulated: bool = False,
    ) -> GPUSku:
        return GPUSku(
            sku_id=f"azure:{region_id}:{arm_sku}:{pricing_type.value}",
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
            price_per_gpu_hour=round(price_per_gpu_hour, 4),
            price_band=_price_band(price_per_gpu_hour),
            availability=availability,
            available_count=available_count,
            latitude=lat,
            longitude=lon,
            sovereignty_zones=sov,
            refreshed_at=now,
            staleness_seconds=0.0,
            simulated=simulated,
        )

