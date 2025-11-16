# Full Platform Deployment Guide

This guide explains how to deploy the complete HSY Blominmäki AI Agent Pumping Optimization System with all agents and services using Docker Compose.

## Quick Start

```bash
# 1. Create .env file (optional, uses defaults otherwise)
cp .env.example .env  # Edit as needed

# 2. Build all images
docker compose -f docker-compose.full.yml build

# 3. Start all services
docker compose -f docker-compose.full.yml up -d

# 4. Check status
docker compose -f docker-compose.full.yml ps

# 5. View logs
docker compose -f docker-compose.full.yml logs -f
```

## What Gets Deployed

### Services

1. **Backend** (FastAPI) - `http://localhost:8000`
   - Orchestrates all agents
   - Provides REST API
   - Background optimization scheduler

2. **Frontend** (React + Nginx) - `http://localhost:5173`
   - Operator dashboard
   - Real-time monitoring

3. **Agents** (HTTP/REST):
   - **Weather Agent** - `http://localhost:8101`
   - **Price Agent** - `http://localhost:8102`
   - **Optimizer Agent** - `http://localhost:8105`

4. **Digital Twin**:
   - **OPC UA Server** - `opc.tcp://localhost:4840`
   - **MCP Server** - `http://localhost:8080`

5. **Databases** (Optional):
   - **PostgreSQL** - `localhost:5432`
   - **Redis** - `localhost:6379`

## Configuration

### Environment Variables

Key variables in `.env`:

```bash
# Backend
BACKEND_PORT=8000
LOG_LEVEL=INFO
OPTIMIZER_INTERVAL_MINUTES=15

# Agent URLs (internal Docker network)
WEATHER_AGENT_URL=http://weather-agent:8101
PRICE_AGENT_URL=http://price-agent:8102
OPTIMIZER_AGENT_URL=http://optimizer-agent:8105

# Agent Ports (external access)
WEATHER_AGENT_PORT=8101
PRICE_AGENT_PORT=8102
OPTIMIZER_AGENT_PORT=8105

# Digital Twin
OPCUA_PORT=4840
MCP_PORT=8080

# Optional: External APIs
OPENWEATHER_API_KEY=your_key_here
USE_OPENWEATHER=false
USE_NORD_POOL=false

# Optional: LLM for explanations
FEATHERLESS_API_BASE=https://api.featherless.ai
FEATHERLESS_API_KEY=your_key_here
```

## File Structure

```
Junction-2025/
├── docker-compose.full.yml      # Full platform deployment
├── docker-compose.yml           # Original (backend + frontend + digital twin)
├── agents/
│   ├── Dockerfile               # Single Dockerfile for all agents
│   ├── weather_agent/
│   │   ├── server.py            # HTTP server (FastAPI)
│   │   └── weather_data.json
│   ├── price_agent/
│   │   ├── server.py            # HTTP server (FastAPI)
│   │   └── price_data.json
│   └── optimizer_agent/
│       ├── server.py            # HTTP server (FastAPI)
│       └── Hackathon_HSY_data.xlsx
└── deploy/docker/
    └── README.md                # Detailed deployment docs
```

## Service Communication

All services communicate via Docker network `hsy-network`:

- **Backend** → **Agents**: HTTP calls to service names (e.g., `http://weather-agent:8101`)
- **Backend** → **Digital Twin**: OPC UA via `opcua-server:4840`
- **Optimizer Agent** → **Other Agents**: HTTP calls
- **Frontend** → **Backend**: HTTP calls

## Verification

```bash
# Backend health
curl http://localhost:8000/system/state

# Weather Agent
curl http://localhost:8101/health

# Price Agent  
curl http://localhost:8102/health

# Optimizer Agent
curl http://localhost:8105/health

# Frontend
open http://localhost:5173
```

## Development vs Production

### Development (default)
- Volume mounts for live code reload
- Hot reload enabled
- Debug logging

### Production
Remove volume mounts and add:
- Resource limits
- Health checks
- Secrets management
- TLS/HTTPS (reverse proxy)

See `deploy/docker/README.md` for production configuration.

## Troubleshooting

### Agents Not Starting
```bash
# Check logs
docker compose -f docker-compose.full.yml logs weather-agent
docker compose -f docker-compose.full.yml logs price-agent
docker compose -f docker-compose.full.yml logs optimizer-agent
```

### Port Conflicts
Update `.env` to change ports:
```bash
WEATHER_AGENT_PORT=18101
PRICE_AGENT_PORT=18102
```

### Missing Data Files
Ensure data files exist:
```bash
ls agents/weather_agent/weather_data.json
ls agents/price_agent/price_data.json  
ls agents/optimizer_agent/Hackathon_HSY_data.xlsx
```

### Network Issues
```bash
# Test connectivity between containers
docker compose -f docker-compose.full.yml exec backend curl http://weather-agent:8101/health
```

## Scaling

Scale stateless agents:
```bash
docker compose -f docker-compose.full.yml up -d --scale optimizer-agent=3
```

## Cleanup

```bash
# Stop services
docker compose -f docker-compose.full.yml down

# Remove volumes (data loss)
docker compose -f docker-compose.full.yml down -v

# Remove images
docker compose -f docker-compose.full.yml down --rmi all
```

## Additional Resources

- [Detailed Deployment Guide](deploy/docker/README.md)
- [Docker Documentation](docs/DOCKER.md)
- [Backend Documentation](docs/BACKEND.md)
- [Agent Documentation](docs/AGENT.MD)

