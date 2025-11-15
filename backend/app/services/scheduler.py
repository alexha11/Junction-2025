from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.agents_client import AgentsCoordinator


class OptimizationScheduler:
    """Background job that periodically requests a new schedule."""

    def __init__(self, agents: AgentsCoordinator, interval_minutes: int) -> None:
        self._agents = agents
        self._interval_minutes = interval_minutes
        self._scheduler = AsyncIOScheduler()
        self._logger = logging.getLogger(self.__class__.__name__)

    async def _optimize(self) -> None:
        recommendation = await self._agents.get_schedule_recommendation()
        # TODO: persist + broadcast via WebSocket once storage layer exists.
        self._logger.debug(
            "New schedule recommendation computed generated_at=%s entries=%s",
            recommendation.generated_at.isoformat(),
            len(recommendation.entries),
        )

    def start(self) -> None:
        self._logger.info(
            "Starting optimization scheduler interval_minutes=%s",
            self._interval_minutes,
        )
        self._scheduler.add_job(self._optimize, "interval", minutes=self._interval_minutes)
        self._scheduler.start()

    def shutdown(self) -> None:
        self._logger.info("Shutting down optimization scheduler")
        self._scheduler.shutdown()
