# WebSocket Integration Guide

This guide explains how to integrate the WebSocket demo simulator with the frontend.

## Architecture

```
Frontend (React) 
    ↓ WebSocket Connection
Backend (FastAPI) - /system/demo/simulate
    ↓ Uses DemoSimulator
Optimizer Agent - Runs simulation
    ↓ Streams updates
Frontend receives real-time updates
```

## Backend Setup

The WebSocket endpoint is automatically registered when the backend starts:

**Endpoint**: `ws://localhost:8000/system/demo/simulate`

### Query Parameters

- `speed_multiplier` (float): Simulation speed (1.0 = real-time, 10.0 = 10x faster)
- `start_time` (ISO string): Simulation start time (optional)
- `end_time` (ISO string): Simulation end time (optional)
- `data_file` (string): Excel data file name (default: `Hackathon_HSY_data.xlsx`)

## Frontend Integration

### 1. Using the React Hook (Recommended)

```typescript
import { useDemoSimulator } from '../hooks/useDemoSimulator';

function DemoDashboard() {
  const { connect, disconnect, isConnected, messages, lastMessage, error } = useDemoSimulator();

  useEffect(() => {
    // Connect with 10x speed
    connect({ speed_multiplier: 10 });
    
    // Cleanup on unmount
    return () => disconnect();
  }, []);

  return (
    <div>
      <p>Status: {isConnected ? '🟢 Connected' : '🔴 Disconnected'}</p>
      
      {error && <p className="error">Error: {error}</p>}
      
      {lastMessage && (
        <div>
          {lastMessage.type === 'simulation_start' && (
            <div>
              <h3>Simulation Started</h3>
              <p>Steps: {lastMessage.total_steps}</p>
            </div>
          )}
          
          {lastMessage.type === 'simulation_step' && (
            <div>
              <h3>Step {lastMessage.step + 1}/{lastMessage.total_steps}</h3>
              
              {/* Current State */}
              <div>
                <h4>Current State</h4>
                <p>L1: {lastMessage.state.l1_m.toFixed(2)} m</p>
                <p>L1 Volume: {lastMessage.state.l1_volume_m3.toFixed(0)} m³</p>
                {lastMessage.state.l2_m && (
                  <p>L2: {lastMessage.state.l2_m.toFixed(2)} m</p>
                )}
                <p>Inflow: {lastMessage.state.inflow_m3_s.toFixed(2)} m³/s</p>
                <p>Outflow: {lastMessage.state.outflow_m3_s.toFixed(2)} m³/s</p>
                <p>Price: {lastMessage.state.price_c_per_kwh.toFixed(2)} c/kWh</p>
              </div>
              
              {/* Optimization Result */}
              {lastMessage.optimization && (
                <div>
                  <h4>Optimization</h4>
                  <p>Mode: {lastMessage.optimization.mode}</p>
                  <p>Success: {lastMessage.optimization.success ? '✓' : '✗'}</p>
                  <p>Energy: {lastMessage.optimization.total_energy_kwh.toFixed(2)} kWh</p>
                  <p>Cost: {lastMessage.optimization.total_cost_eur.toFixed(2)} EUR</p>
                  <p>Solve Time: {lastMessage.optimization.solve_time_seconds.toFixed(2)}s</p>
                  
                  {/* Baseline Comparison */}
                  {lastMessage.optimization.baseline && (
                    <div>
                      <h5>Baseline</h5>
                      <p>Cost: {lastMessage.optimization.baseline.cost_eur.toFixed(2)} EUR</p>
                      <p>Energy: {lastMessage.optimization.baseline.energy_kwh.toFixed(2)} kWh</p>
                    </div>
                  )}
                  
                  {/* Savings */}
                  {lastMessage.optimization.savings && (
                    <div>
                      <h5>Savings</h5>
                      <p>Cost: {lastMessage.optimization.savings.cost_eur.toFixed(2)} EUR ({lastMessage.optimization.savings.cost_percent.toFixed(1)}%)</p>
                      <p>Energy: {lastMessage.optimization.savings.energy_kwh.toFixed(2)} kWh ({lastMessage.optimization.savings.energy_percent.toFixed(1)}%)</p>
                    </div>
                  )}
                  
                  {/* Violations */}
                  {lastMessage.optimization.l1_violations > 0 && (
                    <p className="warning">
                      ⚠ Violations: {lastMessage.optimization.l1_violations}
                    </p>
                  )}
                  
                  {/* Smoothness */}
                  {lastMessage.optimization.smoothness && (
                    <div>
                      <h5>Smoothness</h5>
                      <p>Variance: {lastMessage.optimization.smoothness.optimized_variance.toFixed(4)}</p>
                      <p>Improvement: {lastMessage.optimization.smoothness.improvement_percent.toFixed(1)}%</p>
                    </div>
                  )}
                  
                  {/* Pump Schedules */}
                  {lastMessage.optimization.schedules && (
                    <div>
                      <h5>Pump Schedules</h5>
                      <ul>
                        {lastMessage.optimization.schedules
                          .filter(s => s.time_step === 0)
                          .map(schedule => (
                            <li key={schedule.pump_id}>
                              {schedule.pump_id}: {schedule.is_on ? 'ON' : 'OFF'} 
                              {schedule.is_on && ` @ ${schedule.frequency_hz.toFixed(1)} Hz`}
                            </li>
                          ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              
              {/* Metrics */}
              {lastMessage.metrics && (
                <div>
                  <h4>Metrics</h4>
                  <p>Pumps ON: {lastMessage.metrics.pumps_on}/{lastMessage.metrics.pump_count}</p>
                  <p>Violation Count: {lastMessage.metrics.violation_count}</p>
                  <p>Running Time (cumulative): {lastMessage.metrics.total_running_time_hours?.cumulative.toFixed(2)}h</p>
                  <p>Smoothness: {lastMessage.metrics.smoothness_variance.toFixed(4)}</p>
                </div>
              )}
              
              {/* Forecast */}
              {lastMessage.forecast && (
                <div>
                  <h4>Forecast</h4>
                  <p>Timestamps: {lastMessage.forecast.timestamps.length}</p>
                  <p>Inflow range: {Math.min(...lastMessage.forecast.inflow_m3_s).toFixed(2)} - {Math.max(...lastMessage.forecast.inflow_m3_s).toFixed(2)} m³/s</p>
                  <p>Price range: {Math.min(...lastMessage.forecast.price_c_per_kwh).toFixed(2)} - {Math.max(...lastMessage.forecast.price_c_per_kwh).toFixed(2)} c/kWh</p>
                </div>
              )}
              
              {/* LLM Content */}
              {lastMessage.explanation && (
                <div>
                  <h4>Explanation</h4>
                  <p>{lastMessage.explanation}</p>
                </div>
              )}
              
              {lastMessage.strategic_plan && (
                <div>
                  <h4>Strategic Plan</h4>
                  <p>Type: {lastMessage.strategic_plan.plan_type}</p>
                  <p>Confidence: {lastMessage.strategic_plan.forecast_confidence}</p>
                  <p>{lastMessage.strategic_plan.description}</p>
                </div>
              )}
            </div>
          )}
          
          {lastMessage.type === 'simulation_summary' && (
            <div>
              <h3>Simulation Complete</h3>
              {lastMessage.comparison && (
                <div>
                  <p>Energy Savings: {lastMessage.comparison.energy_savings_percent.toFixed(2)}%</p>
                  <p>Cost Savings: {lastMessage.comparison.cost_savings_percent.toFixed(2)}%</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Message History (optional) */}
      <details>
        <summary>Message History ({messages.length} messages)</summary>
        <pre>{JSON.stringify(messages, null, 2)}</pre>
      </details>
    </div>
  );
}
```

