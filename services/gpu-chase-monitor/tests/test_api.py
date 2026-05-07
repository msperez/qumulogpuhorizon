import pytest
from fastapi.testclient import TestClient
from src.main import app, _store
from src.adapters.aws import AWSAdapter


@pytest.fixture(autouse=True)
def seed_store():
    import asyncio
    adapter = AWSAdapter()
    skus = adapter._fetch_simulated()
    asyncio.get_event_loop().run_until_complete(_store.update(skus))


client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_regions():
    r = client.get("/api/v1/regions")
    assert r.status_code == 200
    data = r.json()
    assert data["total_regions"] > 0
    assert len(data["regions"]) == data["total_regions"]


def test_list_regions_filter_provider():
    r = client.get("/api/v1/regions?provider=aws")
    assert r.status_code == 200
    for region in r.json()["regions"]:
        assert region["provider"] == "aws"


def test_region_skus_returns_skus():
    # Get any region from the catalog first
    regions = client.get("/api/v1/regions").json()["regions"]
    assert len(regions) > 0
    region = regions[0]
    r = client.get(f"/api/v1/regions/{region['provider']}/{region['region']}/skus")
    assert r.status_code == 200
    data = r.json()
    assert len(data["skus"]) > 0


def test_region_skus_not_found():
    r = client.get("/api/v1/regions/aws/us-fake-99/skus")
    assert r.status_code == 404


def test_configure_spoke():
    # Get a real sku_id from the catalog
    regions = client.get("/api/v1/regions/aws/us-east-1/skus").json()
    sku = regions["skus"][0]

    r = client.post("/api/v1/configure/spoke", json={
        "provider": "aws",
        "region": "us-east-1",
        "sku_id": sku["sku_id"],
        "workload_profile": "ai_training",
        "gpu_count": 8,
        "dataset_size_tb": 50.0,
        "ephemeral_lifetime_hours": 24,
        "price_ceiling_usd": 5000,
    })
    assert r.status_code == 200
    proposal = r.json()
    assert proposal["spoke_node_count"] > 0
    assert proposal["estimated_cost_per_hour"] > 0
    assert isinstance(proposal["warnings"], list)


def test_configure_spoke_warns_on_short_lifetime():
    regions = client.get("/api/v1/regions/aws/us-east-1/skus").json()
    sku = regions["skus"][0]

    r = client.post("/api/v1/configure/spoke", json={
        "provider": "aws",
        "region": "us-east-1",
        "sku_id": sku["sku_id"],
        "workload_profile": "ai_training",
        "gpu_count": 8,
        "dataset_size_tb": 100.0,
        "ephemeral_lifetime_hours": 1,
    })
    assert r.status_code == 200
    warnings = r.json()["warnings"]
    # Should warn about short lifetime relative to large dataset
    assert any("ephemeral" in w.lower() or "lifetime" in w.lower() for w in warnings)
