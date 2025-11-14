from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel

from agents.common import BaseMCPAgent


class WeatherRequest(BaseModel):
    lookahead_hours: int


class WeatherPoint(BaseModel):
    timestamp: datetime
    precipitation_mm: float
    temperature_c: float


class WeatherAgent(BaseMCPAgent):
    def __init__(self) -> None:
        super().__init__(name="weather-agent")

    def configure(self) -> None:  # noqa: D401
        self.register_tool("get_precipitation_forecast", self.get_precipitation_forecast)

    def get_precipitation_forecast(self, request: WeatherRequest) -> List[WeatherPoint]:
        now = datetime.utcnow()
        return [
            WeatherPoint(
                timestamp=now + timedelta(hours=i),
                precipitation_mm=0.2 * i,
                temperature_c=5 + i,
            )
            for i in range(request.lookahead_hours)
        ]


def serve() -> None:
    WeatherAgent().serve()


if __name__ == "__main__":
    serve()
