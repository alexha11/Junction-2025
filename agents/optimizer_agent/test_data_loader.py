"""Data loader for Hackathon_HSY_data.xlsx for testing optimizer."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .optimizer import CurrentState, ForecastData


class HSYDataLoader:
    """Load and parse Hackathon_HSY_data.xlsx for testing."""

    def __init__(self, excel_file: str):
        """Initialize data loader with Excel file path."""
        self.excel_file = excel_file
        self.df: Optional[pd.DataFrame] = None
        self._load_data()

    def _load_data(self) -> None:
        """Load and preprocess Excel data."""
        # Read Excel file
        # Row 0 contains column names, row 1 contains units - we'll use row 0 as header
        # and skip row 1 by filtering out rows where timestamp is NaT or is a string like 'm', 'm3', etc.
        self.df = pd.read_excel(self.excel_file, skiprows=0)
        
        # Rename columns for easier access
        self.df.columns = self.df.columns.str.strip()
        
        # Convert timestamp column to datetime and filter out unit row
        if 'Time stamp' in self.df.columns:
            self.df['Time stamp'] = pd.to_datetime(self.df['Time stamp'], errors='coerce')
            # Remove rows where timestamp is NaT (unit row and any invalid rows)
            self.df = self.df[self.df['Time stamp'].notna()].copy()
            # Set timestamp as index
            self.df.set_index('Time stamp', inplace=True)
        
        # Parse numeric columns, handling any string values with units
        numeric_cols = [
            'Water level in tunnel L1',
            'Water volume in tunnel V',
            'Sum of pumped flow to WWTP F2',
            'Inflow to tunnel F1',
        ]
        
        # Add pump columns
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            numeric_cols.extend([
                f'Pump flow {pump_num}',
                f'Pump power uptake {pump_num}',
                f'Pump frequency {pump_num}',
            ])
        
        # Add price columns
        numeric_cols.extend([
            'Electricity price 1: high',
            'Electricity price 2: normal',
        ])
        
        # Convert to numeric, coercing errors to NaN
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
        
        # Forward fill missing values
        self.df.ffill(inplace=True)
        self.df.bfill(inplace=True)  # Fill any remaining NaNs at start
        
        # Convert units:
        # - F1 (Inflow) is in m³/15min -> convert to m³/s (divide by 15*60 = 900)
        # - F2 (Outflow) is in m³/15min -> convert to m³/s
        # - Pump flows are in m³/h -> convert to m³/s (divide by 3600)
        # - Electricity price is in EUR/kWh -> convert to EUR/MWh (multiply by 1000)
        
        if 'Inflow to tunnel F1' in self.df.columns:
            self.df['F1_m3_s'] = self.df['Inflow to tunnel F1'] / 900.0  # m³/15min to m³/s
        
        if 'Sum of pumped flow to WWTP F2' in self.df.columns:
            self.df['F2_m3_s'] = self.df['Sum of pumped flow to WWTP F2'] / 900.0  # m³/15min to m³/s
        
        # Convert pump flows from m³/h to m³/s
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            flow_col = f'Pump flow {pump_num}'
            if flow_col in self.df.columns:
                self.df[f'{flow_col}_m3_s'] = self.df[flow_col] / 3600.0  # m³/h to m³/s
        
        # Convert electricity price from EUR/kWh to EUR/MWh
        if 'Electricity price 2: normal' in self.df.columns:
            self.df['Price_EUR_MWh'] = self.df['Electricity price 2: normal'] * 1000.0

    def get_state_at_time(self, timestamp: datetime) -> Optional[CurrentState]:
        """Get CurrentState object at given timestamp."""
        if self.df is None:
            return None
        
        # Find closest timestamp using get_indexer
        closest_indices = self.df.index.get_indexer([timestamp], method='nearest')
        if len(closest_indices) == 0 or closest_indices[0] == -1:
            return None
        
        closest_idx = closest_indices[0]
        row = self.df.iloc[closest_idx]
        actual_time = self.df.index[closest_idx]
        
        # Extract pump states
        pump_states: List[Tuple[str, bool, float]] = []
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            flow_col = f'Pump flow {pump_num}'
            freq_col = f'Pump frequency {pump_num}'
            
            # Map pump ID from data format (1.1, 1.2) to optimizer format (P1, P2, etc.)
            # Pumps 1.1-1.4 become P1-P4, pumps 2.1-2.4 become P5-P8
            if pump_num.startswith('1.'):
                pump_id = f"P{int(pump_num.split('.')[1])}"
            else:  # 2.x
                pump_id = f"P{int(pump_num.split('.')[1]) + 4}"
            
            flow = row.get(f'{flow_col}_m3_s', row.get(flow_col, 0.0))
            freq = row.get(freq_col, 0.0)
            is_on = flow > 0.01 and freq > 10.0  # Threshold for pump being on
            
            pump_states.append((pump_id, bool(is_on), float(freq)))
        
        return CurrentState(
            timestamp=actual_time.to_pydatetime(),
            l1_m=float(row.get('Water level in tunnel L1', 0.0)),
            inflow_m3_s=float(row.get('F1_m3_s', row.get('Inflow to tunnel F1', 0.0) / 900.0)),
            outflow_m3_s=float(row.get('F2_m3_s', row.get('Sum of pumped flow to WWTP F2', 0.0) / 900.0)),
            pump_states=pump_states,
            price_eur_mwh=float(row.get('Price_EUR_MWh', row.get('Electricity price 2: normal', 0.0) * 1000.0)),
        )

    def get_forecast_from_time(
        self, timestamp: datetime, horizon_steps: int, method: str = 'perfect'
    ) -> Optional[ForecastData]:
        """Get ForecastData from given timestamp using specified method.
        
        Args:
            timestamp: Starting timestamp
            horizon_steps: Number of 15-minute steps to forecast
            method: 'perfect' uses historical data, 'persistence' uses last known value
        """
        if self.df is None:
            return None
        
        # Find starting index using get_indexer
        try:
            start_indices = self.df.index.get_indexer([timestamp], method='nearest')
            if len(start_indices) == 0 or start_indices[0] == -1:
                return None
            start_idx = start_indices[0]
        except (KeyError, ValueError):
            return None
        
        end_idx = min(start_idx + horizon_steps, len(self.df))
        
        if method == 'perfect':
            # Use historical future data as "perfect forecast"
            forecast_df = self.df.iloc[start_idx:end_idx]
            timestamps = forecast_df.index.to_list()
            inflows = forecast_df['F1_m3_s'].fillna(0.0).tolist()
            prices = forecast_df['Price_EUR_MWh'].fillna(0.0).tolist()
            
        elif method == 'persistence':
            # Use last known value
            if start_idx > 0:
                last_inflow = self.df.iloc[start_idx - 1].get('F1_m3_s', 0.0)
                last_price = self.df.iloc[start_idx - 1].get('Price_EUR_MWh', 0.0)
            else:
                last_inflow = self.df.iloc[0].get('F1_m3_s', 0.0)
                last_price = self.df.iloc[0].get('Price_EUR_MWh', 0.0)
            
            timestamps = [
                timestamp + pd.Timedelta(minutes=15 * i)
                for i in range(horizon_steps)
            ]
            inflows = [last_inflow] * horizon_steps
            prices = [last_price] * horizon_steps
            
        else:
            return None
        
        # Ensure correct length
        while len(timestamps) < horizon_steps:
            timestamps.append(timestamps[-1] + pd.Timedelta(minutes=15))
        while len(inflows) < horizon_steps:
            inflows.append(inflows[-1] if inflows else 0.0)
        while len(prices) < horizon_steps:
            prices.append(prices[-1] if prices else 0.0)
        
        return ForecastData(
            timestamps=[ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts for ts in timestamps[:horizon_steps]],
            inflow_m3_s=inflows[:horizon_steps],
            price_eur_mwh=prices[:horizon_steps],
        )

    def get_baseline_schedule_at_time(self, timestamp: datetime) -> dict:
        """Get baseline pump schedule from historical data."""
        if self.df is None:
            return {}
        
        try:
            row_indices = self.df.index.get_indexer([timestamp], method='nearest')
            if len(row_indices) == 0 or row_indices[0] == -1:
                return {}
            row_idx = row_indices[0]
            row = self.df.iloc[row_idx]
        except (KeyError, IndexError, ValueError):
            return {}
        
        schedule = {}
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            # Map pump ID
            if pump_num.startswith('1.'):
                pump_id = f"P{int(pump_num.split('.')[1])}"
            else:
                pump_id = f"P{int(pump_num.split('.')[1]) + 4}"
            
            flow_col = f'Pump flow {pump_num}'
            freq_col = f'Pump frequency {pump_num}'
            power_col = f'Pump power uptake {pump_num}'
            
            flow_m3_s = row.get(f'{flow_col}_m3_s', row.get(flow_col, 0.0) / 3600.0)
            freq_hz = row.get(freq_col, 0.0)
            power_kw = row.get(power_col, 0.0)
            is_on = flow_m3_s > 0.01 and freq_hz > 10.0
            
            schedule[pump_id] = {
                'is_on': bool(is_on),
                'frequency_hz': float(freq_hz),
                'flow_m3_s': float(flow_m3_s),
                'power_kw': float(power_kw),
            }
        
        return schedule

    def get_data_range(self) -> Tuple[datetime, datetime]:
        """Get the time range of available data."""
        if self.df is None or len(self.df) == 0:
            raise ValueError("No data loaded")
        
        start_idx = self.df.index[0]
        end_idx = self.df.index[-1]
        
        # Handle different index types
        if isinstance(start_idx, pd.Timestamp):
            start_dt = start_idx.to_pydatetime()
        elif isinstance(start_idx, datetime):
            start_dt = start_idx
        else:
            # Fallback: convert if it's a datetime-like value
            start_dt = pd.to_datetime(start_idx).to_pydatetime()
        
        if isinstance(end_idx, pd.Timestamp):
            end_dt = end_idx.to_pydatetime()
        elif isinstance(end_idx, datetime):
            end_dt = end_idx
        else:
            end_dt = pd.to_datetime(end_idx).to_pydatetime()
        
        return (start_dt, end_dt)

    def get_pump_specs_from_data(self) -> dict:
        """Extract pump specifications from historical data."""
        if self.df is None:
            return {}
        
        specs = {}
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            # Map pump ID
            if pump_num.startswith('1.'):
                pump_id = f"P{int(pump_num.split('.')[1])}"
            else:
                pump_id = f"P{int(pump_num.split('.')[1]) + 4}"
            
            flow_col = f'Pump flow {pump_num}'
            power_col = f'Pump power uptake {pump_num}'
            freq_col = f'Pump frequency {pump_num}'
            
            # Get max values from historical data
            max_flow_m3_s = (self.df[f'{flow_col}_m3_s'].max() 
                           if f'{flow_col}_m3_s' in self.df.columns 
                           else self.df[flow_col].max() / 3600.0)
            max_power_kw = self.df[power_col].max()
            max_freq_hz = self.df[freq_col].max()
            min_freq_hz = self.df[freq_col][self.df[freq_col] > 10.0].min()  # Only when pump is on
            
            specs[pump_id] = {
                'max_flow_m3_s': float(max_flow_m3_s),
                'max_power_kw': float(max_power_kw),
                'max_frequency_hz': float(max_freq_hz),
                'min_frequency_hz': float(min_freq_hz) if not np.isnan(min_freq_hz) else 47.8,
            }
        
        return specs

