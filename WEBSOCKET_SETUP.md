# WebSocket Integration - Quick Setup Guide

## Overview

The WebSocket integration allows real-time streaming of simulation updates from the backend to the frontend.

## Architecture

```
Frontend (React Hook: useDemoSimulator)
    ↓ WebSocket: ws://localhost:8000/system/demo/simulate
Backend (FastAPI WebSocket Endpoint)
    ↓ Uses DemoSimulator
Optimizer Agent - Runs rolling MPC simulation
    ↓ Streams JSON messages
Frontend receives and displays real-time updates
```

## Backend Setup ✅

**File**: `backend/app/api/routes/demo.py`
- WebSocket endpoint at `/system/demo/simulate`
- Automatically registered in `backend/app/main.py`

**Endpoint**: `ws://localhost:8000/system/demo/simulate`

**Query Parameters**:
- `speed_multiplier` (float): 1.0 = real-time, 10.0 = 10x faster
- `start_time` (ISO string): Optional start time
- `end_time` (ISO string): Optional end time  
- `data_file` (string): Excel file name (default: Hackathon_HSY_data.xlsx)

## Frontend Setup ✅

**File**: `frontend/src/hooks/useDemoSimulator.ts`
- React hook for WebSocket connection
- Handles connection lifecycle
- Parses and stores messages

## Usage Example

```typescript
import { useDemoSimulator } from '../hooks/useDemoSimulator';

function MyComponent() {
  const { connect, disconnect, isConnected, lastMessage, messages, error } = useDemoSimulator();

  useEffect(() => {
    // Connect with 10x speed
    connect({ speed_multiplier: 10 });
    
    return () => disconnect(); // Cleanup
  }, []);

  if (!isConnected) {
    return <div>Connecting...</div>;
  }

  if (error) {
    return <div>Error: {error}</div>;
  }

  if (lastMessage?.type === 'simulation_step') {
    return (
      <div>
        <h3>Step {lastMessage.step + 1}/{lastMessage.total_steps}</h3>
        
        {/* Current State */}
        <div>
          <p>L1: {lastMessage.state.l1_m.toFixed(2)} m</p>
          <p>L1 Volume: {lastMessage.state.l1_volume_m3.toFixed(0)} m³</p>
          <p>Inflow: {lastMessage.state.inflow_m3_s.toFixed(2)} m³/s</p>
          <p>Outflow: {lastMessage.state.outflow_m3_s.toFixed(2)} m³/s</p>
          <p>Price: {lastMessage.state.price_c_per_kwh.toFixed(2)} c/kWh</p>
        </div>
        
        {/* Optimization Results */}
        {lastMessage.optimization && (
          <div>
            <p>Mode: {lastMessage.optimization.mode}</p>
            <p>Success: {lastMessage.optimization.success ? '✓' : '✗'}</p>
            <p>Cost: {lastMessage.optimization.total_cost_eur.toFixed(2)} EUR</p>
            <p>Energy: {lastMessage.optimization.total_energy_kwh.toFixed(2)} kWh</p>
            
            {/* Savings vs Baseline */}
            {lastMessage.optimization.savings && (
              <div>
                <p>Savings: {lastMessage.optimization.savings.cost_eur.toFixed(2)} EUR ({lastMessage.optimization.savings.cost_percent.toFixed(1)}%)</p>
              </div>
            )}
            
            {/* Violations */}
            {lastMessage.optimization.l1_violations > 0 && (
              <p>⚠ Violations: {lastMessage.optimization.l1_violations}</p>
            )}
            
            {/* Running Time */}
            {lastMessage.metrics?.total_running_time_hours && (
              <p>Total Running Time: {lastMessage.metrics.total_running_time_hours.cumulative.toFixed(2)}h</p>
            )}
            
            {/* Smoothness */}
            {lastMessage.optimization.smoothness && (
              <p>Smoothness Variance: {lastMessage.optimization.smoothness.optimized_variance.toFixed(4)}</p>
            )}
          </div>
        )}
      </div>
    );
  }

  return <div>Waiting for simulation...</div>;
}
```

## Message Types

### 1. `simulation_start`
Sent once at the beginning.

### 2. `simulation_step` 
Sent for each optimization step. Contains:
- `state`: Current system state (L1, L2, inflow, outflow, price, pumps)
- `forecast`: Full forecast data
- `optimization`: Optimization result with:
  - Success/failure
  - Cost, energy, solve time
  - Baseline comparison
  - Savings (cost & energy)
  - Smoothness metrics
  - Violations
  - Pump schedules
- `metrics`: Additional metrics (running time, etc.)
- `explanation`: LLM explanation (if enabled)
- `strategic_plan`: 24h strategic plan (if enabled)

### 3. `simulation_summary`
Sent once at the end with comparison metrics.

### 4. `error`
Sent if an error occurs.

## Data Available in Each Step

The `simulation_step` message includes all the information you requested:

1. ✅ **Start time**: `start_time` field
2. ✅ **Baseline**: `optimization.baseline` (cost, energy, variance)
3. ✅ **Savings**: `optimization.savings` (EUR and percentage for cost & energy)
4. ✅ **Violation count**: `optimization.l1_violations` and `metrics.violation_count`
5. ✅ **Smoothness**: `optimization.smoothness` (variance and improvement %)
6. ✅ **L1 & L2**: `state.l1_m`, `state.l1_volume_m3`, `state.l2_m`
7. ✅ **Total running time**: `metrics.total_running_time_hours` (cumulative & per-pump)

## Testing

### 1. Test Backend Endpoint

```bash
# Start backend
cd backend
uvicorn app.main:app --reload

# Test with Python script
python agents/optimizer_agent/test_demo_websocket.py --speed 10
```

### 2. Test Frontend Hook

```typescript
// In your React component
const { connect, isConnected, lastMessage } = useDemoSimulator();

useEffect(() => {
  connect({ speed_multiplier: 10 });
}, []);

console.log('Connected:', isConnected);
console.log('Last message:', lastMessage);
```

### 3. Check Browser Console

Open browser DevTools → Console to see:
- WebSocket connection status
- Incoming messages
- Any errors

## Environment Variables

In `frontend/.env.local`:
```bash
VITE_API_URL=http://localhost:8000
```

The hook automatically converts `http://` → `ws://` and `https://` → `wss://`.

## Next Steps

1. **Create visualization components**:
   - Real-time L1/L2 level charts
   - Pump schedule timeline
   - Cost/energy savings dashboard
   - Forecast visualization

2. **Add controls**:
   - Start/stop simulation button
   - Speed multiplier slider
   - Time range picker

3. **Add to Operations Portal**:
   - Integrate `useDemoSimulator` hook
   - Display real-time updates
   - Show metrics and savings

See `WEBSOCKET_INTEGRATION.md` for detailed documentation.

