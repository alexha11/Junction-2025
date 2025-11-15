from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    api_title: str = "HSY Optimization Backend"
    api_version: str = "0.1.0"
    optimizer_interval_minutes: int = 15
    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hsy"

    # Agent URLs
    weather_agent_url: str = "http://localhost:8101"
    price_agent_url: str = "http://localhost:8102"
    inflow_agent_url: str = "http://localhost:8104"
    optimizer_agent_url: str = "http://localhost:8105"
    
    # Digital Twin configuration
    digital_twin_opcua_url: str = "opc.tcp://localhost:4840/wastewater/"
    digital_twin_mcp_url: str = "http://localhost:8080"
    use_digital_twin: bool = True
    
    # Weather agent configuration
    use_weather_agent: bool = True
    weather_agent_url: str = "http://localhost:8101"  # HTTP endpoint (legacy)
    weather_agent_mcp_url: str = "http://localhost:8101"  # MCP server endpoint
    use_weather_mcp: bool = True  # Use MCP server instead of HTTP
    weather_agent_location: str = "Helsinki"  # Default location for weather forecasts
    openweather_api_key: str = ""  # Optional - required for live weather data
    
    # Future agent URLs (placeholders)
    electricity_agent_url: str = "http://localhost:8106"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
