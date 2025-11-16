# HSY Blominmäki AI Agent Pumping Optimization System

End-to-end platform for optimizing HSY Blominmäki wastewater pumping using multi-agent forecasts, a FastAPI orchestration backend, a React operator dashboard, and supporting digital-twin tooling.

## 📚 Table of Contents

- [HSY Blominmäki AI Agent Pumping Optimization System](#hsy-blominmäki-ai-agent-pumping-optimization-system)
  - [📚 Table of Contents](#-table-of-contents)
  - [🚀 Features](#-features)
  - [🛠️ Technology Stack](#%EF%B8%8F-technology-stack)
  - [📦 Installation & Setup](#-installation--setup)
    - [Backend](#backend)
    - [MCP Agents](#mcp-agents)
    - [Frontend](#frontend)
    - [Digital-Twin Tooling](#digital-twin-tooling)
  - [🚀 Running the Application](#-running-the-application)
  - [📦 Production Build & Deployment](#-production-build--deployment)
  - [📁 Project Structure](#-project-structure)
  - [🔑 Key Features Explained](#-key-features-explained)
  - [🔌 API Endpoints](#-api-endpoints)
  - [🔧 Troubleshooting](#-troubleshooting)
  - [📝 Notes](#-notes)
  - [🤝 Contributing](#-contributing)
  - [🔐 Configuration & Secrets](#-configuration--secrets)
    - [🧾 Sample `.env`](#-sample-env)
  - [🧬 Data, Models & Digital Twin](#-data-models--digital-twin)
  - [🧪 Testing & QA](#-testing--qa)
  - [🗂️ Documentation Map](#%EF%B8%8F-documentation-map)
  - [🧭 Roadmap](#-roadmap)

## 🚀 Features

- Coordinate deterministic MCP agents (weather, price, status, inflow, optimizer) to refresh pump recommendations every 15 minutes.
- Surface tunnel telemetry, forecasts, AI schedules, and operator overrides through a Tailwind-styled React dashboard.
- Mirror field conditions via a digital twin (OPC UA + MCP bridge) backed by historical HSY data for safe experimentation.
- Package research-grade Nord Pool price forecasting tools to accelerate optimization strategy iteration.

## 🛠️ Technology Stack

- Python 3.12 recommended (backend + agents) with component-specific `requirements.txt` files.
- FastAPI, Pydantic, SQLAlchemy, APScheduler, Redis/Postgres clients for orchestration logic.
- Node.js 20+, Vite, React 18, React Query, Zustand, Tailwind, Recharts for the operator portal.
- Docker & Docker Compose for consistent multi-service workflows across dev, demo, and production.

## 📦 Installation & Setup

> All commands assume the repository root. Use one virtual environment per workspace to prevent dependency clashes.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Or with Docker:

```bash
cd backend
docker build -t hsy-backend .
docker run -p 8000:8000 --env-file .env hsy-backend
```

- Optional: `LOG_LEVEL=DEBUG uvicorn app.main:app --reload` enables verbose router/scheduler logs.
- API smoke tests: `pytest tests/test_api_routes.py -q`.

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

- Update each agent's `main.py` to point at live integrations once credentials are available.

### Frontend

```bash
cd frontend
npm install
export VITE_WEATHER_AGENT_URL="http://localhost:8000/weather/forecast"
npm run dev
```

Or with Docker:

```bash
cd frontend
docker build -t hsy-frontend .
docker run -p 5173:5173 --env VITE_WEATHER_AGENT_URL="http://localhost:8000/weather/forecast" hsy-frontend
```

- Dev proxy forwards `/api/*` to `http://localhost:8000`; keep the backend running to avoid 404s.
- Planned tests: `npm run test` (Vitest) and `npx playwright test` when E2E flows stabilize.

### Digital-Twin Tooling

- **OPC UA server**

  ```bash
  cd digital-twin/opcua-server
  pip install -r requirements.txt
  python opcua_server.py  # streams historical HSY data into the OPC UA namespace
  ```

  Or via Docker Compose:

  ```bash
  cd digital-twin
  docker compose up --build  # starts both the OPC UA server & the MCP bridge
  ```

- **MCP bridge**

  ```bash
  cd digital-twin/mcp-server
  pip install -r requirements.txt
  export MCP_SERVER_PORT=8080
  python mcp_server.py  # exposes browse/read/write/history tools over SSE
  ```

  Or via Docker Compose (same command as above).

- **Test clients**

  ```bash
  cd digital-twin/test-clients
  ./run.sh  # Requires Python 3.13 on PATH
  ```

## 🚀 Running the Application

- Maintain separate shells for backend, agents, frontend, and the digital twin for faster iteration.
- Quick local dev loop:

  ```bash
  # Terminal 1
  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

  # Terminal 2
  cd agents && source .venv/bin/activate && python -m agents.weather_agent.server

  # Terminal 3
  cd frontend && npm run dev
  ```

- For fully deterministic smoke tests, export `USE_SAMPLE_DATA=1` (backend) and rely on `sample/*.json` fallbacks.

## 📦 Production Build & Deployment

- `docker-compose.yml` (repo root) brings up FastAPI, the Vite build served by NGINX, and digital-twin services:

  ```bash
  docker compose build
  docker compose up -d
  ```

- Services:

  - Backend API – `http://localhost:8000`
  - Frontend dashboard – `http://localhost:5173`
  - OPC UA server – `opc.tcp://localhost:4840/wastewater/`
  - MCP bridge – `http://localhost:8080`

- Stop with `docker compose down` (add `-v` to reset volumes). Tail logs with `docker compose logs -f backend`.

## 📁 Project Structure

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

## 🔑 Key Features Explained

- **Multi-agent forecasting** – Weather, electricity price, inflow, status, and optimizer agents expose deterministic tools that can be swapped for live data sources without changing contracts.
- **Optimization scheduler** – A background `OptimizationScheduler` in FastAPI orchestrates Redis/Postgres state, agent calls, and schedule refreshes every 15 minutes.
- **Operator dashboard** – React + Tailwind portal showcases tunnel telemetry, AI recommendations, override flows, alerts, and agent health cards.
- **Digital twin** – OPC UA server seeded from historical HSY dumps plus an MCP bridge enables safe pump simulations and read/write experiments before field rollout.
- **Research toolkit** – `spot-price-forecast/` contains notebooks, models, and scripts for Nord Pool spot price modeling to feed optimizer heuristics.

## 🔌 API Endpoints

| Endpoint                  | Method | Description                                     |
| ------------------------- | ------ | ----------------------------------------------- |
| `/system/health`          | GET    | FastAPI liveness + dependency probes.           |
| `/system/status`          | GET    | Aggregated agent + scheduler state.             |
| `/system/recommendations` | GET    | Latest pump schedule produced by the optimizer. |
| `/alerts`                 | GET    | Active alerts surfaced to the operator portal.  |
| `/weather/forecast`       | POST   | Weather agent shim exposing deterministic data. |

- Additional curls and payloads live in `docs/CURL.md` and `backend/DEBUGGING.md`.

## 🔧 Troubleshooting

- Curl snippets: `docs/CURL.md` and `backend/DEBUGGING.md` cover `/system/*`, `/weather/forecast`, `/alerts`.
- Scheduler idle: ensure `OPTIMIZER_INTERVAL_MINUTES` > 0 and watch for `OptimizationScheduler started` in logs with `LOG_LEVEL=DEBUG`.
- Agent HTTP failures: confirm service URLs (`WEATHER`, `PRICE`, `STATUS`, `INFLOW`, `OPTIMIZER`) and agent servers (e.g., `agents/weather_agent/server.py`) are running.
- Frontend blank data: verify `VITE_WEATHER_AGENT_URL` resolves and backend proxy exposes `/weather/forecast`.
- Digital twin timeouts: launch the OPC UA server (`opc.tcp://localhost:4840/wastewater/`) before the MCP server or clients.

## 📝 Notes

- Prefer `.env` files listed below for reproducible demos; never commit tenant secrets.
- `sample/` data keeps demos deterministic when FMI/Nord Pool keys are unavailable.
- The digital twin expects historical files under `digital-twin/opcua-server/data/`; regenerate Parquet via `parse_historical_data.py` when data updates.

## 🤝 Contributing

- Fork or branch from `main`, keep pull requests small, and attach screenshots/logs for UI or agent changes.
- Run relevant unit tests (`pytest`, `npm run test`) plus linting before opening a PR.
- Update documentation (`docs/*.md`, this README) whenever APIs, env vars, or workflows change.

## 🔐 Configuration & Secrets

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

### 🧾 Sample `.env`

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

## 🧬 Data, Models & Digital Twin

- `digital-twin/opcua-server/parse_historical_data.py` ingests HSY-provided CSVs (`digital-twin/opcua-server/data/*.txt`) into Parquet for fast replay.
- `digital-twin/opcua-server/opcua_server.py` streams rows through a namespace of pump variables while `digital-twin/mcp-server/mcp_server.py` exposes browse/read/write/history/aggregate tools over SSE for MCP clients.
- `sample/` contains JSON fallbacks (`weather_fallback.json`, `market_price_fallback.json`) and Valmet metadata for demos without live integrations.
- `spot-price-forecast/` bundles notebooks (`notebooks/`), scripts (`script/main.py`), and trained model metadata (`models/consumption_forecast_model_info.json`) to bootstrap price forecasting research. Requires `FINGRID_API_KEY` as described in its README.

## 🧪 Testing & QA

- Backend: `pytest -q` (see `docs/TESTING.md` for coverage goals, scheduler tests, async fixtures).
- Agents: add suites under `agents/tests/` exercising tool contracts (example patterns in `docs/TESTING.md`).
- Frontend: configure Vitest/RTL for component coverage plus Playwright for E2E once endpoints stabilize.
- Digital twin: use `digital-twin/test-clients/run.sh` to verify MCP and OPC UA endpoints prior to hooking them into the backend scheduler.

## 🗂️ Documentation Map

- `docs/PRD.md` – product requirements, KPIs, and success metrics.
- `docs/AGENT.md` – per-agent responsibilities, schemas, and TODOs.
- `docs/BACKEND.md` – file-by-file FastAPI reference.
- `docs/FRONTEND.md` – component inventory and layout guidance.
- `docs/TESTING.md` – test strategy, commands, and CI recommendations.
- `docs/CURL.md` – curated smoke-test commands for every public API.
- `backend/DEBUGGING.md` – troubleshooting checklist for FastAPI + scheduler flows.

## 🧭 Roadmap

1. Replace deterministic agent stubs with live FMI, Nord Pool, simulator, and optimization solvers (Pyomo/OR-Tools).
2. Persist schedules, overrides, and alert history in Postgres and expose WebSocket streams for real-time dashboards.
3. Expand automated tests (agents, backend scheduler, frontend components, Playwright E2E) and wire them into CI.
4. Integrate the digital twin OPC UA stream with backend telemetry ingestion, feeding simulator data into optimization loops.
5. Formalize price forecasting pipeline by uplifting `spot-price-forecast/` notebooks into production-grade services.
