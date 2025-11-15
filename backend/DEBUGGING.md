# Backend Logging & Diagnostics

Everything you need to trace what the FastAPI backend is doing and verify the main routes with `curl`.

## Logging configuration

- The backend now centralizes logging via `app/logging_config.py` with the format `timestamp | level | logger | message`.
- Configure verbosity using the `LOG_LEVEL` environment variable (defaults to `INFO`). Example for local runs:
  ```bash
  export LOG_LEVEL=DEBUG
  uvicorn app.main:app --reload
  ```
- Docker Compose inherits the same setting. Override it inline when needed:
  ```bash
  LOG_LEVEL=DEBUG docker compose up backend
  ```

## What gets logged

| Component                      | Sample message                                     | When it fires                                                                                                           |
| ------------------------------ | -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `app.main`                     | `Starting optimization scheduler`                  | During FastAPI lifespan startup/shutdown, including interval metadata.                                                  |
| `OptimizationScheduler`        | `New schedule recommendation computed (entries=2)` | Each APScheduler tick after `AgentsCoordinator.get_schedule_recommendation()` resolves.                                 |
| `AgentsCoordinator`            | `Requesting weather forecast (location=Helsinki)`  | Whenever the backend reaches out to agents (or emits synthetic fallback data). Exceptions are logged with stack traces. |
| `/system/*` & `/alerts` routes | `Received request for schedule recommendation`     | Logged per incoming HTTP request so you can correlate API traffic with agent calls.                                     |

All logs go to STDOUT, so they appear in your terminal, `docker compose logs backend`, and any centralized collector you hook up later.

## Quick `curl` smoke tests

1. Set the base URL once (defaults to localhost):
   ```bash
   export BASE_URL=${BASE_URL:-http://localhost:8000}
   ```
2. System state snapshot:
   ```bash
   curl -sS "$BASE_URL/system/state" | jq
   ```
3. Forecast bundle (inflow + price):
   ```bash
   curl -sS "$BASE_URL/system/forecasts" | jq
   ```
4. Schedule recommendation:
   ```bash
   curl -sS "$BASE_URL/system/schedule" | jq
   ```
5. Weather proxy (falls back to synthetic data if the agent is down):
   ```bash
   curl -sS -X POST "$BASE_URL/weather/forecast" \
     -H "Content-Type: application/json" \
     -d '{"lookahead_hours":12,"location":"Helsinki"}' | jq
   ```
6. Alerts feed:
   ```bash
   curl -sS "$BASE_URL/alerts/" | jq
   ```

Log output will show each request, making it easy to line up terminal responses with backend activity. For a deeper set of examples, see `docs/CURL.md`.
