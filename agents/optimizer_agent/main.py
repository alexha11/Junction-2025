from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel

from agents.common import BaseMCPAgent


class OptimizationRequest(BaseModel):
    horizon_minutes: int


class ScheduleEntry(BaseModel):
    pump_id: str
    start_time: datetime
    end_time: datetime
    target_frequency_hz: float


class OptimizationResponse(BaseModel):
    generated_at: datetime
    entries: List[ScheduleEntry]
    justification: str


class OptimizationAgent(BaseMCPAgent):
    def __init__(self) -> None:
        super().__init__(name="optimization-agent")

    def configure(self) -> None:
        self.register_tool("generate_schedule", self.generate_schedule)

    def generate_schedule(self, request: OptimizationRequest) -> OptimizationResponse:
        now = datetime.utcnow()
        start = now.replace(minute=0, second=0, microsecond=0)
        entries = [
            ScheduleEntry(
                pump_id="P1",
                start_time=start,
                end_time=start + timedelta(minutes=request.horizon_minutes // 2),
                target_frequency_hz=48.5,
            ),
            ScheduleEntry(
                pump_id="P2",
                start_time=start + timedelta(minutes=30),
                end_time=start + timedelta(minutes=request.horizon_minutes),
                target_frequency_hz=47.8,
            ),
        ]
        return OptimizationResponse(
            generated_at=now,
            entries=entries,
            justification="Maintain safe tunnel level while minimizing cost.",
        )


def serve() -> None:
    OptimizationAgent().serve()


if __name__ == "__main__":
    serve()
