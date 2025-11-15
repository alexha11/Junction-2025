from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

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

from app.services.digital_twin import (
    get_digital_twin_current_state,
    write_pump_schedule,
    aggregate_variables_data,
)
from app.services.digital_twin_adapter import DigitalTwinAdapter

# Make the local spot-price-forecast sources importable without packaging them.
REPO_ROOT = Path(__file__).resolve().parents[3]
FORECASTER_SRC = REPO_ROOT / "spot-price-forecast" / "src"
if str(FORECASTER_SRC) not in sys.path:
    sys.path.append(str(FORECASTER_SRC))

# Import optimizer agent (with fallback if not available)
AGENTS_SRC = REPO_ROOT / "agents"
if str(AGENTS_SRC) not in sys.path:
    sys.path.insert(0, str(AGENTS_SRC))

try:
    from agents.optimizer_agent.main import OptimizationAgent, OptimizationRequest
    OPTIMIZER_AVAILABLE = True
except ImportError as e:
    OPTIMIZER_AVAILABLE = False
    OptimizationAgent = None
    OptimizationRequest = None
    # Log warning but don't fail - backend can work without optimizer
    import logging
    logging.getLogger(__name__).warning(f"Optimizer agent not available: {e}")

from forecaster.models import models

WEATHER_SAMPLE_FILE = (
    Path(__file__).resolve().parents[3] / "sample" / "weather_fallback.json"
)
PRICE_SAMPLE_FILE = (
    Path(__file__).resolve().parents[3] / "sample" / "market_price_fallback.json"
)
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
        self._settings = get_settings()
        self._adapter = DigitalTwinAdapter()
        
        # Initialize optimizer agent if available
        self._optimizer_agent: Optional[Any] = None
        self._latest_optimization_result: Optional[Dict] = None
        if OPTIMIZER_AVAILABLE and OptimizationAgent:
            try:
                # Initialize optimizer agent with backend URL (for digital twin access)
                # The optimizer will call backend endpoints which use digital twin
                backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
                self._optimizer_agent = OptimizationAgent(
                    backend_url=backend_url,
                    weather_agent_url=self._settings.weather_agent_url,
                )
                self._logger.info(
                    "Optimizer agent initialized successfully backend_url=%s",
                    backend_url,
                )
            except Exception as e:
                self._logger.warning(
                    f"Failed to initialize optimizer agent: {e}",
                    exc_info=True,
                )
                self._optimizer_agent = None

    async def get_system_state(self) -> SystemState:
        """Get current system state from digital twin (or fallback to synthetic)."""
        now = datetime.utcnow()
        
        # Try to get state from digital twin if enabled
        if self._settings.use_digital_twin:
            try:
                self._logger.debug(
                    "Fetching system state from digital twin timestamp=%s", now.isoformat()
                )
                opcua_values = await get_digital_twin_current_state(
                    opcua_url=self._settings.digital_twin_opcua_url
                )
                
                if opcua_values:
                    # Convert OPC UA values to SystemState
                    state_dict = self._adapter.convert_opcua_to_system_state(opcua_values)
                    
                    # Build SystemState from converted values
                    pumps = [
                        PumpStatus(
                            pump_id=pump_data["pump_id"],
                            state=PumpState.on if pump_data["state"] == "on" else PumpState.off,
                            frequency_hz=pump_data["frequency_hz"],
                            power_kw=pump_data["power_kw"],
                        )
                        for pump_data in state_dict.get("pumps", [])
                    ]
                    
                    return SystemState(
                        timestamp=now,
                        tunnel_level_m=state_dict.get("tunnel_level_m", 0.0),
                        tunnel_level_l2_m=state_dict.get("tunnel_level_l2_m", 0.0),
                        tunnel_water_volume_l1_m3=state_dict.get("tunnel_water_volume_l1_m3", 0.0),
                        inflow_m3_s=state_dict.get("inflow_m3_s", 0.0),
                        outflow_m3_s=state_dict.get("outflow_m3_s", 0.0),
                        electricity_price_eur_mwh=state_dict.get("electricity_price_eur_mwh", 0.0),
                        pumps=pumps,
                    )
                else:
                    self._logger.warning("Digital twin returned empty values, using fallback")
            except Exception as e:
                self._logger.warning(
                    "Failed to get system state from digital twin, using fallback: %s", e
                )
        
        # Fallback to synthetic data
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
            tunnel_level_l2_m=3.0,
            tunnel_water_volume_l1_m3=1250.0,
            inflow_m3_s=2.1,
            outflow_m3_s=2.0,
            electricity_price_eur_mwh=72.5,
            pumps=pumps,
        )

    async def get_digital_twin_current_state(self) -> dict:
        """Get raw OPC UA values from digital twin (deprecated - use get_system_state instead)."""
        self._logger.warning(
            "get_digital_twin_current_state is deprecated, use get_system_state instead"
        )
        return await get_digital_twin_current_state(
            opcua_url=self._settings.digital_twin_opcua_url
        )
    
    async def write_optimization_schedule(
        self, schedule: ScheduleRecommendation
    ) -> bool:
        """Write optimization schedule to digital twin.
        
        Args:
            schedule: Schedule recommendation with pump entries
            
        Returns:
            True if successful, False otherwise
        """
        if not self._settings.use_digital_twin:
            self._logger.warning("Digital twin is disabled, cannot write schedule")
            return False
        
        try:
            self._logger.info(
                "Writing optimization schedule to digital twin entries=%s",
                len(schedule.entries),
            )
            
            # Convert ScheduleEntry objects to dictionaries
            schedule_dicts = [
                {
                    "pump_id": entry.pump_id,
                    "target_frequency_hz": entry.target_frequency_hz,
                }
                for entry in schedule.entries
            ]
            
            success = await write_pump_schedule(
                schedule_entries=schedule_dicts,
                opcua_url=self._settings.digital_twin_opcua_url,
            )
            
            if success:
                self._logger.info("Successfully wrote schedule to digital twin")
            else:
                self._logger.warning("Failed to write schedule to digital twin")
            
            return success
        except Exception as e:
            self._logger.error("Error writing schedule to digital twin: %s", e)
            return False
    
    async def get_digital_twin_history(
        self, variable_names: List[str], hours_back: int = 24
    ) -> List[Dict]:
        """Get historical data for multiple variables from digital twin MCP server.
        
        Args:
            variable_names: List of OPC UA variable names
            hours_back: Number of hours to look back
            
        Returns:
            List of aggregation results for each variable
        """
        if not self._settings.use_digital_twin:
            self._logger.warning("Digital twin is disabled, cannot get history")
            return []
        
        try:
            self._logger.debug(
                "Getting digital twin history variables=%s hours_back=%s",
                variable_names,
                hours_back,
            )
            
            results = await aggregate_variables_data(
                variable_names=variable_names,
                hours_back=hours_back,
                mcp_url=self._settings.digital_twin_mcp_url,
            )
            
            return results
        except Exception as e:
            self._logger.error("Error getting digital twin history: %s", e)
            return []
    
    async def get_electricity_forecast(self) -> List[ForecastPoint]:
        """Get electricity price forecast from electricity agent (placeholder for future implementation).
        
        Returns:
            List of forecast points
        """
        # TODO: Implement when electricity agent is available
        self._logger.debug("Electricity agent not yet implemented, returning empty forecast")
        return []
    
    async def get_weather_forecast_agent(
        self, *, lookahead_hours: int, location: str
    ) -> List[WeatherPoint]:
        """Get weather forecast from weather agent.
        
        This method calls the weather agent HTTP endpoint to get precipitation
        and temperature forecasts. Falls back to sample data if agent unavailable.
        
        Args:
            lookahead_hours: Hours to forecast ahead (1-72)
            location: Location for forecast (city name or lat,lon)
            
        Returns:
            List of weather points with timestamp, precipitation_mm, temperature_c
        """
        # Use the existing get_weather_forecast which already calls the weather agent
        return await self.get_weather_forecast(
            lookahead_hours=lookahead_hours, location=location
        )

    async def get_forecasts(self) -> List[ForecastSeries]:
        """Generate a 24-hour forecast from now using LinearModel."""
        now = datetime.utcnow()
        horizon = 24
        self._logger.info("Building forecast bundle horizon_hours=%s", horizon)

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        MODEL_PATH = os.path.join(
            BASE_DIR,
            "../../../spot-price-forecast/models/consumption_forecast_model.pkl",
        )
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
        recent_values = hist["y"].iloc[-max_lag:].tolist()

        forecast_hours = pd.date_range(start=now, periods=horizon, freq="h")
        price_predictions = []

        for ts in forecast_hours:
            features = {
                f"y_lag_avg_{lag}": (
                    recent_values[-lag]
                    if len(recent_values) >= lag
                    else recent_values[-1]
                )
                for lag in model.daily_price_lags
            }

            hour = ts.hour
            is_weekend = ts.weekday() >= 5
            for col in feature_cols:
                if col.startswith("weekday_hour_") or col.startswith("weekend_hour_"):
                    features[col] = 0.0
            current = f"weekend_hour_{hour}" if is_weekend else f"weekday_hour_{hour}"
            if current in feature_cols:
                features[current] = 1.0

            X = (
                pd.DataFrame(
                    [
                        [
                            features.get(
                                col,
                                (
                                    last_row[col]
                                    if col in last_row.index and col != "y"
                                    else 0.0
                                ),
                            )
                            for col in feature_cols
                        ]
                    ],
                    columns=feature_cols,
                )
                if feature_cols
                else pd.DataFrame([[0]])
            )

            y_hat = abs(model.predict(X).values[0]) if feature_cols else 1.0
            print(f"Predicted price for {ts.isoformat()}: {y_hat}")
            price_predictions.append(ForecastPoint(timestamp=ts, value=round(y_hat, 2)))

            recent_values.append(y_hat)
            recent_values = recent_values[-max_lag:]

        return [
            ForecastSeries(metric="inflow", unit="m3/s", points=[]),
            ForecastSeries(metric="price", unit="C/kWh", points=price_predictions),
        ]

    async def get_schedule_recommendation(
        self, horizon_minutes: int = 120
    ) -> ScheduleRecommendation:
        """Get optimization schedule recommendation from optimizer agent.
        
        Args:
            horizon_minutes: Optimization horizon in minutes (default: 120)
            
        Returns:
            Schedule recommendation with pump schedule entries
        """
        # Try to use optimizer agent if available
        if self._optimizer_agent and OPTIMIZER_AVAILABLE:
            try:
                self._logger.info(
                    "Requesting optimization schedule from optimizer agent horizon_minutes=%s",
                    horizon_minutes,
                )
                
                # Call optimizer agent
                request = OptimizationRequest(horizon_minutes=horizon_minutes)
                response = self._optimizer_agent.generate_schedule(request)
                
                # Convert OptimizationResponse to ScheduleRecommendation
                entries = [
                    ScheduleEntry(
                        pump_id=entry.pump_id,
                        target_frequency_hz=entry.target_frequency_hz,
                        start_time=entry.start_time,
                        end_time=entry.end_time,
                    )
                    for entry in response.entries
                ]
                
                # Store latest result for dashboard
                self._latest_optimization_result = {
                    "generated_at": response.generated_at.isoformat(),
                    "total_cost_eur": response.total_cost_eur,
                    "total_energy_kwh": response.total_energy_kwh,
                    "optimization_mode": response.optimization_mode,
                    "horizon_minutes": horizon_minutes,
                }
                
                return ScheduleRecommendation(
                    generated_at=response.generated_at,
                    horizon_minutes=horizon_minutes,
                    entries=entries,
                    justification=response.justification,
                )
            except Exception as e:
                self._logger.warning(
                    f"Optimizer agent failed, using fallback: {e}",
                    exc_info=True,
                )
        
        # Fallback to stub data
        now = datetime.utcnow()
        self._logger.info(
            "Producing fallback schedule recommendation generated_at=%s", now.isoformat()
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
            horizon_minutes=horizon_minutes,
            entries=entries,
            justification=justification,
        )
    
    async def trigger_optimization(
        self, horizon_minutes: int = 120
    ) -> Dict[str, Any]:
        """Trigger optimization and return full result with metrics.
        
        Args:
            horizon_minutes: Optimization horizon in minutes
            
        Returns:
            Dictionary with schedule, metrics, and optimization details
        """
        schedule = await self.get_schedule_recommendation(horizon_minutes=horizon_minutes)
        
        result = {
            "schedule": schedule.model_dump(),
            "metrics": self._latest_optimization_result or {},
        }
        
        return result
    
    def get_latest_optimization_metrics(self) -> Optional[Dict[str, Any]]:
        """Get the latest optimization metrics (cost, energy, mode).
        
        Returns:
            Dictionary with optimization metrics or None if not available
        """
        return self._latest_optimization_result

    async def get_weather_forecast(
        self, *, lookahead_hours: int, location: str = None
    ) -> List[WeatherPoint]:
        """Get weather forecast from weather agent (MCP or HTTP) or fallback.
        
        Args:
            lookahead_hours: Hours to forecast ahead (1-72)
            location: Location for forecast (defaults to config value)
            
        Returns:
            List of weather points
        """
        settings = get_settings()
        
        # Use configured location if not provided
        if location is None:
            location = settings.weather_agent_location
        
        # Try weather agent if enabled
        if settings.use_weather_agent:
            # Try MCP server first if enabled
            if settings.use_weather_mcp:
                try:
                    mcp_url = f"{settings.weather_agent_mcp_url.rstrip('/')}/tools/get_precipitation_forecast"
                    payload = {
                        "lookahead_hours": lookahead_hours,
                        "location": location,
                    }
                    self._logger.info(
                        "Requesting weather forecast from MCP server url=%s lookahead_hours=%s location=%s",
                        mcp_url,
                        lookahead_hours,
                        location,
                    )
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(mcp_url, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        self._logger.debug(
                            "Weather MCP server responded successfully points=%s",
                            len(data),
                        )
                        # Convert timestamps from ISO strings to datetime objects
                        weather_points = []
                        for point in data:
                            if isinstance(point.get("timestamp"), str):
                                point["timestamp"] = datetime.fromisoformat(
                                    point["timestamp"].replace("Z", "+00:00")
                                )
                            weather_points.append(WeatherPoint(**point))
                        return weather_points
                except httpx.HTTPStatusError as exc:
                    self._logger.warning(
                        "Weather MCP server returned error status %s, trying HTTP fallback",
                        exc.response.status_code,
                    )
                except httpx.RequestError as exc:
                    self._logger.warning(
                        "Weather MCP server request failed: %s, trying HTTP fallback", exc
                    )
                except Exception as e:
                    self._logger.warning(
                        "Weather MCP server error: %s, trying HTTP fallback", e
                    )
            
            # Fallback to HTTP endpoint
            try:
                url = f"{settings.weather_agent_url.rstrip('/')}/weather/forecast"
                payload = {"lookahead_hours": lookahead_hours, "location": location}
                self._logger.info(
                    "Requesting weather forecast from HTTP endpoint url=%s lookahead_hours=%s location=%s",
                    url,
                    lookahead_hours,
                    location,
                )
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    self._logger.debug(
                        "Weather agent HTTP responded successfully points=%s",
                        len(data),
                    )
                    return [WeatherPoint(**point) for point in data]
            except httpx.HTTPStatusError as exc:
                self._logger.warning(
                    "Weather agent returned error status %s for %s, using fallback",
                    exc.response.status_code,
                    url,
                )
            except httpx.RequestError as exc:
                self._logger.warning(
                    "Weather agent request failed url=%s error=%s, using fallback", url, exc
                )
            except Exception:
                self._logger.exception("Unexpected error while requesting weather forecast, using fallback")

        # Fallback to sample data
        self._logger.debug("Using fallback weather data")
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

    def _build_price_forecast_points(
        self, now: datetime, hours: int
    ) -> List[ForecastPoint]:
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

    def _synthetic_weather_series(
        self, start: datetime, hours: int
    ) -> List[WeatherPoint]:
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

    def _synthetic_price_series(
        self, start: datetime, hours: int
    ) -> List[ForecastPoint]:
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
