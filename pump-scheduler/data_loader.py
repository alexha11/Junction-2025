from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

try:
    from .models import TimeStepData
except ImportError:  # pragma: no cover - allows running as script
    from models import TimeStepData


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class LevelVolumeCurve:
    levels: List[float]
    volumes: List[float]

    def level_to_volume(self, level_m: float) -> float:
        if level_m <= self.levels[0]:
            return self.volumes[0]
        if level_m >= self.levels[-1]:
            return self.volumes[-1]
        for i in range(1, len(self.levels)):
            if level_m <= self.levels[i]:
                l0, l1 = self.levels[i - 1], self.levels[i]
                v0, v1 = self.volumes[i - 1], self.volumes[i]
                w = (level_m - l0) / (l1 - l0)
                return v0 + w * (v1 - v0)
        return self.volumes[-1]

    def volume_to_level(self, volume_m3: float) -> float:
        if volume_m3 <= self.volumes[0]:
            return self.levels[0]
        if volume_m3 >= self.volumes[-1]:
            return self.levels[-1]
        for i in range(1, len(self.volumes)):
            if volume_m3 <= self.volumes[i]:
                v0, v1 = self.volumes[i - 1], self.volumes[i]
                l0, l1 = self.levels[i - 1], self.levels[i]
                w = (volume_m3 - v0) / (v1 - v0)
                return l0 + w * (l1 - l0)
        return self.levels[-1]


def _to_float(raw: str) -> float:
    return float(raw.strip()) if raw is not None and raw != "" else 0.0


def load_hsy_csv(path: Path, price_column: str = "normal") -> Tuple[List[TimeStepData], LevelVolumeCurve]:
    """Load HSY CSV and convert units.

    CSV units:
    - Inflow to tunnel F1: m3 / 15 min -> converted to m3/s
    - Electricity price: c/kWh (already)
    """
    price_col = (
        "Electricity price (c/kWh) 1: high"
        if price_column == "high"
        else "Electricity price (c/kWh) 2: normal"
    )

    data: List[TimeStepData] = []
    curve_points: List[Tuple[float, float]] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.strptime(row["Time stamp"], TIME_FORMAT)
            level = _to_float(row["Water level in tunnel L2"])
            volume = _to_float(row["Water volume in tunnel V"])
            inflow_m3_s = _to_float(row["Inflow to tunnel F1"]) / 900.0
            price_c_per_kwh = _to_float(row.get(price_col, "0"))
            data.append(
                TimeStepData(
                    timestamp=ts,
                    level_m=level,
                    volume_m3=volume,
                    inflow_m3_s=inflow_m3_s,
                    price_c_per_kwh=price_c_per_kwh,
                )
            )
            curve_points.append((level, volume))

    curve = build_level_volume_curve(curve_points)
    return data, curve


def build_level_volume_curve(points: List[Tuple[float, float]]) -> LevelVolumeCurve:
    """Build monotonic piecewise-linear curve by averaging duplicate levels."""
    if not points:
        raise ValueError("No level-volume points available")

    buckets: dict[float, List[float]] = {}
    for level, volume in points:
        key = round(level, 3)
        buckets.setdefault(key, []).append(volume)

    pairs = sorted((lvl, sum(vals) / len(vals)) for lvl, vals in buckets.items())

    levels = [pairs[0][0]]
    volumes = [pairs[0][1]]
    for lvl, vol in pairs[1:]:
        if vol <= volumes[-1]:
            vol = volumes[-1] + 1e-6
        levels.append(lvl)
        volumes.append(vol)

    return LevelVolumeCurve(levels=levels, volumes=volumes)
