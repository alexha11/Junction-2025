from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List

import httpx
from pydantic import BaseModel, Field

from agents.common import BaseMCPAgent


class WeatherRequest(BaseModel):
    lookahead_hours: int = Field(gt=0, le=72, description="Number of hours to fetch (1-72).")
    location: str = Field(
        default="Helsinki",
        min_length=1,
        max_length=128,
        description="Any OpenWeatherMap-supported query (city name or lat,lon).",
    )


class WeatherPoint(BaseModel):
    timestamp: datetime
    precipitation_mm: float
    temperature_c: float


class WeatherProviderError(RuntimeError):
    """Raised when the upstream weather provider fails or sends bad data."""


class WeatherAgent(BaseMCPAgent):
    MAX_LOOKAHEAD_HOURS = 72

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openweathermap.org/data/2.5",
    ) -> None:
        super().__init__(name="weather-agent")
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.base_url = base_url.rstrip("/")

    def configure(self) -> None:  # noqa: D401
        self.register_tool("get_precipitation_forecast", self.get_precipitation_forecast)

    def get_precipitation_forecast(self, request: WeatherRequest) -> List[WeatherPoint]:
        hours = min(request.lookahead_hours, self.MAX_LOOKAHEAD_HOURS)
        current_point = self._fetch_openweather_current(location=request.location)
        base_timestamp = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        return [
            WeatherPoint(
                timestamp=base_timestamp + timedelta(hours=i),
                precipitation_mm=current_point.precipitation_mm,
                temperature_c=current_point.temperature_c,
            )
            for i in range(hours)
        ]

    def _fetch_openweather_current(self, *, location: str) -> WeatherPoint:
        """Call OpenWeatherMap's current weather endpoint and normalize precipitation/temperature."""
        api_key = self._require_api_key()
        url = f"{self.base_url}/weather"
        params = {
            **self._build_location_params(location),
            "appid": api_key,
            "units": "metric",
        }
        try:
            response = httpx.get(url, params=params, timeout=httpx.Timeout(10.0))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WeatherProviderError(f"OpenWeatherMap request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherProviderError("OpenWeatherMap response was not JSON") from exc

        timestamp = datetime.utcfromtimestamp(payload.get("dt", datetime.utcnow().timestamp()))
        temp_c = float(payload.get("main", {}).get("temp", 0.0))
        precip_mm = self._extract_precipitation(payload)

        return WeatherPoint(timestamp=timestamp, precipitation_mm=precip_mm, temperature_c=temp_c)

    @staticmethod
    def _extract_precipitation(payload: dict) -> float:
        rain = payload.get("rain") or {}
        snow = payload.get("snow") or {}
        rain_mm = float(rain.get("1h") or 0.0)
        snow_mm = float(snow.get("1h") or 0.0)
        return rain_mm + snow_mm

    def _build_location_params(self, location: str) -> dict[str, str]:
        parts = [part.strip() for part in location.split(",")]
        if len(parts) == 2 and all(self._is_number(part) for part in parts):
            return {"lat": parts[0], "lon": parts[1]}
        return {"q": location}

    @staticmethod
    def _is_number(value: str) -> bool:
        try:
            float(value)
        except ValueError:
            return False
        return True

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise WeatherProviderError(
                "OpenWeatherMap API key missing. Set OPENWEATHER_API_KEY or pass api_key to WeatherAgent."
            )
        return self.api_key


def serve() -> None:
    WeatherAgent().serve()


if __name__ == "__main__":
    serve()
