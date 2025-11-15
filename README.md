# HSY Blominmäki AI Agent Pumping Optimization System

This repository contains the end-to-end scaffolding for the multi-agent optimization platform described in `docs/PRD.md`. It is organized as a mono-repo with three main workspaces:

- `backend/` – FastAPI service that exposes REST + WebSocket APIs, schedules optimization runs, and orchestrates agents.
- `agents/` – Collection of Model Context Protocol (MCP) microservices (weather, electricity price, system status, inflow forecast, and optimization coordinator) powered by the OpenAI Agents SDK pattern.
- `frontend/` – React dashboard for operators showing plant state, forecasts, AI recommendations, alerts, and manual override logging.

## Quick Start

### Note: We are using Python version 3.12

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

> Tip: set `LOG_LEVEL=DEBUG` before launching uvicorn to surface the new structured logs from routers, the agents coordinator, and the optimization scheduler.

### 2. Agents (local stubs)

Each agent currently ships with deterministic stub logic so the rest of the stack is runnable without external integrations. Replace `serve()` with the official MCP server hooks once the OpenAI Agents SDK MCP utilities are available.

```bash
cd agents
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..  # run agents as modules so the package is discoverable
# Real weather calls require an API key from https://home.openweathermap.org/api_keys
export OPENWEATHER_API_KEY="<your-openweather-key>"
python -m agents.weather_agent.main
python -m agents.price_agent.main
python -m agents.status_agent.main
python -m agents.inflow_agent.main
python -m agents.optimizer_agent.main
# ... repeat for other agents as needed
```

### 3. Frontend

```bash
cd frontend
npm install
# Point the UI to a running weather-agent HTTP endpoint (FastAPI proxy or direct OpenWeather URL)
export VITE_WEATHER_AGENT_URL="http://localhost:8000/weather/forecast"
npm run dev
```

The Vite dev server proxies API calls to `http://localhost:8000` so both the backend and frontend must be running.

## Running with Docker

Build the containers and start the entire stack (FastAPI backend, Vite build served via Nginx, Postgres, Redis) with Docker Compose:

```bash
docker compose build
docker compose up -d
```

Services:

- Backend API: http://localhost:8000
- Frontend dashboard: http://localhost:5173
- Postgres: localhost:5432 (user/password: `postgres` / `postgres`, db: `hsy`)
- Redis: localhost:6379

Stop everything with `docker compose down` (append `-v` to drop volumes). To see logs for a specific service run `docker compose logs -f backend`.

## Architectural Highlights

- **MCP-first Agents:** Each agent implements a single MCP tool (e.g., `get_precipitation_forecast`). A thin base class in `agents/common` makes it easy to attach to the OpenAI Agents SDK later.
- **Coordinator Scheduler:** The FastAPI backend hosts an `OptimizationScheduler` that refreshes recommendations every 15 minutes (configurable). This is where MCP agent calls are orchestrated.
- **Simulator Adapter:** `backend/app/services/simulator_adapter.py` acts as an integration point for the HSY simulator, ensuring telemetry flows back into the dashboard.
- **Operator Dashboard:** The React UI consumes `/system/state`, `/system/forecasts`, `/system/schedule`, and `/alerts` endpoints, updating via React Query polling. Components mirror FR1 sections (system overview, forecast, AI recommendation, alerts, manual override form).

## Debugging & Testing

- Use the `backend/DEBUGGING.md` cheat sheet (mirrors `docs/CURL.md`) for ready-made `curl` smoke tests plus logging tips. Running commands like `curl -sS "$BASE_URL/system/forecasts" | jq` while tailing the backend logs makes it easy to verify new deployments.
- Control verbosity with `LOG_LEVEL` (defaults to `INFO`). Example: `LOG_LEVEL=DEBUG uvicorn app.main:app --reload`.
- For end-to-end guidance across backend, agents, and frontend test suites, see `docs/TESTING.md`.
- Backend API routes now have deterministic coverage via `backend/tests/conftest.py` (stubbed `AgentsCoordinator`) and `backend/tests/test_api_routes.py`. Run them quickly while iterating with:

```bash
cd backend
pytest tests/test_api_routes.py -q
```

## Next Steps

1. Swap stub agent implementations with real FMI, Nord Pool, simulator, and ML integrations.
2. Extend the backend persistence layer (Postgres + Redis) for schedule history, overrides, and alerting.
3. Replace the optimizer stub with a Pyomo/OR-Tools solver that enforces all constraints outlined in the PRD.
4. Add WebSocket streaming for real-time updates and tighten automated test coverage (unit + integration + E2E/playwright).
