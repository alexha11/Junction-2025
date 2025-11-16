# Demo Simulator with WebSocket

Quick guide to use the demo simulator for real-time visualization.

## Quick Start

### 1. Start the Backend Server

```bash
cd backend
uvicorn app.main:app --reload
```

The backend will be available at `http://localhost:8000`

### 2. Test with Python Script

```bash
# Basic usage (10x speed, 1 day)
python agents/optimizer_agent/test_demo_websocket.py

# Custom speed (20x faster)
python agents/optimizer_agent/test_demo_websocket.py --speed 20

# Custom time range
python agents/optimizer_agent/test_demo_websocket.py \
  --start-time "2024-11-15T00:00:00" \
  --end-time "2024-11-16T00:00:00" \
  --speed 10
```

### 3. Use from Frontend (React)

```typescript
import { useDemoSimulator } from './hooks/useDemoSimulator';

function DemoComponent() {
  const { connect, disconnect, isConnected, messages, lastMessage } = useDemoSimulator();

  useEffect(() => {
    connect({ speed_multiplier: 10 });
    return () => disconnect();
  }, []);

  return (
    <div>
      <p>Status: {isConnected ? 'Connected' : 'Disconnected'}</p>
      {lastMessage && (
        <div>
          {lastMessage.type === 'simulation_step' && (
            <div>
              <p>Step: {lastMessage.step + 1}/{lastMessage.total_steps}</p>
              <p>L1: {lastMessage.state.l1_m.toFixed(2)} m</p>
              <p>Price: {lastMessage.state.price_c_per_kwh.toFixed(2)} c/kWh</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### 4. Use from JavaScript/TypeScript (Vanilla)

```javascript
const ws = new WebSocket('ws://localhost:8000/system/demo/simulate?speed_multiplier=10');

ws.onopen = () => {
  console.log('Connected to demo simulator');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'simulation_start') {
    console.log('Simulation started:', data);
  } else if (data.type === 'simulation_step') {
    console.log(`Step ${data.step + 1}/${data.total_steps}`);
    console.log('State:', data.state);
    console.log('Optimization:', data.optimization);
  } else if (data.type === 'simulation_summary') {
    console.log('Simulation completed:', data.comparison);
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Connection closed');
};
```

## WebSocket Endpoint

**URL**: `ws://localhost:8000/system/demo/simulate`

### Query Parameters

- `speed_multiplier` (float, optional): Simulation speed multiplier
  - `1.0` = real-time (15 minutes = 15 minutes wait)
  - `10.0` = 10x faster (15 minutes = 1.5 minutes wait)
  - `100.0` = 100x faster (15 minutes = 9 seconds wait)
  - Default: `1.0`

- `start_time` (ISO datetime, optional): Simulation start time
  - Format: `2024-11-15T00:00:00` or `2024-11-15T00:00:00+00:00`
  - Default: Start of data file

- `end_time` (ISO datetime, optional): Simulation end time
  - Format: `2024-11-16T00:00:00` or `2024-11-16T00:00:00+00:00`
  - Default: `start_time + 1 day`

- `data_file` (string, optional): Excel data file name
  - Default: `Hackathon_HSY_data.xlsx`

### Example URLs

```
ws://localhost:8000/system/demo/simulate?speed_multiplier=10
ws://localhost:8000/system/demo/simulate?speed_multiplier=20&start_time=2024-11-15T00:00:00
ws://localhost:8000/system/demo/simulate?speed_multiplier=50&start_time=2024-11-15T00:00:00&end_time=2024-11-15T12:00:00
```

## Message Types

### 1. `simulation_start`

Sent once at the beginning.

```json
{
  "type": "simulation_start",
  "start_time": "2024-11-15T00:00:00",
  "end_time": "2024-11-16T00:00:00",
  "total_steps": 96,
  "reoptimize_interval_minutes": 15
}
```

### 2. `simulation_step`

Sent for each optimization step.

```json
{
  "type": "simulation_step",
  "step": 0,
  "total_steps": 96,
  "timestamp": "2024-11-15T00:00:00",
  "state": {
    "timestamp": "2024-11-15T00:00:00",
    "l1_m": 3.2,
    "inflow_m3_s": 2.1,
    "outflow_m3_s": 2.0,
    "price_c_per_kwh": 64.5,
    "pumps": [
      {"pump_id": "1.1", "state": "on", "frequency_hz": 48.5}
    ]
  },
  "forecast": {
    "timestamps": ["2024-11-15T00:15:00", ...],
    "inflow_m3_s": [2.1, 2.0, ...],
    "price_c_per_kwh": [64.5, 65.0, ...]
  },
  "optimization": {
    "success": true,
    "mode": "full",
    "total_energy_kwh": 150.5,
    "total_cost_eur": 9.7,
    "l1_trajectory": [3.2, 3.1, ...],
    "schedules": [
      {
        "pump_id": "1.1",
        "is_on": true,
        "frequency_hz": 48.5,
        "flow_m3_s": 0.45,
        "power_kw": 195.0
      }
    ]
  },
  "baseline_schedule": {...}
}
```

### 3. `simulation_summary`

Sent once at the end.

```json
{
  "type": "simulation_summary",
  "start_time": "2024-11-15T00:00:00",
  "end_time": "2024-11-16T00:00:00",
  "total_steps": 96,
  "comparison": {
    "energy_savings_percent": 19.28,
    "cost_savings_percent": 17.37,
    "total_optimized_energy": 21800.5,
    "total_baseline_energy": 27019.2,
    "total_optimized_cost": 1645.8,
    "total_baseline_cost": 1990.1
  }
}
```

### 4. `error`

Sent if an error occurs.

```json
{
  "type": "error",
  "message": "Error description"
}
```

## Troubleshooting

### Connection Refused

Make sure the backend is running:
```bash
cd backend
uvicorn app.main:app --reload
```

### No Messages Received

- Check that the data file exists
- Verify start/end times are within data range
- Check backend logs for errors

### Slow Performance

- Increase `speed_multiplier` for faster simulation
- Reduce simulation duration (fewer days)
- Disable LLM features (already disabled in demo mode)

