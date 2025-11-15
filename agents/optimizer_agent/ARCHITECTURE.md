# Optimizer Agent Architecture

## System Overview

```mermaid
graph TB
    subgraph "External Data Sources"
        BACKEND[Backend API<br/>FastAPI :8000]
        DIGITALTWIN[Digital Twin<br/>OPC UA :4840]
        WEATHER[Weather Agent<br/>HTTP/MCP :8101]
        PRICE[Price Agent<br/>Future]
        BACKEND --> DIGITALTWIN
        BACKEND --> WEATHER
        BACKEND -.-> PRICE
    end

    subgraph "Data Layer"
        DATA[Historical Data<br/>Hackathon_HSY_data.xlsx]
        LOADER[HSYDataLoader<br/>test_data_loader.py]
        DATA --> LOADER
    end

    subgraph "Core Optimizer"
        OPT[MPCOptimizer<br/>optimizer.py]
        PUMP[PumpSpec<br/>Pump Specifications]
        CONST[SystemConstraints<br/>Hard/Soft Constraints]
        PUMP --> OPT
        CONST --> OPT
    end

    subgraph "Optimization Process"
        SOLVER[OR-Tools Solver<br/>SCIP Linear Programming]
        FULL[Full Optimization<br/>Dual Horizon MPC]
        SIMPLE[Simplified Optimization<br/>Fallback]
        RULE[Rule-Based<br/>Fallback]
        OPT --> SOLVER
        SOLVER --> FULL
        SOLVER --> SIMPLE
        SOLVER --> RULE
    end

    subgraph "LLM Integration"
        EXPLAINER[LLMExplainer<br/>explainability.py]
        FEATHERLESS[Featherless API<br/>Llama 3.1 8B Instruct]
        STRATPLAN[Strategic Plan<br/>24h Strategy Generation]
        EXPLANATION[Explanation<br/>Schedule Interpretation]
        EXPLAINER --> STRATPLAN
        EXPLAINER --> EXPLANATION
        STRATPLAN --> FEATHERLESS
        EXPLANATION --> FEATHERLESS
    end

    subgraph "Agent Interface"
        AGENT[OptimizationAgent<br/>main.py]
        MCP[BaseMCPAgent<br/>Common Framework]
        DIVERGENCE[Divergence Detection<br/>L1, Inflow, Price]
        EMERGENCY[Emergency Response<br/>Adaptive Constraints]
        AGENT --> MCP
        AGENT --> OPT
        AGENT --> EXPLAINER
        AGENT --> DIVERGENCE
        AGENT --> EMERGENCY
    end

    subgraph "State Management"
        STATETRACK[State Tracking<br/>Previous Predictions]
        CACHE[Strategic Plan Cache<br/>TTL-based]
        STATETRACK --> AGENT
        CACHE --> AGENT
    end

    subgraph "Testing & Simulation"
        SIM[RollingMPCSimulator<br/>test_simulator.py]
        METRICS[MetricsCalculator<br/>test_metrics.py]
        TEST[test_optimizer_with_data.py<br/>Main Test Script]
        SIM --> OPT
        SIM --> EXPLAINER
        METRICS --> SIM
        TEST --> SIM
        TEST --> METRICS
        TEST --> LOADER
    end

    AGENT -->|GET /system/state| BACKEND
    AGENT -->|GET /weather/forecast| BACKEND
    AGENT -->|POST /system/schedule| BACKEND
    LOADER --> SIM
    FULL --> AGENT
```

## Optimization Flow

