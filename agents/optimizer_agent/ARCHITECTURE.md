# Optimizer Agent Architecture

## System Overview

```mermaid
graph TB
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
        EXPLAINER --> FEATHERLESS
    end

    subgraph "Agent Interface"
        AGENT[OptimizationAgent<br/>main.py]
        MCP[BaseMCPAgent<br/>Common Framework]
        AGENT --> MCP
        AGENT --> OPT
        AGENT --> EXPLAINER
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

    LOADER --> SIM
    FULL --> AGENT
```

## Optimization Flow

```mermaid
sequenceDiagram
    participant User/Test
    participant Agent/Optimizer
    participant MPC Optimizer
    participant OR-Tools Solver
    participant LLM Explainer
    participant Featherless API

    User/Test->>Agent/Optimizer: Request Schedule
    Agent/Optimizer->>Agent/Optimizer: Get Current State
    Agent/Optimizer->>Agent/Optimizer: Get Forecasts
    
    Agent/Optimizer->>MPC Optimizer: solve_optimization()
    
    alt Full Optimization
        MPC Optimizer->>OR-Tools Solver: Solve (24h strategic + 2h tactical)
        OR-Tools Solver-->>MPC Optimizer: Optimization Result
    else Simplified Fallback
        MPC Optimizer->>OR-Tools Solver: Solve (simplified constraints)
        OR-Tools Solver-->>MPC Optimizer: Optimization Result
    else Rule-Based Fallback
        MPC Optimizer->>MPC Optimizer: Generate rule-based schedule
        MPC Optimizer-->>MPC Optimizer: Optimization Result
    end
    
    MPC Optimizer-->>Agent/Optimizer: Result (success/failure)
    
    Agent/Optimizer->>Agent/Optimizer: Compute Metrics
    Agent/Optimizer->>Agent/Optimizer: Derive Strategic Guidance
    
    alt LLM Available
        Agent/Optimizer->>LLM Explainer: generate_explanation()
        LLM Explainer->>Featherless API: API Call
        Featherless API-->>LLM Explainer: Explanation Text
        LLM Explainer-->>Agent/Optimizer: Explanation
    else LLM Unavailable
        Agent/Optimizer->>Agent/Optimizer: Fallback Explanation
    end
    
    Agent/Optimizer-->>User/Test: OptimizationResponse
```

## Rolling MPC Simulation Flow

```mermaid
flowchart TD
    START[Start Simulation] --> INIT[Initialize Simulator<br/>with LLM Explainer]
    INIT --> LOOP{More Time Steps?}
    
    LOOP -->|Yes| GETSTATE[Get Current State<br/>from Historical Data]
    GETSTATE --> GETFORECAST[Get Forecast<br/>Perfect/Persistence]
    GETFORECAST --> OPTIMIZE[Run Optimization<br/>solve_optimization]
    
    OPTIMIZE --> CHECK{Success?}
    CHECK -->|Yes| RESULT1[Store Result]
    CHECK -->|No| FALLBACK[Try Fallback Mode]
    FALLBACK --> RESULT1
    
    RESULT1 --> LLM{LLM Enabled?}
    LLM -->|Yes| GETSTRATEGY[Get Strategic Guidance]
    GETSTRATEGY --> COMPUTE[Compute Step Metrics]
    COMPUTE --> CALLAPI[Call LLM API]
    CALLAPI --> STORE[Store Explanation]
    
    LLM -->|No| SKIP[Skip Explanation]
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
        AGENT --> REQUEST
        AGENT --> RESPONSE
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
    RESULT --> EXPLAINER
    RESULT --> AGENT
    EXPLAINER --> RESPONSE
    
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
        +float price_eur_mwh
    }
    
    class ForecastData {
        +List[datetime] timestamps
        +List[float] inflow_m3_s
        +List[float] price_eur_mwh
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
        +str explanation
        +str strategy
    }
    
    CurrentState --> OptimizationResult
    ForecastData --> OptimizationResult
    PumpSpec --> OptimizationResult
    SystemConstraints --> OptimizationResult
    OptimizationResult --> ScheduleMetrics
    OptimizationResult --> SimulationResult
    ScheduleMetrics --> SimulationResult
```

## File Structure

```
optimizer_agent/
├── main.py                    # OptimizationAgent (MCP Agent Interface)
├── optimizer.py               # MPCOptimizer (Core Optimization Engine)
├── explainability.py          # LLMExplainer (Featherless Integration)
│
├── test_data_loader.py        # HSYDataLoader (Historical Data Loading)
├── test_simulator.py          # RollingMPCSimulator (MPC Simulation)
├── test_metrics.py            # MetricsCalculator (Performance Metrics)
├── test_optimizer_with_data.py # Main Test Script
│
├── .env                       # Agent Configuration (API Keys)
└── PLAN.md                    # Implementation Plan
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

## LLM Explanation Flow

```mermaid
flowchart TD
    START[Optimization Complete] --> CHECK{LLM Configured?}
    
    CHECK -->|No| FALLBACK[Generate Fallback<br/>Rule-Based Explanation]
    
    CHECK -->|Yes| BUILD[Build Prompt<br/>with Metrics & Strategy]
    BUILD --> CALL[Call Featherless API]
    
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

## Constraint Hierarchy

```mermaid
graph TD
    subgraph "Hard Constraints"
        H1[L1 Min/Max Bounds<br/>0.5m - 8.0m]
        H2[Pump Min Frequency<br/>47.8 Hz]
        H3[Min Pumps On<br/>At least 1 pump]
        H4[Min On/Off Duration<br/>120 minutes]
    end
    
    subgraph "Soft Constraints (with Violations)"
        S1[L1 Violation Tolerance<br/>±0.5m with Penalty]
        S2[Outflow Smoothness<br/>Minimize Variance]
        S3[Pump Fairness<br/>Balance Operating Hours]
    end
    
    subgraph "Objectives"
        O1[Minimize Cost<br/>Energy × Price]
        O2[Minimize Energy<br/>Total kWh]
        O3[Minimize Violations<br/>L1 Penalty]
        O4[Maximize Efficiency<br/>Specific Energy]
    end
    
    H1 --> OPT[Optimizer]
    H2 --> OPT
    H3 --> OPT
    H4 --> OPT
    
    S1 --> OPT
    S2 --> OPT
    S3 --> OPT
    
    O1 --> OPT
    O2 --> OPT
    O3 --> OPT
    O4 --> OPT
```

