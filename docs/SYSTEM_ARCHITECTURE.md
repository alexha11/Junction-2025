# Complete System Architecture

This document describes the full architecture of the HSY Blominmäki AI Agent Pumping Optimization System.

## High-Level Architecture

```mermaid
flowchart LR
    subgraph Frontend["Frontend Dashboard (React + Vite, :5173)"]
        PanelState[System State Panel]
        PanelForecast[Forecast & Price Cards]
        PanelSchedule[Schedule & Overrides]
        PanelWeather[Weather Widget]
    end

    subgraph Backend["FastAPI Backend (:8000)"]
        API["REST API\\n/system/*, /alerts, /weather/*"]
        AC["AgentsCoordinator\\n+ Services"]
        Scheduler["APScheduler Loop\\n(15 min cadence)"]
        OptimizerCore["Optimizer Interface\\n(in-process OR HTTP)"]
    end

    subgraph Agents["MCP / HTTP Agents"]
        WeatherAgent["Weather Agent\\n(:8101)"]
        PriceAgent["Price Agent\\n(:8102)"]
        InflowAgent["Inflow Agent"]
        StatusAgent["Status Agent"]
        OptimizerAgent["Optimizer Agent\\nHTTP/MCP (:8105)"]
    end

    subgraph Twin["Digital Twin"]
        OPCUA["OPC UA Server\\n(:4840)"]
        MCPBridge["MCP Bridge\\n(:8080)"]
        Historical["Historical Data\\n(Parquet / CSV)"]
    end

    subgraph Data["State, Models & Fallbacks"]
        Postgres[("PostgreSQL\\n(:5432)")]
        Redis[("Redis\\n(:6379)")]
        Samples["sample/*.json\\nDeterministic data"]
        SpotForecast["spot-price-forecast/\\nmodels & scripts"]
    end

    PanelState --> API
    PanelForecast --> API
    PanelSchedule --> API
    PanelWeather --> API
    API --> AC
    Scheduler --> AC
    AC --> OptimizerCore
    OptimizerCore --> OptimizerAgent
    AC --> WeatherAgent
    AC --> PriceAgent
    AC --> InflowAgent
    AC --> StatusAgent
    AC -->|OPC UA read/write| OPCUA
    AC -->|MCP tools| MCPBridge
    MCPBridge --> OPCUA
    OPCUA --> Historical
    Historical --> OPCUA
    AC <-->|state/cache| Postgres
    AC <-->|jobs/cache| Redis
    OptimizerAgent --> SpotForecast
    WeatherAgent --> Samples
    PriceAgent --> Samples
    InflowAgent --> Samples
    AC --> Samples
```

## Component Details

### 1. Frontend Dashboard

- **Technology**: React + Vite + TypeScript
- **Port**: 5173
- **Proxy**: `/api/*` → `http://localhost:8000/*`
- **Components**:
  - System Overview Card (tunnel levels, pumps, flows)
  - Forecast Panel (inflow, price forecasts)
  - Schedule Panel (optimization recommendations)
  - Weather Panel (precipitation, temperature)
  - Alerts Banner (critical warnings)

### 2. Backend API

- **Technology**: FastAPI + Python 3.12+
- **Port**: 8000
- **Key Services**:
  - `AgentsCoordinator`: Orchestrates all agents
  - `OptimizationScheduler`: Background job scheduler
  - `DigitalTwinService`: OPC UA client
  - `DigitalTwinAdapter`: Variable mapping & conversions

### 3. Optimizer Agent (Integrated)

- **Location**: Runs inside backend process
- **Technology**: OR-Tools (SCIP solver) + LLM (optional)
- **Features**:
  - MPC-style optimization (2-hour tactical horizon)
  - Strategic planning (24-hour, LLM-generated)
  - Divergence detection (L1, inflow, price)
  - Emergency response (adaptive constraints/weights)
  - Pump fairness/rotation
  - Multiple objectives (cost, smoothness, safety, efficiency)

### 4. Digital Twin