```mermaid
sequenceDiagram
    participant User/Backend
    participant Agent as OptimizationAgent
    participant Backend as Backend API
    participant DigitalTwin as Digital Twin
    participant Weather as Weather Agent
    participant LLM as LLM Explainer
    participant Featherless as Featherless API
    participant Optimizer as MPC Optimizer
    participant Solver as OR-Tools Solver

    User/Backend->>Agent: generate_schedule(request)
    
    Note over Agent: Data Gathering Phase
    Agent->>Backend: GET /system/state
    Backend->>DigitalTwin: Read OPC UA variables
    DigitalTwin-->>Backend: System state
    Backend-->>Agent: CurrentState
    
    Agent->>Backend: GET /weather/forecast
    Backend->>Weather: Get precipitation forecast
    Weather-->>Backend: Weather forecast
    Backend-->>Agent: Weather data
    
    Agent->>Agent: Get price forecast (fallback or future agent)
    Agent->>Agent: Estimate inflow (weather-based if needed)
    
    Note over Agent: Divergence Detection
    Agent->>Agent: Detect divergence (L1, inflow, price)
    alt Divergence Detected
        Agent->>LLM: generate_emergency_response()
        LLM->>Featherless: API Call (Emergency)
        Featherless-->>LLM: Emergency adjustments
        LLM-->>Agent: Constraint/weight adjustments
    end
    
    Note over Agent: Strategic Planning
    alt Strategic Plan Cached & Valid
        Agent->>Agent: Use cached strategic plan
    else Need New Strategic Plan
        alt LLM Available
            Agent->>LLM: generate_strategic_plan(24h forecast)
            LLM->>Featherless: API Call (Strategic Planning)
            Featherless-->>LLM: StrategicPlan
            LLM-->>Agent: StrategicPlan
            Agent->>Agent: Cache strategic plan
        else LLM Unavailable
            Agent->>Agent: Use Algorithmic Guidance
        end
    end
    
    Note over Agent: Optimization Phase
    Agent->>Optimizer: solve_optimization(strategic_plan, emergency_response)
    Optimizer->>Solver: Solve (24h strategic + 2h tactical)
    Solver-->>Optimizer: Optimization Result
    Optimizer-->>Agent: Result (success/failure)
    
    Note over Agent: Post-Processing
    Agent->>Agent: Compute Metrics
    Agent->>Agent: Update state tracking
    
    alt LLM Available (Explanation)
        Agent->>LLM: generate_explanation(strategic_plan, metrics)
        LLM->>Featherless: API Call (Explanation)
        Featherless-->>LLM: Explanation Text
        LLM-->>Agent: Explanation
    else LLM Unavailable
        Agent->>Agent: Fallback Explanation
    end
    
    Note over Agent: Schedule Writing
    Agent->>Backend: POST /system/schedule
    Backend->>DigitalTwin: Write pump frequencies
    DigitalTwin-->>Backend: Confirmation
    Backend-->>Agent: Success
    
    Agent-->>User/Backend: OptimizationResponse
```

## Rolling MPC Simulation Flow

```mermaid
flowchart TD
    START[Start Simulation] --> INIT[Initialize Simulator<br/>with LLM Explainer]
    INIT --> LOOP{More Time Steps?}
    
    LOOP -->|Yes| GETSTATE[Get Current State<br/>from Historical Data]
    GETSTATE --> GET24H[Get 24h Forecast<br/>Perfect/Persistence]
    
    GET24H --> LLMSTRAT{LLM Enabled?}
    LLMSTRAT -->|Yes| GENPLAN[Generate Strategic Plan<br/>24h LLM Strategy]
    LLMSTRAT -->|No| ALGO[Algorithmic Guidance]
    
    GENPLAN --> GET2H[Get 2h Tactical Forecast]
    ALGO --> GET2H
    
    GET2H --> OPTIMIZE[Run Optimization<br/>solve_optimization with strategic_plan]
    
    OPTIMIZE --> CHECK{Success?}
    CHECK -->|Yes| RESULT1[Store Result]
    CHECK -->|No| FALLBACK[Try Fallback Mode]
    FALLBACK --> RESULT1
    
    RESULT1 --> LLMEXPL{LLM Enabled?}
    LLMEXPL -->|Yes| COMPUTE[Compute Step Metrics]
    COMPUTE --> CALLEXPL[Call LLM API<br/>Generate Explanation]
    CALLEXPL --> STORE[Store Explanation & Strategy]
    
    LLMEXPL -->|No| SKIP[Skip Explanation]
    STORE --> UPDATE[Update L1 Trajectory]
    SKIP --> UPDATE
    
    UPDATE --> ADVANCE[Advance Time<br/>+15 minutes]
    ADVANCE --> LOOP
    
    LOOP -->|No| COMPARE[Compare with Baseline]
    COMPARE --> METRICS[Calculate Metrics]
    METRICS --> SUMMARY{LLM for Summary?}
    SUMMARY -->|Yes| SUMMARYLLM[Generate Summary<br/>Explanation]
    SUMMARY -->|No| REPORT
    SUMMARYLLM --> REPORT[Generate Report]
    REPORT --> END[End]
```

