import logging

from fastapi import APIRouter, Depends

from app.models import (
    ForecastSeries,
    ScheduleRecommendation,
    SystemState,
    WeatherForecastRequest,
    WeatherPoint,
)
from app.services.agents_client import AgentsCoordinator

router = APIRouter(prefix="/system", tags=["system"])
weather_router = APIRouter(prefix="/weather", tags=["weather"])
logger = logging.getLogger(__name__)


def get_agents() -> AgentsCoordinator:
    return AgentsCoordinator()


@router.get("/state", response_model=SystemState)
async def read_state(agents: AgentsCoordinator = Depends(get_agents)) -> SystemState:
    logger.info("Received request for system state")
    return await agents.get_system_state()


@router.get("/digital-twin/state", response_model=dict)
async def read_digital_twin_state(
    agents: AgentsCoordinator = Depends(get_agents),
) -> dict:
    logger.info("Received request for digital twin current state")
    return await agents.get_digital_twin_current_state()


@router.get("/forecasts", response_model=list[ForecastSeries])
async def read_forecasts(
    agents: AgentsCoordinator = Depends(get_agents),
) -> list[ForecastSeries]:
    logger.info("Received request for forecast bundle")
    return await agents.get_forecasts()


@router.get("/schedule", response_model=ScheduleRecommendation)
async def read_schedule(
    horizon_minutes: int = 120,
    agents: AgentsCoordinator = Depends(get_agents),
) -> ScheduleRecommendation:
    """Get optimization schedule recommendation.
    
    Args:
        horizon_minutes: Optimization horizon in minutes (default: 120)
    """
    logger.info(
        "Received request for schedule recommendation horizon_minutes=%s", horizon_minutes
    )
    return await agents.get_schedule_recommendation(horizon_minutes=horizon_minutes)


@router.post("/schedule/optimize", response_model=dict)
async def trigger_optimization(
    horizon_minutes: int = 120,
    agents: AgentsCoordinator = Depends(get_agents),
) -> dict:
    """Trigger optimization and get full result with metrics.
    
    Args:
        horizon_minutes: Optimization horizon in minutes (default: 120)
        
    Returns:
        Dictionary with schedule, metrics (cost, energy, mode), and optimization details
    """
    logger.info("Received request to trigger optimization horizon_minutes=%s", horizon_minutes)
    return await agents.trigger_optimization(horizon_minutes=horizon_minutes)


@router.get("/schedule/metrics", response_model=dict)
async def get_optimization_metrics(
    agents: AgentsCoordinator = Depends(get_agents),
) -> dict:
    """Get latest optimization metrics (cost, energy, mode).
    
    Returns:
        Dictionary with optimization metrics or empty dict if not available
    """
    metrics = agents.get_latest_optimization_metrics()
    if metrics:
        return metrics
    return {
        "message": "No optimization metrics available yet. Trigger optimization first.",
    }


@router.post("/schedule", response_model=dict)
async def write_schedule(
    schedule: ScheduleRecommendation,
    agents: AgentsCoordinator = Depends(get_agents),
) -> dict:
    """Write optimization schedule to digital twin."""
    logger.info("Received request to write schedule to digital twin")
    success = await agents.write_optimization_schedule(schedule)
    return {"success": success, "message": "Schedule written to digital twin" if success else "Failed to write schedule"}


@router.get("/history")
async def read_history(
    variable_names: str,
    hours_back: int = 24,
    agents: AgentsCoordinator = Depends(get_agents),
) -> list:
    """Get historical data for variables from digital twin.
    
    Args:
        variable_names: Comma-separated list of OPC UA variable names
        hours_back: Number of hours to look back (default: 24)
    """
    logger.info(
        "Received request for digital twin history variables=%s hours_back=%s",
        variable_names,
        hours_back,
    )
    var_list = [v.strip() for v in variable_names.split(",")]
    return await agents.get_digital_twin_history(var_list, hours_back=hours_back)


@router.get("/digital-twin/health")
async def digital_twin_health(
    agents: AgentsCoordinator = Depends(get_agents),
) -> dict:
    """Health check for digital twin connectivity."""
    from app.services.digital_twin import get_digital_twin_current_state
    from app.config import get_settings
    
    settings = get_settings()
    try:
        values = await get_digital_twin_current_state(
            opcua_url=settings.digital_twin_opcua_url
        )
        if values:
            return {
                "status": "healthy",
                "connected": True,
                "variables_count": len(values),
            }
        else:
            return {
                "status": "degraded",
                "connected": False,
                "message": "Digital twin returned empty values",
            }
    except Exception as e:
        logger.error(f"Digital twin health check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "error": str(e),
        }


@router.get("/weather/health")
async def weather_agent_health(
    agents: AgentsCoordinator = Depends(get_agents),
) -> dict:
    """Health check for weather agent connectivity (MCP or HTTP)."""
    from app.config import get_settings
    import httpx
    
    settings = get_settings()
    if not settings.use_weather_agent:
        return {
            "status": "disabled",
            "connected": False,
            "message": "Weather agent is disabled in configuration",
        }
    
    # Try MCP server first if enabled
    if settings.use_weather_mcp:
        try:
            mcp_url = f"{settings.weather_agent_mcp_url.rstrip('/')}/tools/check_weather_agent_health"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(mcp_url, json={})
                response.raise_for_status()
                data = response.json()
                return {
                    "status": data.get("status", "unknown"),
                    "connected": data.get("status") == "healthy",
                    "api_key_configured": data.get("api_key_configured", False),
                    "mode": "mcp",
                    "agent_status": data,
                }
        except httpx.RequestError as e:
            logger.warning(f"Weather MCP server health check failed: {e}, trying HTTP")
        except Exception as e:
            logger.warning(f"Weather MCP server health check error: {e}, trying HTTP")
    
    # Fallback to HTTP endpoint
    try:
        url = f"{settings.weather_agent_url.rstrip('/')}/health"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return {
                "status": "healthy",
                "connected": True,
                "agent_status": data.get("status", "unknown"),
                "mode": "http",
            }
    except httpx.RequestError as e:
        logger.warning(f"Weather agent HTTP health check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "error": str(e),
            "mode": "http",
        }
    except Exception as e:
        logger.error(f"Weather agent health check error: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "error": str(e),
        }


@weather_router.post("/forecast", response_model=list[WeatherPoint])
async def read_weather_forecast(
    request: WeatherForecastRequest, agents: AgentsCoordinator = Depends(get_agents)
) -> list[WeatherPoint]:
    logger.info(
        "Received weather forecast request lookahead_hours=%s location=%s",
        request.lookahead_hours,
        request.location,
    )
    return await agents.get_weather_forecast(
        lookahead_hours=request.lookahead_hours, location=request.location
    )
