from __future__ import annotations

from typing import List

from fastapi import FastAPI, HTTPException

from agents.weather_agent.main import (
    WeatherAgent,
    WeatherPoint,
    WeatherProviderError,
    WeatherRequest,
)

app = FastAPI(title="Weather Agent HTTP Bridge", version="0.1.0")
_agent = WeatherAgent()
_agent.configure()


@app.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/weather/forecast", response_model=List[WeatherPoint])
async def weather_forecast(request: WeatherRequest) -> List[WeatherPoint]:
    try:
        return _agent.get_precipitation_forecast(request)
    except WeatherProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def run() -> None:
    """Convenience entrypoint for `python -m agents.weather_agent.server`."""
    import uvicorn

    uvicorn.run(
        "agents.weather_agent.server:app",
        host="0.0.0.0",
        port=8101,
        reload=False,
    )


if __name__ == "__main__":
    run()
