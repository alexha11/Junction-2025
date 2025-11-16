# HSY Blominmäki AI Agent Pumping Optimization System

End-to-end platform for optimizing HSY Blominmäki wastewater pumping using multi-agent forecasts, a FastAPI orchestration backend, a React operator dashboard, and supporting digital-twin tooling.

## Table of Contents

- [HSY Blominmäki AI Agent Pumping Optimization System](#hsy-blominmäki-ai-agent-pumping-optimization-system)
  - [Table of Contents](#table-of-contents)
  - [Mission Overview](#mission-overview)
  - [System Architecture](#system-architecture)
  - [Repository Layout](#repository-layout)
  - [Technology Stack](#technology-stack)
  - [Environment Setup](#environment-setup)
    - [Backend](#backend)
    - [MCP Agents](#mcp-agents)
    - [Frontend](#frontend)
    - [Digital-Twin Tooling](#digital-twin-tooling)
  - [Docker Orchestration](#docker-orchestration)
  - [Configuration \& Secrets](#configuration--secrets)
    - [Sample `.env`](#sample-env)
  - [Data, Models \& Digital Twin](#data-models--digital-twin)
  - [Testing \& QA](#testing--qa)
  - [Troubleshooting](#troubleshooting)
  - [Documentation Map](#documentation-map)
  - [Roadmap](#roadmap)

## Mission Overview

-   Coordinate deterministic MCP agents (weather, electricity price, system status, inflow, optimizer) to refresh pumping recommendations every 15 minutes.
-   Surface tunnel telemetry, forecasts, AI schedules, and manual override flows through a Tailwind-styled React dashboard.
-   Provide a digital twin (OPC UA + MCP bridge) plus price forecasting research assets to accelerate integration with HSY simulators and Nord Pool/FMI sources.

## System Architecture

-   **Backend** (`backend/`): FastAPI service hosting `/system/*`, `/alerts`, background `OptimizationScheduler`, Redis/Postgres clients, and agent facades.
-   **Agents** (`agents/`): MCP-style microservices sharing a `BaseMCPAgent` harness. Each registers a single tool (`generate_schedule`, `get_precipitation_forecast`, etc.) and can be run directly or via an HTTP shim.
-   **Frontend** (`frontend/`): Vite + React dashboard with React Query data hooks, Zustand-ready stores, Tailwind theming, and multi-panel layouts for telemetry, forecasts, and recommendations.
-   **Digital Twin** (`digital-twin/`): OPC UA simulator seeded from historical CSV/Parquet plus an MCP server that exposes browse/read/write/history tooling for pump variables.
-   **Research Assets** (`spot-price-forecast/`): Linear regression notebooks, scripts, and data describing Nord Pool spot price modeling.

## Repository Layout

| Path                   | Purpose                                                                                                                                                        |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/app/`         | FastAPI app (`main.py`), Pydantic schemas (`models.py`), config (`config.py`), logging, services (`agents_client.py`, `scheduler.py`, `simulator_adapter.py`). |
| `backend/tests/`       | Pytest suites for health checks and API routes with stubbed `AgentsCoordinator`.                                                                               |
| `agents/`              | MCP agent implementations (weather, price, inflow, status, optimizer) plus shared base classes.                                                                |
| `frontend/src/`        | React entry points, components (`SystemOverviewCard`, `RecommendationPanel`, etc.), hooks, styles.                                                             |
| `digital-twin/`        | `opcua-server/`, `mcp-server/`, `test-clients/`, and helper scripts for replaying HSY telemetry.                                                               |
| `docs/`                | Deep-dive references: `PRD`, `AGENT`, `BACKEND`, `FRONTEND`, `TESTING`, `CURL`.                                                                                |
| `sample/`              | Deterministic JSON fallbacks for market price, weather, and Valmet artifacts.                                                                                  |
| `spot-price-forecast/` | Independent project exploring day-ahead price models with data, notebooks, and scripts.                                                                        |

## Technology Stack

-   Python 3.12 recommended (backend + agents) with their respective requirements in `requirements.txt`
-   Node.js 20+ for Vite/React frontend (React 18, React Query, Tailwind, Recharts, Zustand)
-   Docker + Docker Compose for local orchestration

## Environment Setup

> All commands assume repo root. Create isolated virtualenvs per workspace to avoid dependency clashes.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Or with docker . . .

```bash
cd backend
docker build -t hsy-backend .
docker run -p 8000:8000 --env-file .env hsy-backend
```

-   Optional: `LOG_LEVEL=DEBUG uvicorn app.main:app --reload` exposes structured logs from routers, scheduler, and coordinator.
-   Run API smoke tests: `pytest tests/test_api_routes.py -q`.

### MCP Agents

```bash
cd agents
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Weather agent (requires OpenWeather key for live data)
export OPENWEATHER_API_KEY="<your-openweather-key>"
python -m agents.weather_agent.main
python -m agents.weather_agent.server  # exposes POST /weather/forecast on :8101

python -m agents.price_agent.main
python -m agents.inflow_agent.main
python -m agents.optimizer_agent.main
```

-   Replace stub logic with real integrations by editing the respective `main.py` files.

### Frontend

```bash
cd frontend
npm install
export VITE_WEATHER_AGENT_URL="http://localhost:8000/weather/forecast"
npm run dev
```

Or with docker . . .

```bash
cd frontend
docker build -t hsy-frontend .
docker run -p 5173:5173 --env VITE_WEATHER_AGENT_URL="http://localhost:8000/weather/forecast" hsy-frontend
```

-   Vite dev proxy forwards `/api/*` to `http://localhost:8000`. Keep backend running to avoid 404s.
-   Planned tests: `npm run test` (Vitest) and `npx playwright test` once configured.

### Digital-Twin Tooling

-   **OPC UA server**

    ```bash
    cd digital-twin/opcua-server
    pip install -r requirements.txt
    python opcua_server.py  # streams historical HSY data into OPC UA namespace
    ```

    Or with Docker Compose . . .

    ```bash
    cd digital-twin
    docker compose up --build # Starts both the OPC UA server & the MCP bridge
    ```

-   **MCP bridge**

    ```bash
    cd digital-twin/mcp-server
    pip install -r requirements.txt
    export MCP_SERVER_PORT=8080
    python mcp_server.py  # exposes browse/read/write/history tools over SSE
    ```

    Or with Docker Compose . . .

    ```bash
    cd digital-twin
    docker compose up --build # Starts both the OPC UA server & the MCP bridge
    ```

-   **Test clients**: `digital-twin/test-clients/opcua_client.py` and `mcp_client.py` demonstrate bidirectional calls. Can be run using:
    ```bash
    cd digital-twin/test-clients
    ./run.sh # NOTE: Need to have Python3.13 on PATH
    ```

## Docker Orchestration

`docker-compose.yml` brings up backend (Uvicorn), frontend (Nginx + Vite build) & the digital twin services

```bash
docker compose build
docker compose up -d
```

-   Backend API: `http://localhost:8000`
-   Frontend dashboard: `http://localhost:5173`
-   Digital twin OPC UA Server: `opc.tcp://localhost:4840/wastewater/`
-   Digital twin MCP-bridge: `http://localhost:8080`

Stop services with `docker compose down` (add `-v` to purge volumes). Tail logs via `docker compose logs -f backend`.

## Configuration & Secrets

| Variable                     | Default                                                     | Description                                                                                |
| ---------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `LOG_LEVEL`                  | `INFO`                                                      | Controls backend logging verbosity.                                                        |
| `OPTIMIZER_INTERVAL_MINUTES` | `15`                                                        | Scheduler cadence for refreshing pump recommendations.                                     |
| `REDIS_URL`                  | `redis://localhost:6379/0`                                  | Backend cache/broker endpoint.                                                             |
| `DATABASE_URL`               | `postgresql+asyncpg://postgres:postgres@localhost:5432/hsy` | Async SQLAlchemy connection string.                                                        |
| `WEATHER_AGENT_URL`          | `http://localhost:8101`                                     | Base URL used by `AgentsCoordinator`. Repeat for `PRICE`, `STATUS`, `INFLOW`, `OPTIMIZER`. |
| `OPENWEATHER_API_KEY`        | _required for live data_                                    | Injected into `WeatherAgent`. Set before invoking the agent or weather HTTP shim.          |
| `VITE_WEATHER_AGENT_URL`     | `http://localhost:8000/weather/forecast`                    | Frontend env var consumed by React Query hook.                                             |
| `MCP_SERVER_PORT`            | `8080`                                                      | Digital-twin MCP server port (also doubles as simulation speedup for OPC UA server).       |

Backends read from `backend/.env` (handled by `pydantic-settings`). Agents can either use `.env` or exported variables. Frontend expects a `.env.local` with `VITE_*` keys.

### Sample `.env`

```
# backend/.env
LOG_LEVEL=DEBUG
OPTIMIZER_INTERVAL_MINUTES=15
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hsy
WEATHER_AGENT_URL=http://localhost:8101
PRICE_AGENT_URL=http://localhost:8102
INFLOW_AGENT_URL=http://localhost:8104
OPTIMIZER_AGENT_URL=http://localhost:8105

# agents/.env
OPENWEATHER_API_KEY=changeme

# frontend/.env.local
VITE_WEATHER_AGENT_URL=http://localhost:8000/weather/forecast

# digital-twin/.env
MCP_SERVER_PORT=8080
```

## Data, Models & Digital Twin

-   `digital-twin/opcua-server/parse_historical_data.py` ingests HSY-provided CSVs (`digital-twin/opcua-server/data/*.txt`) into Parquet for fast replay.
-   `digital-twin/opcua-server/opcua_server.py` streams rows through a namespace of pump variables while `digital-twin/mcp-server/mcp_server.py` exposes browse/read/write/history/aggregate tools over SSE for MCP clients.
-   `sample/` contains JSON fallbacks (`weather_fallback.json`, `market_price_fallback.json`) and Valmet metadata for demos without live integrations.
-   `spot-price-forecast/` bundles notebooks (`notebooks/`), scripts (`script/main.py`), and trained model metadata (`models/consumption_forecast_model_info.json`) to bootstrap price forecasting research. Requires `FINGRID_API_KEY` as described in its README.

## Testing & QA

-   Backend: `pytest -q` (see `docs/TESTING.md` for coverage goals, scheduler tests, async fixtures).
-   Agents: add suites under `agents/tests/` exercising tool contracts (example patterns in `docs/TESTING.md`).
-   Frontend: configure Vitest/RTL for component coverage plus Playwright for E2E once endpoints stabilize.
-   Digital twin: use `digital-twin/test-clients/run.sh` to verify MCP and OPC UA endpoints prior to hooking them into the backend scheduler.

## Troubleshooting

-   Curl snippets: `docs/CURL.md` and `backend/DEBUGGING.md` list ready-made commands for `/system/*`, `/weather/forecast`, `/alerts`.
-   Scheduler not running: confirm `OPTIMIZER_INTERVAL_MINUTES` > 0 and watch logs for `OptimizationScheduler started`. Use `LOG_LEVEL=DEBUG` to surface APScheduler events.
-   Agent HTTP failures: check environment URLs and ensure each agent shim (e.g., `agents/weather_agent/server.py`) is running. Backend falls back to deterministic stubs but logs warnings.
-   Frontend blank data: verify `VITE_WEATHER_AGENT_URL` is reachable and the backend proxy exposes `/weather/forecast`.
-   Digital twin timeouts: confirm OPC UA server (default `opc.tcp://localhost:4840/wastewater/`) started before launching the MCP server or clients.

## Documentation Map

-   `docs/PRD.md` – product requirements, KPIs, and success metrics.
-   `docs/AGENT.md` – per-agent responsibilities, schemas, and TODOs.
-   `docs/BACKEND.md` – file-by-file FastAPI reference.
-   `docs/FRONTEND.md` – component inventory and layout guidance.
-   `docs/TESTING.md` – test strategy, commands, and CI recommendations.
-   `docs/CURL.md` – curated smoke-test commands for every public API.
-   `backend/DEBUGGING.md` – troubleshooting checklist for FastAPI + scheduler flows.

## Roadmap

1. Replace deterministic agent stubs with live FMI, Nord Pool, simulator, and optimization solvers (Pyomo/OR-Tools).
2. Persist schedules, overrides, and alert history in Postgres and expose WebSocket streams for real-time dashboards.
3. Expand automated tests (agents, backend scheduler, frontend components, Playwright E2E) and wire them into CI.
4. Integrate the digital twin OPC UA stream with backend telemetry ingestion, feeding simulator data into optimization loops.
5. Formalize price forecasting pipeline by uplifting `spot-price-forecast/` notebooks into production-grade services.
