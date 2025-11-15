from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

import httpx

from app.config import get_settings

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


class AgentsCoordinator:
    """Facade that will later call MCP agents via the OpenAI Agents SDK.

    Today it returns deterministic placeholder values so the rest of the
    stack can be developed end-to-end without external dependencies.
    """

    async def get_system_state(self) -> SystemState:
        now = datetime.utcnow()
        pumps = [
            PumpStatus(
                pump_id=f"P{i+1}",
                state=PumpState.on if i % 2 == 0 else PumpState.off,
                frequency_hz=48.0 if i % 2 == 0 else 0.0,
                power_kw=350.0 if i % 2 == 0 else 0.0,
            )
            for i in range(8)
        ]
        return SystemState(
            timestamp=now,
            tunnel_level_m=3.2,
            inflow_m3_s=2.1,
            outflow_m3_s=2.0,
            electricity_price_eur_mwh=72.5,
            pumps=pumps,
        )

    async def get_forecasts(self) -> List[ForecastSeries]:
        now = datetime.utcnow()
        horizon = 12
        points = [
            ForecastPoint(timestamp=now + timedelta(hours=i), value=2.0 + i * 0.1)
            for i in range(horizon)
        ]
        price_points = [
            ForecastPoint(timestamp=now + timedelta(hours=i), value=60 + i * 2)
            for i in range(horizon)
        ]
        return [
            ForecastSeries(metric="inflow", unit="m3/s", points=points),
            ForecastSeries(metric="price", unit="EUR/MWh", points=price_points),
        ]

    async def get_schedule_recommendation(self) -> ScheduleRecommendation:
        now = datetime.utcnow()
        entries = [
            ScheduleEntry(
                pump_id="P1",
                target_frequency_hz=48.5,
                start_time=now,
                end_time=now + timedelta(hours=2),
            ),
            ScheduleEntry(
                pump_id="P2",
                target_frequency_hz=47.8,
                start_time=now + timedelta(minutes=30),
                end_time=now + timedelta(hours=2, minutes=30),
            ),
        ]
        justification = (
            "Maintain tunnel level near 3.0 m while anticipating higher inflow in 2 hours."
        )
        return ScheduleRecommendation(
            generated_at=now,
            horizon_minutes=120,
            entries=entries,
            justification=justification,
        )

    async def get_weather_forecast(self, *, lookahead_hours: int, location: str) -> List[WeatherPoint]:
        settings = get_settings()
        url = f"{settings.weather_agent_url.rstrip('/')}/weather/forecast"
        payload = {"lookahead_hours": lookahead_hours, "location": location}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return [WeatherPoint(**point) for point in data]
        except Exception:  # noqa: BLE001
            return self._fallback_weather_series(lookahead_hours)

    def _fallback_weather_series(self, hours: int) -> List[WeatherPoint]:
        now = datetime.utcnow()
        return [
            WeatherPoint(
                timestamp=now + timedelta(hours=i),
                precipitation_mm=max(0.0, 0.2 * (i % 4)),
                temperature_c=3.0 + 0.5 * i,
            )
            for i in range(hours)
        ]
