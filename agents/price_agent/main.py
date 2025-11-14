from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel

from agents.common import BaseMCPAgent


class PriceRequest(BaseModel):
    lookahead_hours: int


class PricePoint(BaseModel):
    timestamp: datetime
    eur_mwh: float


class ElectricityPriceAgent(BaseMCPAgent):
    def __init__(self) -> None:
        super().__init__(name="electricity-price-agent")

    def configure(self) -> None:
        self.register_tool("get_electricity_price_forecast", self.get_forecast)

    def get_forecast(self, request: PriceRequest) -> List[PricePoint]:
        now = datetime.utcnow()
        return [
            PricePoint(timestamp=now + timedelta(hours=i), eur_mwh=60 + i * 1.5)
            for i in range(request.lookahead_hours)
        ]


def serve() -> None:
    ElectricityPriceAgent().serve()


if __name__ == "__main__":
    serve()