## Component Relationships

```mermaid
graph LR
    subgraph "Configuration"
        ENV[.env File<br/>API Keys & Model]
        CONFIG[config.py<br/>Backend Config]
    end

    subgraph "Data Processing"
        LOADER[HSYDataLoader]
        STATE[CurrentState]
        FORECAST[ForecastData]
        LOADER --> STATE
        LOADER --> FORECAST
    end

    subgraph "Optimization Core"
        OPT[MPCOptimizer]
        PUMP1[PumpSpec P1]
        PUMP2[PumpSpec P2]
        CONST[SystemConstraints]
        RESULT[OptimizationResult]
        OPT --> PUMP1
        OPT --> PUMP2
        OPT --> CONST
        OPT --> RESULT
    end

    subgraph "Explainability"
        EXPLAINER[LLMExplainer]
        METRICS[ScheduleMetrics]
        EXPLAINER --> METRICS
        ENV --> EXPLAINER
    end

    subgraph "Agent Interface"
        AGENT[OptimizationAgent]
        REQUEST[OptimizationRequest]
        RESPONSE[OptimizationResponse]
        BACKEND_CLIENT[Backend HTTP Client]
        AGENT --> REQUEST
        AGENT --> RESPONSE
        AGENT --> BACKEND_CLIENT
    end
    
    subgraph "External Services"
        BACKEND_API[Backend API<br/>:8000]
        DIGITALTWIN_SVC[Digital Twin<br/>OPC UA :4840]
        WEATHER_SVC[Weather Agent<br/>:8101]
        BACKEND_API --> DIGITALTWIN_SVC
        BACKEND_API --> WEATHER_SVC
    end

    subgraph "Testing"
        SIM[RollingMPCSimulator]
        SIMRESULT[SimulationResult]
        SIM --> SIMRESULT
        CALC[MetricsCalculator]
        REPORT[ComparisonReport]
        CALC --> REPORT
    end

    STATE --> OPT
    FORECAST --> OPT
    EXPLAINER --> STRATPLAN[StrategicPlan<br/>24h Strategy]
    STRATPLAN --> OPT
    RESULT --> EXPLAINER
    RESULT --> AGENT
    EXPLAINER --> RESPONSE
    
    BACKEND_CLIENT --> BACKEND_API
    BACKEND_API --> STATE
    BACKEND_API --> FORECAST
    
    LOADER --> SIM
    OPT --> SIM
    EXPLAINER --> SIM
    SIM --> CALC
```

## Data Structures

```mermaid
classDiagram
    class CurrentState {
        +float l1_m
        +float inflow_m3_s
        +float outflow_m3_s
        +float price_c_per_kwh
    }
    
    class ForecastData {
        +List[datetime] timestamps
        +List[float] inflow_m3_s
        +List[float] price_c_per_kwh
        +int horizon_steps
    }
    
    class PumpSpec {
        +str pump_id
        +float max_flow_m3_s
        +float max_power_kw
        +float min_frequency_hz
        +float max_frequency_hz
    }
    
    class SystemConstraints {
        +float l1_min_m
        +float l1_max_m
        +float tunnel_volume_m3
        +int min_pumps_on
        +bool allow_l1_violations
        +float l1_violation_tolerance_m
    }
    
    class OptimizationResult {
        +bool success
        +OptimizationMode mode
        +List[PumpSchedule] schedules
        +List[float] l1_trajectory
        +float total_cost_eur
        +float total_energy_kwh
        +int l1_violations
        +float max_violation_m
    }
    
    class StrategicPlan {
        +str plan_type
        +str description
        +List[tuple] time_periods
        +str reasoning
        +Optional[dict] recommended_weights
    }
    
    class ScheduleMetrics {
        +float total_energy_kwh
        +float total_cost_eur
        +float avg_l1_m
        +float min_l1_m
        +float max_l1_m
        +int num_pumps_used
        +str risk_level
        +str optimization_mode
    }
    
    class SimulationResult {
        +datetime timestamp
        +CurrentState current_state
        +OptimizationResult optimization_result
        +dict baseline_schedule
        +Optional[StrategicPlan] strategic_plan
        +str explanation
        +str strategy
    }
    
    CurrentState --> OptimizationResult
    ForecastData --> OptimizationResult
    PumpSpec --> OptimizationResult
    SystemConstraints --> OptimizationResult
    StrategicPlan --> OptimizationResult
    OptimizationResult --> ScheduleMetrics
    OptimizationResult --> SimulationResult
    StrategicPlan --> SimulationResult
    ScheduleMetrics --> SimulationResult
```

