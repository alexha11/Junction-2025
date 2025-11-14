# Product Requirements Document (PRD)

## Title: HSY Blominmäki AI Agent Pumping Optimization System

---

## 1. Introduction

### 1.1 Problem Statement

The Blominmäki wastewater treatment plant's pumping process is a significant operational expense, driven by high and volatile energy costs. Optimizing pump schedules is a complex multivariate problem, requiring the system to balance:

- **Variable wastewater inflow (F1)**, influenced by daily cycles and weather.
- **Fluctuating electricity prices.**
- **Complex physical constraints of the pumps** (efficiency, start/stop frequency).
- **Strict operational boundaries** (tunnel levels, stable outflow).

Manually (or with simple logic) optimizing these variables in real-time is inefficient and leads to unnecessary energy expenditure.

### 1.2 Goal & Vision

- **Goal:** Develop an AI-driven "copilot" system that provides real-time, cost-optimal pump control schedules to plant operators.
- **Vision:** A modular, intelligent multi-agent system that minimizes total energy cost (kWh \* price) while guaranteeing adherence to all operational and safety constraints. The system will serve as an advisory dashboard for operators, building trust through reliable, explainable recommendations.

### 1.3 Target Users

- **Plant Operator (Primary):** Needs a simple, clear interface to monitor the plant's state, see the AI's recommendation, and understand why a schedule is proposed.
- **System Engineer:** Needs to monitor agent health, data source integrity, and overall system performance.

---

## 2. System Architecture

The system will be built using a modern, decoupled architecture:

- **Frontend:** React web application providing the operator dashboard.
- **Backend:** Python (e.g., FastAPI) application serving a REST API for the frontend and orchestrating the agent system.
- **Agent Framework:** OpenAI Agents SDK (Python) to build, manage, and orchestrate the agents.
- **Agent Communication:** Agents expose capabilities as "tools" using the Model Context Protocol (MCP). Each specialized agent runs as its own microservice, exposing MCP-compatible interfaces.
- **Coordinating Agent:** Central "Optimization Agent" consumes MCP tools from specialized agents to gather data and make decisions.
- **Data Sources:**
  - **External APIs:** Weather forecasts (FMI), electricity prices (Nord Pool).
  - **Internal Data:** HSY historical data (CSV/Excel) for model training.
  - **Simulation:** Python-based simulation environment providing real-time data (L1, F1, etc.).

---

## 3. Functional Requirements

### FR1: React Operator Dashboard

- **System Overview:** Real-time visualization of key metrics:
  - Tunnel Water Level (L1) (min/max boundaries)
  - Current Wastewater Inflow (F1)
  - Total Pumped Outflow (F2)
  - Current Electricity Price
  - Status of all 8 pumps (On/Off, Frequency Hz, Power kW)
- **Forecast Panel:** 12-hour lookahead showing:
  - Predicted Inflow (F1)
  - Predicted Electricity Price
- **AI Recommendation Panel:** Displays AI's recommended schedule for the next 1-2 hours (e.g., "Run Pump 1.1 at 48 Hz, Stop Pump 1.2"). Provides human-readable justification.
- **Alerts:** Persistent banner for critical alerts (e.g., "High risk of L1 max breach in 2 hours").
- **Manual Override:** Operator can reject AI recommendations and log a reason.

### FR2: AI Agent System (Backend)

**Core system built with OpenAI Agents SDK.**

- **Agent 1: Weather Agent**

  - Purpose: Provide accurate weather data.
  - Function: `get_precipitation_forecast(lookahead_hours: int) -> list[dict]`
  - Details: Fetches precipitation and temperature forecasts from FMI.
  - Interface: Exposes as MCP tool.

- **Agent 2: Electricity Price Agent**

  - Purpose: Provide real-time and forecasted electricity prices.
  - Function: `get_electricity_price_forecast(lookahead_hours: int) -> list[dict]`
  - Details: Fetches current and forecasted spot prices from Nord Pool.
  - Interface: Exposes as MCP tool.

- **Agent 3: System Status & Physics Agent**

  - Purpose: Provide current state and physical constraints of the plant.
  - Functions:
    - `get_current_system_state() -> dict` — Returns latest values for L1, F1, F2, and pump status.
    - `get_tunnel_volume(level: float) -> float` — Calculates tunnel volume.
    - `get_pump_efficiency(pump_id: str, flow: float, head: float) -> float` — Calculates pump efficiency.
  - Interface: All functions as MCP tools.

- **Agent 4: Inflow Forecast Agent**

  - Purpose: Predict near-term wastewater inflow (F1).
  - Function: `predict_inflow(weather_data: list, lookahead_hours: int) -> list[dict]`
  - Details: Simple ML/statistical model trained on Hackathon_HSY_data.csv.
  - Interface: Exposes as MCP tool.

- **Agent 5: Optimization Agent (Coordinator)**
  - Purpose: Central "brain," orchestrates other agents to create optimal pump schedule.
  - Workflow (every 15 min):
    1. **Context Gathering:** Calls tools from other agents:
       - `get_current_system_state()`
       - `get_precipitation_forecast(lookahead_hours=12)`
       - `get_electricity_price_forecast(lookahead_hours=12)`
    2. **Prediction:** Calls `predict_inflow()` using weather data.
    3. **Reasoning & Optimization:** LLM analyzes dataset to find the best schedule. Constraints include:
       - Minimize total cost (Power_kW \* Price_EUR/kWh)
       - Keep L1 between 0.5m and 8m
       - Stable F2 outflow
       - Pumps must not stop entirely
       - Pumps must not start/stop frequently (<2h interval)
       - Operate pumps near full speed (>47.5 Hz)
       - Perform daily tunnel flush during low inflow
    4. **Output:** JSON with recommended pump schedule and justification.

### FR3: Simulation Integration

- System Status Agent reads data from simulator.
- Optimization Agent's schedule is fed into simulator to validate performance and ensure no constraint breaches.

---

## 4. Non-Functional Requirements

- **Performance:** Optimization Agent must return schedule within 2 minutes.
- **Reliability:** Agents calling external APIs must have robust error handling, retries, and fallback logic.
- **Modularity:** MCP architecture must allow adding new agents without re-architecting the system.
- **Security:** API keys and credentials stored securely (environment variables, secrets manager).

---

## 5. Out of Scope (v1)

- Direct hardware control (system is advisory-only).
- User authentication (internal use on trusted network).
- Complex ML training (inflow agent uses simple model; deep learning out of scope).

---

## 6. Success Metrics

- **Primary:** X% reduction in simulated energy cost over a 14-day test period compared to baseline logic.
- **Constraint Adherence:** Zero critical constraint breaches (e.g., L1 > 8m).
- **Qualitative:** Operator feedback indicates AI recommendations are "trustworthy, understandable, and useful."
