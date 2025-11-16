# Release Notes – 2025.11 "Full-Stack Demo"

> Snapshot date: 2025-11-16  
> Branch: `main`

## 1. Overview

This release bundles every component required to run the HSY Blominmäki optimization loop end to end:

- FastAPI backend with scheduler, digital-twin adapters, and public `/system/*` APIs.
- Deterministic MCP/HTTP agents (weather, price, inflow, status, optimizer) with Docker targets.
- React + Vite operator dashboard served via NGINX.
- Digital twin (OPC UA server + MCP bridge) seeded with historical HSY data.
- Hardened `docker-compose.full.yml` stack plus deployment playbooks in `DEPLOYMENT.md` and `deploy/docker/README.md`.

## 2. Component Matrix

| Area            | Version / Location            | Notes |
| --------------- | ----------------------------- | ----- |
| Backend API     | `backend/app`                 | FastAPI 0.115+, APScheduler-driven optimizer loop.
| MCP Agents      | `agents/`                     | Weather, price, inflow, status, optimizer (HTTP + MCP).
| Frontend        | `frontend/`                   | React 18, Vite dev server + NGINX production image.
| Digital Twin    | `digital-twin/opcua-server`, `digital-twin/mcp-server` | Replay HSY telemetry via OPC UA + MCP bridge.
| Deployment      | `docker-compose.full.yml`, `DEPLOYMENT.md`, `deploy/docker/README.md` | Full stack orchestrated with optional Postgres/Redis.
| Simulation Core | `simulation/`                 | Pump/tunnel models shared across agents & backend.
| Research Tools  | `spot-price-forecast/`        | Nord Pool modeling notebooks and scripts.

## 3. Release Highlights

1. **Unified architecture documentation** – README + `docs/SYSTEM_ARCHITECTURE.md` now share the same multi-layer Mermaid diagram describing the frontend, backend, agents, twin, and data planes.
2. **Full-stack Docker flow** – `docker-compose.full.yml` exposes backend, frontend, all MCP agents, OPC UA + MCP servers, and optional Postgres/Redis from a single command.
3. **Expanded agent coverage** – Weather/price shims now document their HTTP servers, optimizer exposes an HTTP bridge, and status/inflow agents are highlighted for integration parity.
4. **Environment guidance** – Sample `.env` values cover new ports, LLM keys, and digital-twin knobs to prevent drift between dev and deploy environments.

## 4. Breaking Changes & Migration Notes

- `docker-compose.full.yml` is the preferred entry point; previous two-step stacks should update env files to include the new `*_PORT`, `USE_OPENWEATHER`, `USE_NORD_POOL`, and Featherless variables.
- Optimizer agent defaults to calling the backend and MCP services by container name; update `.env` if running outside Docker.
- Documentation references for deployment moved to `DEPLOYMENT.md` and `deploy/docker/README.md`; ensure internal wikis link to these files.

## 5. Prerequisites & Compatibility

| Component  | Requirement |
| ---------- | ----------- |
| Python     | 3.12+ for backend/agents/digital-twin tooling. |
| Node.js    | 20+ for the frontend. |
| Docker     | Engine 24+ / Compose V2 for the full stack. |
| Hardware   | 8 GB RAM (16 GB recommended) + 4 CPU cores when running all services concurrently. |
| External APIs | Optional keys: `OPENWEATHER_API_KEY`, Nord Pool credentials, Featherless LLM token. |

## 6. Deployment Checklist

```bash
# 1. Copy or craft env overrides
cp .env.example .env  # edit ports, secrets, API keys

# 2. Build and launch the full platform
docker compose -f docker-compose.full.yml build
docker compose -f docker-compose.full.yml up -d

# 3. Verify health
curl http://localhost:8000/system/health
curl http://localhost:8101/health
curl http://localhost:8102/health
curl http://localhost:8105/health
```

Additional details live in `DEPLOYMENT.md` and `deploy/docker/README.md` (port overrides, scaling, troubleshooting, cleanup).

## 7. Validation Matrix

| Area      | Command / File                              | Status |
| --------- | ------------------------------------------- | ------ |
| Backend   | `cd backend && pytest -q`                    | Run before tagging release. |
| Frontend  | `cd frontend && npm run build`              | Ensures Vite/NGINX bundle compiles. |
| Agents    | Manual smoke: `python -m agents.weather_agent.server` etc. | Confirmed deterministic responses. |
| Digital Twin | `cd digital-twin && docker compose up --build` | Validates OPC UA + MCP bridge wiring. |
| Full Stack | `docker compose -f docker-compose.full.yml up -d` | Verified on Linux host. |

## 8. Known Issues & Mitigations

1. **No live Nord Pool feed** – price agent defaults to deterministic JSON; set `USE_NORD_POOL=true` and provide credentials to enable real data.
2. **Optimizer HTTP cold start** – first schedule can take ~20s while OR-Tools warms up. Mitigation: keep container warm or pre-trigger via `/system/recommendations`.
3. **Digital twin dependency** – backend logs warnings if OPC UA is offline; export `USE_SAMPLE_DATA=1` to run without the twin.
4. **Frontend polling** – dashboard still polls every 30s; WebSocket upgrade is tracked on the roadmap.

## 9. Next Steps

- Replace deterministic agents with live FMI, Nord Pool, and simulator feeds (Roadmap item #1).
- Persist overrides/schedules in Postgres and expose WebSocket updates.
- Expand automated testing: Vitest/Playwright for the frontend, OR-Tools regression tests for the optimizer, and CI wiring for docker-compose smoke tests.

## 10. References

- `README.md` – quick start, architecture overview, and command snippets.
- `docs/SYSTEM_ARCHITECTURE.md` – deep dive diagrams and data flows.
- `DEPLOYMENT.md`, `deploy/docker/README.md` – full-stack deployment playbooks.
- `docs/TESTING.md` – testing strategy and future CI hooks.
