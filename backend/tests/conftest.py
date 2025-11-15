from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure the backend root is importable even when pytest runs from the repo root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes import system
from app.main import app
from app.models import (
    ForecastPoint,
    ForecastSeries,
    PumpState,
    PumpStatus,
    ScheduleEntry,
    ScheduleRecommendation,
    SystemState,
    WeatherPoint,
)


class StubAgents:
    """Test double that mimics the AgentsCoordinator facade."""

    def __init__(self) -> None:
        now = datetime.utcnow()
        pumps = [
            PumpStatus(pump_id="P1", state=PumpState.on, frequency_hz=48.0, power_kw=350.0),
            PumpStatus(pump_id="P2", state=PumpState.off, frequency_hz=0.0, power_kw=0.0),
        ]
        self.system_state = SystemState(
            timestamp=now,
            tunnel_level_m=3.5,
            inflow_m3_s=2.4,
            outflow_m3_s=2.2,
            electricity_price_eur_mwh=70.0,
            pumps=pumps,
        )
        points = [ForecastPoint(timestamp=now + timedelta(hours=i), value=2.0 + i) for i in range(3)]
        self.forecasts = [ForecastSeries(metric="inflow", unit="m3/s", points=points)]
        self.schedule = ScheduleRecommendation(
            generated_at=now,
            horizon_minutes=90,
            entries=[
                ScheduleEntry(
                    pump_id="P1",
                    target_frequency_hz=49.0,
                    start_time=now,
                    end_time=now + timedelta(hours=2),
                )
            ],
            justification="Balance inflow with energy price",
        )
        self.last_weather_request: dict[str, str | int] | None = None
        self.weather_template = [
            WeatherPoint(timestamp=now + timedelta(hours=i), precipitation_mm=0.1 * i, temperature_c=4 + i)
            for i in range(24)
        ]

    async def get_system_state(self) -> SystemState:
        return self.system_state

    async def get_forecasts(self) -> list[ForecastSeries]:
        return self.forecasts

    async def get_schedule_recommendation(self) -> ScheduleRecommendation:
        return self.schedule

    async def get_weather_forecast(self, *, lookahead_hours: int, location: str) -> list[WeatherPoint]:
        self.last_weather_request = {"lookahead_hours": lookahead_hours, "location": location}
        return self.weather_template[:lookahead_hours]


@pytest.fixture()
def api_client():
    """Provide a FastAPI TestClient with agent dependencies stubbed out."""

    stub = StubAgents()
    app.dependency_overrides[system.get_agents] = lambda: stub
    with TestClient(app) as client:
        yield client, stub
    app.dependency_overrides.pop(system.get_agents, None)
