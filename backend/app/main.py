from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.routes import alerts, system
from app.config import get_settings
from app.logging_config import configure_logging
from app.services.agents_client import AgentsCoordinator
from app.services.scheduler import OptimizationScheduler
from fastapi.middleware.cors import CORSMiddleware

_agents = AgentsCoordinator()
_scheduler: OptimizationScheduler | None = None
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _scheduler
    settings = get_settings()
    logger.info(
        "Starting optimization scheduler interval_minutes=%s",
        settings.optimizer_interval_minutes,
    )
    _scheduler = OptimizationScheduler(
        agents=_agents, interval_minutes=settings.optimizer_interval_minutes
    )
    _scheduler.start()
    try:
        yield
    finally:
        if _scheduler:
            logger.info("Shutting down optimization scheduler")
            _scheduler.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Creating FastAPI application title=%s version=%s",
        settings.api_title,
        settings.api_version,
    )
    application = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)

    application.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
    application.include_router(system.router)
    application.include_router(system.weather_router)
    application.include_router(alerts.router)
    return application


app = create_app()
