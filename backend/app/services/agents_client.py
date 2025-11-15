from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
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

WEATHER_SAMPLE_FILE = Path(__file__).resolve().parents[3] / "sample" / "weather_fallback.json"
PRICE_SAMPLE_FILE = Path(__file__).resolve().parents[3] / "sample" / "market_price_fallback.json"
DEFAULT_WEATHER_SAMPLE = [
    {
        "timestamp": "2025-01-01T00:00:00+00:00",
        "precipitation_mm": 0.0,
        "temperature_c": 3.0,
    },
    {
        "timestamp": "2025-01-01T01:00:00+00:00",
        "precipitation_mm": 0.2,
        "temperature_c": 3.5,
    },
    {
        "timestamp": "2025-01-01T02:00:00+00:00",
        "precipitation_mm": 0.4,
        "temperature_c": 4.0,
    },
]
DEFAULT_PRICE_SAMPLE = [
    {"timestamp": "2025-01-01T00:00:00+00:00", "price_eur_mwh": 64.0},
    {"timestamp": "2025-01-01T01:00:00+00:00", "price_eur_mwh": 62.5},
    {"timestamp": "2025-01-01T02:00:00+00:00", "price_eur_mwh": 61.0},
    {"timestamp": "2025-01-01T03:00:00+00:00", "price_eur_mwh": 60.0},
    {"timestamp": "2025-01-01T04:00:00+00:00", "price_eur_mwh": 59.5},
    {"timestamp": "2025-01-01T05:00:00+00:00", "price_eur_mwh": 60.5},
    {"timestamp": "2025-01-01T06:00:00+00:00", "price_eur_mwh": 63.0},
    {"timestamp": "2025-01-01T07:00:00+00:00", "price_eur_mwh": 66.0},
    {"timestamp": "2025-01-01T08:00:00+00:00", "price_eur_mwh": 70.0},
    {"timestamp": "2025-01-01T09:00:00+00:00", "price_eur_mwh": 74.0},
    {"timestamp": "2025-01-01T10:00:00+00:00", "price_eur_mwh": 77.5},
    {"timestamp": "2025-01-01T11:00:00+00:00", "price_eur_mwh": 79.0},
    {"timestamp": "2025-01-01T12:00:00+00:00", "price_eur_mwh": 78.0},
    {"timestamp": "2025-01-01T13:00:00+00:00", "price_eur_mwh": 75.0},
    {"timestamp": "2025-01-01T14:00:00+00:00", "price_eur_mwh": 72.0},
    {"timestamp": "2025-01-01T15:00:00+00:00", "price_eur_mwh": 70.5},
    {"timestamp": "2025-01-01T16:00:00+00:00", "price_eur_mwh": 69.0},
    {"timestamp": "2025-01-01T17:00:00+00:00", "price_eur_mwh": 68.0},
    {"timestamp": "2025-01-01T18:00:00+00:00", "price_eur_mwh": 67.5},
    {"timestamp": "2025-01-01T19:00:00+00:00", "price_eur_mwh": 68.5},
    {"timestamp": "2025-01-01T20:00:00+00:00", "price_eur_mwh": 70.0},
    {"timestamp": "2025-01-01T21:00:00+00:00", "price_eur_mwh": 71.5},
    {"timestamp": "2025-01-01T22:00:00+00:00", "price_eur_mwh": 70.0},
    {"timestamp": "2025-01-01T23:00:00+00:00", "price_eur_mwh": 67.0},
]


