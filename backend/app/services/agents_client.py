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

import pickle
import pandas as pd
from datetime import datetime, timedelta
from forecaster.models import models
import os 

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
        """Generate a 24-hour forecast from now using LinearModel."""
        now = datetime.utcnow()
        horizon = 24
        self._logger.info("Building forecast bundle horizon_hours=%s", horizon)

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        MODEL_PATH = os.path.join(BASE_DIR, "../../../spot-price-forecast/models/consumption_forecast_model.pkl")
        DATA_PATH = os.path.join(BASE_DIR, "../../../spot-price-forecast/data/165.csv")

        with open(MODEL_PATH, "rb") as f:
            md = pickle.load(f)
            model = models.LinearModel(
                daily_price_lags=md["daily_price_lags"],
                time_features=md["time_features"],
            )
            model.coeffs = md["coeffs"]
      

        df = pd.read_csv(DATA_PATH)
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True).dt.tz_localize(None)
        df.set_index("startTime", inplace=True)
        hist = model.preprocess_data(df)
        feature_cols = hist.drop(columns="y").columns.tolist()
        last_row = hist.iloc[-1]
        max_lag = max(model.daily_price_lags)
        recent_values = hist['y'].iloc[-max_lag:].tolist()
       

        forecast_hours = pd.date_range(start=now, periods=horizon, freq="h")
        price_predictions = []

        for ts in forecast_hours:
            features = {f'y_lag_avg_{lag}': recent_values[-lag] if len(recent_values) >= lag else recent_values[-1]
                        for lag in model.daily_price_lags}

            hour = ts.hour
            is_weekend = ts.weekday() >= 5
            for col in feature_cols:
                if col.startswith("weekday_hour_") or col.startswith("weekend_hour_"):
                    features[col] = 0.0
            current = f"weekend_hour_{hour}" if is_weekend else f"weekday_hour_{hour}"
            if current in feature_cols:
                features[current] = 1.0

            X = pd.DataFrame([[features.get(col, last_row[col] if col in last_row.index and col != 'y' else 0.0)
                               for col in feature_cols]], columns=feature_cols) if feature_cols else pd.DataFrame([[0]])

            y_hat = abs(model.predict(X).values[0]) if feature_cols else 1.0
            print(f"Predicted price for {ts.isoformat()}: {y_hat}")
            price_predictions.append(ForecastPoint(timestamp=ts, value=round(y_hat + 3, 2))) 

            recent_values.append(y_hat)
            recent_values = recent_values[-max_lag:]

        return [
            ForecastSeries(metric="inflow", unit="m3/s", points=[]),
            ForecastSeries(metric="price", unit="EUR/MWh", points=price_predictions),
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
        self._logger.info("Falling back to synthetic weather series hours=%s", hours)
        return [
            WeatherPoint(
                timestamp=now + timedelta(hours=i),
                precipitation_mm=max(0.0, 0.2 * (i % 4)),
                temperature_c=3.0 + 0.5 * i,
            )
            for i in range(hours)
        ]
