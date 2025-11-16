from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from agents.optimizer_agent.main import (
    OptimizationAgent,
    OptimizationRequest,
    OptimizationResponse,
)

app = FastAPI(title="Optimizer Agent HTTP Bridge", version="0.1.0")

# Initialize agent with environment variables
_agent = OptimizationAgent(
    backend_url=os.getenv("BACKEND_URL", "http://localhost:8000"),
    weather_agent_url=os.getenv("WEATHER_AGENT_URL", "http://localhost:8101"),
    price_agent_url=os.getenv("PRICE_AGENT_URL", "http://localhost:8102"),
    digital_twin_mcp_url=os.getenv("DIGITAL_TWIN_MCP_URL"),
    featherless_api_base=os.getenv("FEATHERLESS_API_BASE"),
    featherless_api_key=os.getenv("FEATHERLESS_API_KEY"),
)
_agent.configure()


@app.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/optimize", response_model=OptimizationResponse)
async def optimize(request: OptimizationRequest) -> OptimizationResponse:
    try:
        # Call agent's generate_schedule tool directly
        response = _agent.generate_schedule(request)
        return response
    except Exception as exc:
        import traceback
        error_detail = f"{str(exc)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=502, detail=error_detail) from exc


def run() -> None:
    """Convenience entrypoint for `python -m agents.optimizer_agent.server`."""
    import uvicorn
    
    port = int(os.getenv("AGENT_PORT", "8105"))
    
    uvicorn.run(
        "agents.optimizer_agent.server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()

