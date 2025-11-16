"""Digital Twin Adapter - Maps OPC UA variables to internal models and handles unit conversions."""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Tunnel volume constant (m³) - used to convert volume to level
TUNNEL_VOLUME_M3 = 50000.0

# OPC UA variable display names to internal field mapping
VARIABLE_MAPPING = {
    "WaterLevelInTunnel.L2.m": "tunnel_level_l2_m",
    "WaterVolumeInTunnel.L1.m3": "tunnel_level_m",  # needs conversion from volume to level
    "InflowToTunnel.F1.m3per15min": "inflow_m3_s",
    "SumOfPumpedFlowToWwtp.F2.m3h": "outflow_m3_s",
    "ElectricityPrice.2.Normal.ckwh": "price_c_per_kwh",
}

# Pump variable patterns
PUMP_IDS = ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4"]


class DigitalTwinAdapter:
    """Adapter to convert OPC UA variables to internal SystemState model."""

    @staticmethod
    def convert_opcua_to_system_state(opcua_values: Dict[str, float]) -> Dict:
        """Convert OPC UA variable values to SystemState-compatible dictionary.
        
        Args:
            opcua_values: Dictionary of OPC UA variable names to values
            
        Returns:
            Dictionary with keys matching SystemState model fields
        """
        result = {}
        
        # Map tunnel levels
        if "WaterLevelInTunnel.L2.m" in opcua_values:
            result["tunnel_level_l2_m"] = float(opcua_values["WaterLevelInTunnel.L2.m"])
        
        # Convert L1 volume to level
        if "WaterVolumeInTunnel.L1.m3" in opcua_values:
            volume_m3 = float(opcua_values["WaterVolumeInTunnel.L1.m3"])
            # Convert volume to level (assuming constant cross-section)
            # Level = Volume / CrossSectionArea
            # For simplicity, use: Level ≈ Volume / (TunnelVolume / MaxLevel)
            # Max level is typically 8m, so cross-section ≈ 50000/8 = 6250 m²
            # Level = Volume / 6250
            result["tunnel_level_m"] = volume_m3 / (TUNNEL_VOLUME_M3 / 8.0)
            result["tunnel_water_volume_l1_m3"] = volume_m3
        else:
            result["tunnel_water_volume_l1_m3"] = 0.0
        
        # Convert inflow (m³ per 15 min → m³/s)
        if "InflowToTunnel.F1.m3per15min" in opcua_values:
            f1_m3per15min = float(opcua_values["InflowToTunnel.F1.m3per15min"])
            result["inflow_m3_s"] = f1_m3per15min / 900.0  # 15 min = 900 seconds
        else:
            result["inflow_m3_s"] = 0.0
        
        # Convert outflow (m³/h → m³/s)
        if "SumOfPumpedFlowToWwtp.F2.m3h" in opcua_values:
            f2_m3h = float(opcua_values["SumOfPumpedFlowToWwtp.F2.m3h"])
            result["outflow_m3_s"] = f2_m3h / 3600.0
        else:
            result["outflow_m3_s"] = 0.0
        
        # Convert electricity price (c/kWh → EUR/MWh)
        # 1 c/kWh = 10 EUR/MWh (1 cent = 0.01 EUR, 1 kWh = 0.001 MWh, so 0.01/0.001 = 10)
        if "ElectricityPrice.2.Normal.ckwh" in opcua_values:
            price_ckwh = float(opcua_values["ElectricityPrice.2.Normal.ckwh"])
            result["electricity_price_eur_mwh"] = price_ckwh * 10.0
        else:
            result["electricity_price_eur_mwh"] = 0.0
        
        # Extract pump data
        pumps = []
        for pump_id in PUMP_IDS:
            # Extract pump frequency
            freq_var = f"PumpFrequency.{pump_id}.hz"
            frequency_hz = float(opcua_values.get(freq_var, 0.0))
            
            # Extract pump flow to determine state
            flow_var = f"PumpFlow.{pump_id}.m3h"
            flow_m3h = float(opcua_values.get(flow_var, 0.0))
            is_on = flow_m3h > 0.01  # Consider pump on if flow > 0.01 m³/h
            
            # Extract pump power
            power_var = f"PumpEfficiency.{pump_id}.kw"
            power_kw = float(opcua_values.get(power_var, 0.0))
            
            # If pump is off, set frequency and power to 0
            if not is_on:
                frequency_hz = 0.0
                power_kw = 0.0
            
            pumps.append({
                "pump_id": pump_id,
                "state": "on" if is_on else "off",
                "frequency_hz": frequency_hz,
                "power_kw": power_kw,
            })
        
        result["pumps"] = pumps
        
        return result
    
    @staticmethod
    def get_pump_frequency_variable_name(pump_id: str) -> str:
        """Get OPC UA variable name for pump frequency.
        
        Args:
            pump_id: Pump ID (e.g., "1.1", "2.3")
            
        Returns:
            OPC UA variable name (e.g., "PumpFrequency.1.1.hz")
        """
        return f"PumpFrequency.{pump_id}.hz"
    
    @staticmethod
    def extract_pump_ids_from_schedule(schedule_entries: List[Dict]) -> Dict[str, float]:
        """Extract pump IDs and target frequencies from schedule entries.
        
        Args:
            schedule_entries: List of schedule entries with pump_id and target_frequency_hz
            
        Returns:
            Dictionary mapping pump_id to target frequency
        """
        pump_frequencies = {}
        for entry in schedule_entries:
            pump_id = entry.get("pump_id") or entry.get("pumpId", "")
            # Handle both "1.1" format and "P1" format
            if pump_id.startswith("P"):
                # Convert "P1" to "1.1" format (assuming P1=1.1, P2=1.2, etc.)
                pump_num = int(pump_id[1:])
                line = (pump_num - 1) // 4 + 1
                pump = ((pump_num - 1) % 4) + 1
                pump_id = f"{line}.{pump}"
            
            frequency = float(entry.get("target_frequency_hz") or entry.get("targetFrequencyHz", 0.0))
            if frequency > 0:
                pump_frequencies[pump_id] = frequency
        
        return pump_frequencies

