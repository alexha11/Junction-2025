from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel

from agents.common import BaseMCPAgent


class InflowRequest(BaseModel):
    lookahead_hours: int


class WeatherDatum(BaseModel):
    timestamp: datetime
    precipitation_mm: float


class InflowPoint(BaseModel):
    timestamp: datetime
    inflow_m3_s: float


class InflowForecastAgent(BaseMCPAgent):
    def __init__(self) -> None:
        super().__init__(name="inflow-forecast-agent")

    def configure(self) -> None:
        self.register_tool("predict_inflow", self.predict_inflow)

    def predict_inflow(self, request: InflowRequest) -> List[InflowPoint]:
        now = datetime.utcnow()
        return [
            InflowPoint(timestamp=now + timedelta(hours=i), inflow_m3_s=2 + 0.05 * i)
            for i in range(request.lookahead_hours)
        ]


def serve() -> None:
    InflowForecastAgent().serve()


if __name__ == "__main__":
    serve()
