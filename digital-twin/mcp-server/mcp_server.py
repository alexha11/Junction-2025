import logging
import os
import sys
from typing import Dict, List, Union
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
from opcua import Client

DEFAULT_OPCUA_SERVER_URL = "opc.tcp://135.125.143.85:4840/wastewater/"
OPCUA_SERVER_URL = os.environ.get("OPCUA_SERVER_URL", DEFAULT_OPCUA_SERVER_URL)

NAME = "demo-digital-twin-mcp-server"
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(NAME)

port = int(os.environ.get("MCP_SERVER_PORT", 8080))
mcp = FastMCP(NAME, log_level="INFO", port=port, host="0.0.0.0")


@mcp.tool()
def browse_opcua_variables() -> list[str]:
    try:
        client = Client(OPCUA_SERVER_URL)
        client.connect()

        # Browse pump station variables
        objects = client.get_objects_node()
        variables: list[str] = []

        for child in objects.get_children():
            browse_name = str(child.get_browse_name())
            if "PumpStation" in browse_name:
                pump_vars = child.get_children()
                for var in pump_vars:
                    var_name = str(var.get_browse_name()).replace("2:", "")
                    variables.append(var_name)

        client.disconnect()
        return variables
    except Exception:
        return []


@mcp.tool()
def read_opcua_variable(
    variable_name: str,
) -> str:
    try:
        client = Client(OPCUA_SERVER_URL)
        client.connect()

        objects = client.get_objects_node()

        for child in objects.get_children():
            if "PumpStation" in str(child.get_browse_name()):
                for var in child.get_children():
                    var_browse_name = str(var.get_browse_name()).replace("2:", "")
                    if variable_name in var_browse_name:
                        value = var.get_value()
                        client.disconnect()
                        return str(value)

        client.disconnect()
        return ""
    except Exception:
        return ""


@mcp.tool()
def write_opcua_variable(
    variable_name: str,
    value: float,
) -> bool:
    try:
        client = Client(OPCUA_SERVER_URL)
        client.connect()

        objects = client.get_objects_node()

        for child in objects.get_children():
            if "PumpStation" in str(child.get_browse_name()):
                for var in child.get_children():
                    var_browse_name = str(var.get_browse_name()).replace("2:", "")
                    if variable_name in var_browse_name:
                        var.set_value(value)
                        client.disconnect()
                        return True

        client.disconnect()
        return False
    except Exception:
        return False


@mcp.tool()
def get_variable_history(
    variable_name: str,
    hours_back: int = 24,
) -> List[Dict[str, Union[str, float]]]:
    try:
        client = Client(OPCUA_SERVER_URL)
        client.connect()

        objects = client.get_objects_node()
        variable_node = None

        for child in objects.get_children():
            if "PumpStation" in str(child.get_browse_name()):
                for var in child.get_children():
                    var_browse_name = str(var.get_browse_name()).replace("2:", "")
                    if variable_name in var_browse_name:
                        variable_node = var
                        break
                if variable_node:
                    break

        if not variable_node:
            client.disconnect()
            return []

        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours_back)

        history = variable_node.read_raw_history(start_time, end_time)

        history_data = []
        for data_value in history:
            history_data.append(
                {
                    "timestamp": str(data_value.SourceTimestamp),
                    "value": (
                        float(data_value.Value.Value)
                        if data_value.Value.Value is not None
                        else None
                    ),
                    "quality": str(data_value.StatusCode),
                }
            )

        client.disconnect()
        return history_data if history_data else []
    except Exception:
        return []


@mcp.tool()
def aggregate_variable_data(
    variable_name: str,
    hours_back: int = 24,
) -> Dict[str, Union[str, float, int]]:
    try:
        history_data = get_variable_history(variable_name, hours_back)

        if not history_data:
            return {
                "variable_name": variable_name,
                "error": "No historical data",
            }

        values = []
        for point in history_data:
            if "value" in point and point["value"] is not None:
                try:
                    values.append(float(point["value"]))
                except (ValueError, TypeError):
                    continue

        if not values:
            return {
                "variable_name": variable_name,
                "error": "No valid numeric values found in historical data",
            }

        return {
            "variable_name": variable_name,
            "period_hours": hours_back,
            "data_points": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "first_timestamp": history_data[0].get("timestamp", "Unknown"),
            "last_timestamp": history_data[-1].get("timestamp", "Unknown"),
        }
    except Exception:
        return {
            "variable_name": variable_name,
            "error": "Error calculating aggregations",
        }


@mcp.tool()
def aggregate_multiple_variables_data(
    variable_names: List[str],
    hours_back: int = 24,
) -> List[Dict[str, Union[str, float, int]]]:
    results = []

    for var_name in variable_names:
        try:
            aggregation = aggregate_variable_data(var_name, hours_back)
            results.append(aggregation)
        except Exception:
            results.append(
                {
                    "variable_name": var_name,
                    "error": f"Failed to process variable",
                }
            )
    return results


if __name__ == "__main__":
    logger.info(f"Starting MCP Server on port {port}...")
    try:
        mcp.run(transport="sse")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")
