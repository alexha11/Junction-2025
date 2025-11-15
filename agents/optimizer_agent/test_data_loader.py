"""Data loader for Hackathon_HSY_data.xlsx for testing optimizer."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .optimizer import CurrentState, ForecastData


class HSYDataLoader:
    """Load and parse Hackathon_HSY_data.xlsx for testing."""

    def __init__(self, excel_file: str, price_type: str = 'normal'):
        """Initialize data loader with Excel file path.
        
        Args:
            excel_file: Path to Excel file
            price_type: 'normal' or 'high' for electricity price column
        """
        self.excel_file = excel_file
        self.price_type = price_type  # 'normal' or 'high'
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
        # - Electricity price column is already provided in c/kWh
        
        if 'Inflow to tunnel F1' in self.df.columns:
            self.df['F1_m3_s'] = self.df['Inflow to tunnel F1'] / 900.0  # m³/15min to m³/s
        
        if 'Sum of pumped flow to WWTP F2' in self.df.columns:
            self.df['F2_m3_s'] = self.df['Sum of pumped flow to WWTP F2'] / 900.0  # m³/15min to m³/s
        
        # Convert pump flows from m³/h to m³/s
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            flow_col = f'Pump flow {pump_num}'
            if flow_col in self.df.columns:
                self.df[f'{flow_col}_m3_s'] = self.df[flow_col] / 3600.0  # m³/h to m³/s
        
        # Electricity price: support both "high" and "normal" columns
        # Select based on price_type parameter
        # Both are already in c/kWh
        if self.price_type == 'high' and 'Electricity price 1: high' in self.df.columns:
            self.df['Price_c_per_kWh'] = self.df['Electricity price 1: high']
        elif 'Electricity price 2: normal' in self.df.columns:
            self.df['Price_c_per_kWh'] = self.df['Electricity price 2: normal']
        else:
            # Fallback: try to use whatever is available
            if 'Electricity price 1: high' in self.df.columns:
                self.df['Price_c_per_kWh'] = self.df['Electricity price 1: high']
            elif 'Electricity price 2: normal' in self.df.columns:
                self.df['Price_c_per_kWh'] = self.df['Electricity price 2: normal']
            else:
                self.df['Price_c_per_kWh'] = 0.0

    def get_state_at_time(self, timestamp: datetime, include_pump_states: bool = False) -> Optional[CurrentState]:
        """Get CurrentState object at given timestamp.
        
        Args:
            timestamp: Time to get state for
            include_pump_states: If True, include pump states from historical data (for reference only).
                                 If False, use empty/default pump states (data represents old strategy with violations).
        
        Note: Historical pump states represent the OLD strategy with constraint violations.
              For optimization, pump states should come from previous optimization results, not historical data.
        """
        if self.df is None:
            return None
        
        # Find closest timestamp using get_indexer
        closest_indices = self.df.index.get_indexer([timestamp], method='nearest')
        if len(closest_indices) == 0 or closest_indices[0] == -1:
            return None
        
        closest_idx = closest_indices[0]
        row = self.df.iloc[closest_idx]
        actual_time = self.df.index[closest_idx]
        
        # Extract pump states ONLY if requested (for reference/comparison)
        # By default, don't use historical pump states as they represent the old strategy
        pump_states: List[Tuple[str, bool, float]] = []
        if include_pump_states:
            for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
                flow_col = f'Pump flow {pump_num}'
                freq_col = f'Pump frequency {pump_num}'
                
                # Use dataset pump ID directly
                pump_id = pump_num
                
                flow = row.get(f'{flow_col}_m3_s', row.get(flow_col, 0.0))
                freq = row.get(freq_col, 0.0)
                is_on = flow > 0.01 and freq > 10.0  # Threshold for pump being on
                
                pump_states.append((pump_id, bool(is_on), float(freq)))
        else:
            # Default: all pumps off (will be set by optimizer)
            for pump_id in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
                pump_states.append((pump_id, False, 0.0))
        
        return CurrentState(
            timestamp=actual_time.to_pydatetime(),
            l1_m=float(row.get('Water level in tunnel L1', 0.0)),
            inflow_m3_s=float(row.get('F1_m3_s', row.get('Inflow to tunnel F1', 0.0) / 900.0)),
            outflow_m3_s=float(row.get('F2_m3_s', row.get('Sum of pumped flow to WWTP F2', 0.0) / 900.0)),
            pump_states=pump_states,  # Empty/default by default - represents old strategy violations
            # Store price in c/kWh
            price_c_per_kwh=float(row.get('Price_c_per_kWh', row.get('Electricity price 2: normal', 0.0))),
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
            prices = forecast_df['Price_c_per_kWh'].fillna(0.0).tolist()
            
        elif method == 'persistence':
            # Use last known value
            if start_idx > 0:
                last_inflow = self.df.iloc[start_idx - 1].get('F1_m3_s', 0.0)
                last_price = self.df.iloc[start_idx - 1].get('Price_c_per_kWh', 0.0)
            else:
                last_inflow = self.df.iloc[0].get('F1_m3_s', 0.0)
                last_price = self.df.iloc[0].get('Price_c_per_kWh', 0.0)
            
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
            price_c_per_kwh=prices[:horizon_steps],
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
            # Use dataset pump ID directly (1.1-1.4, 2.1-2.4)
            pump_id = pump_num
            
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
        """Extract pump specifications from historical data.
        
        DEPRECATED: Pump specs are now hardcoded in test_optimizer_with_data.py
        to avoid learning from old system's strategy decisions.
        
        This method extracted pump specs from historical operational data, but that
        created circular reasoning (calibrating new strategy from old bad strategy).
        Now we use hardcoded physical pump capacities instead.
        
        Kept for reference only.
        """
        if self.df is None:
            return {}
        
        specs = {}
        for pump_num in ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4']:
            # Use dataset pump ID directly (1.1-1.4, 2.1-2.4)
            pump_id = pump_num
            
            flow_col = f'Pump flow {pump_num}'
            power_col = f'Pump power uptake {pump_num}'
            freq_col = f'Pump frequency {pump_num}'
            
            # Get max values from historical data (operational parameters)
            max_flow_m3_s = (self.df[f'{flow_col}_m3_s'].max() 
                           if f'{flow_col}_m3_s' in self.df.columns 
                           else self.df[flow_col].max() / 3600.0)
            max_power_kw = self.df[power_col].max()
            
            # Frequency limits are pump hardware specifications, not operational data
            # Use fixed standard values (don't extract from historical operational data)
            # Historical frequency data shows what was used, not what the pump is capable of
            min_freq_hz = 47.8  # Standard minimum operating frequency for pumps
            max_freq_hz = 50.0  # Standard maximum operating frequency for pumps
            
            # Analyze power vs L1 relationship from historical data
            # Power = f(flow, frequency, L1/lifting_height, efficiency)
            # Higher L1 = lower lifting height = less power needed (if pumping to fixed level above L1)
            # Extract relationship: when pump is running, how does power vary with L1?
            l1_col = 'Water level in tunnel L1'
            power_vs_l1_slope = 0.0  # kW per meter of L1 change
            power_vs_l1_base = max_power_kw * 0.8  # Base power at reference L1
            
            if (power_col in self.df.columns and l1_col in self.df.columns and 
                freq_col in self.df.columns):
                # Filter to pump-on conditions (flow > 0 or frequency > 10 Hz)
                pump_on_mask = (
                    (self.df[power_col] > 0.1) | 
                    (self.df[freq_col] > 10.0)
                )
                
                if pump_on_mask.sum() > 10:  # Need sufficient data points
                    pump_data = self.df[pump_on_mask].copy()
                    
                    # Get flow column (convert if needed)
                    flow_data = (pump_data[f'{flow_col}_m3_s'] 
                               if f'{flow_col}_m3_s' in pump_data.columns
                               else pump_data[flow_col] / 3600.0)
                    
                    # Analyze power vs L1 for similar flow/frequency conditions
                    # For similar flow and frequency, power should decrease with L1
                    # (higher L1 = less lifting height needed)
                    try:
                        # Calculate correlation between power and L1 at similar operating points
                        # Group by frequency bins to normalize for frequency effects
                        freq_bins = pd.cut(pump_data[freq_col], bins=5, labels=False)
                        
                        # For each frequency bin, check if power decreases with L1
                        for bin_idx in range(5):
                            bin_mask = (freq_bins == bin_idx) & (flow_data > 0.1)
                            if bin_mask.sum() > 5:
                                bin_data = pump_data[bin_mask]
                                bin_power = bin_data[power_col]
                                bin_l1 = bin_data[l1_col]
                                
                                # Simple linear fit: power = base - slope * L1
                                # (negative slope: higher L1 = less power)
                                if bin_l1.std() > 0.1:  # Need variation in L1
                                    correlation = bin_power.corr(bin_l1)
                                    if correlation < -0.3:  # Significant negative correlation
                                        # Estimate slope (power change per meter of L1)
                                        slope_estimate = (bin_power.max() - bin_power.min()) / (
                                            bin_l1.max() - bin_l1.min() + 1e-6
                                        )
                                        if slope_estimate < 0:  # Power decreases with L1
                                            power_vs_l1_slope = abs(slope_estimate) * 0.5  # Conservative estimate
                                            break
                    except Exception:
                        # If analysis fails, use default (no L1 correction)
                        pass
            
            # If no significant correlation found, use small default slope
            # Typical: ~1-5% power reduction per meter of L1 increase
            if power_vs_l1_slope < 0.1:
                power_vs_l1_slope = max_power_kw * 0.02  # ~2% per meter (conservative)
            
            specs[pump_id] = {
                'max_flow_m3_s': float(max_flow_m3_s),
                'max_power_kw': float(max_power_kw),
                'max_frequency_hz': max_freq_hz,  # Fixed hardware specification
                'min_frequency_hz': min_freq_hz,  # Fixed hardware specification
                'power_vs_l1_slope_kw_per_m': float(power_vs_l1_slope),  # Power reduction per meter of L1 increase
                'power_l1_reference_m': 4.0,  # Reference L1 level for power calculation
            }
        
        return specs

