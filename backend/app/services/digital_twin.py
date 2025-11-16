"""Digital Twin Service - Interface to OPC UA server and MCP server."""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
from opcua import Client

from app.services.digital_twin_adapter import DigitalTwinAdapter

logger = logging.getLogger(__name__)

DEFAULT_OPCUA_SERVER_URL = "opc.tcp://localhost:4840/wastewater/"
OPCUA_SERVER_URL = os.getenv("OPCUA_SERVER_URL", DEFAULT_OPCUA_SERVER_URL)
DEFAULT_MCP_SERVER_URL = "http://localhost:8080"


async def get_digital_twin_current_state(
    opcua_url: str = DEFAULT_OPCUA_SERVER_URL,
) -> Dict[str, float]:
    """Get current system state from OPC UA server.
    
    Args:
        opcua_url: OPC UA server URL
        
    Returns:
        Dictionary mapping OPC UA variable names to values
    """
    try:
        client = Client(opcua_url)
        client.connect()

        # Read all pump station variables
        objects = client.get_objects_node()
        values: Dict[str, float] = {}

        for child in objects.get_children():
            browse_name = str(child.get_browse_name())
            if "PumpStation" in browse_name:
                pump_vars = child.get_children()

                for var in pump_vars:
                    var_name = str(var.get_browse_name()).replace("2:", "")
                    try:
                        value = var.get_value()
                        if value is not None:
                            values[var_name] = float(value)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not convert {var_name} value to float: {e}")

        client.disconnect()
        return values
    except Exception as e:
        logger.error(f"Error connecting to digital twin OPC UA server: {e}")
        return {}


async def write_pump_schedule(
    schedule_entries: List[Dict],
    opcua_url: str = DEFAULT_OPCUA_SERVER_URL,
) -> bool:
    """Write pump schedule (frequencies) to OPC UA server.
    
    Args:
        schedule_entries: List of schedule entries with pump_id and target_frequency_hz
        opcua_url: OPC UA server URL
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract pump frequencies from schedule
        pump_frequencies = DigitalTwinAdapter.extract_pump_ids_from_schedule(schedule_entries)
        
        if not pump_frequencies:
            logger.warning("No pump frequencies to write")
            return False
        
        client = Client(opcua_url)
        client.connect()
        
        objects = client.get_objects_node()
        written_count = 0
        
        for child in objects.get_children():
            browse_name = str(child.get_browse_name())
            if "PumpStation" in browse_name:
                pump_vars = child.get_children()
                
                for var in pump_vars:
                    var_name = str(var.get_browse_name()).replace("2:", "")
                    
                    # Check if this is a pump frequency variable we need to write
                    for pump_id, frequency in pump_frequencies.items():
                        expected_var = DigitalTwinAdapter.get_pump_frequency_variable_name(pump_id)
                        if var_name == expected_var:
                            try:
                                var.set_value(float(frequency))
                                written_count += 1
                                logger.info(f"Wrote {var_name} = {frequency} Hz")
                            except Exception as e:
                                logger.error(f"Failed to write {var_name}: {e}")
        
        client.disconnect()
        
        if written_count > 0:
            logger.info(f"Successfully wrote {written_count} pump frequencies to digital twin")
            return True
        else:
            logger.warning("No pump frequency variables were written")
            return False
            
    except Exception as e:
        logger.error(f"Error writing pump schedule to digital twin: {e}")
        return False


async def get_variable_history(
    variable_name: str,
    hours_back: int = 24,
    mcp_url: str = DEFAULT_MCP_SERVER_URL,
) -> List[Dict]:
    """Get historical data for a variable from MCP server.
    
    Args:
        variable_name: OPC UA variable name
        hours_back: Number of hours to look back
        mcp_url: MCP server URL
        
    Returns:
        List of historical data points with timestamp, value, quality
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Call MCP server's get_variable_history tool
            response = await client.post(
                f"{mcp_url}/tools/get_variable_history",
                json={
                    "variable_name": variable_name,
                    "hours_back": hours_back,
                }
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Error getting variable history from MCP server: {e}")
        return []


async def aggregate_variables_data(
    variable_names: List[str],
    hours_back: int = 24,
    mcp_url: str = DEFAULT_MCP_SERVER_URL,
) -> List[Dict]:
    """Get aggregated data for multiple variables from MCP server.
    
    Args:
        variable_names: List of OPC UA variable names
        hours_back: Number of hours to look back
        mcp_url: MCP server URL
        
    Returns:
        List of aggregation results (min, max, avg, etc.) for each variable
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Call MCP server's aggregate_multiple_variables_data tool
            response = await client.post(
                f"{mcp_url}/tools/aggregate_multiple_variables_data",
                json={
                    "variable_names": variable_names,
                    "hours_back": hours_back,
                }
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Error getting aggregated data from MCP server: {e}")
        return []
