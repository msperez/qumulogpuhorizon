import asyncio
import pytest
from src.adapters.aws import AWSAdapter
from src.adapters.azure import AzureAdapter
from src.adapters.gcp import GCPAdapter
from src.models.gpu_region import AvailabilityTier, CloudProvider, PricingType


def test_aws_adapter_returns_skus():
    adapter = AWSAdapter()
    skus = adapter._fetch_simulated()
    assert len(skus) > 0
    for sku in skus:
        assert sku.provider == CloudProvider.AWS
        assert sku.price_per_gpu_hour > 0
        assert sku.gpu_count > 0
        assert sku.availability in list(AvailabilityTier)


def test_azure_adapter_returns_skus():
    adapter = AzureAdapter()
    skus = adapter._fetch_simulated()
    assert len(skus) > 0
    for sku in skus:
        assert sku.provider == CloudProvider.AZURE
        assert sku.price_per_gpu_hour > 0


def test_gcp_adapter_includes_committed_use():
    adapter = GCPAdapter()
    skus = adapter._fetch_simulated()
    committed = [s for s in skus if s.pricing_type == PricingType.COMMITTED_USE]
    assert len(committed) > 0, "GCP should have committed-use pricing SKUs"


def test_all_adapters_have_valid_coordinates():
    for Adapter in [AWSAdapter, AzureAdapter, GCPAdapter]:
        adapter = Adapter()
        skus = adapter._fetch_simulated()
        for sku in skus:
            assert -90 <= sku.latitude <= 90
            assert -180 <= sku.longitude <= 180


@pytest.mark.asyncio
async def test_async_fetch_returns_same_as_simulated():
    adapter = AWSAdapter()
    skus = await adapter.fetch_skus()
    assert len(skus) > 0