class AgentsCoordinator:
    """Facade that will later call MCP agents via the OpenAI Agents SDK.

    Today it returns deterministic placeholder values so the rest of the
    stack can be developed end-to-end without external dependencies.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    async def get_system_state(self) -> SystemState:
        now = datetime.utcnow()
        self._logger.debug("Generating synthetic system state timestamp=%s", now.isoformat())
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
            tunnel_level_l2_m=3.0,
            inflow_m3_s=2.1,
            outflow_m3_s=2.0,
            electricity_price_eur_mwh=72.5,
            pumps=pumps,
        )

    async def get_forecasts(self) -> List[ForecastSeries]:
        now = datetime.utcnow()
        horizon = 12
        self._logger.info("Building forecast bundle horizon_hours=%s", horizon)
        points = [
            ForecastPoint(timestamp=now + timedelta(hours=i), value=2.0 + i * 0.1)
            for i in range(horizon)
        ]
        price_points = self._build_price_forecast_points(now, horizon)
        return [
            ForecastSeries(metric="inflow", unit="m3/s", points=points),
            ForecastSeries(metric="price", unit="EUR/MWh", points=price_points),
        ]

    async def get_schedule_recommendation(self) -> ScheduleRecommendation:
        now = datetime.utcnow()
        self._logger.info("Producing schedule recommendation generated_at=%s", now.isoformat())
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
            self._logger.warning("Weather agent request failed url=%s error=%s", url, exc)
        except Exception:
            self._logger.exception("Unexpected error while requesting weather forecast")

        return self._fallback_weather_series(lookahead_hours)

    def _fallback_weather_series(self, hours: int) -> List[WeatherPoint]:
        now = datetime.utcnow()
        self._logger.info("Building fallback weather series hours=%s", hours)
        sample_values = self._load_sample_weather_values()
        selected_points = self._select_weather_window(sample_values, now, hours)
        if not selected_points:
            self._logger.warning(
                "Weather sample data missing for requested horizon; using synthetic fallback",
            )
            return self._synthetic_weather_series(now, hours)
        return [
            WeatherPoint(
                timestamp=point["timestamp"],
                precipitation_mm=point["precipitation_mm"],
                temperature_c=point["temperature_c"],
            )
            for point in selected_points
        ]

    def _build_price_forecast_points(self, now: datetime, hours: int) -> List[ForecastPoint]:
        self._logger.info("Building fallback price series hours=%s", hours)
        sample_values = self._load_sample_price_values()
        selected_points = self._select_price_window(sample_values, now, hours)
        if not selected_points:
            self._logger.warning(
                "Price sample data missing for requested horizon; using synthetic fallback",
            )
            return self._synthetic_price_series(now, hours)
        return [
            ForecastPoint(timestamp=point["timestamp"], value=point["price_eur_mwh"])
            for point in selected_points
        ]

    def _load_sample_weather_values(self) -> List[dict]:
        try:
            with WEATHER_SAMPLE_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, list) or not data:
                raise ValueError("Weather sample data must be a non-empty list")
            return data
        except FileNotFoundError:
            self._logger.warning(
                "Weather sample file not found path=%s; using defaults",
                WEATHER_SAMPLE_FILE,
            )
        except Exception:
            self._logger.warning(
                "Failed to read weather sample file path=%s; using defaults",
                WEATHER_SAMPLE_FILE,
                exc_info=True,
            )
        return DEFAULT_WEATHER_SAMPLE

    def _load_sample_price_values(self) -> List[dict]:
        try:
            with PRICE_SAMPLE_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, list) or not data:
                raise ValueError("Price sample data must be a non-empty list")
            return data
        except FileNotFoundError:
            self._logger.warning(
                "Price sample file not found path=%s; using defaults",
                PRICE_SAMPLE_FILE,
            )
        except Exception:
            self._logger.warning(
                "Failed to read price sample file path=%s; using defaults",
                PRICE_SAMPLE_FILE,
                exc_info=True,
            )
        return DEFAULT_PRICE_SAMPLE

    def _select_weather_window(
        self,
        sample_values: List[dict],
        now: datetime,
        hours: int,
    ) -> List[dict]:
        parsed_points = []
        for entry in sample_values:
            try:
                timestamp = self._parse_iso_timestamp(entry["timestamp"])
                parsed_points.append(
                    {
                        "timestamp": timestamp,
                        "precipitation_mm": float(entry.get("precipitation_mm", 0.0)),
                        "temperature_c": float(entry.get("temperature_c", 0.0)),
                    }
                )
            except (KeyError, ValueError, TypeError):
                self._logger.debug(
                    "Skipping invalid weather sample entry entry=%s",
                    entry,
                )
                continue
        parsed_points.sort(key=lambda item: item["timestamp"])
        if not parsed_points:
            return []
        if len(parsed_points) < hours:
            return []

        rounded_now = now.replace(minute=0, second=0, microsecond=0)

        start_idx = None
        for idx, entry in enumerate(parsed_points):
            if entry["timestamp"] >= rounded_now:
                start_idx = idx
                break

        if start_idx is None:
            start_idx = len(parsed_points)

        end_idx = start_idx + hours
        if end_idx > len(parsed_points):
            start_idx = max(0, len(parsed_points) - hours)
            end_idx = start_idx + hours

        window = parsed_points[start_idx:end_idx]
        if len(window) < hours:
            return []
        return window

    def _synthetic_weather_series(self, start: datetime, hours: int) -> List[WeatherPoint]:
        return [
            WeatherPoint(
                timestamp=start + timedelta(hours=i),
                precipitation_mm=max(0.0, 0.2 * (i % 4)),
                temperature_c=3.0 + 0.5 * i,
            )
            for i in range(hours)
        ]

    def _select_price_window(
        self,
        sample_values: List[dict],
        now: datetime,
        hours: int,
    ) -> List[dict]:
        parsed_points = []
        for entry in sample_values:
            try:
                timestamp = self._parse_iso_timestamp(entry["timestamp"])
                parsed_points.append(
                    {
                        "timestamp": timestamp,
                        "price_eur_mwh": float(entry.get("price_eur_mwh", 0.0)),
                    }
                )
            except (KeyError, ValueError, TypeError):
                self._logger.debug(
                    "Skipping invalid price sample entry entry=%s",
                    entry,
                )
                continue
        parsed_points.sort(key=lambda item: item["timestamp"])
        if not parsed_points:
            return []
        if len(parsed_points) < hours:
            return []

        rounded_now = now.replace(minute=0, second=0, microsecond=0)

        start_idx = None
        for idx, entry in enumerate(parsed_points):
            if entry["timestamp"] >= rounded_now:
                start_idx = idx
                break

        if start_idx is None:
            start_idx = len(parsed_points)

        end_idx = start_idx + hours
        if end_idx > len(parsed_points):
            start_idx = max(0, len(parsed_points) - hours)
            end_idx = start_idx + hours

        window = parsed_points[start_idx:end_idx]
        if len(window) < hours:
            return []
        return window

    def _synthetic_price_series(self, start: datetime, hours: int) -> List[ForecastPoint]:
        base_price = 65.0
        cycle = [0.0, -1.5, -2.5, -1.0, 0.5, 2.0, 4.0, 6.0]
        return [
            ForecastPoint(
                timestamp=start + timedelta(hours=i),
                value=base_price + cycle[i % len(cycle)] + 0.4 * i,
            )
            for i in range(hours)
        ]

    def _parse_iso_timestamp(self, value: str) -> datetime:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