- **OPC UA Server**: Simulates wastewater system
  - Port: 4840
  - Protocol: OPC UA
  - Data: Historical HSY data (Parquet/CSV)
  - Variables: L1, L2, F1, F2, pump frequencies, prices
- **MCP Server**: Bridge to OPC UA
  - Port: 8080
  - Protocol: MCP (Server-Sent Events)
  - Tools: browse, read, write, history, aggregate

### 5. Weather Agent

- **HTTP Server**: REST API
  - Port: 8101
  - Endpoint: `/weather/forecast`
- **MCP Server**: MCP protocol
  - Port: 8101 (same port, different transport)
  - Tools: `get_precipitation_forecast`, `get_current_weather`, `check_weather_agent_health`
- **Data Source**: OpenWeatherMap API (optional, falls back to sample data)

## Data Flow

### Optimization Flow

```mermaid
sequenceDiagram
    participant Scheduler as Optimization Scheduler
    participant Coordinator as AgentsCoordinator
    participant Optimizer as OptimizationAgent
    participant Backend as Backend API
    participant DigitalTwin as Digital Twin (OPC UA)
    participant Weather as Weather Agent
    participant Price as Price Agent
    participant LLM as LLM (Strategic Planning)
    participant Solver as OR-Tools Solver
    participant Dashboard as Frontend Dashboard

    Note over Scheduler: Every 15 minutes
    Scheduler->>Coordinator: get_schedule_recommendation()
    Coordinator->>Optimizer: generate_schedule()

    Optimizer->>Backend: GET /system/state
    Backend->>DigitalTwin: Read OPC UA variables
    DigitalTwin-->>Backend: System state
    Backend-->>Optimizer: CurrentState

    Optimizer->>Weather: Get weather forecast
    Weather-->>Optimizer: Precipitation data

    Optimizer->>Price: Get price forecast (future)
    Price-->>Optimizer: Price forecast or fallback

    Optimizer->>Optimizer: Estimate inflow (weather-based)

    Optimizer->>LLM: Get strategic plan (cached)
    LLM-->>Optimizer: Strategic plan (24h)

    Optimizer->>Optimizer: Detect divergence
    Optimizer->>Optimizer: Generate emergency response (if needed)

    Optimizer->>Solver: Run MPC optimization
    Solver-->>Optimizer: Schedule + metrics

    Optimizer-->>Coordinator: ScheduleRecommendation
    Coordinator->>Coordinator: Store in _latest_optimization_result

    Coordinator->>DigitalTwin: Write schedule (OPC UA)
    DigitalTwin-->>Coordinator: Confirmation

    Dashboard->>Backend: GET /system/schedule
    Backend-->>Dashboard: Schedule + metrics
```

### System State Flow

```mermaid
sequenceDiagram
    participant Dashboard as Frontend Dashboard
    participant Backend as Backend API
    participant Coordinator as AgentsCoordinator
    participant DigitalTwinSvc as DigitalTwinService
    participant Adapter as DigitalTwinAdapter
    participant OPCUA as OPC UA Server

    Dashboard->>Backend: GET /api/system/state
    Backend->>Coordinator: get_system_state()
    Coordinator->>DigitalTwinSvc: get_digital_twin_current_state()
    DigitalTwinSvc->>OPCUA: Connect opc.tcp://localhost:4840/wastewater/

    Note over OPCUA: Read Variables:
    Note over OPCUA: - WaterLevelInTunnel.L2.m
    Note over OPCUA: - WaterVolumeInTunnel.L1.m3
    Note over OPCUA: - InflowToTunnel.F1.m3per15min
    Note over OPCUA: - SumOfPumpedFlowToWwtp.F2.m3h
    Note over OPCUA: - PumpFrequency.{pump_id}.hz
    Note over OPCUA: - PumpFlow.{pump_id}.m3h
    Note over OPCUA: - ElectricityPrice.2.Normal.ckwh

    OPCUA-->>DigitalTwinSvc: Raw OPC UA values
    DigitalTwinSvc->>Adapter: Convert units & map variables

    Note over Adapter: Conversions:
    Note over Adapter: - m³/h → m³/s
    Note over Adapter: - c/kWh → EUR/MWh
    Note over Adapter: - Volume → Level (L1)
    Note over Adapter: - Flow → Pump state (on/off)

    Adapter-->>DigitalTwinSvc: SystemState model
    DigitalTwinSvc-->>Coordinator: SystemState
    Coordinator-->>Backend: SystemState
    Backend-->>Dashboard: JSON SystemState
    Dashboard->>Dashboard: Display real-time data
```

