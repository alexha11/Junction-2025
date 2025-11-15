# Backend Reference

A map of every file under `backend/`, covering configuration, FastAPI modules, background services, and tests.

## Project Metadata

| File | Purpose |
| --- | --- |
| `backend/pyproject.toml` | Declares the FastAPI app as `hsy-optimizer-backend`, pins Python 3.11+, lists runtime deps (FastAPI, APScheduler, Redis, SQLAlchemy, asyncpg, etc.), and configures pytest defaults (`tests/`, `app/` on `PYTHONPATH`). |
| `backend/requirements.txt` | Plain `pip` equivalent of the dependencies in `pyproject.toml`. Use it when creating a bare virtualenv. |

## Application Package (`backend/app/`)

| File | Description |
| --- | --- |
| `app/__init__.py` | Marks the folder as a package. |
| `app/config.py` | `pydantic-settings` powered `Settings` class. Stores API metadata, scheduler cadence, Redis/Postgres URLs, and the base URLs for each MCP agent microservice. `get_settings()` memoizes the config so FastAPI and background jobs share the same object. |
| `app/main.py` | FastAPI entry point. Creates a module-level `AgentsCoordinator`, wires an `OptimizationScheduler` into the lifespan hook, and includes the `/system` + `/alerts` routers. Exposes `app = create_app()` for ASGI servers and `TestClient`. |
| `app/models.py` | Central Pydantic schemas shared across routers/services: pump/system telemetry, forecast series, schedule recommendations, override requests, and alert envelopes. Enumerations (`PumpState`, `AlertLevel`) keep payloads type-safe. |
| `app/api/routes/__init__.py` | Package marker for routers. |
| `app/api/routes/system.py` | Defines the `/system` group: `/state`, `/forecasts`, `/schedule`. Uses FastAPI dependency injection to fetch an `AgentsCoordinator` and simply forwards async calls to its stub methods. Response models reference `SystemState`, `ForecastSeries`, `ScheduleRecommendation`. |
| `app/api/routes/alerts.py` | Simple `/alerts/` endpoint returning a hard-coded `Alert` to drive frontend banner development. Replace this with Redis/DB reads later. |
| `app/services/agents_client.py` | Stub facade that emulates calls to the MCP agents. Generates deterministic telemetry, forecast series, and pump schedules so the rest of the stack can work without live agents. This is the abstraction you will swap for real `httpx` requests once the agents expose their API. |
| `app/services/scheduler.py` | Wraps APScheduler to run `AgentsCoordinator.get_schedule_recommendation()` every `interval_minutes`. Currently prints the JSON payload; TODO items include persistence and WebSocket broadcasting. |
| `app/services/simulator_adapter.py` | Async iterator placeholder that reuses `AgentsCoordinator` data. Later, connect it to the real HSY simulator stream and emit `SystemState` updates to the backend. |
| `app/data/uploads/` | Empty drop zone reserved for CSV/model artifacts (e.g., simulator exports or inflow training files). |

## Tests (`backend/tests/`)

| File | Description |
| --- | --- |
| `tests/test_health.py` | Minimal smoke test proving `/system/state` responds with HTTP 200 and positive tunnel level. Extend this suite following the recommendations in `docs/testing.md` (models, schedulers, agent stubs, etc.). |

## Operational Flow

1. **FastAPI startup**: `lifespan()` instantiates `OptimizationScheduler`, starting the APScheduler job alongside the API server. Shutdown stops the scheduler gracefully.
2. **Request handling**: `system` and `alerts` routes simply proxy to `AgentsCoordinator`, which currently fabricates data but will later call MCP agents (see `docs/agent.md`).
3. **Background optimization**: The scheduler executes `_optimize()`, awaiting the latest schedule and (for now) printing it. Future work: persist schedules, push WebSocket/SSE updates, and trigger alert generation.

## Next Steps

- Replace `AgentsCoordinator` implementations with real HTTP/MCP calls using URLs from `Settings`.
- Wire Redis/Postgres clients (configured in `config.py`) for caching, overrides, and audit logs.
- Expand `tests/` to cover routers, services, and scheduler timing guarantees (`pytest-asyncio`).
- Expose health endpoints & OpenAPI tags via FastAPI to align with the frontend's telemetry expectations.

Keep this reference handy whenever you update the backend—every relevant file, schema, and service is cataloged above.
