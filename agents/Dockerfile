# Multi-stage Dockerfile for MCP Agents
# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH="/opt/venv"

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl --version  # Verify curl installation

RUN python -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

RUN pip install --upgrade pip

# Copy requirements
COPY agents/requirements.txt agents/pyproject.toml ./agents/

# Install dependencies
RUN pip install -r agents/requirements.txt

# Copy agent code and data
COPY agents ./agents
COPY sample ./sample

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /workspace ${VENV_PATH}
USER appuser

WORKDIR /workspace/agents

# Default command (will be overridden by docker-compose)
CMD ["python", "-m", "agents.weather_agent.main"]

