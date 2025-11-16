# Digital Twin Configuration

## Production URLs

The digital twin is deployed to the following production URLs:

- **OPC UA Server**: `opc.tcp://opcua.flowoptimization.app:4840/wastewater/`
- **MCP Server**: `https://mcp.flowoptimization.app/sse`

## Configuration Files Updated

### 1. Backend Configuration

**File**: `backend/app/config.py`
- `digital_twin_opcua_url`: Defaults to production URL
- `digital_twin_mcp_url`: Defaults to production URL

**File**: `backend/app/services/digital_twin.py`
- `DEFAULT_OPCUA_SERVER_URL`: Defaults to production URL
- `DEFAULT_MCP_SERVER_URL`: Defaults to production URL

### 2. Docker Compose

**Files**: `docker-compose.yml`, `docker-compose.full.yml`
- `OPCUA_SERVER_URL`: Defaults to production URL
- `DIGITAL_TWIN_MCP_URL`: Defaults to production URL

## Environment Variables

You can override the production URLs via environment variables:

```bash
# Production (default)
OPCUA_SERVER_URL=opc.tcp://opcua.flowoptimization.app:4840/wastewater/
DIGITAL_TWIN_MCP_URL=https://mcp.flowoptimization.app/sse
MCP_SERVER_URL=https://mcp.flowoptimization.app/sse

# For local development (override)
OPCUA_SERVER_URL=opc.tcp://localhost:4840/wastewater/
DIGITAL_TWIN_MCP_URL=http://localhost:8080
```

## MCP Server Endpoints

The MCP server at `https://mcp.flowoptimization.app/sse` is accessed with these endpoints:

- `POST /tools/get_variable_history` - Get historical data for a variable
- `POST /tools/aggregate_multiple_variables_data` - Get aggregated data for multiple variables

The backend automatically appends `/tools/` to the base MCP URL when making requests.

## Testing

### Verify OPC UA Connection

```python
from app.services.digital_twin import get_digital_twin_current_state

state = await get_digital_twin_current_state()
print(state)  # Should return OPC UA variable values
```

### Verify MCP Connection

```python
from app.services.digital_twin import get_variable_history

history = await get_variable_history("WaterLevelInTunnel.L2.m", hours_back=24)
print(history)  # Should return historical data points
```

### Check Configuration

```bash
# In backend directory
python -c "from app.config import get_settings; s = get_settings(); print(f'OPC UA: {s.digital_twin_opcua_url}'); print(f'MCP: {s.digital_twin_mcp_url}')"
```

## Deployment

When deploying with Docker Compose:

```bash
# Production URLs (default)
docker compose -f docker-compose.full.yml up -d

# Or override for local development
OPCUA_SERVER_URL=opc.tcp://localhost:4840/wastewater/ \
DIGITAL_TWIN_MCP_URL=http://localhost:8080 \
docker compose -f docker-compose.full.yml up -d
```

## Troubleshooting

### Connection Issues

1. **Verify network connectivity**:
   ```bash
   # Test OPC UA endpoint (requires OPC UA client)
   # Or check backend logs for connection errors
   
   # Test MCP endpoint
   curl https://mcp.flowoptimization.app/sse/tools/get_variable_history \
     -X POST \
     -H "Content-Type: application/json" \
     -d '{"variable_name": "WaterLevelInTunnel.L2.m", "hours_back": 24}'
   ```

2. **Check firewall/network rules**:
   - Ensure port 4840 (OPC UA) is accessible
   - Ensure HTTPS (443) is accessible for MCP server

3. **Verify DNS resolution**:
   ```bash
   nslookup opcua.flowoptimization.app
   nslookup mcp.flowoptimization.app
   ```

### SSL/TLS Issues

If the MCP server uses HTTPS, ensure:
- SSL certificate is valid
- Backend has proper CA certificates installed
- No certificate pinning conflicts

## Notes

- OPC UA uses TCP protocol (not HTTP), so URL format is `opc.tcp://`
- MCP server uses HTTPS for secure communication
- Both URLs can be overridden via environment variables for testing/local development
- The MCP server base URL should include the `/sse` path if that's where the SSE endpoint is hosted

