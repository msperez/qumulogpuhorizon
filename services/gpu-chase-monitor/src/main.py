from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os

from src.adapters import AWSAdapter, AzureAdapter, GCPAdapter
from src.api import routes
from src.cache.store import GPUCatalogStore, REFRESH_INTERVAL_SECONDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GPU Chase Monitor",
    description="Real-time GPU availability and pricing across AWS, Azure, and Google Cloud.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tightened by the API gateway in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_store = GPUCatalogStore()

# Comma-separated list of enabled providers. Defaults to aws only.
# Set ENABLED_CLOUDS=aws,azure,gcp in the environment to enable all.
_ENABLED = {p.strip().lower() for p in os.getenv("ENABLED_CLOUDS", "aws,azure,gcp").split(",")}
_ALL_ADAPTERS = {"aws": AWSAdapter(), "azure": AzureAdapter(), "gcp": GCPAdapter()}
_adapters = [a for name, a in _ALL_ADAPTERS.items() if name in _ENABLED]
logger.info("Active cloud adapters: %s", [type(a).__name__ for a in _adapters])

app.include_router(routes.router, prefix="/api/v1")


def _get_store() -> GPUCatalogStore:
    return _store


app.dependency_overrides[routes.get_store] = _get_store


async def _refresh_loop() -> None:
    while True:
        try:
            all_skus = []
            for adapter in _adapters:
                skus = await adapter.fetch_skus()
                all_skus.extend(skus)
            await _store.update(all_skus)
        except Exception:
            logger.exception("Error refreshing GPU catalog")
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_refresh_loop())


@app.get("/healthz")
async def health() -> dict:
    return {
        "status": "ok",
        "last_refresh": _store.last_refresh,
        "sku_count": len(await _store.get_all_skus()),
    }
