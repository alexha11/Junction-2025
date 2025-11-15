"""Utilities for loading the HSY historical dataset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "digital-twin" / "opcua-server" / "data" / "historical-data.parquet"
)


@dataclass
class HistoricalDataset:
    path: Path = DEFAULT_DATA_PATH
    level_column: str = "water_level_in_tunnel_l2"
    inflow_column: str = "inflow_to_tunnel_f1"
    outflow_column: str = "sum_of_pumped_flow_to_wwtp_f2"

    def load(self, columns: Iterable[str] | None = None) -> pd.DataFrame:
        if columns is None:
            df = pd.read_parquet(self.path)
        else:
            df = pd.read_parquet(self.path, columns=list(columns))
        df = df.sort_index()
        return df

