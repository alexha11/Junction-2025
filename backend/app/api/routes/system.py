from fastapi import APIRouter, Depends

from app.models import ForecastSeries, ScheduleRecommendation, SystemState
from app.services.agents_client import AgentsCoordinator

router = APIRouter(prefix="/system", tags=["system"])


def get_agents() -> AgentsCoordinator:
    return AgentsCoordinator()


@router.get("/state", response_model=SystemState)
async def read_state(agents: AgentsCoordinator = Depends(get_agents)) -> SystemState:
    return await agents.get_system_state()


@router.get("/forecasts", response_model=list[ForecastSeries])
async def read_forecasts(agents: AgentsCoordinator = Depends(get_agents)) -> list[ForecastSeries]:
    return await agents.get_forecasts()


@router.get("/schedule", response_model=ScheduleRecommendation)
async def read_schedule(agents: AgentsCoordinator = Depends(get_agents)) -> ScheduleRecommendation:
    return await agents.get_schedule_recommendation()
