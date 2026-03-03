from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List


@dataclass(frozen=True)
class PumpSpec:
    pump_id: str
    kind: str
    flow_m3_s: float
    power_kw: float
    efficiency: float
    min_on_steps: int = 8
    min_off_steps: int = 8


@dataclass
class TimeStepData:
    timestamp: datetime
    level_m: float
    volume_m3: float
    inflow_m3_s: float
    price_c_per_kwh: float


@dataclass
class PumpState:
    is_on: bool = False
    steps_in_state: int = 999999


@dataclass
class ScheduleDecision:
    timestamp: datetime
    level_before_m: float
    level_after_m: float
    inflow_m3_s: float
    outflow_m3_s: float
    price_c_per_kwh: float
    pumps_on: List[str]
    total_power_kw: float
    energy_kwh: float
    cost_eur: float
    flush_active: bool


@dataclass
class RunSummary:
    steps: int
    min_level_m: float
    max_level_m: float
    avg_outflow_m3_s: float
    outflow_std_m3_s: float
    total_energy_kwh: float
    total_cost_eur: float
    specific_energy_kwh_per_m3: float
    violation_l1_min_steps: int
    violation_l1_max_steps: int
    daily_flush_hits: int
    per_pump_runtime_hours: Dict[str, float]
    max_daily_runtime_spread_hours: float
    daily_runtime_balance_violations: int
