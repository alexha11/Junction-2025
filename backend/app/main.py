from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alerts, system, demo
from app.config import get_settings
from app.logging_config import configure_logging
from app.services.agents_client import AgentsCoordinator
from app.services.scheduler import OptimizationScheduler

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
    
    # Configure CORS for frontend access
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative frontend port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
            "*",  # Allow all origins for development (can be restricted in production)
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routers
    application.include_router(system.router)
    application.include_router(system.weather_router)
    application.include_router(alerts.router)
    
    # Include demo simulator REST API routes (if available)
    try:
        application.include_router(demo.router)
        logger.info("Demo simulator REST API endpoints registered at /system/demo/simulate/*")
    except Exception as e:
        logger.warning(f"Demo simulator endpoints not available: {e}")
    
    return application


app = create_app()
