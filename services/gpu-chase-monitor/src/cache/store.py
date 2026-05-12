from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from src.models.gpu_region import (
    AvailabilityTier,
    CapacityAlert,
    CapacityThreshold,
    CloudProvider,
    CrossRegionEntry,
    CrossRegionSummary,
    GPUFamily,
    GPUSku,
    PriceBand,
    PricingType,
    RegionSummary,
)

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SECONDS = 300
REFRESH_INTERVAL_SECONDS = 60


class GPUCatalogStore:
    """In-process catalog store.  Postgres + Redis in production."""

    def __init__(self) -> None:
        self._skus: list[GPUSku] = []
        self._last_refresh: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._thresholds: list[CapacityThreshold] = []
        # Track which thresholds already fired to avoid spam (reset on drop)
        self._fired: set[str] = set()

    async def update(self, skus: list[GPUSku]) -> None:
        async with self._lock:
            now = datetime.now(timezone.utc)
            for sku in skus:
                age = (now - sku.refreshed_at).total_seconds()
                sku.staleness_seconds = max(0.0, age)
            self._skus = skus
            self._last_refresh = now
            logger.info("Catalog store updated: %d SKUs", len(skus))

        # Threshold check runs outside the lock so callbacks don't deadlock
        await self._check_thresholds(skus)

    async def _check_thresholds(self, skus: list[GPUSku]) -> None:
        if not self._thresholds:
            return

        for threshold in self._thresholds:
            matching = [
                s for s in skus
                if s.region == threshold.region
                and s.provider == threshold.provider
                and s.availability != AvailabilityTier.UNAVAILABLE
                and (threshold.gpu_family is None or s.gpu_family == threshold.gpu_family)
                and (threshold.pricing_type is None or s.pricing_type == threshold.pricing_type)
            ]
            total_gpus = sum(s.gpu_count for s in matching)

            if total_gpus >= threshold.min_gpu_count:
                if threshold.threshold_id not in self._fired:
                    self._fired.add(threshold.threshold_id)
                    alert = CapacityAlert(
                        threshold_id=threshold.threshold_id,
                        provider=threshold.provider,
                        region=threshold.region,
                        gpu_family=threshold.gpu_family,
                        pricing_type=threshold.pricing_type,
                        available_gpu_count=total_gpus,
                        triggered_at=datetime.now(timezone.utc),
                    )
                    asyncio.create_task(self._fire_callback(threshold.callback_url, alert))
                    logger.info("Capacity threshold %s crossed: %d GPUs in %s/%s",
                                threshold.threshold_id, total_gpus,
                                threshold.provider.value, threshold.region)
            else:
                # Reset so it can fire again if capacity drops and recovers
                self._fired.discard(threshold.threshold_id)

    @staticmethod
    async def _fire_callback(url: str, alert: CapacityAlert) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=alert.model_dump(mode="json"))
            logger.info("Capacity alert posted to %s", url)
        except Exception as exc:
            logger.warning("Capacity alert callback failed (%s): %s", url, exc)

    def register_threshold(self, threshold: CapacityThreshold) -> None:
        self._thresholds = [t for t in self._thresholds
                            if t.threshold_id != threshold.threshold_id]
        self._thresholds.append(threshold)
        self._fired.discard(threshold.threshold_id)

    def remove_threshold(self, threshold_id: str) -> bool:
        before = len(self._thresholds)
        self._thresholds = [t for t in self._thresholds if t.threshold_id != threshold_id]
        self._fired.discard(threshold_id)
        return len(self._thresholds) < before

    def list_thresholds(self) -> list[CapacityThreshold]:
        return list(self._thresholds)

    async def get_all_skus(
        self,
        providers: Optional[list[CloudProvider]] = None,
        gpu_families: Optional[list[GPUFamily]] = None,
        price_bands: Optional[list[PriceBand]] = None,
        availability: Optional[list[AvailabilityTier]] = None,
        pricing_types: Optional[list[PricingType]] = None,
        sovereignty_zones: Optional[list[str]] = None,
    ) -> list[GPUSku]:
        async with self._lock:
            result = list(self._skus)

        if providers:
            result = [s for s in result if s.provider in providers]
        if gpu_families:
            result = [s for s in result if s.gpu_family in gpu_families]
        if price_bands:
            result = [s for s in result if s.price_band in price_bands]
        if availability:
            result = [s for s in result if s.availability in availability]
        if pricing_types:
            result = [s for s in result if s.pricing_type in pricing_types]
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

        groups: dict[tuple[CloudProvider, str], list[GPUSku]] = {}
        for sku in skus:
            key = (sku.provider, sku.region)
            groups.setdefault(key, []).append(sku)

        tier_order = [
            AvailabilityTier.HIGH,
            AvailabilityTier.MEDIUM,
            AvailabilityTier.LOW,
            AvailabilityTier.UNAVAILABLE,
        ]

        summaries: list[RegionSummary] = []
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
                pricing_types=list({s.pricing_type for s in region_skus}),
                sku_count=len(region_skus),
                refreshed_at=sample.refreshed_at,
                staleness_seconds=sample.staleness_seconds,
            ))

        return summaries

    async def get_cross_region_summary(
        self,
        providers: Optional[list[CloudProvider]] = None,
        gpu_families: Optional[list[GPUFamily]] = None,
        pricing_types: Optional[list[PricingType]] = None,
    ) -> CrossRegionSummary:
        """
        Unified view across all regions: for each (instance_type, pricing_type) combination,
        show every region that has it available and the best price. This is the
        anti-isolated-islands view Shell needs to see multi-region capacity holistically.
        """
        skus = await self.get_all_skus(
            providers=providers,
            gpu_families=gpu_families,
            pricing_types=pricing_types,
        )
        # Only include available SKUs
        skus = [s for s in skus if s.availability != AvailabilityTier.UNAVAILABLE]

        # Group by (instance_type derived from sku_id, pricing_type)
        groups: dict[tuple[str, PricingType], list[GPUSku]] = {}
        for sku in skus:
            # sku_id format: provider:region:instance:pricing_type
            parts = sku.sku_id.split(":")
            instance = parts[2] if len(parts) >= 3 else sku.sku_id
            key = (instance, sku.pricing_type)
            groups.setdefault(key, []).append(sku)

        entries: list[CrossRegionEntry] = []
        for (instance, pricing_type), group_skus in sorted(groups.items()):
            best = min(group_skus, key=lambda s: s.price_per_gpu_hour)
            entries.append(CrossRegionEntry(
                instance_type=instance,
                gpu_family=best.gpu_family,
                gpu_count=best.gpu_count,
                pricing_type=pricing_type,
                available_regions=sorted({s.region for s in group_skus}),
                best_price_per_gpu_hour=best.price_per_gpu_hour,
                best_region=best.region,
                best_provider=best.provider,
            ))

        return CrossRegionSummary(
            generated_at=datetime.now(timezone.utc),
            entries=entries,
        )

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
