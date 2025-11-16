"""Weather Agent MCP Server - Exposes weather forecast tools via MCP protocol."""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

from mcp.server.fastmcp import FastMCP

from agents.weather_agent.main import (
    WeatherAgent,
    WeatherPoint,
    WeatherProviderError,
    WeatherRequest,
)

NAME = "weather-agent-mcp-server"
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(NAME)

# Initialize weather agent
_weather_agent = WeatherAgent()
_weather_agent.configure()

port = int(os.environ.get("WEATHER_MCP_SERVER_PORT", 8101))
mcp = FastMCP(NAME, log_level="INFO", port=port, host="0.0.0.0")


@mcp.tool()
def get_precipitation_forecast(
    lookahead_hours: int = 24,
    location: str = "Helsinki",
) -> List[Dict[str, Any]]:
    """Get precipitation and temperature forecast for a location.
    
    Args:
        lookahead_hours: Number of hours to forecast (1-72)
        location: Location for forecast (city name or lat,lon)
        
    Returns:
        List of weather points with timestamp, precipitation_mm, temperature_c
    """
    try:
        request = WeatherRequest(
            lookahead_hours=lookahead_hours,
            location=location,
        )
        weather_points = _weather_agent.get_precipitation_forecast(request)
        
        # Convert WeatherPoint objects to dictionaries for JSON serialization
        return [
            {
                "timestamp": point.timestamp.isoformat(),
                "precipitation_mm": point.precipitation_mm,
                "temperature_c": point.temperature_c,
            }
            for point in weather_points
        ]
    except WeatherProviderError as e:
        logger.error(f"Weather provider error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting weather forecast: {e}")
        return []


@mcp.tool()
def get_current_weather(location: str = "Helsinki") -> Dict[str, Any]:
    """Get current weather conditions for a location.
    
    Args:
        location: Location for weather (city name or lat,lon)
        
    Returns:
        Current weather point with timestamp, precipitation_mm, temperature_c
    """
    try:
        current_point = _weather_agent._fetch_openweather_current(location=location)
        return {
            "timestamp": current_point.timestamp.isoformat(),
            "precipitation_mm": current_point.precipitation_mm,
            "temperature_c": current_point.temperature_c,
            "location": location,
        }
    except WeatherProviderError as e:
        logger.error(f"Weather provider error: {e}")
        return {
            "error": str(e),
            "location": location,
        }
    except Exception as e:
        logger.error(f"Error getting current weather: {e}")
        return {
            "error": str(e),
            "location": location,
        }


@mcp.tool()
def check_weather_agent_health() -> Dict[str, Any]:
    """Check if weather agent is healthy and can fetch weather data.
    
    Returns:
        Health status with agent status and API key availability
    """
    try:
        # Try to fetch current weather to verify connectivity
        test_location = "Helsinki"
        current_point = _weather_agent._fetch_openweather_current(location=test_location)
        
        return {
            "status": "healthy",
            "api_key_configured": _weather_agent.api_key is not None,
            "test_location": test_location,
            "last_check": datetime.utcnow().isoformat(),
            "sample_temperature_c": current_point.temperature_c,
        }
    except WeatherProviderError as e:
        return {
            "status": "degraded",
            "api_key_configured": _weather_agent.api_key is not None,
            "error": str(e),
            "last_check": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "api_key_configured": _weather_agent.api_key is not None,
            "error": str(e),
            "last_check": datetime.utcnow().isoformat(),
        }


if __name__ == "__main__":
    logger.info(f"Starting Weather Agent MCP Server on port {port}...")
    logger.info("Note: FastMCP uses SSE transport. For HTTP REST endpoints, use server.py instead.")
    try:
        # FastMCP uses SSE (Server-Sent Events) transport for MCP protocol
        # For HTTP REST endpoints, use agents.weather_agent.server instead
        mcp.run(transport="sse")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")

