from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    api_title: str = "HSY Optimization Backend"
    api_version: str = "0.1.0"
    optimizer_interval_minutes: int = 15
    log_level: str = "INFO"

    weather_agent_url: str = "http://localhost:8101"
    price_agent_url: str = "http://localhost:8102"
    status_agent_url: str = "http://localhost:8103"
    inflow_agent_url: str = "http://localhost:8104"
    optimizer_agent_url: str = "http://localhost:8105"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
