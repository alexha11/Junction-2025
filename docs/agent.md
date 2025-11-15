# Agent Services Reference

This guide walks through every file inside `agents/`, explaining how the MCP-style microservices are structured and how to extend them.

## Top-Level Files

| File                      | Purpose                                                                                                                                                                                                                   |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agents/__init__.py`      | Declares the package, signaling that the folder contains importable modules.                                                                                                                                              |
| `agents/pyproject.toml`   | Python packaging metadata (`hatchling` build). Declares the project as `hsy-mcp-agents`, pins Python 3.11+, and lists core dependencies (`pydantic`, `httpx`, `openai`, `aiofiles`). Includes a `dev` extra for `pytest`. |
| `agents/requirements.txt` | Lightweight alternative for virtualenv bootstrap. Mirrors the dependencies from `pyproject.toml`. Use this with `pip install -r requirements.txt` when not invoking `pip install -e .`.                                   |

## Common Utilities

| File                        | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                   |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agents/common/__init__.py` | Re-exports `BaseMCPAgent` and `ToolSchema` so other modules can import via `from agents.common import BaseMCPAgent`.                                                                                                                                                                                                                                                                                                      |
| `agents/common/base.py`     | Defines `ToolSchema` (a thin `pydantic.BaseModel`) plus the `BaseMCPAgent` abstract class. `BaseMCPAgent` stores a registry of MCP-style tools, exposes `register_tool`/`call_tool`, and implements a `serve()` helper that prints registered tools. Subclasses override `configure()` to register their tool handlers. This file is the core harness you will swap with the OpenAI Agents SDK once MCP servers are live. |

## Weather Agent (`agents/weather_agent/main.py`)

- **Classes**: `WeatherRequest`, `WeatherPoint`, `WeatherAgent`.
- **Tools**: `get_precipitation_forecast(WeatherRequest)` returns deterministic hourly precipitation + temperature points for the requested horizon.
- **Usage**: Call `WeatherAgent().serve()` (or run the module) to register the tool; swap the stub logic with FMI API calls later.

## Electricity Price Agent (`agents/price_agent/main.py`)

- **Classes**: `PriceRequest`, `PricePoint`, `ElectricityPriceAgent`.
- **Tools**: `get_electricity_price_forecast(PriceRequest)` produces an increasing EUR/MWh curve for the lookahead window.
- **Usage**: Run the module to print the registered tool. Replace the body with Nord Pool API fetches and convert the response into `PricePoint` entries.

## Inflow Forecast Agent (`agents/inflow_agent/main.py`)

- **Classes**: `InflowRequest`, `WeatherDatum` (reserved for future conditioning), `InflowPoint`, `InflowForecastAgent`.
- **Tools**: `predict_inflow(InflowRequest)` emits a gentle upward-sloping inflow series. Later this should incorporate weather features (see unused `WeatherDatum`).

## System Status Agent (`agents/status_agent/main.py`)

- **Schemas**: `SystemStatePayload`, `SystemStateRequest`, `TunnelVolumeRequest`, `PumpEfficiencyRequest`.
- **Tools**:
  - `get_current_system_state(SystemStateRequest)` returns telemetry snapshot plus pump array placeholders.
  - `get_tunnel_volume(TunnelVolumeRequest)` estimates volume linearly (TODO: replace with real lookup curve).
  - `get_pump_efficiency(PumpEfficiencyRequest)` provides a capped efficiency heuristic.
- **Notes**: This agent is responsible for simulator integration in the PRD. Replace the placeholder calculations with real simulator/SCADA calls and enforce validation via `pydantic` constraints (`Field(gt=0)` already guards tunnel volume inputs).

## Optimization Agent (`agents/optimizer_agent/main.py`)

- **Schemas**: `OptimizationRequest`, `ScheduleEntry`, `OptimizationResponse`.
- **Tool**: `generate_schedule(OptimizationRequest)` fabricates two pump entries spanning the requested horizon and returns a textual justification.
- **Notes**: In production this agent will orchestrate other agents via MCP to gather state/forecasts, then run the optimization routine before emitting a schedule.

## Package-Level Patterns

- Every agent module defines a `serve()` helper and runs it under `if __name__ == "__main__"`, so you can execute `python agents/weather_agent/main.py` to verify tool registration.
- Tool payloads inherit from `pydantic.BaseModel`, ensuring type validation prior to calling business logic. When integrating with OpenAI's MCP server, reuse these schemas for request/response typing.
- Networking (`httpx`), file I/O (`aiofiles`), and OpenAI Agents SDK bindings are installed but not yet used; they are placeholders for future real data fetches and MCP hosting.

## Next Steps

1. Replace each stub implementation with real integrations (FMI, Nord Pool, simulator adapters) and add retry/timeout handling using `httpx`.
2. Introduce `agents/tests/` (see `docs/testing.md`) to exercise every tool method directly.
3. Swap `BaseMCPAgent.serve()` with the official `openai.resources.mcp` hosting code once the SDK is available, preserving the current interfaces so the backend can continue calling `generate_schedule`, `get_current_system_state`, etc.

This reference ensures every file inside `agents/` has a clear owner, responsibility, and follow-up work item.