## File Structure

```
optimizer_agent/
├── main.py                    # OptimizationAgent (Integrated with Backend)
│                              # - Backend integration (HTTP client)
│                              # - Digital twin state reading
│                              # - Weather agent integration
│                              # - Divergence detection
│                              # - Emergency response
│                              # - State tracking
│                              # - Schedule writing to digital twin
├── optimizer.py               # MPCOptimizer (Core Optimization Engine)
│                              # - Dual-horizon MPC (24h strategic + 2h tactical)
│                              # - Pump fairness/rotation
│                              # - Multiple objectives (cost, smoothness, safety)
│                              # - Fallback modes (simplified, rule-based)
├── explainability.py          # LLMExplainer (Featherless Integration)
│                              # - Strategic plan generation (24h)
│                              # - Schedule explanation
│                              # - Emergency response generation
│
├── test_data_loader.py        # HSYDataLoader (Historical Data Loading)
├── test_simulator.py          # RollingMPCSimulator (MPC Simulation)
│                              # - Divergence detection in simulation
│                              # - Emergency response testing
├── test_metrics.py            # MetricsCalculator (Performance Metrics)
├── test_optimizer_with_data.py # Main Test Script
│
├── .env                       # Agent Configuration (API Keys)
├── ARCHITECTURE.md            # This file
├── ALL_CONSTRAINTS.md          # Complete constraints documentation
├── CONSTRAINTS_INVENTORY.md    # Constraints inventory
└── ARCHITECTURE_TREE.txt      # Component tree structure
```

## Optimization Modes

```mermaid
stateDiagram-v2
    [*] --> ReceiveRequest
    
    ReceiveRequest --> GetStateForecast: Gather Data
    GetStateForecast --> TryFullOptimization: Attempt Optimization
    
    TryFullOptimization --> Success: Solved Successfully
    TryFullOptimization --> Timeout: Timeout/Error
    TryFullOptimization --> Infeasible: No Solution
    
    Timeout --> TrySimplified: Fallback Strategy
    Infeasible --> TrySimplified: Fallback Strategy
    
    TrySimplified --> Success: Solved Successfully
    TrySimplified --> Fail: Still Failed
    
    Fail --> UseRuleBased: Last Resort
    
    UseRuleBased --> Success: Always Works
    
    Success --> GenerateExplanation: Generate LLM Explanation
    GenerateExplanation --> ReturnResponse: Complete
    
    ReturnResponse --> [*]
```

## LLM Strategic Plan Flow

```mermaid
flowchart TD
    START[Before Optimization] --> GET24H[Get 24h Forecast<br/>Inflow & Price]
    GET24H --> CHECK{LLM Configured?}
    
    CHECK -->|No| ALGO[Use Algorithmic<br/>Strategic Guidance]
    
    CHECK -->|Yes| BUILDPLAN[Build Strategic Plan Prompt<br/>24h Forecast + Current L1]
    BUILDPLAN --> CALLPLAN[Call Featherless API<br/>Strategic Planning]
    
    CALLPLAN --> SUCCESS{API Success?}
    SUCCESS -->|Yes| PARSE[Parse StrategicPlan<br/>Type, Periods, Reasoning]
    SUCCESS -->|No| ERROR{Error Type?}
    
    ERROR -->|Timeout| TIMEOUT[Log Timeout<br/>Use Algorithmic]
    ERROR -->|HTTP Error| HTTP[Log HTTP Error<br/>Use Algorithmic]
    ERROR -->|Other| OTHER[Log Error<br/>Use Algorithmic]
    
    TIMEOUT --> ALGO
    HTTP --> ALGO
    OTHER --> ALGO
    
    PARSE --> ADJUST[Adjust Optimization Weights<br/>Based on Strategy]
    ALGO --> ADJUST
    ADJUST --> OPTIMIZE[Run Optimization<br/>with Strategic Guidance]
    
    style START fill:#e1f5ff
    style OPTIMIZE fill:#d4edda
    style ALGO fill:#fff3cd
    style PARSE fill:#d1ecf1
```

