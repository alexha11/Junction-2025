# Docker Guide

This repository includes first-class Docker support for the FastAPI backend, Vite frontend, and supporting infrastructure (Postgres + Redis). Use this guide to build local images, boot the stack with Docker Compose, and customize the environment for development or demo runs.

## Key Files

| File | Purpose |
| --- | --- |
| `backend/Dockerfile` | Builds the FastAPI backend plus its data assets (sample fallbacks and price-model sources). Creates a dedicated Python 3.12 virtual environment and runs Uvicorn as a non-root user. |
| `frontend/Dockerfile` | Builds the Vite/React dashboard, parameterized by `VITE_WEATHER_AGENT_URL` so the compiled bundle can point at any backend weather endpoint. |
| `docker-compose.yml` | Orchestrates backend, frontend, Postgres 16, and Redis 7. Applies health checks, bind mounts the backend source for rapid iteration, and exposes ports 8000/5173/5432/6379. |
| `.dockerignore` | Keeps the backend image lean by excluding docs, agents, digital-twin tooling, raw datasets, and other non-runtime assets from the build context. |

## Prerequisites

- Docker Engine 24+ (or Docker Desktop) with the Compose V2 plugin.
- At least 4 CPU cores and 6 GB RAM for the full stack (FastAPI + frontend build + Postgres + Redis).
- (Optional) Local instances of the MCP agents running on ports 8101–8105 if you want the backend to call live services instead of fallbacks.

## Building Images

From the repo root:

```bash
# Build every service defined in docker-compose.yml
docker compose build

# Build a single service when iterating on Dockerfiles
docker compose build backend
```

The backend image copies `backend/`, `sample/`, and `spot-price-forecast/` so the service can access fallback JSON and the price-model assets at runtime. The frontend image accepts a `VITE_WEATHER_AGENT_URL` build argument (default: `http://backend:8000/weather/forecast`). Override it via Compose build args or `docker build --build-arg` when pointing at a different backend domain.

## Running the Stack

```bash
# Start the entire platform in the background
docker compose up -d

# Follow backend logs (scheduler + API)
docker compose logs -f backend

# Tear everything down and remove volumes
docker compose down -v
```

Services exposed:

- Backend API: http://localhost:8000
- Frontend dashboard (nginx): http://localhost:5173
- Postgres: localhost:5432 (`postgres` / `postgres`, db `hsy`)
- Redis: localhost:6379

The backend container bind-mounts `./backend` into `/workspace/backend`, so code edits on the host immediately reflect inside the container. Restart the backend service after dependency changes:

```bash
docker compose restart backend
```

## Environment Variables

Compose ships with sensible defaults but everything can be overridden through your shell env or a `.env` file in the repo root. Common settings:

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | FastAPI + scheduler log verbosity. |
| `OPTIMIZER_INTERVAL_MINUTES` | `15` | Background optimization cadence. |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@postgres:5432/hsy` | SQLAlchemy DSN pre-wired to the Compose Postgres service. |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection for caching/broker duties. |
| `WEATHER_AGENT_URL` … `OPTIMIZER_AGENT_URL` | `http://host.docker.internal:81xx` | Base URLs for the MCP agents. Update these if you run the agents inside Compose or on another host. |
| `VITE_WEATHER_AGENT_URL` (build arg) | `http://backend:8000/weather/forecast` | Compile-time endpoint baked into the frontend bundle. |
| `BACKEND_PORT` | `8000` | Host port forwarded to the FastAPI container. |
| `FRONTEND_PORT` | `5173` | Host port for the nginx-served dashboard. |
| `POSTGRES_PORT` | `5432` | Host port for Postgres; change if the default conflicts. |
| `REDIS_PORT` | `6379` | Host port for Redis. |
| `POSTGRES_DB/USER/PASSWORD` | `hsy` / `postgres` / `postgres` | Database bootstrap credentials. |

Sample workflow with a `.env` file:

```
LOG_LEVEL=DEBUG
WEATHER_AGENT_URL=http://backend:8000/weather
VITE_WEATHER_AGENT_URL=https://api.example.com/weather/forecast
```

Compose automatically loads `.env` before evaluating the file.

## Interacting With Containers

```bash
# Open a shell inside the backend container
docker compose exec backend bash

# Run backend tests inside the container
docker compose exec backend pytest -q

# Tail frontend nginx logs
docker compose logs -f frontend
```

Because the backend image already contains the project’s dev dependencies (pytest, ruff, etc.), you can run quality checks without installing Python locally.

## Agent Integration Options

- **Host-run agents (default)**: The backend targets `http://host.docker.internal:8101-8105`, so launch each agent on the host and leave the defaults intact.
- **Compose-managed agents**: Add new services to `docker-compose.yml` (or use the existing `deploy/docker/compose.yaml` as a template) and update the backend environment variables to reference the in-network hostnames, e.g. `WEATHER_AGENT_URL=http://weather-agent:8101`.
- **Remote agents**: Point the URLs at any reachable HTTP endpoint; the backend does not assume agents live on the same machine.

If an agent is unavailable, the backend logs a warning and falls back to deterministic sample data (`sample/weather_fallback.json`, `sample/market_price_fallback.json`).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Backend health check keeps failing | Run `docker compose logs backend` and ensure the scheduler is not throwing import errors. Verify the agent URLs resolve (or set them to `http://backend:8000/...` for stubbed flows). |
| Postgres container restart loop | Port `5432` may already be in use on the host. Set `POSTGRES_PORT=55432` (and update `DATABASE_URL` if you connect from outside Compose), then re-run `docker compose up`. |
| File edits not reflected | The backend mount only watches Python modules; restart the container after changing dependencies or compiled assets. For frontend tweaks you must rebuild the image (or run `npm run dev` outside Docker). |
| Need to inspect DB contents | Use `docker compose exec postgres psql -U postgres -d hsy`. |

## Cleanup

```bash
# Stop services but keep volumes
docker compose down

# Remove dangling images and volumes
docker system prune -f
```

Refer back to `README.md` for high-level architecture context and to `docs/BACKEND.md` / `docs/FRONTEND.md` for service-specific development guidance.
