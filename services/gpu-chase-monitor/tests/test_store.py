import asyncio
import pytest
import pytest_asyncio
from src.adapters.aws import AWSAdapter
from src.cache.store import GPUCatalogStore
from src.models.gpu_region import AvailabilityTier, CloudProvider, PriceBand


@pytest_asyncio.fixture
async def loaded_store():
    store = GPUCatalogStore()
    adapter = AWSAdapter()
    skus = adapter._fetch_simulated()
    await store.update(skus)
    return store


@pytest.mark.asyncio
async def test_store_returns_all_skus(loaded_store):
    skus = await loaded_store.get_all_skus()
    assert len(skus) > 0


@pytest.mark.asyncio
async def test_store_filters_by_provider(loaded_store):
    skus = await loaded_store.get_all_skus(providers=[CloudProvider.AWS])
    assert all(s.provider == CloudProvider.AWS for s in skus)


@pytest.mark.asyncio
async def test_store_filters_by_price_band(loaded_store):
    skus = await loaded_store.get_all_skus(price_bands=[PriceBand.PREMIUM, PriceBand.ULTRA])
    assert all(s.price_band in (PriceBand.PREMIUM, PriceBand.ULTRA) for s in skus)


@pytest.mark.asyncio
async def test_region_summaries_are_unique(loaded_store):
    summaries = await loaded_store.get_region_summaries()
    keys = [(s.provider, s.region) for s in summaries]
    assert len(keys) == len(set(keys)), "Each (provider, region) pair should appear once"


@pytest.mark.asyncio
async def test_region_summary_best_availability(loaded_store):
    summaries = await loaded_store.get_region_summaries()
    for summary in summaries:
        assert summary.best_availability in list(AvailabilityTier)
        assert summary.best_price_per_gpu_hour > 0