### 2. Using Native WebSocket API

```typescript
const ws = new WebSocket('ws://localhost:8000/system/demo/simulate?speed_multiplier=10');

ws.onopen = () => {
  console.log('Connected to demo simulator');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'simulation_start':
      console.log('Simulation started:', data);
      break;
      
    case 'simulation_step':
      console.log(`Step ${data.step + 1}/${data.total_steps}`);
      console.log('State:', data.state);
      console.log('Optimization:', data.optimization);
      console.log('Metrics:', data.metrics);
      break;
      
    case 'simulation_summary':
      console.log('Simulation completed:', data.comparison);
      break;
      
    case 'error':
      console.error('Error:', data.message);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Connection closed');
};
```

## Environment Variables

Set in `.env` or `.env.local`:

```bash
# Frontend .env
VITE_API_URL=http://localhost:8000

# Or for production
VITE_API_URL=https://api.example.com
```

The hook automatically converts `http://` to `ws://` or `https://` to `wss://`.

## Message Format

### simulation_start

```json
{
  "type": "simulation_start",
  "start_time": "2024-11-15T00:00:00",
  "end_time": "2024-11-16T00:00:00",
  "total_steps": 96,
  "reoptimize_interval_minutes": 15
}
```

### simulation_step

```json
{
  "type": "simulation_step",
  "step": 0,
  "total_steps": 96,
  "timestamp": "2024-11-15T00:00:00",
  "start_time": "2024-11-15T00:00:00",
  "state": {
    "timestamp": "2024-11-15T00:00:00",
    "l1_m": 3.2,
    "l1_volume_m3": 20000.0,
    "l2_m": null,
    "inflow_m3_s": 2.1,
    "outflow_m3_s": 2.0,
    "price_c_per_kwh": 64.5,
    "pumps": [...]
  },
  "forecast": {
    "timestamps": [...],
    "inflow_m3_s": [...],
    "price_c_per_kwh": [...]
  },
  "optimization": {
    "success": true,
    "mode": "full",
    "total_energy_kwh": 150.5,
    "total_cost_eur": 9.7,
    "solve_time_seconds": 2.34,
    "l1_violations": 0,
    "max_violation_m": 0.0,
    "l1_trajectory": [...],
    "baseline": {
      "cost_eur": 12.3,
      "energy_kwh": 185.2,
      "outflow_variance": 0.045
    },
    "savings": {
      "cost_eur": 2.6,
      "cost_percent": 21.1,
      "energy_kwh": 34.7,
      "energy_percent": 18.7
    },
    "smoothness": {
      "optimized_variance": 0.032,
      "baseline_variance": 0.045,
      "improvement_percent": 28.9
    },
    "schedules": [...]
  },
  "metrics": {
    "pump_count": 8,
    "pumps_on": 2,
    "pumps_off": 6,
    "l1_m": 3.2,
    "l1_volume_m3": 20000.0,
    "violation_count": 0,
    "smoothness_variance": 0.032,
    "total_running_time_hours": {
      "cumulative": 45.5,
      "horizon": 0.5,
      "per_pump_cumulative": {...},
      "per_pump_horizon": {...}
    }
  },
  "explanation": "...",
  "strategic_plan": {...}
}
```

