# Full Platform Deployment Guide

This guide explains how to deploy the complete HSY Blominmäki AI Agent Pumping Optimization System with all agents and services.

## Architecture Overview

The full platform consists of:

1. **Backend** (FastAPI) - Port 8000
2. **Frontend** (React + Nginx) - Port 5173
3. **Agents**:
   - Weather Agent - Port 8101
   - Price Agent - Port 8102
   - Optimizer Agent - Port 8105
4. **Digital Twin**:
   - OPC UA Server - Port 4840
   - MCP Server - Port 8080
5. **Supporting Services** (Optional):
   - PostgreSQL - Port 5432
   - Redis - Port 6379

## Quick Start

### 1. Prerequisites

- Docker Engine 24+ or Docker Desktop with Compose V2
- At least 8 GB RAM (16 GB recommended)
- 4+ CPU cores

### 2. Environment Setup

Create a `.env` file in the repository root:

```bash
# Backend Configuration
LOG_LEVEL=INFO
OPTIMIZER_INTERVAL_MINUTES=15
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Agent URLs (internal - don't change unless needed)
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
OPCUA_SERVER_URL=opc.tcp://opcua-server:4840/wastewater/

# Database (if using)
POSTGRES_PORT=5432
REDIS_PORT=6379
POSTGRES_DB=hsy
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Optional: External APIs
OPENWEATHER_API_KEY=your_key_here
USE_OPENWEATHER=false
USE_NORD_POOL=false

# Optional: LLM/Featherless for explanations
FEATHERLESS_API_BASE=https://api.featherless.ai
FEATHERLESS_API_KEY=your_key_here
LLM_MODEL=llama-3.1-8b-instruct
```

### 3. Deploy

```bash
# Build all images
docker compose -f docker-compose.full.yml build

# Start all services
docker compose -f docker-compose.full.yml up -d

# View logs
docker compose -f docker-compose.full.yml logs -f

# Check service status
docker compose -f docker-compose.full.yml ps
```

### 4. Verify Deployment

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

## Service Details

### Backend Service

- **Image**: `hsy-backend:latest`
- **Port**: 8000
- **Health Check**: `/system/state`
- **Depends On**: All agents, OPC UA server, PostgreSQL

### Weather Agent

- **Image**: `hsy-weather-agent:latest`
- **Port**: 8101
- **Data**: Uses `agents/weather_agent/weather_data.json`
- **Optional**: OpenWeather API (set `USE_OPENWEATHER=true`)

### Price Agent

- **Image**: `hsy-price-agent:latest`
- **Port**: 8102
- **Data**: Uses `agents/price_agent/price_data.json`
- **Optional**: Nord Pool API (set `USE_NORD_POOL=true`)

### Optimizer Agent

- **Image**: `hsy-optimizer-agent:latest`
- **Port**: 8105
- **Dependencies**: OR-Tools, NumPy, Pandas
- **Data**: Uses `agents/optimizer_agent/Hackathon_HSY_data.xlsx`
- **Optional**: LLM for explanations (set Featherless API key)

## Networking

All services communicate via the `hsy-network` Docker network. Agents are accessible:

- **Within Docker**: Use service names (e.g., `http://weather-agent:8101`)
- **From Host**: Use `localhost` with mapped ports (e.g., `http://localhost:8101`)

## Volume Mounts

For development, agent source code is mounted as volumes:

- `./agents/weather_agent` → `/workspace/agents/weather_agent`
- `./agents/price_agent` → `/workspace/agents/price_agent`
- `./agents/optimizer_agent` → `/workspace/agents/optimizer_agent`

Changes to code will be reflected after container restart.

## Troubleshooting

### Agents Not Starting

```bash
# Check agent logs
docker compose -f docker-compose.full.yml logs weather-agent
docker compose -f docker-compose.full.yml logs price-agent
docker compose -f docker-compose.full.yml logs optimizer-agent

# Verify agent health
docker compose -f docker-compose.full.yml ps
```

### Port Conflicts

If ports are already in use, update `.env`:

```bash
WEATHER_AGENT_PORT=18101
PRICE_AGENT_PORT=18102
# etc.
```

### Agent Communication Issues

Verify network connectivity:

```bash
# From backend container
docker compose -f docker-compose.full.yml exec backend curl http://weather-agent:8101/health

# Check DNS resolution
docker compose -f docker-compose.full.yml exec backend ping weather-agent
```

### Missing Data Files

Ensure data files exist:

```bash
ls agents/weather_agent/weather_data.json
ls agents/price_agent/price_data.json
ls agents/optimizer_agent/Hackathon_HSY_data.xlsx
```

## Production Deployment

For production, consider:

1. **Remove volume mounts** - Use baked-in code in images
2. **Add secrets management** - Use Docker secrets or external vault
3. **Enable TLS** - Use reverse proxy (Traefik/Nginx) with Let's Encrypt
4. **Add monitoring** - Prometheus + Grafana
5. **Configure backups** - For PostgreSQL and Redis volumes
6. **Use orchestration** - Kubernetes or Docker Swarm for scaling

### Example Production Overrides

Create `docker-compose.prod.yml`:

```yaml
services:
  backend:
    volumes:
      # Remove development mounts
      - ./backend/app/logging_config.py:/workspace/backend/app/logging_config.py:ro
  
  weather-agent:
    volumes:
      # Remove development mounts
  
  # Add resource limits
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 512M
```

Deploy with:

```bash
docker compose -f docker-compose.full.yml -f docker-compose.prod.yml up -d
```

## Scaling

To scale agents horizontally:

```bash
# Scale optimizer agents (if stateless)
docker compose -f docker-compose.full.yml up -d --scale optimizer-agent=3
```

Note: Ensure agents are stateless or share state via Redis/PostgreSQL.

## Cleanup

```bash
# Stop all services
docker compose -f docker-compose.full.yml down

# Remove volumes (data will be lost)
docker compose -f docker-compose.full.yml down -v

# Remove images
docker compose -f docker-compose.full.yml down --rmi all
```

## Additional Resources

- [Main README](../README.md)
- [Docker Guide](../../docs/DOCKER.md)
- [Backend Documentation](../../docs/BACKEND.md)
- [Agent Documentation](../../docs/AGENT.MD)

