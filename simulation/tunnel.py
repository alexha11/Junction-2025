"""Tunnel volume/level conversions derived from the HSY documentation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import DEFAULT_TUNNEL_DIMENSIONS, TunnelDimensions


@dataclass
class TunnelModel:
    """Implements the piecewise V=f(L1) curve extracted from the Valmet document."""

    dimensions: TunnelDimensions = DEFAULT_TUNNEL_DIMENSIONS
    base_volume_m3: float = 350.0

    def volume_from_level(self, level_m: float) -> float:
        level = max(0.0, min(level_m, self.dimensions.level_threshold_4_m))
        dims = self.dimensions
        if level < dims.level_threshold_1_m:
            # Document states constant 350 m3, but we allow proportionally less to keep inverse solvable.
            ratio = level / dims.level_threshold_1_m if dims.level_threshold_1_m else 0.0
            return self.base_volume_m3 * ratio
        if level < dims.level_threshold_2_m:
            delta = level - dims.level_threshold_1_m
            return self.base_volume_m3 + 0.5 * 1000 * (delta ** 2) * dims.width_m
        if level < dims.level_threshold_3_m:
            delta = level - dims.level_threshold_2_m
            return 75975.0 + 5500.0 * delta * dims.width_m
        delta = level - dims.level_threshold_3_m
        height = dims.height_m
        term = (height * 5500.0 / 2.0) - (max(height - delta, 0.0) ** 2) * 1000.0 / 2.0
        return 150225.0 + term * dims.width_m

    def level_from_volume(self, volume_m3: float) -> float:
        volume = max(0.0, volume_m3)
        dims = self.dimensions
        if volume <= self.base_volume_m3:
            if self.base_volume_m3 == 0:
                return 0.0
            return (volume / self.base_volume_m3) * dims.level_threshold_1_m
        if volume <= 75975.0:
            # Invert Case 2 quadratic.
            numerator = volume - self.base_volume_m3
            denominator = 0.5 * 1000.0 * dims.width_m
            delta = math.sqrt(max(numerator / denominator, 0.0))
            return dims.level_threshold_1_m + delta
        if volume <= 150225.0:
            delta = (volume - 75975.0) / (5500.0 * dims.width_m)
            return dims.level_threshold_2_m + delta
        a = dims.width_m * 1000.0 / 2.0
        b = dims.width_m * dims.height_m * 5500.0 / 2.0
        remainder = volume - 150225.0
        inside = max((b - remainder) / a, 0.0)
        delta = dims.height_m - math.sqrt(inside)
        return dims.level_threshold_3_m + delta

    def clamp_level(self, level_m: float) -> float:
        return max(0.0, min(level_m, self.dimensions.level_threshold_4_m))

    def clamp_volume(self, volume_m3: float) -> float:
        min_volume = 0.0
        max_volume = self.volume_from_level(self.dimensions.level_threshold_4_m)
        return max(min_volume, min(volume_m3, max_volume))

