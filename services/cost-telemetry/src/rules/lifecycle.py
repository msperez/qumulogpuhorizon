from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable

from src.models.telemetry import DeploymentCostSummary, LifecycleEvent, TelemetryRecord

logger = logging.getLogger(__name__)

COST_SAMPLE_INTERVAL_SECONDS = 30
LIFETIME_WARNING_PCT = 0.80   # warn when 80% of lifetime is consumed
CEILING_WARNING_PCT = 0.80    # warn when 80% of price ceiling is consumed


class DeploymentTracker:
    """Tracks a single deployment's cost and enforces ephemeral lifecycle rules."""

    def __init__(
        self,
        deployment_id: str,
        provider: str,
        region: str,
        workload_profile: str,
        cost_per_hour_usd: float,
        spoke_cost_per_hour_usd: float,
        started_at: datetime,
        phase: str,
        price_ceiling_usd: float | None,
        lifetime_hours: float | None,
        on_teardown: Callable[[str, str], Awaitable[None]],
    ) -> None:
        self.deployment_id = deployment_id
        self.provider = provider
        self.region = region
        self.workload_profile = workload_profile
        self.cost_per_hour_usd = cost_per_hour_usd
        self.spoke_cost_per_hour_usd = spoke_cost_per_hour_usd
        self.started_at = started_at
        self.phase = phase
        self.price_ceiling_usd = price_ceiling_usd
        self.lifetime_hours = lifetime_hours
        self._on_teardown = on_teardown
        self._records: list[TelemetryRecord] = []
        self._teardown_triggered = False
        self._teardown_reason: str | None = None
        self._updated_at = started_at

    def update_phase(self, phase: str) -> None:
        self.phase = phase
        self._record(LifecycleEvent.PHASE_CHANGED, message=f"Phase changed to {phase}")

    async def tick(self) -> None:
        """Called periodically to sample cost and enforce lifecycle rules."""
        now = datetime.now(timezone.utc)
        runtime_hours = (now - self.started_at).total_seconds() / 3600.0
        total_per_hour = self.cost_per_hour_usd + self.spoke_cost_per_hour_usd
        current_cost = runtime_hours * total_per_hour
        self._updated_at = now

        self._record(
            LifecycleEvent.COST_SAMPLE,
            value=round(current_cost, 4),
            message=f"${current_cost:.2f} after {runtime_hours:.2f}h",
        )

        if self._teardown_triggered:
            return

        # Price ceiling enforcement
        if self.price_ceiling_usd is not None:
            ceiling_pct = (current_cost / self.price_ceiling_usd) * 100
            if ceiling_pct >= 100.0:
                logger.warning("[%s] Price ceiling breached (%.2f / %.2f)",
                               self.deployment_id[:8], current_cost, self.price_ceiling_usd)
                self._record(LifecycleEvent.PRICE_CEILING_BREACHED,
                             value=current_cost,
                             message=f"Price ceiling ${self.price_ceiling_usd} breached at ${current_cost:.2f}")
                await self._trigger_teardown("price_ceiling_breached")
                return
            if ceiling_pct >= CEILING_WARNING_PCT * 100:
                self._record(LifecycleEvent.PRICE_CEILING_WARNING,
                             value=ceiling_pct,
                             message=f"{ceiling_pct:.0f}% of price ceiling consumed")

        # Ephemeral lifetime enforcement
        if self.lifetime_hours is not None:
            remaining = self.lifetime_hours - runtime_hours
            lifetime_pct = runtime_hours / self.lifetime_hours
            if remaining <= 0:
                logger.info("[%s] Lifetime expired", self.deployment_id[:8])
                self._record(LifecycleEvent.LIFETIME_EXPIRED,
                             value=runtime_hours,
                             message=f"Ephemeral lifetime of {self.lifetime_hours}h expired")
                await self._trigger_teardown("lifetime_expired")
                return
            if lifetime_pct >= LIFETIME_WARNING_PCT:
                self._record(LifecycleEvent.LIFETIME_WARNING,
                             value=remaining,
                             message=f"{remaining:.1f}h remaining of ephemeral lifetime")

    async def _trigger_teardown(self, reason: str) -> None:
        self._teardown_triggered = True
        self._teardown_reason = reason
        self._record(LifecycleEvent.TEARDOWN_TRIGGERED, message=f"Teardown triggered: {reason}")
        await self._on_teardown(self.deployment_id, reason)

    def summary(self) -> DeploymentCostSummary:
        now = datetime.now(timezone.utc)
        runtime_hours = (now - self.started_at).total_seconds() / 3600.0
        total_per_hour = self.cost_per_hour_usd + self.spoke_cost_per_hour_usd
        current_cost = runtime_hours * total_per_hour

        ceiling_pct = None
        if self.price_ceiling_usd:
            ceiling_pct = round((current_cost / self.price_ceiling_usd) * 100, 1)

        remaining = None
        if self.lifetime_hours:
            remaining = max(0.0, self.lifetime_hours - runtime_hours)

        return DeploymentCostSummary(
            deployment_id=self.deployment_id,
            provider=self.provider,
            region=self.region,
            started_at=self.started_at,
            updated_at=self._updated_at,
            phase=self.phase,
            runtime_hours=round(runtime_hours, 4),
            cost_per_hour_usd=round(total_per_hour, 4),
            current_cost_usd=round(current_cost, 4),
            price_ceiling_usd=self.price_ceiling_usd,
            ceiling_pct_consumed=ceiling_pct,
            lifetime_hours=self.lifetime_hours,
            lifetime_remaining_hours=round(remaining, 3) if remaining is not None else None,
            teardown_triggered=self._teardown_triggered,
            teardown_reason=self._teardown_reason,
        )

    def records(self) -> list[TelemetryRecord]:
        return list(self._records)

    def _record(self, event: LifecycleEvent, value: float | None = None, message: str = "") -> None:
        self._records.append(TelemetryRecord(
            record_id=str(uuid.uuid4()),
            deployment_id=self.deployment_id,
            event=event,
            timestamp=datetime.now(timezone.utc),
            value=value,
            message=message,
        ))