### Weather Forecast Flow

```mermaid
sequenceDiagram
    participant Dashboard as Frontend Dashboard
    participant Backend as Backend API
    participant Coordinator as AgentsCoordinator
    participant WeatherMCP as Weather MCP Server
    participant WeatherHTTP as Weather HTTP Server
    participant WeatherAgent as Weather Agent
    participant OpenWeather as OpenWeatherMap API
    participant Fallback as Sample Data

    Dashboard->>Backend: POST /api/weather/forecast
    Backend->>Coordinator: get_weather_forecast()

    alt MCP Server enabled
        Coordinator->>WeatherMCP: POST /tools/get_precipitation_forecast
        alt MCP Success
            WeatherMCP->>WeatherAgent: get_precipitation_forecast()
            WeatherAgent->>OpenWeather: API call (if key set)
            alt API Key Available
                OpenWeather-->>WeatherAgent: Live weather data
            else No API Key
                WeatherAgent->>Fallback: Use sample data
                Fallback-->>WeatherAgent: Sample weather
            end
            WeatherAgent-->>WeatherMCP: WeatherPoint[]
            WeatherMCP-->>Coordinator: WeatherPoint[]
        else MCP Fails
            Coordinator->>WeatherHTTP: POST /weather/forecast
            alt HTTP Success
                WeatherHTTP->>WeatherAgent: get_precipitation_forecast()
                WeatherAgent->>OpenWeather: API call (if key set)
                alt API Key Available
                    OpenWeather-->>WeatherAgent: Live weather data
                else No API Key
                    WeatherAgent->>Fallback: Use sample data
                    Fallback-->>WeatherAgent: Sample weather
                end
                WeatherAgent-->>WeatherHTTP: WeatherPoint[]
                WeatherHTTP-->>Coordinator: WeatherPoint[]
            else HTTP Fails
                Coordinator->>Fallback: Use fallback data
                Fallback-->>Coordinator: Sample WeatherPoint[]
            end
        end
    else MCP Disabled
        Coordinator->>WeatherHTTP: POST /weather/forecast
        alt HTTP Success
            WeatherHTTP->>WeatherAgent: get_precipitation_forecast()
            WeatherAgent->>OpenWeather: API call (if key set)
            alt API Key Available
                OpenWeather-->>WeatherAgent: Live weather data
            else No API Key
                WeatherAgent->>Fallback: Use sample data
                Fallback-->>WeatherAgent: Sample weather
            end
            WeatherAgent-->>WeatherHTTP: WeatherPoint[]
            WeatherHTTP-->>Coordinator: WeatherPoint[]
        else HTTP Fails
            Coordinator->>Fallback: Use fallback data
            Fallback-->>Coordinator: Sample WeatherPoint[]
        end
    end

    Coordinator-->>Backend: WeatherPoint[]
    Backend-->>Dashboard: JSON WeatherPoint[]
    Dashboard->>Dashboard: Display forecast
```

## Integration Points

