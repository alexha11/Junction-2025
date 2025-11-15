from __future__ import annotations

from datetime import datetime, timedelta
import logging
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

from app.services.digital_twin import get_digital_twin_current_state


class AgentsCoordinator:
    """Facade that will later call MCP agents via the OpenAI Agents SDK.

    Today it returns deterministic placeholder values so the rest of the
    stack can be developed end-to-end without external dependencies.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    async def get_system_state(self) -> SystemState:
        now = datetime.utcnow()
        self._logger.debug(
            "Generating synthetic system state timestamp=%s", now.isoformat()
        )
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

    async def get_digital_twin_current_state(self) -> dict:
        self._logger.debug("Fetching current digital twin synthetic system state")

        state = await get_digital_twin_current_state(self)
        return state

    async def get_forecasts(self) -> List[ForecastSeries]:
        now = datetime.utcnow()
        horizon = 12
        self._logger.info("Building forecast bundle horizon_hours=%s", horizon)
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
        self._logger.info(
            "Producing schedule recommendation generated_at=%s", now.isoformat()
        )
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
        justification = "Maintain tunnel level near 3.0 m while anticipating higher inflow in 2 hours."
        return ScheduleRecommendation(
            generated_at=now,
            horizon_minutes=120,
            entries=entries,
            justification=justification,
        )

    async def get_weather_forecast(
        self, *, lookahead_hours: int, location: str
    ) -> List[WeatherPoint]:
        settings = get_settings()
        url = f"{settings.weather_agent_url.rstrip('/')}/weather/forecast"
        payload = {"lookahead_hours": lookahead_hours, "location": location}
        self._logger.info(
            "Requesting weather forecast url=%s lookahead_hours=%s location=%s",
            url,
            lookahead_hours,
            location,
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                self._logger.debug(
                    "Weather agent responded successfully points=%s",
                    len(data),
                )
                return [WeatherPoint(**point) for point in data]
        except httpx.HTTPStatusError as exc:
            self._logger.warning(
                "Weather agent returned error status %s for %s",
                exc.response.status_code,
                url,
            )
        except httpx.RequestError as exc:
            self._logger.warning(
                "Weather agent request failed url=%s error=%s", url, exc
            )
        except Exception:
            self._logger.exception("Unexpected error while requesting weather forecast")

        return self._fallback_weather_series(lookahead_hours)

    def _fallback_weather_series(self, hours: int) -> List[WeatherPoint]:
        now = datetime.utcnow()
        self._logger.info("Falling back to synthetic weather series hours=%s", hours)
        return [
            WeatherPoint(
                timestamp=now + timedelta(hours=i),
                precipitation_mm=max(0.0, 0.2 * (i % 4)),
                temperature_c=3.0 + 0.5 * i,
            )
            for i in range(hours)
        ]
