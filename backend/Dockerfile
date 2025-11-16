# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH="/opt/venv"

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

RUN pip install --upgrade pip \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org

COPY backend/requirements.txt backend/pyproject.toml ./backend/
RUN pip install -r backend/requirements.txt \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org

COPY backend ./backend
COPY sample ./sample
COPY spot-price-forecast ./spot-price-forecast

RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /workspace ${VENV_PATH}
USER appuser

WORKDIR /workspace/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
