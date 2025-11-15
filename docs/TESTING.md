# Testing Guide

This document describes how to validate the HSY Blominmäki AI Agent Pumping Optimization System across the backend, MCP agents, and frontend. It also highlights future automated test suites required to satisfy the PRD.

## 1. Prerequisites

- Python 3.11+ with virtual environments (`uv`/`pip` or `poetry`).
- Node.js 20+ with npm.
- Redis/Postgres (optional for now; mocked/stubbed layers are used but integration tests can target real services later).
- Simulator data (`Hackathon_HSY_data.csv`) available locally for inflow model tests.

### Environment Setup

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt  # requirements-dev TBD, see roadmap

# Agents
cd ../agents
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

> **Note:** When running tests from the repo root, prefix commands with the correct virtualenv (`.venv/bin/python`).

## 2. Backend Testing

The backend uses FastAPI + APScheduler. Testing focuses on three layers: models/validators, API routes, and background scheduler logic.

### 2.1 Unit Tests (Pytest)

`backend/tests/test_health.py` demonstrates a minimal test. Extend coverage with modules under `app/models.py`, `app/services/*`, and routers.

```bash
cd backend
pytest -q
```

**Recommended additions**

- **Model validation**: ensure `SystemState`, `ForecastSeries`, `ScheduleRecommendation`, and `Alert` schemas reject invalid payloads.
- **Agents coordinator stubs**: test deterministic outputs and future MCP client error handling.
- **Scheduler**: mock `AgentsCoordinator` to assert scheduling cadence and persistence hooks.

### 2.2 Integration Tests

Once the simulator adapter, Redis, and Postgres are wired, add integration suites that:

1. Spin up a FastAPI test client with dependency overrides for agents/simulator.
2. Verify `/system/*` and `/alerts` endpoints respond with cached DB values.
3. Ensure background tasks persist new schedules and broadcast via WebSockets.

Use `pytest-asyncio` for async route testing.

### 2.3 Performance & Regression

- Target: Optimization loop must complete within 2 minutes. Add async tests that instrument the optimization call path and assert runtime thresholds using `pytest.mark.timeout` or custom timers.
- Regression: Record sample schedule responses in fixtures and compare JSON outputs for stability.

### 2.4 Logging & Curl Diagnostics

- Set `LOG_LEVEL` before starting FastAPI/pytest to surface detailed traces from routers, the `AgentsCoordinator`, and the scheduler (defaults to `INFO`).

  ```bash
  export LOG_LEVEL=DEBUG
  uvicorn app.main:app --reload
  ```

- Use the curated snippets in `backend/DEBUGGING.md` (mirrors `docs/CURL.md`) to hit `/system/state`, `/system/forecasts`, `/system/schedule`, `/weather/forecast`, and `/alerts/`. Pair each `curl` invocation with the STDOUT logs to confirm requests reach the expected code paths and fallback logic kicks in when upstream agents are unavailable.
- When triaging flaky tests, re-run `pytest -q` with `LOG_LEVEL=DEBUG` to capture scheduler invocations and HTTP client failures inside the test logs.

## 3. MCP Agent Testing

Each agent currently serves deterministic responses. Testing ensures MCP tool contracts remain stable before integrating the OpenAI Agents SDK.

### 3.1 Unit Tests

Create `agents/tests/` with separate modules per agent. Sample pattern:

```python
from agents.weather_agent.main import WeatherAgent, WeatherRequest

def test_weather_forecast_length():
    agent = WeatherAgent()
    agent.configure()
    result = agent.get_precipitation_forecast(WeatherRequest(lookahead_hours=3))
    assert len(result) == 3
```

Use direct function calls until real MCP bindings exist. When swapping to the Agents SDK, add contract tests hitting the MCP server via `httpx.AsyncClient` or the SDK tooling.

### 3.2 Integration Tests

- Mock external APIs (FMI, Nord Pool) using `respx` or `responses` to ensure retry/fallback logic.
- Validate the Inflow model by loading a small fixture of `Hackathon_HSY_data.csv` and asserting predictions stay within expected ranges.
- For the Optimization Agent, craft scenario fixtures describing constraints (L1 bounds, pump cooldowns) and assert the output schedule respects each rule.

### 3.3 Simulator-in-the-loop Tests

When the System Status Agent connects to the HSY simulator, add async tests that:

1. Seed the simulator with deterministic inflow/time-of-day data.
2. Call `get_current_system_state()` and assert the response matches simulator telemetry.
3. Run an end-to-end optimization step and feed the schedule back into the simulator to ensure constraint compliance.

## 4. Frontend Testing

The React/Vite dashboard requires both component-level and end-to-end validation.

### 4.1 Unit + Component Tests

Adopt Vitest or Jest with React Testing Library.

```bash
cd frontend
npm run test  # configure in package.json once vitest is added
```

Suggested coverage:

- `SystemOverviewCard`: renders stats and pump table given mock `SystemState` data.
- `ForecastPanel`: charts data correctly and shows loading states when props missing.
- `RecommendationPanel` and `OverridePanel`: user interactions (form submission, justification display).

### 4.2 Integration Tests (Mock API)

Use MSW (Mock Service Worker) with React Testing Library or Storybook stories to simulate backend responses and verify the dashboard layout updates as data changes.

### 4.3 End-to-End Tests

Leverage Playwright or Cypress:

1. Boot backend (with stubbed agents) and frontend dev server.
2. Run scenarios such as “Operator sees alert when L1 high” or “Manual override submission calls backend endpoint”.
3. Validate charts update after WebSocket/SSE messages once implemented.

Example Playwright command once configured:

```bash
cd frontend
npx playwright test
```

## 5. CI/CD Recommendations

- Use GitHub Actions with separate jobs for backend pytest, agents pytest, frontend lint + tests, and Playwright E2E.
- Cache Python wheels (`pip cache dir`) and npm packages for faster runs.
- Fail builds on lint/test errors; publish coverage artifacts (e.g., `pytest --cov`, `vitest --coverage`).

## 6. Manual QA Checklist

Until full automation exists, run these manual checks before demos:

1. `LOG_LEVEL=DEBUG uvicorn app.main:app --reload` (verify `/system/state` returns JSON and watch scheduler start/stop logs).
2. `npm run dev` (dashboard loads, shows stub data).
3. Manual override form logs reason (check backend log placeholder until persistence added).
4. Optimization scheduler log prints every 15 minutes—cross-check with the `curl` smoke tests in `backend/DEBUGGING.md` to confirm endpoints respond consistently.

## 7. Future Enhancements

- **Property-based testing** for optimization constraints (Hypothesis/Hedgehog) to explore edge cases.
- **Load testing** using Locust or K6 to simulate multiple dashboard clients and ensure backend throughput.
- **Chaos testing** for agent outages, ensuring backend falls back gracefully (record & replay last known data).

Refer back to `docs/PRD.md` to confirm all functional requirements have corresponding tests as features mature.
