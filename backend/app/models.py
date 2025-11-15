from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PumpState(str, Enum):
    on = "on"
    off = "off"


class PumpStatus(BaseModel):
    pump_id: str
    state: PumpState
    frequency_hz: float = Field(ge=0)
    power_kw: float = Field(ge=0)


class SystemState(BaseModel):
    timestamp: datetime
    tunnel_level_m: float = Field(description="L1")
    tunnel_level_l2_m: float = Field(description="L2")
    inflow_m3_s: float = Field(description="F1")
    outflow_m3_s: float = Field(description="F2")
    electricity_price_eur_mwh: float
    pumps: List[PumpStatus]


class ForecastPoint(BaseModel):
    timestamp: datetime
    value: float


class ForecastSeries(BaseModel):
    metric: str
    unit: str
    points: List[ForecastPoint]


class WeatherPoint(BaseModel):
    timestamp: datetime
    precipitation_mm: float
    temperature_c: float


class WeatherForecastRequest(BaseModel):
    lookahead_hours: int = Field(gt=0, le=72)
    location: str = Field(default="Helsinki", min_length=1, max_length=128)


class ScheduleEntry(BaseModel):
    pump_id: str
    target_frequency_hz: float
    start_time: datetime
    end_time: datetime


class ScheduleRecommendation(BaseModel):
    generated_at: datetime
    horizon_minutes: int
    entries: List[ScheduleEntry]
    justification: str


class OverrideRequest(BaseModel):
    schedule_id: str
    operator: str
    reason: str
    accepted: bool


class AlertLevel(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class Alert(BaseModel):
    id: str
    level: AlertLevel
    message: str
    detected_at: datetime
    acknowledged_at: Optional[datetime] = None