### simulation_summary

```json
{
  "type": "simulation_summary",
  "start_time": "2024-11-15T00:00:00",
  "end_time": "2024-11-16T00:00:00",
  "total_steps": 96,
  "comparison": {
    "energy_savings_percent": 19.28,
    "cost_savings_percent": 17.37,
    ...
  }
}
```

## Example Component

See `frontend/src/pages/OperationsPortal.tsx` for an example of integrating WebSocket updates into an existing component.

## Troubleshooting

### Connection Refused

- Ensure backend is running: `cd backend && uvicorn app.main:app --reload`
- Check WebSocket endpoint is registered in backend logs
- Verify `VITE_API_URL` is set correctly

### No Messages Received

- Check data file exists at expected location
- Verify start/end times are within data range
- Check backend logs for errors
- Ensure speed_multiplier is > 0

### Type Errors

- Ensure TypeScript types match message format
- Check `useDemoSimulator.ts` for latest message interfaces

## Next Steps

1. Add visualization components for:
   - L1 trajectory over time
   - Pump schedule timeline
   - Cost/energy savings charts
   - Forecast visualization

2. Add controls for:
   - Start/stop simulation
   - Adjust speed multiplier
   - Change time range
   - Pause/resume

3. Add persistence:
   - Save simulation results
   - Load previous simulations
   - Compare multiple runs

