from __future__ import annotations

import abc
import logging
from datetime import datetime, timezone

from src.models.gpu_region import CloudProvider, GPUSku

logger = logging.getLogger(__name__)


class CloudAdapter(abc.ABC):
    """Base class for per-cloud GPU availability and pricing adapters."""

    provider: CloudProvider

    @abc.abstractmethod
    async def fetch_skus(self) -> list[GPUSku]:
        """Return a fresh snapshot of all GPU SKUs for this provider."""

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
