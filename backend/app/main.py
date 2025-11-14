from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import alerts, system
from app.config import get_settings
from app.services.agents_client import AgentsCoordinator
from app.services.scheduler import OptimizationScheduler

_agents = AgentsCoordinator()
_scheduler: OptimizationScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _scheduler
    settings = get_settings()
    _scheduler = OptimizationScheduler(
        agents=_agents, interval_minutes=settings.optimizer_interval_minutes
    )
    _scheduler.start()
    try:
        yield
    finally:
        if _scheduler:
            _scheduler.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)
    application.include_router(system.router)
    application.include_router(alerts.router)
    return application


app = create_app()
