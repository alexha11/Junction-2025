"""Pump curve derivation and fleet-level flow/power calculations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

import numpy as np
import pandas as pd

from .constants import (
    BASE_DELIVERY_HEAD_M,
    GRAVITY_M_S2,
    HEAD_GAIN_PER_M_LEVEL,
    MIN_PUMP_FREQUENCY_HZ,
    NOMINAL_PUMP_FREQUENCY_HZ,
    WATER_DENSITY_KG_M3,
)
from .dataset import DEFAULT_DATA_PATH, HistoricalDataset
from .tunnel import TunnelModel


@dataclass(frozen=True)
class PumpCommand:
    pump_id: str
    frequency_hz: float = NOMINAL_PUMP_FREQUENCY_HZ


@dataclass
class PumpCurve:
    pump_id: str
    level_midpoints: np.ndarray
    flow_values: np.ndarray
    efficiency_values: np.ndarray

    def flow(self, level_m: float) -> float:
        return float(np.interp(level_m, self.level_midpoints, self.flow_values, left=0.0, right=self.flow_values[-1]))

    def efficiency(self, level_m: float) -> float:
        return float(
            np.interp(
                level_m,
                self.level_midpoints,
                self.efficiency_values,
                left=self.efficiency_values[0],
                right=self.efficiency_values[-1],
            )
        )


@dataclass
class PumpFleetModel:
    tunnel: TunnelModel
    curves: Mapping[str, PumpCurve]
    min_frequency_hz: float = MIN_PUMP_FREQUENCY_HZ
    nominal_frequency_hz: float = NOMINAL_PUMP_FREQUENCY_HZ

    def compute_flow_and_power(
        self,
        level_m: float,
        commands: Iterable[PumpCommand],
    ) -> tuple[float, float, Dict[str, dict]]:
        total_flow = 0.0
        total_power = 0.0
        per_pump: Dict[str, dict] = {}
        for command in commands:
            curve = self.curves.get(command.pump_id)
            if curve is None:
                continue
            frequency = max(command.frequency_hz, 0.0)
            if frequency < self.min_frequency_hz:
                continue
            frequency_scale = frequency / self.nominal_frequency_hz
            base_flow = curve.flow(level_m)
            flow = base_flow * frequency_scale
            efficiency = max(curve.efficiency(level_m), 0.05)
            head = BASE_DELIVERY_HEAD_M + level_m * HEAD_GAIN_PER_M_LEVEL
            power_kw = (WATER_DENSITY_KG_M3 * GRAVITY_M_S2 * head * flow) / (efficiency * 1000.0)
            total_flow += flow
            total_power += power_kw
            per_pump[command.pump_id] = {
                "frequency_hz": frequency,
                "flow_m3_s": flow,
                "power_kw": power_kw,
                "efficiency": efficiency,
            }
        return total_flow, total_power, per_pump


PUMP_COLUMN_TEMPLATE = {
    "P11": ("pump_flow_11", "pump_efficiency_11", "pump_frequency_11"),
    "P12": ("pump_flow_12", "pump_efficiency_12", "pump_frequency_12"),
    "P13": ("pump_flow_13", "pump_efficiency_13", "pump_frequency_13"),
    "P14": ("pump_flow_14", "pump_efficiency_14", "pump_frequency_14"),
    "P21": ("pump_flow_21", "pump_efficiency_21", "pump_frequency_21"),
    "P22": ("pump_flow_22", "pump_efficiency_22", "pump_frequency_22"),
    "P23": ("pump_flow_23", "pump_efficiency_23", "pump_frequency_23"),
    "P24": ("pump_flow_24", "pump_efficiency_24", "pump_frequency_24"),
}


def build_fleet_from_historical_data(
    dataset_path: Path = DEFAULT_DATA_PATH,
    level_column: str = "water_level_in_tunnel_l2",
) -> PumpFleetModel:
    columns: List[str] = [level_column]
    for flow_col, eff_col, freq_col in PUMP_COLUMN_TEMPLATE.values():
        columns.extend([flow_col, eff_col, freq_col])
    df = HistoricalDataset(path=dataset_path, level_column=level_column).load(columns)
    curves: Dict[str, PumpCurve] = {}
    for pump_id, (flow_col, eff_col, freq_col) in PUMP_COLUMN_TEMPLATE.items():
        pump_df = df[[level_column, flow_col, eff_col, freq_col]].dropna()
        pump_df = pump_df[pump_df[freq_col] >= MIN_PUMP_FREQUENCY_HZ]
        pump_df = pump_df[pump_df[flow_col] > 0.01]
        if pump_df.empty:
            continue
        stats = _aggregate_curve_points(pump_df, level_column, flow_col, eff_col)
        if stats is None:
            continue
        levels, flows, efficiencies = stats
        curves[pump_id] = PumpCurve(
            pump_id=pump_id,
            level_midpoints=levels,
            flow_values=flows,
            efficiency_values=efficiencies,
        )
    if not curves:
        raise RuntimeError("Failed to derive pump curves from historical dataset")
    return PumpFleetModel(tunnel=TunnelModel(), curves=curves)


def _aggregate_curve_points(
    pump_df: pd.DataFrame,
    level_col: str,
    flow_col: str,
    eff_col: str,
    bins: int = 40,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    level_min = pump_df[level_col].min()
    level_max = pump_df[level_col].max()
    if not np.isfinite(level_min) or not np.isfinite(level_max):
        return None
    if level_max - level_min < 0.1:
        return None
    bin_edges = np.linspace(level_min, level_max, bins)
    pump_df = pump_df.copy()
    pump_df["level_bin"] = pd.cut(pump_df[level_col], bins=bin_edges, include_lowest=True)
    grouped = (
        pump_df.groupby("level_bin", observed=False)
        .agg({level_col: "mean", flow_col: "mean", eff_col: "mean"})
        .dropna()
    )
    if grouped.empty:
        return None
    # Remove zero-flow bins to keep interpolation stable.
    grouped = grouped[grouped[flow_col] > 0.0]
    if grouped.empty:
        return None
    levels = grouped[level_col].to_numpy()
    flows = grouped[flow_col].to_numpy()
    efficiencies = grouped[eff_col].clip(lower=0.05).to_numpy()
    sort_idx = np.argsort(levels)
    return levels[sort_idx], flows[sort_idx], efficiencies[sort_idx]

