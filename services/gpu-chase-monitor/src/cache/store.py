from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from src.models.gpu_region import (
    AvailabilityTier,
    CloudProvider,
    GPUFamily,
    GPUSku,
    PriceBand,
    RegionSummary,
)

logger = logging.getLogger(__name__)

# How long before a region's data is considered stale (seconds)
STALE_THRESHOLD_SECONDS = 300
REFRESH_INTERVAL_SECONDS = 60


class GPUCatalogStore:
    """In-process catalog store.  Postgres + Redis in production."""

    def __init__(self) -> None:
        self._skus: list[GPUSku] = []
        self._last_refresh: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def update(self, skus: list[GPUSku]) -> None:
        async with self._lock:
            now = datetime.now(timezone.utc)
            # Tag staleness for any sku fetched before this update
            for sku in skus:
                age = (now - sku.refreshed_at).total_seconds()
                sku.staleness_seconds = max(0.0, age)
            self._skus = skus
            self._last_refresh = now
            logger.info("Catalog store updated: %d SKUs", len(skus))

    async def get_all_skus(
        self,
        providers: Optional[list[CloudProvider]] = None,
        gpu_families: Optional[list[GPUFamily]] = None,
        price_bands: Optional[list[PriceBand]] = None,
        availability: Optional[list[AvailabilityTier]] = None,
        sovereignty_zones: Optional[list[str]] = None,
    ) -> list[GPUSku]:
        async with self._lock:
            result = self._skus

        if providers:
            result = [s for s in result if s.provider in providers]
        if gpu_families:
            result = [s for s in result if s.gpu_family in gpu_families]
        if price_bands:
            result = [s for s in result if s.price_band in price_bands]
        if availability:
            result = [s for s in result if s.availability in availability]
        if sovereignty_zones:
            zones_set = set(sovereignty_zones)
            result = [s for s in result if zones_set.issubset(set(s.sovereignty_zones))]

        return result

    async def get_region_summaries(
        self,
        providers: Optional[list[CloudProvider]] = None,
        gpu_families: Optional[list[GPUFamily]] = None,
        price_bands: Optional[list[PriceBand]] = None,
        sovereignty_zones: Optional[list[str]] = None,
    ) -> list[RegionSummary]:
        skus = await self.get_all_skus(
            providers=providers,
            gpu_families=gpu_families,
            price_bands=price_bands,
            sovereignty_zones=sovereignty_zones,
        )

        # Group by (provider, region)
        groups: dict[tuple[CloudProvider, str], list[GPUSku]] = {}
        for sku in skus:
            key = (sku.provider, sku.region)
            groups.setdefault(key, []).append(sku)

        summaries: list[RegionSummary] = []
        tier_order = [
            AvailabilityTier.HIGH,
            AvailabilityTier.MEDIUM,
            AvailabilityTier.LOW,
            AvailabilityTier.UNAVAILABLE,
        ]

        for (provider, region), region_skus in groups.items():
            best_avail = sorted(
                region_skus,
                key=lambda s: tier_order.index(s.availability),
            )[0].availability

            cheapest = min(region_skus, key=lambda s: s.price_per_gpu_hour)
            sample = region_skus[0]

            summaries.append(RegionSummary(
                provider=provider,
                region=region,
                display_region=sample.display_region,
                latitude=sample.latitude,
                longitude=sample.longitude,
                best_availability=best_avail,
                best_price_per_gpu_hour=cheapest.price_per_gpu_hour,
                price_band=cheapest.price_band,
                gpu_families=list({s.gpu_family for s in region_skus}),
                sku_count=len(region_skus),
                refreshed_at=sample.refreshed_at,
                staleness_seconds=sample.staleness_seconds,
            ))

        return summaries

    async def get_skus_for_region(
        self,
        provider: CloudProvider,
        region: str,
    ) -> list[GPUSku]:
        skus = await self.get_all_skus()
        return [s for s in skus if s.provider == provider and s.region == region]

    @property
    def last_refresh(self) -> Optional[datetime]:
        return self._last_refresh
