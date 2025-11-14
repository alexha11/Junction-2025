# HSY Blominmäki AI Agent Pumping Optimization System

This repository contains the end-to-end scaffolding for the multi-agent optimization platform described in `docs/PRD.md`. It is organized as a mono-repo with three main workspaces:

- `backend/` – FastAPI service that exposes REST + WebSocket APIs, schedules optimization runs, and orchestrates agents.
- `agents/` – Collection of Model Context Protocol (MCP) microservices (weather, electricity price, system status, inflow forecast, and optimization coordinator) powered by the OpenAI Agents SDK pattern.
- `frontend/` – React dashboard for operators showing plant state, forecasts, AI recommendations, alerts, and manual override logging.

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 2. Agents (local stubs)

Each agent currently ships with deterministic stub logic so the rest of the stack is runnable without external integrations. Replace `serve()` with the official MCP server hooks once the OpenAI Agents SDK MCP utilities are available.

```bash
cd agents
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..  # run agents as modules so the package is discoverable
python -m agents.weather_agent.main
python -m agents.price_agent.main
# ... repeat for other agents as needed
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies API calls to `http://localhost:8000` so both the backend and frontend must be running.

## Architectural Highlights

- **MCP-first Agents:** Each agent implements a single MCP tool (e.g., `get_precipitation_forecast`). A thin base class in `agents/common` makes it easy to attach to the OpenAI Agents SDK later.
- **Coordinator Scheduler:** The FastAPI backend hosts an `OptimizationScheduler` that refreshes recommendations every 15 minutes (configurable). This is where MCP agent calls are orchestrated.
- **Simulator Adapter:** `backend/app/services/simulator_adapter.py` acts as an integration point for the HSY simulator, ensuring telemetry flows back into the dashboard.
- **Operator Dashboard:** The React UI consumes `/system/state`, `/system/forecasts`, `/system/schedule`, and `/alerts` endpoints, updating via React Query polling. Components mirror FR1 sections (system overview, forecast, AI recommendation, alerts, manual override form).

## Next Steps

1. Swap stub agent implementations with real FMI, Nord Pool, simulator, and ML integrations.
2. Extend the backend persistence layer (Postgres + Redis) for schedule history, overrides, and alerting.
3. Replace the optimizer stub with a Pyomo/OR-Tools solver that enforces all constraints outlined in the PRD.
4. Add WebSocket streaming for real-time updates and tighten automated test coverage (unit + integration + E2E/playwright).