```mermaid
graph TB
    subgraph Frontend["Frontend"]
        FE[React Dashboard]
    end

    subgraph Backend["Backend API"]
        AC[AgentsCoordinator]
        OA[Optimizer Agent<br/>Integrated]
        DT[Digital Twin Service]
        WC[Weather Client]
    end

    subgraph External["External Services"]
        OPCUA[OPC UA Server]
        MCP[MCP Server]
        WA[Weather Agent]
        PA[Price Agent<br/>Future]
    end

    FE -->|HTTP REST<br/>/api/*| AC
    AC -->|Direct call| OA
    AC -->|Read/Write| DT
    AC -->|HTTP/MCP| WC
    DT -->|OPC UA Protocol| OPCUA
    DT -->|HTTP Tool Calls| MCP
    WC -->|HTTP/MCP| WA
    OA -.->|HTTP| PA
    OA -->|GET /system/state| AC
    OA -->|GET /weather/forecast| AC

    style Frontend fill:#e1f5ff
    style Backend fill:#fff4e1
    style External fill:#e8f5e9
```

### Backend ↔ Digital Twin

- **Read**: OPC UA Client → Read variables → Convert units → SystemState
- **Write**: Schedule → Convert pump IDs → Write frequencies to OPC UA
- **History**: MCP Server → Aggregate variables → Return statistics

### Backend ↔ Weather Agent

- **Primary**: HTTP endpoint (`/weather/forecast`)
- **Optional**: MCP tools (`/tools/get_precipitation_forecast`)
- **Fallback**: Sample JSON data

### Backend ↔ Optimizer Agent

- **Integrated**: Runs in same process
- **Direct calls**: `optimizer_agent.generate_schedule()`
- **Data sources**: Backend endpoints (digital twin, weather)

### Frontend ↔ Backend

- **Proxy**: Vite dev server proxies `/api/*` to `http://localhost:8000/*`
- **CORS**: Enabled for `localhost:5173` and `localhost:3000`
- **Endpoints**: All `/system/*` and `/weather/*` routes

## Configuration

### Backend Configuration (`backend/.env`)

```bash
# Digital Twin
DIGITAL_TWIN_OPCUA_URL=opc.tcp://localhost:4840/wastewater/
DIGITAL_TWIN_MCP_URL=http://localhost:8080
USE_DIGITAL_TWIN=true

# Weather Agent
USE_WEATHER_AGENT=true
WEATHER_AGENT_URL=http://localhost:8101
WEATHER_AGENT_MCP_URL=http://localhost:8101
USE_WEATHER_MCP=true
WEATHER_AGENT_LOCATION=Helsinki
OPENWEATHER_API_KEY=your-key-here

# Optimizer
OPTIMIZER_INTERVAL_MINUTES=15
BACKEND_URL=http://localhost:8000

# Scheduler
OPTIMIZER_INTERVAL_MINUTES=15
```

### Frontend Configuration (`frontend/.env.local`)

```bash
VITE_WEATHER_AGENT_URL=http://localhost:8000/weather/forecast
```

## Deployment Architecture

### Development (Local)

```mermaid
graph LR
    Frontend[Frontend<br/>Vite<br/>:5173] -->|HTTP| Backend[Backend<br/>FastAPI<br/>:8000]
    Backend -->|OPC UA| DigitalTwin[Digital Twin<br/>OPC UA<br/>:4840]
    Backend -->|HTTP/MCP| Weather[Weather Agent<br/>:8101]
    Backend -.->|Integrated| Optimizer[Optimizer Agent<br/>in-process]

    style Frontend fill:#e1f5ff
    style Backend fill:#fff4e1
    style DigitalTwin fill:#e8f5e9
    style Weather fill:#f3e5f5
    style Optimizer fill:#fff9c4
```

### Production (Docker Compose)

```mermaid
graph TB
    subgraph Docker["Docker Compose Network"]
        Frontend[Frontend<br/>Nginx]
        Backend[Backend<br/>Uvicorn]
        Postgres[Postgres]
        Redis[Redis]

        Frontend --> Backend
        Backend --> Postgres
        Backend --> Redis
    end

    Docker -->|OPC UA| DigitalTwin[Digital Twin<br/>OPC UA Server]
    Docker -->|HTTP/MCP| WeatherAgent[Weather Agent<br/>HTTP/MCP Server]

    style Docker fill:#e3f2fd
    style DigitalTwin fill:#e8f5e9
    style WeatherAgent fill:#f3e5f5
```

