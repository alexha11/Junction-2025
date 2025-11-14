from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.agents_client import AgentsCoordinator


class OptimizationScheduler:
    """Background job that periodically requests a new schedule."""

    def __init__(self, agents: AgentsCoordinator, interval_minutes: int) -> None:
        self._agents = agents
        self._interval_minutes = interval_minutes
        self._scheduler = AsyncIOScheduler()

    async def _optimize(self) -> None:
        recommendation = await self._agents.get_schedule_recommendation()
        # TODO: persist + broadcast via WebSocket once storage layer exists.
        print(f"[{datetime.utcnow():%Y-%m-%d %H:%M:%S}] Optimizer stub {recommendation.json()}")

    def start(self) -> None:
        self._scheduler.add_job(self._optimize, "interval", minutes=self._interval_minutes)
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown()
