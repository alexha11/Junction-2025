# Backend cURL Playbook

This guide collects ready-to-run `curl` snippets for every public FastAPI route in the backend so you can smoke-test the stack without opening the browser.

## 1. Prerequisites
- Backend running locally. The quickest path is Docker Compose:

```bash
docker compose up backend
```

- `curl` (ships with most Linux distros) and `jq` for pretty-printing JSON (optional but handy).

```bash
sudo apt-get update
sudo apt-get install -y jq
```

## 2. Base URL helper
Set a single environment variable so the rest of the commands just work. Adjust the host/port if you are tunneling or using a remote server.

```bash
export BASE_URL=${BASE_URL:-http://localhost:8000}
```

Verify the FastAPI docs UI if you want a quick visual check:

```bash
xdg-open "$BASE_URL/docs"
```

## 3. System snapshot
Fetch the real-time hydrology/system state returned by the Agents Coordinator stub.

```bash
curl -sS "$BASE_URL/system/state" | jq
```

- **Purpose:** sanity-check the backend process; response includes tunnel level, inflow/outflow, price, and eight pump objects.
- **HTTP 200 expectation:** `tunnel_level_m` should be greater than zero (mirrors `backend/tests/test_health.py`).

## 4. Forecast bundles
Retrieve the deterministic inflow and price forecasts.

```bash
curl -sS "$BASE_URL/system/forecasts" | jq
```

- **Purpose:** validate data shaping for the frontend charts.
- **Tip:** pipe to `jq 'map({metric, points: [.points[0], .points[-1]]})'` if you only need boundary values.

## 5. Schedule recommendation
Pull the current pump schedule proposal and justification text.

```bash
curl -sS "$BASE_URL/system/schedule" | jq
```

- **Purpose:** confirm optimization output reaches the API.
- **Payload:** includes `generated_at`, `horizon_minutes`, and an array of `entries` per pump.

## 6. Weather forecast proxy
Request a weather forecast via the backend. The API forwards the call to the weather agent (`settings.weather_agent_url`); if that service is down you still get a fallback series from `AgentsCoordinator`.

```bash
curl -sS -X POST "$BASE_URL/weather/forecast" \
  -H "Content-Type: application/json" \
  -d '{"lookahead_hours":12,"location":"Helsinki"}' | jq
```

- **lookahead_hours:** integer 1-72 (validated by `WeatherForecastRequest`).
- **location:** free-form label that downstream services can interpret.
- **Troubleshooting:** an HTTP 502/504 usually means the weather agent container is unavailable; the backend will still emit fallback data with monotonically increasing timestamps.

## 7. Alerts feed
List currently active operational alerts. Right now this is mocked data, but the schema matches what the real alerting pipeline will send.

```bash
curl -sS "$BASE_URL/alerts/" | jq
```

- **Purpose:** test the frontend banner and ensure severity levels (`info|warning|critical`) render correctly.
- **Note:** timestamps are issued in UTC, so adjust when comparing to local logs.

## 8. Automation hints
- Batch-run everything: `for path in system/state system/forecasts system/schedule alerts/; do curl -sS "$BASE_URL/$path" >/dev/null && echo "OK $path"; done`
- Capture regression artifacts: `curl -sS "$BASE_URL/system/state" -o snapshot.json` and commit to a diagnostics folder when debugging.
- Hit a remote server: override `BASE_URL`, e.g., `export BASE_URL=https://api.staging.yourdomain.com`.