## LLM Explanation Flow

```mermaid
flowchart TD
    START[Optimization Complete] --> CHECK{LLM Configured?}
    
    CHECK -->|No| FALLBACK[Generate Fallback<br/>Rule-Based Explanation]
    
    CHECK -->|Yes| BUILD[Build Prompt<br/>with Metrics, Strategy & StrategicPlan]
    BUILD --> CALL[Call Featherless API<br/>Explanation Generation]
    
    CALL --> SUCCESS{API Success?}
    SUCCESS -->|Yes| RETURN[Return LLM Explanation]
    SUCCESS -->|No| ERROR{Error Type?}
    
    ERROR -->|Timeout| TIMEOUT[Log Timeout<br/>Use Fallback]
    ERROR -->|HTTP Error| HTTP[Log HTTP Error<br/>Use Fallback]
    ERROR -->|Other| OTHER[Log Error<br/>Use Fallback]
    
    TIMEOUT --> FALLBACK
    HTTP --> FALLBACK
    OTHER --> FALLBACK
    
    RETURN --> END[Explanation Ready]
    FALLBACK --> END
    
    style START fill:#e1f5ff
    style END fill:#d4edda
    style FALLBACK fill:#fff3cd
    style RETURN fill:#d1ecf1
```

## State Tracking & Caching

```mermaid
graph LR
    subgraph "State Tracking"
        PREV_STATE[Previous Prediction<br/>L1, inflow, price]
        PREV_FORECAST[Previous Forecast<br/>Hash-based validation]
        TIMESTAMP[Last Update Timestamp]
        TTL[State TTL<br/>30 minutes]
    end
    
    subgraph "Strategic Plan Cache"
        CACHED_PLAN[Cached Strategic Plan]
        PLAN_HASH[Forecast Hash]
        PLAN_TIMESTAMP[Plan Timestamp]
        PLAN_TTL[Plan TTL<br/>60 minutes]
    end
    
    subgraph "Cache Logic"
        CHECK_HASH{Forecast Hash<br/>Changed?}
        CHECK_TTL{Within TTL?}
        INVALIDATE[Invalidate Cache]
        USE_CACHE[Use Cached Plan]
    end
    
    PREV_STATE --> CHECK_HASH
    PREV_FORECAST --> CHECK_HASH
    PLAN_HASH --> CHECK_HASH
    
    CHECK_HASH -->|No Change| CHECK_TTL
    CHECK_HASH -->|Changed| INVALIDATE
    
    CHECK_TTL -->|Valid| USE_CACHE
    CHECK_TTL -->|Expired| INVALIDATE
    
    INVALIDATE --> LLM[Generate New Plan]
    USE_CACHE --> OPT[Use Cached Plan]
    
    style USE_CACHE fill:#d4edda
    style INVALIDATE fill:#ffebee
    style LLM fill:#e1f5ff
```

## Constraint Hierarchy

