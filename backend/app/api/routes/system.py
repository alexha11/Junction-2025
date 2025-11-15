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
    agents: AgentsCoordinator = Depends(get_agents),
) -> ScheduleRecommendation:
    logger.info("Received request for schedule recommendation")
    return await agents.get_schedule_recommendation()


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