## Technology Stack

### Frontend

- React 18
- Vite
- TypeScript
- React Query (data fetching)
- Tailwind CSS
- Recharts (visualization)

### Backend

- FastAPI
- Python 3.12+
- APScheduler (background jobs)
- Pydantic (data validation)
- httpx (HTTP client)
- opcua (OPC UA client)

### Optimizer Agent

- OR-Tools (SCIP solver)
- NumPy, Pandas (data processing)
- LLM (optional, for strategic planning)

### Digital Twin

- OPC UA Server (python-opcua)
- MCP Server (FastMCP)
- SQLite (historical data storage)
- Pandas (data processing)

### Weather Agent

- FastAPI (HTTP server)
- FastMCP (MCP server)
- httpx (OpenWeatherMap client)

## Data Models

### SystemState

```python
{
  "timestamp": datetime,
  "tunnel_level_m": float,        # L1 (from volume)
  "tunnel_level_l2_m": float,     # L2
  "tunnel_water_volume_l1_m3": float,
  "inflow_m3_s": float,           # F1
  "outflow_m3_s": float,           # F2
  "electricity_price_eur_mwh": float,
  "pumps": [
    {
      "pump_id": "1.1",
      "state": "on" | "off",
      "frequency_hz": float,
      "power_kw": float
    }
  ]
}
```

### ScheduleRecommendation

```python
{
  "generated_at": datetime,
  "horizon_minutes": int,
  "entries": [
    {
      "pump_id": "1.1",
      "target_frequency_hz": float,
      "start_time": datetime,
      "end_time": datetime
    }
  ],
  "justification": str
}
```

### OptimizationMetrics

```python
{
  "generated_at": str,
  "total_cost_eur": float,
  "total_energy_kwh": float,
  "optimization_mode": "full" | "safety" | "cost",
  "horizon_minutes": int
}
```

## Communication Protocols

### HTTP REST API

- **Backend ↔ Frontend**: JSON over HTTP
- **Backend ↔ Weather Agent**: JSON over HTTP
- **Backend ↔ Digital Twin MCP**: JSON over HTTP (tool calls)

### OPC UA

- **Backend ↔ Digital Twin**: OPC UA protocol
- **Variables**: Read/Write operations
- **History**: Historical data queries

### MCP (Model Context Protocol)

- **Digital Twin MCP Server**: SSE transport
- **Weather Agent MCP Server**: SSE transport
- **Tool-based**: Browse, read, write, aggregate operations

## Error Handling & Fallbacks

### Digital Twin Unavailable

1. Backend logs warning
2. Falls back to synthetic system state
3. Dashboard still works (shows stub data)

### Weather Agent Unavailable

1. Backend tries MCP, then HTTP
2. Falls back to sample weather data
3. Optimization continues (uses fallback forecasts)

### Optimizer Agent Unavailable

1. Backend logs warning
2. Falls back to stub schedule
3. Dashboard still works (shows stub schedule)

### Network Failures

- All HTTP calls have timeouts
- Graceful degradation at each layer
- Logging for debugging

## Security Considerations

- **CORS**: Configured for development (localhost only)
- **API Keys**: Environment variables (not in code)
- **OPC UA**: Local network only (not exposed externally)
- **Validation**: Pydantic models validate all inputs

## Performance

- **Optimization**: Runs every 15 minutes (configurable)
- **State Updates**: Dashboard polls every 30 seconds
- **Forecasts**: Cached for 5 minutes
- **Strategic Plan**: Cached for 1 hour (if forecasts stable)

## Future Extensions

- **Price Agent**: Integrate Nord Pool API
- **Inflow Agent**: Enhance with ML models
- **Electricity Agent**: Real-time grid data
- **WebSocket**: Real-time updates (replace polling)
- **Persistence**: Store schedules in Postgres
- **Analytics**: Historical optimization performance
