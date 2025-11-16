from __future__ import annotations

from typing import List

from fastapi import FastAPI, HTTPException

from agents.price_agent.main import (
    ElectricityPriceAgent,
    PricePoint,
    PriceRequest,
)

app = FastAPI(title="Price Agent HTTP Bridge", version="0.1.0")
_agent = ElectricityPriceAgent()
_agent.configure()


@app.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/price/forecast", response_model=List[PricePoint])
async def price_forecast(request: PriceRequest) -> List[PricePoint]:
    try:
        return _agent.get_forecast(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def run() -> None:
    """Convenience entrypoint for `python -m agents.price_agent.server`."""
    import os
    import uvicorn
    
    port = int(os.getenv("AGENT_PORT", "8102"))
    
    uvicorn.run(
        "agents.price_agent.server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()

