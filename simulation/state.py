"""High-level simulation loop that evolves tunnel state over 15 minute steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .constants import DEFAULT_TIME_STEP_SECONDS
from .pumps import PumpCommand, PumpFleetModel
from .tunnel import TunnelModel


@dataclass
class SimulationState:
    level_m: float
    volume_m3: float


@dataclass
class SimulationResult:
    state: SimulationState
    total_outflow_m3_s: float
    total_power_kw: float
    per_pump: dict[str, dict]


class PumpingSimulation:
    def __init__(
        self,
        tunnel: TunnelModel,
        fleet: PumpFleetModel,
        dt_seconds: int = DEFAULT_TIME_STEP_SECONDS,
    ) -> None:
        self._tunnel = tunnel
        self._fleet = fleet
        self._dt_seconds = dt_seconds

    def step(
        self,
        state: SimulationState,
        inflow_m3_s: float,
        commands: Iterable[PumpCommand],
    ) -> SimulationResult:
        current_volume = state.volume_m3 or self._tunnel.volume_from_level(state.level_m)
        level = self._tunnel.clamp_level(state.level_m)
        flow, power, per_pump = self._fleet.compute_flow_and_power(level, commands)
        new_volume = self._tunnel.clamp_volume(current_volume + (inflow_m3_s - flow) * self._dt_seconds)
        new_level = self._tunnel.level_from_volume(new_volume)
        new_state = SimulationState(level_m=new_level, volume_m3=new_volume)
        return SimulationResult(
            state=new_state,
            total_outflow_m3_s=flow,
            total_power_kw=power,
            per_pump=per_pump,
        )

