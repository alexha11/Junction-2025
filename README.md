# Flow Optimizer

## Build & Run

```bash
docker compose up --build
```

Services:

- `opcua-server` on `opc.tcp://localhost:4840/wastewater/`
- `pump-scheduler` web UI/API on `http://localhost:8090`
- `pump-actuator` worker that polls pending DB commands and dispatches/acks them

## Web + API

- `GET /` -> live status page
- `GET /health`
- `GET /api/status`
- `GET /api/commands?limit=50&pending_only=false`
- `POST /api/commands/{id}/ack`
- `GET /api/simulation/speed`
- `POST /api/simulation/speed?speedup=1200`

## Database

Default DB path inside container: `/app/data/scheduler.db`

Compose mounts it to host path:

- `pump-scheduler/data/scheduler.db`

Main tables:

- `decisions`
- `summaries`
- `constraints`
- `operations`
- `commands`