```mermaid
graph TD
    subgraph "Hard Constraints"
        H1[L1 Min/Max Bounds<br/>0.0m - 8.0m]
        H2[Pump Min Frequency<br/>47.8 Hz]
        H3[Min Pumps On<br/>At least 1 pump]
        H4[Min On/Off Duration<br/>120 minutes]
    end
    
    subgraph "Soft Constraints (with Violations)"
        S1[L1 Violation Tolerance<br/>±0.5m with Penalty]
        S2[Outflow Smoothness<br/>Minimize Variance]
    end
    
    subgraph "Strategic Guidance"
        ST1[LLM Strategic Plan<br/>24h Strategy Type]
        ST2[Time Period Strategies<br/>Per-Hour Guidance]
        ST3[Weight Adjustment<br/>Cost/Energy/Smoothness]
        ST1 --> ST2
        ST2 --> ST3
    end
    
    subgraph "Objectives"
        O1[Minimize Cost<br/>Energy × Price]
        O2[Minimize Energy<br/>Total kWh]
        O3[Minimize Violations<br/>L1 Penalty]
        O4[Maximize Efficiency<br/>Specific Energy]
    O5[Pump Fairness<br/>Rotation/Runtime Balance]
    end
    
    H1 --> OPT[Optimizer]
    H2 --> OPT
    H3 --> OPT
    H4 --> OPT
    
    S1 --> OPT
    S2 --> OPT
    
    ST3 --> OPT
    O1 --> OPT
    O2 --> OPT
    O3 --> OPT
    O4 --> OPT
    O5 --> OPT
```

## Integration Architecture

```mermaid
graph TB
    subgraph "Production Mode (Backend Integration)"
        BACKEND[Backend API<br/>FastAPI :8000]
        COORD[AgentsCoordinator]
        AGENT_PROD[OptimizationAgent<br/>Integrated]
        COORD --> AGENT_PROD
        BACKEND --> COORD
    end
    
    subgraph "Standalone Mode (Testing)"
        AGENT_STAND[OptimizationAgent<br/>Standalone]
        MCP_DIRECT[Direct MCP Access<br/>Optional]
        AGENT_STAND -.-> MCP_DIRECT
    end
    
    subgraph "Data Sources"
        DT[Digital Twin<br/>OPC UA :4840]
        WA[Weather Agent<br/>:8101]
        PA[Price Agent<br/>Future]
        HIST[Historical Data<br/>For Testing]
    end
    
    AGENT_PROD -->|GET /system/state| BACKEND
    AGENT_PROD -->|GET /weather/forecast| BACKEND
    AGENT_PROD -->|POST /system/schedule| BACKEND
    BACKEND --> DT
    BACKEND --> WA
    BACKEND -.-> PA
    
    AGENT_STAND -->|Direct OPC UA| DT
    AGENT_STAND -->|HTTP/MCP| WA
    AGENT_STAND --> HIST
    
    style BACKEND fill:#fff4e1
    style AGENT_PROD fill:#d4edda
    style AGENT_STAND fill:#fff3cd
    style DT fill:#e8f5e9
    style WA fill:#f3e5f5
```

## Divergence Detection & Emergency Response

```mermaid
flowchart TD
    START[Optimization Cycle] --> GETSTATE[Get Current State]
    GETSTATE --> CHECK{Previous State<br/>Exists?}
    
    CHECK -->|No| SKIP[Skip Divergence Check<br/>Store Current State]
    CHECK -->|Yes| COMPARE[Compare Current vs Previous]
    
    COMPARE --> L1_CHECK{L1 Divergence?<br/>|L1_current - L1_predicted| > threshold}
    COMPARE --> INFLOW_CHECK{Inflow Divergence?<br/>|inflow_current - inflow_forecast| > threshold}
    COMPARE --> PRICE_CHECK{Price Divergence?<br/>|price_current - price_forecast| > threshold}
    
    L1_CHECK -->|Yes| DIVERGENCE[Divergence Detected]
    INFLOW_CHECK -->|Yes| DIVERGENCE
    PRICE_CHECK -->|Yes| DIVERGENCE
    
    DIVERGENCE --> LLM_CHECK{LLM Available?}
    LLM_CHECK -->|Yes| EMERGENCY[Generate Emergency Response<br/>via LLM]
    LLM_CHECK -->|No| ALGO[Algorithmic Emergency Response]
    
    EMERGENCY --> ADJUST[Adjust Constraints/Weights]
    ALGO --> ADJUST
    
    ADJUST --> OPTIMIZE[Run Optimization<br/>with Emergency Adjustments]
    SKIP --> OPTIMIZE
    
    OPTIMIZE --> STORE[Store Current Prediction<br/>for Next Cycle]
    STORE --> END[End]
    
    style DIVERGENCE fill:#ffebee
    style EMERGENCY fill:#fff3cd
    style ADJUST fill:#e8f5e9
```

