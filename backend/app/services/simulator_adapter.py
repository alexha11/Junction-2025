from __future__ import annotations

from typing import AsyncIterator

from app.models import SystemState
from app.services.agents_client import AgentsCoordinator


class SimulatorAdapter:
    """Thin wrapper around the simulator feed.

    In this early iteration we reuse the AgentsCoordinator stub data so frontend work
    can progress before the actual simulator integration is ready.
    """

    def __init__(self, agents: AgentsCoordinator) -> None:
        self._agents = agents

    async def stream_state(self) -> AsyncIterator[SystemState]:
        yield await self._agents.get_system_state()
