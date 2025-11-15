"""Shared constants for the HSY tunnel simulation package."""

from __future__ import annotations

from dataclasses import dataclass

WATER_DENSITY_KG_M3 = 1000.0
GRAVITY_M_S2 = 9.81
DEFAULT_TIME_STEP_SECONDS = 900  # 15 minutes
NOMINAL_PUMP_FREQUENCY_HZ = 50.0
MIN_PUMP_FREQUENCY_HZ = 47.5


@dataclass(frozen=True)
class TunnelDimensions:
    width_m: float = 5.0
    height_m: float = 5.5
    length_m: float = 8200.0
    level_threshold_1_m: float = 0.4
    level_threshold_2_m: float = 5.9
    level_threshold_3_m: float = 8.6
    level_threshold_4_m: float = 14.1


DEFAULT_TUNNEL_DIMENSIONS = TunnelDimensions()

# Engineering assumption: delivery head is approximately 45 m when the tunnel surface is at 0 m.
# We raise the head as the level increases to capture the higher static lift requirement.
BASE_DELIVERY_HEAD_M = 45.0
HEAD_GAIN_PER_M_LEVEL = 0.5

